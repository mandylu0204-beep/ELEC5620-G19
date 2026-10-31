"""A-owned model logistics boundary. No model/network calls in persistence."""
import hashlib
import json
from typing import Annotated, Literal, Mapping, Protocol
from uuid import uuid4

from pydantic import Field, StrictBool, StrictInt, StrictStr, ValidationError, field_validator

from ..auth import fail
from ..contracts.base import ContractModel, MoneyCents, Quantity
from ..contracts.dto import ConfirmedContext, LogisticsInput, LogisticsResult, StoredAssessment, VersionContext
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from ..llm.logistics_agent import LOGISTICS_AGENT_VERSION
from ..llm.logistics_schema import LOGISTICS_VALIDATION_VERSION, LogisticsProposal
from ..llm.logistics_tools import LOGISTICS_TOOL_VERSION, BudgetAllocation, LogisticsToolset, SupplyPlan, ValidatedLogisticsPlan
from ..agents.rules.common import SUPPORTED_RULES_VERSIONS
from .model_audit import Hash, Name, Count

LIMIT = 512 * 1024


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def decode(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    def nonfinite(_):
        raise ValueError('Nonfinite JSON number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)


def required(scope):
    return scope.dataset_context.selection_config.get('a_logistics_audit_required') == '1'


def integrity():
    raise ContractFailure(ContractError(code=ErrorCode.PERSISTENCE_FAILURE,
        message='Logistics model audit is missing, damaged or inconsistently linked. Contact the developer.',
        recoverable=False, allowed_actions=['CONTACT_OPERATOR']))


class StrictSupply(SupplyPlan):
    procurement_quantity: Quantity | None
    procurement_unit: Name
    estimated_cost_cents: MoneyCents | None
    cost_line_id: Name | None
    confirmation_required: StrictBool
    reason_unverified: Annotated[StrictStr, Field(min_length=1, max_length=240)]

    @field_validator('procurement_quantity', mode='before')
    @classmethod
    def json_decimal(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError('Use decimal JSON text')
        return value


class StrictAllocation(BudgetAllocation):
    line_id: Name
    required_cents: MoneyCents | None
    allocated_cents: MoneyCents | None
    unfunded_cents: MoneyCents | None


class AuditPlan(ValidatedLogisticsPlan):
    gear_actions: list[StrictSupply] = Field(min_length=1, max_length=64)
    budget_allocations: list[StrictAllocation] = Field(min_length=1, max_length=128)
    projected_total_cents: MoneyCents | None
    budget_difference_cents: StrictInt | None
    budget_feasible: StrictBool | None
    requires_user_confirmation: StrictBool
    decision_summary_unverified: Annotated[StrictStr, Field(min_length=1, max_length=1200)]


class AuditTrace(ContractModel):
    role: Literal['LOGISTICS']
    requested_model: Name
    served_models: list[Name] = Field(max_length=6)
    configuration_fingerprint: Hash
    input_sha256: Hash
    rule_facts_sha256: Hash
    proposal_sha256: Hash
    prompt_sha256: Hash
    tool_version: Name
    turns: StrictInt = Field(ge=3, le=6)
    http_attempts: StrictInt = Field(ge=3, le=18)
    elapsed_ms: Count
    tool_calls: list[Literal['read_logistics_facts', 'evaluate_logistics_plan']] = Field(min_length=2, max_length=5)
    response_sha256: list[Hash] = Field(min_length=3, max_length=6)
    usage: dict[Literal['prompt_tokens', 'completion_tokens', 'total_tokens'], Count]
    validation_passed: Literal[True]

    @field_validator('validation_passed', mode='before')
    @classmethod
    def true_only(cls, value):
        if value is not True:
            raise ValueError('Explicit true required')
        return value


class ModelLogisticsPersistencePort(Protocol):
    async def save_model_logistics_assessment(self, context: VersionContext, result: LogisticsResult,
        plan: Mapping[str, object], trace: Mapping[str, object], write_key: str) -> StoredAssessment: ...


def server_input(scope, confirmed, version):
    return LogisticsInput(version_context=version.version_context, saved_itinerary=version.content,
        confirmed_requirements=confirmed.requirements, profile_snapshot=confirmed.profile_snapshot,
        demo_context=scope.demo_context)


def identity_seed(agent):
    return {key: value for key, value in agent.identity.items()
        if key not in {'workflow_context', 'configuration_fingerprint'}}


def registered_seed(scope):
    choices = scope.dataset_context.selection_config
    seed = decode(choices['a_logistics_identity_seed'])
    if (not required(scope) or choices.get('a_logistics_mode') != 'model'
            or choices.get('a_logistics_audit_contract') != '1.0'
            or scope.demo_context.mode != 'agent'
            or set(seed) != {'agent_version','tool_version','validation_version','kernel_version',
                            'dataset_rules_version','prompt_sha256','model_client'}):
        raise ValueError('Unregistered logistics identity')
    # Versioned verifier: v1 remains available when future roles are introduced.
    if (seed['agent_version'] != LOGISTICS_AGENT_VERSION or seed['tool_version'] != LOGISTICS_TOOL_VERSION
            or seed['validation_version'] != LOGISTICS_VALIDATION_VERSION
            or seed['kernel_version'] not in SUPPORTED_RULES_VERSIONS):
        raise ValueError('Unsupported historical logistics verifier')
    return seed


def validate(scope, input, baseline, result, raw_plan, raw_trace):
    plan = AuditPlan.model_validate(raw_plan)
    trace = AuditTrace.model_validate(raw_trace)
    seed = registered_seed(scope)
    public = seed['model_client']
    expected = digest(canonical({**seed, 'workflow_context':scope.dataset_context.model_dump(mode='json')}))
    if (trace.requested_model != public['model'] or trace.configuration_fingerprint != expected
            or trace.prompt_sha256 != seed['prompt_sha256'] or trace.tool_version != seed['tool_version']
            or trace.input_sha256 != digest(input.model_dump_json())
            or trace.rule_facts_sha256 != digest(baseline.model_dump_json())
            or trace.turns > public['max_turns'] or not trace.turns <= trace.http_attempts <= trace.turns * public['max_attempts']
            or len(trace.response_sha256) != trace.turns or len(trace.tool_calls) != trace.turns - 1
            or trace.tool_calls[0] != 'read_logistics_facts' or 'evaluate_logistics_plan' not in trace.tool_calls
            or len(trace.served_models) > trace.turns or len(trace.served_models) != len(set(trace.served_models))):
        raise ValueError('Trace differs from registered facts or identity')
    proposal = LogisticsProposal(gear_choices=[{'item_key':item.fact.item_key, 'method':item.method,
        'reason':item.reason_unverified} for item in plan.gear_actions],
        cost_priority=[item.line_id for item in plan.budget_allocations],
        decision_summary=plan.decision_summary_unverified)
    tools = LogisticsToolset(input, baseline)
    recomputed = tools.evaluate_logistics_plan(proposal)
    if (trace.proposal_sha256 != tools.proposal_hash(proposal)
            or canonical(recomputed.model_dump(mode='json')) != canonical(plan.model_dump(mode='json'))
            or canonical(tools.result(recomputed).model_dump(mode='json')) != canonical(result.model_dump(mode='json'))):
        raise ValueError('Model payload differs from host calculation')
    return plan, trace


def payload(context, result, plan, trace):
    value = {'context':context.model_dump(mode='json'), 'kind':'LOGISTICS',
             'result':result.model_dump(mode='json'), 'plan':plan, 'trace':trace}
    encoded = canonical(value)
    if len(encoded.encode('utf-8')) > LIMIT:
        raise ValueError('Logistics payload exceeds limit')
    return value, digest(encoded)


def load_audits(connection, scope, version, *, must_exist=False):
    """Historical validation uses saved facts, not current API/data/configuration."""
    rows = connection.execute('SELECT * FROM model_logistics_audits WHERE run_id=?', (scope.run_id,)).fetchall()
    logistics = connection.execute("SELECT * FROM assessments WHERE run_id=? AND kind='LOGISTICS'", (scope.run_id,)).fetchone()
    if not rows:
        if required(scope) and (logistics or must_exist):
            integrity()
        return {}
    try:
        from ..storage.repository import Repository
        if not required(scope) or len(rows) != 1 or not logistics:
            raise ValueError('Unexpected audit')
        row = rows[0]
        run = connection.execute('SELECT * FROM runs WHERE id=?', (scope.run_id,)).fetchone()
        owner = connection.execute('SELECT owner_id FROM plans WHERE id=?', (scope.plan_id,)).fetchone()
        stored = StoredAssessment.model_validate(decode(logistics['payload']))
        confirmed = ConfirmedContext.model_validate(decode(run['confirmed_context']))
        input = server_input(scope, confirmed, version)
        body = decode(row['payload'])
        baseline = LogisticsResult.model_validate(decode(body['rule_facts_json']))
        if (set(body) != {'audit_contract_version','plan','trace','input_json','rule_facts_json'}
                or body['audit_contract_version'] != '1.0' or row['owner_id'] != owner['owner_id']
                or logistics['id'] != stored.assessment_id or logistics['version_id'] != version.version_context.plan_version_id
                or stored.kind != 'LOGISTICS' or stored.depends_on_assessment_id is not None
                or confirmed.request_id != scope.request_id or confirmed.demo_context != scope.demo_context
                or confirmed.dataset_context != scope.dataset_context
                or row['plan_id'] != scope.plan_id or row['version_id'] != version.version_context.plan_version_id
                or row['assessment_id'] != stored.assessment_id or stored.version_context != version.version_context
                or row['gear_checklist_id'] != stored.gear_checklist_id or not row['attempt_id']
                or row['input_fingerprint'] != version.version_context.input_fingerprint
                or body['input_json'] != input.model_dump_json()
                or baseline.version_context != version.version_context or baseline.execution_mode != 'agent'
                or Repository.input_fingerprint(scope, confirmed, version.content.model_dump(mode='json')) != row['input_fingerprint']):
            raise ValueError('Audit association differs')
        plan, trace = validate(scope, input, baseline, stored.result, body['plan'], body['trace'])
        _, hashed = payload(version.version_context, stored.result, body['plan'], body['trace'])
        receipt = connection.execute('SELECT * FROM write_receipts WHERE run_id=? AND write_key=?',
            (scope.run_id, scope.write_keys['logistics'])).fetchone()
        gear = connection.execute('SELECT * FROM gear_checklists WHERE id=?', (stored.gear_checklist_id,)).fetchone()
        if (trace.input_sha256 != digest(body['input_json']) or trace.rule_facts_sha256 != digest(body['rule_facts_json'])
                or row['configuration_fingerprint'] != trace.configuration_fingerprint or row['payload_sha256'] != hashed
                or not receipt or receipt['operation'] != 'logistics' or receipt['input_hash'] != hashed
                or StoredAssessment.model_validate(decode(receipt['result'])) != stored
                or not gear or gear['assessment_id'] != stored.assessment_id
                or decode(gear['payload']) != [item.model_dump(mode='json') for item in stored.result.gear_checklist]):
            raise ValueError('Audit receipt or checklist differs')
        return {'LOGISTICS':{'audit_contract_version':'1.0','audit_id':row['id'],'kind':'LOGISTICS',
            'plan_id':row['plan_id'],'run_id':row['run_id'],'plan_version_id':row['version_id'],
            'assessment_id':row['assessment_id'],'gear_checklist_id':row['gear_checklist_id'],
            'attempt_id':row['attempt_id'],'input_fingerprint':row['input_fingerprint'],
            'configuration_fingerprint':row['configuration_fingerprint'],'payload_sha256':row['payload_sha256'],
            'created_at':row['created_at'],'plan':plan.model_dump(mode='json'),'trace':trace.model_dump(mode='json')}}
    except (ContractFailure, ValidationError, ValueError, TypeError, KeyError, AttributeError):
        integrity()


async def save(port, context, result, raw_plan, raw_trace, write_key):
    from ..storage.repository import Repository, encode, now
    if not port.attempt_id or not required(port.scope):
        fail(ErrorCode.CONTRACT_INVALID, 'Model logistics must use the registered and claimed execution port.')
    if write_key != port.scope.write_keys['logistics']:
        fail(ErrorCode.IDEMPOTENCY_CONFLICT, 'Write key  does not belong to the logistics step.')
    try:
        result = LogisticsResult.model_validate(result)
        context = VersionContext.model_validate(context)
        _, hashed = payload(context, result, raw_plan, raw_trace)
    except (ValidationError, ValueError, TypeError, OverflowError):
        fail(ErrorCode.CONTRACT_INVALID, 'Invalid logistics model payload type, encoding or size.')
    # All work here is local, with one DB snapshot/transaction and no network.
    with port.db.transaction() as connection:
        _, run = port.active(connection, writing=True)
        _, _, version = port.context(connection, context)
        previous = connection.execute('SELECT * FROM write_receipts WHERE run_id=? AND write_key=?',
            (context.run_id, write_key)).fetchone()
        if previous:
            load_audits(connection, port.scope, version, must_exist=True)
            if previous['operation'] != 'logistics' or previous['input_hash'] != hashed:
                fail(ErrorCode.IDEMPOTENCY_CONFLICT, 'The same logistics  key  cannot save different model outputs.')
            return StoredAssessment.model_validate(decode(previous['result']))
        if connection.execute('SELECT 1 FROM model_logistics_audits WHERE run_id=?', (context.run_id,)).fetchone():
            integrity()
        if connection.execute("SELECT 1 FROM assessments WHERE run_id=? AND kind='LOGISTICS'", (context.run_id,)).fetchone():
            integrity()
        if run['status'] != 'RUNNING':
            fail(ErrorCode.INVALID_STATE, 'Model logistics must be saved in the current run.')
        confirmed = ConfirmedContext.model_validate_json(run['confirmed_context'])
        input = server_input(port.scope, confirmed, version)
        if port.workflow.logistics_facts_provider is None:
            fail(ErrorCode.CONTRACT_INVALID, 'Authoritative model logistics fact validator is not connected.')
        baseline = port.workflow.logistics_facts_provider(port.scope, input)
        try:
            if result.version_context != context or result.execution_mode != 'agent':
                raise ValueError('Wrong execution context')
            plan, trace = validate(port.scope, input, baseline, result, raw_plan, raw_trace)
        except (ContractFailure, ValidationError, ValueError, TypeError, KeyError):
            fail(ErrorCode.CONTRACT_INVALID, 'Model logistics differs from saved facts, registered identity or deterministic calculations.')
        port.active(connection, writing=True)
        assessment_id, gear_id, audit_id, timestamp = uuid4().hex, uuid4().hex, uuid4().hex, now()
        stored = StoredAssessment(assessment_id=assessment_id, version_context=context,
            kind='LOGISTICS',result=result,gear_checklist_id=gear_id,depends_on_assessment_id=None)
        connection.execute('INSERT INTO assessments VALUES(?,?,?,?,?,?,?)',
            (assessment_id,context.run_id,context.plan_version_id,'LOGISTICS',encode(stored),None,timestamp))
        connection.execute('INSERT INTO gear_checklists VALUES(?,?,?)',
            (gear_id,assessment_id,encode([item.model_dump(mode='json') for item in result.gear_checklist])))
        body = {'audit_contract_version':'1.0','plan':plan.model_dump(mode='json'),'trace':trace.model_dump(mode='json'),
                'input_json':input.model_dump_json(),'rule_facts_json':baseline.model_dump_json()}
        connection.execute('INSERT INTO model_logistics_audits VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (audit_id,port.owner_id,context.plan_id,context.run_id,context.plan_version_id,assessment_id,gear_id,
             port.attempt_id,context.input_fingerprint,trace.configuration_fingerprint,hashed,timestamp,canonical(body)))
        connection.execute('INSERT INTO write_receipts VALUES(?,?,?,?,?)',
            (context.run_id,write_key,'logistics',hashed,encode(stored)))
        load_audits(connection,port.scope,version,must_exist=True)
        return stored
