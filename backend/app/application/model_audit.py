"""A-owned audit extension; shared AgentPort/DTO schema 1.0 is unchanged."""
import hashlib
import json
from typing import Annotated, Literal, Mapping, Protocol

from pydantic import Field, StrictInt, StrictStr, ValidationError, field_validator

from ..auth import fail
from ..contracts.base import ContractModel
from ..contracts.dto import ItineraryResult, StoredVersion
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
        fail(ErrorCode.CONTRACT_INVALID, '模型审计内容不符合受控接口，未保存方案。')


def validate_trace(scope, content, trace, recommendation):
    values = scope.dataset_context.selection_config
    if scope.demo_context.mode != 'agent' or scope.operation != 'PLAN' or not required(scope):
        fail(ErrorCode.CONTRACT_INVALID, '当前运行未登记模型规划审计。')
    expected = {'configuration_fingerprint': 'hybrid_planning_fingerprint',
        'prompt_sha256': 'a_model_prompt_sha256', 'tool_version': 'a_model_tool_version',
        'requested_model': 'a_model_requested_model'}
    if any(getattr(trace, field) != values.get(key) for field, key in expected.items()):
        fail(ErrorCode.STALE_CONTEXT, '模型审计身份与已登记的配置不同。')
    if (content.selected_campsite_ids != [trace.selected_campsite_id]
            or len(trace.candidate_ids) != len(set(trace.candidate_ids))
            or trace.selected_campsite_id not in trace.candidate_ids
            or not set(trace.candidate_ids).issubset({item.campsite_id for item in recommendation.result.candidates})
            or len(trace.response_sha256) != trace.turns or len(trace.tool_calls) != trace.turns-1
            or trace.http_attempts < trace.turns):
        fail(ErrorCode.CONTRACT_INVALID, '模型审计与保存的营地、推荐或调用记录不一致。')


def trace_hash(trace):
    value = trace.model_dump(mode='json') if isinstance(trace, ModelPlanningTrace) else trace
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def load_model_trace(connection, scope, version):
    row = connection.execute('SELECT * FROM model_planning_traces WHERE run_id=?', (scope.run_id,)).fetchone()
    if not row:
        if required(scope):
            fail(ErrorCode.PERSISTENCE_FAILURE, '模型版本缺少必要审计记录，不能继续放行。')
        return None
    owner = connection.execute('SELECT owner_id FROM plans WHERE id=?', (scope.plan_id,)).fetchone()
    if (not owner or row['owner_id'] != owner['owner_id'] or not row['attempt_id']
            or row['plan_id'] != scope.plan_id or row['version_id'] != version.version_context.plan_version_id
            or row['input_fingerprint'] != version.version_context.input_fingerprint):
        fail(ErrorCode.STALE_CONTEXT, '保存的模型审计不属于当前版本。')
    try:
        trace = trace_payload(json.loads(row['payload']))
    except (ValueError, TypeError):
        fail(ErrorCode.PERSISTENCE_FAILURE, '保存的模型审计无法解码。')
    if trace_hash(trace) != row['payload_sha256']:
        fail(ErrorCode.PERSISTENCE_FAILURE, '保存的模型审计摘要不一致。')
    recommendation = connection.execute('SELECT payload FROM recommendations WHERE run_id=?', (scope.run_id,)).fetchone()
    from ..contracts.dto import StoredRecommendations
    if not recommendation:
        fail(ErrorCode.PERSISTENCE_FAILURE, '模型审计缺少对应推荐。')
    validate_trace(scope, version.content, trace, StoredRecommendations.model_validate_json(recommendation['payload']))
    return {**{key: row[key] for key in ('id','plan_id','run_id','version_id','input_fingerprint','attempt_id','created_at')},
        'trace': trace.model_dump(mode='json')}
