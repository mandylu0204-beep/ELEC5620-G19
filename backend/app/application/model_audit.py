"""A-owned audit extension; shared AgentPort/DTO schema 1.0 is unchanged."""
import hashlib
import json
from typing import Annotated, Literal, Mapping, Protocol

from pydantic import Field, StrictInt, StrictStr, ValidationError, field_validator

from ..auth import fail
from ..contracts.base import ContractModel
from ..contracts.dto import ConfirmedContext, ItineraryResult, RunScope, StoredVersion
from ..contracts.enums import ErrorCode

Hash = Annotated[StrictStr, Field(pattern=r'^[0-9a-f]{64}$')]
Name = Annotated[StrictStr, Field(min_length=1, max_length=200)]
Count = Annotated[StrictInt, Field(ge=0, le=2**63-1)]


class ModelPlanningTrace(ContractModel):
    requested_model: Name
    served_models: list[Name] = Field(max_length=6)
    configuration_fingerprint: Hash
    prompt_sha256: Hash
    tool_version: Name
    turns: StrictInt = Field(ge=2, le=6)
    http_attempts: StrictInt = Field(ge=2, le=18)
    elapsed_ms: Count
    tool_calls: list[Literal['search_campsites']] = Field(min_length=1, max_length=5)
    candidate_ids: list[Name] = Field(min_length=1, max_length=1000)
    selected_campsite_id: Name
    decision_summary: Annotated[StrictStr, Field(min_length=1, max_length=1200)]
    response_sha256: list[Hash] = Field(min_length=2, max_length=6)
    usage: dict[Literal['prompt_tokens','completion_tokens','total_tokens'], Count]
    validation_passed: Literal[True]

    @field_validator('validation_passed', mode='before')
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError('Validation must be explicitly true')
        return value


class ModelPlanningPersistencePort(Protocol):
    async def append_model_plan(self, expected_current_version_id: str | None,
        content: ItineraryResult, request_id: str, reason: str,
        trace: Mapping[str, object], write_key: str) -> StoredVersion: ...


def required(scope):
    return scope.dataset_context.selection_config.get('a_model_trace_required') == '1'


def trace_payload(raw):
    try:
        return ModelPlanningTrace.model_validate(raw)
    except (ValidationError, ValueError, TypeError):
        fail(ErrorCode.CONTRACT_INVALID, 'Model audit does not match the controlled interface. Plan not saved.')


def validate_trace(scope, content, trace, recommendation):
    values = scope.dataset_context.selection_config
    if scope.demo_context.mode != 'agent' or scope.operation not in {'PLAN', 'REVISE'} or not required(scope):
        fail(ErrorCode.CONTRACT_INVALID, 'No model planning audit is registered for this run.')
    expected = {'configuration_fingerprint': 'hybrid_planning_fingerprint',
        'prompt_sha256': 'a_model_prompt_sha256', 'tool_version': 'a_model_tool_version',
        'requested_model': 'a_model_requested_model'}
    if any(getattr(trace, field) != values.get(key) for field, key in expected.items()):
        fail(ErrorCode.STALE_CONTEXT, 'Model audit identity differs from registered settings.')
    if (content.selected_campsite_ids != [trace.selected_campsite_id]
            or len(trace.candidate_ids) != len(set(trace.candidate_ids))
            or trace.selected_campsite_id not in trace.candidate_ids
            or not set(trace.candidate_ids).issubset({item.campsite_id for item in recommendation.result.candidates})
            or len(trace.response_sha256) != trace.turns or len(trace.tool_calls) != trace.turns-1
            or trace.http_attempts < trace.turns):
        fail(ErrorCode.CONTRACT_INVALID, 'Model audit does not match the saved campsite, recommendations or call records.')


def trace_hash(trace):
    value = trace.model_dump(mode='json') if isinstance(trace, ModelPlanningTrace) else trace
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def load_model_trace(connection, scope, version):
    if scope.operation == 'REASSESS' and required(scope):
        return load_origin_trace(connection, scope, version)
    row = connection.execute('SELECT * FROM model_planning_traces WHERE run_id=?', (scope.run_id,)).fetchone()
    if not row:
        if required(scope):
            fail(ErrorCode.PERSISTENCE_FAILURE, 'Model version lacks required audit records and cannot proceed.')
        return None
    owner = connection.execute('SELECT owner_id FROM plans WHERE id=?', (scope.plan_id,)).fetchone()
    if (not owner or row['owner_id'] != owner['owner_id'] or not row['attempt_id']
            or row['plan_id'] != scope.plan_id or row['version_id'] != version.version_context.plan_version_id
            or row['input_fingerprint'] != version.version_context.input_fingerprint):
        fail(ErrorCode.STALE_CONTEXT, 'Saved model audit does not belong to the current version.')
    try:
        trace = trace_payload(json.loads(row['payload']))
    except (ValueError, TypeError):
        fail(ErrorCode.PERSISTENCE_FAILURE, 'Saved model audit cannot be decoded.')
    if trace_hash(trace) != row['payload_sha256']:
        fail(ErrorCode.PERSISTENCE_FAILURE, 'Saved model audit digest differs.')
    recommendation = connection.execute('SELECT payload FROM recommendations WHERE run_id=?', (scope.run_id,)).fetchone()
    from ..contracts.dto import StoredRecommendations
    if not recommendation:
        fail(ErrorCode.PERSISTENCE_FAILURE, 'Model audit has no corresponding recommendation.')
    validate_trace(scope, version.content, trace, StoredRecommendations.model_validate_json(recommendation['payload']))
    return {**{key: row[key] for key in ('id','plan_id','run_id','version_id','input_fingerprint','attempt_id','created_at')},
        'trace': trace.model_dump(mode='json')}


def load_origin_trace(connection, scope, version):
    """Reassessment references immutable generation audit; never clones a call.

    The current run's fingerprint belongs to new assessments. Validate the
    generating run's trace against ITS original confirmation and binding, not
    against the current model/evidence configuration. No new audit row is made.
    """
    if (scope.demo_context.mode != 'agent'
            or scope.dataset_context.selection_config.get('a_model_trace_binding') != 'origin-version-v1'
            or version.version_context.run_id != scope.run_id
            or version.version_context.plan_id != scope.plan_id
            or version.version_context.plan_version_id != scope.expected_current_version_id):
        fail(ErrorCode.STALE_CONTEXT, 'Reassessment has no valid original-version audit link.')
    binding = connection.execute('SELECT * FROM run_versions WHERE run_id=?', (scope.run_id,)).fetchone()
    rows = connection.execute('SELECT * FROM model_planning_traces WHERE plan_id=? AND version_id=?',
        (scope.plan_id, version.version_context.plan_version_id)).fetchall()
    if len(rows) != 1 or not binding or binding['version_id'] != scope.expected_current_version_id or binding['fingerprint'] != version.version_context.input_fingerprint:
        fail(ErrorCode.PERSISTENCE_FAILURE, 'Reassessment version lacks a unique valid original-generation audit.')
    origin = rows[0]
    run = connection.execute('SELECT * FROM runs WHERE id=?', (origin['run_id'],)).fetchone()
    if not run:
        fail(ErrorCode.PERSISTENCE_FAILURE, 'Original model-generation run not found.')
    try:
        original_scope = RunScope.model_validate_json(run['scope'])
        confirmed = ConfirmedContext.model_validate_json(run['confirmed_context'])
    except (ValueError, TypeError):
        fail(ErrorCode.PERSISTENCE_FAILURE, 'Original model-generation context cannot be decoded.')
    if (original_scope.operation not in {'PLAN', 'REVISE'} or not required(original_scope)
            or original_scope.run_id != origin['run_id'] or original_scope.plan_id != scope.plan_id
            or original_scope.request_id != scope.request_id or original_scope.demo_context.mode != 'agent'
            or confirmed.request_id != original_scope.request_id
            or confirmed.demo_context != original_scope.demo_context
            or confirmed.dataset_context != original_scope.dataset_context):
        fail(ErrorCode.STALE_CONTEXT, 'Generation run linked by the original audit does not match.')
    from ..storage.repository import Repository
    original_version = Repository.stored_version(connection, original_scope)
    current_run = connection.execute('SELECT confirmed_context FROM runs WHERE id=?', (scope.run_id,)).fetchone()
    current_confirmed = ConfirmedContext.model_validate_json(current_run['confirmed_context']) if current_run else None
    if (original_version.content != version.content or original_version.content.execution_mode != 'agent'
            or original_version.version_context.plan_version_id != scope.expected_current_version_id
            or original_version.version_context.input_fingerprint != Repository.input_fingerprint(original_scope, confirmed, original_version.content.model_dump(mode='json'))
            or current_confirmed is None or current_confirmed.request_id != scope.request_id
            or current_confirmed.requirements != confirmed.requirements or current_confirmed.profile_snapshot != confirmed.profile_snapshot
            or current_confirmed.demo_context != scope.demo_context or current_confirmed.dataset_context != scope.dataset_context
            or version.version_context.input_fingerprint != Repository.input_fingerprint(scope, current_confirmed, version.content.model_dump(mode='json'))):
        fail(ErrorCode.STALE_CONTEXT, 'Original generation content or reassessment input identity differs.')
    # Recurses only to a PLAN/REVISE scope. Original IDs/attempt/time stay intact.
    return load_model_trace(connection, original_scope, original_version)
