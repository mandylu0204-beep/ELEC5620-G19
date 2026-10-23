"""A-owned atomic safety advisory storage. Never performs inference or fallback."""
from typing import Mapping, Protocol
from uuid import uuid4

from pydantic import ValidationError

from ..auth import fail
from ..contracts.dto import ConfirmedContext, SafetyInput, SafetyResult, StoredAssessment, VersionContext
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from ..agents.rules.trip_evidence import TripEvidenceSelection
from ..agents.rules.common import RULES_VERSION, SUPPORTED_RULES_VERSIONS
from .logistics_audit import canonical, decode, digest, LIMIT


def required(scope):
    return scope.dataset_context.selection_config.get('a_safety_audit_required') == '1'


def integrity():
    raise ContractFailure(ContractError(code=ErrorCode.PERSISTENCE_FAILURE,
        message='Saved safety audit is missing, invalid or inconsistent. Contact the operator.',
        recoverable=False, allowed_actions=['CONTACT_OPERATOR']))


class ModelSafetyPersistencePort(Protocol):
    async def save_model_safety_assessment(self, context: VersionContext, result: SafetyResult,
        plan: Mapping[str, object], trace: Mapping[str, object], write_key: str) -> StoredAssessment: ...


def registered_identity(scope, *, new_write=False):
    choices = scope.dataset_context.selection_config
    seed = decode(choices['a_safety_identity_seed'])
    if (not required(scope) or choices.get('a_safety_mode') != 'model'
            or choices.get('a_safety_audit_contract') != '1.0' or scope.demo_context.mode != 'agent'
            or set(seed) != {'agent_version','tool_version','validation_version','kernel_version',
                            'dataset_rules_version','prompt_sha256','model_client'}):
        raise ValueError('Unregistered safety identity')
    versions = {
        'safety-advisory-validation-1': ('campus-safety-advisory-agent-1','safety-read-only-tools-1'),
        'safety-advisory-validation-2': ('campus-safety-advisory-agent-2','safety-read-only-tools-2'),
        'safety-advisory-validation-3': ('campus-safety-advisory-agent-3','safety-read-only-tools-3'),
    }
    from ..llm.safety_support import matches_live_protocol
    expected = versions.get(seed['validation_version'])
    if (expected is None or (seed['agent_version'],seed['tool_version']) != expected
            or seed['kernel_version'] not in SUPPORTED_RULES_VERSIONS
            or scope.dataset_context.dataset_version != ('2.2.0' if seed['validation_version'] == 'safety-advisory-validation-3' else '2.1.0')
            or (new_write and (not matches_live_protocol(scope.dataset_context.dataset_version, seed)
                               or seed['kernel_version'] != RULES_VERSION))):
        raise ValueError('Unsupported or downgraded safety registration')
    context = scope.dataset_context.model_dump(mode='json')
    identity = {**seed, 'workflow_context':context}
    return {**identity, 'configuration_fingerprint':digest(canonical(identity))}


def replay(scope, input, baseline, result, raw_plan, raw_trace, selection, *, new_write=False):
    # Lazy import: the current rules application does not require B's component.
    # R-S01 and factory registration must be completed before model enablement.
    from ..llm.safety_validation import safety_validator_for
    identity = registered_identity(scope, new_write=new_write)
    validator = safety_validator_for(identity['validation_version'])
    return validator(input, baseline, result, raw_plan, raw_trace,
        identity=identity, selection=selection)


def payload(context, result, plan, trace):
    body = {'context':context.model_dump(mode='json'), 'kind':'SAFETY',
            'result':result.model_dump(mode='json'), 'plan':plan, 'trace':trace}
    encoded = canonical(body)
    if len(encoded.encode('utf-8')) > LIMIT:
        raise ValueError('Safety audit payload exceeds limit')
    return digest(encoded)


def check_facts(scope, confirmed, version, logistics, input, baseline, selection):
    from ..storage.repository import Repository
    if (confirmed.request_id != scope.request_id or confirmed.demo_context != scope.demo_context
            or confirmed.dataset_context != scope.dataset_context
            or input.version_context != version.version_context or input.saved_itinerary != version.content
            or input.confirmed_requirements != confirmed.requirements or input.demo_context != scope.demo_context
            or input.saved_logistics_assessment != logistics or logistics.kind != 'LOGISTICS'
            or input.scenario_context != selection.scenario_context
            or baseline.version_context != version.version_context or baseline.execution_mode != 'agent'
            or baseline.depends_on_assessment_id != logistics.assessment_id
            or Repository.input_fingerprint(scope, confirmed, version.content.model_dump(mode='json'))
                != version.version_context.input_fingerprint):
        raise ValueError('Safety facts differ from authoritative saved context')


def load_audits(connection, scope, version, *, must_exist=False):
    rows = connection.execute('SELECT * FROM model_safety_audits WHERE run_id=?', (scope.run_id,)).fetchall()
    assessment = connection.execute("SELECT * FROM assessments WHERE run_id=? AND kind='SAFETY'", (scope.run_id,)).fetchone()
    if not rows:
        if required(scope) and (assessment or must_exist):
            integrity()
        return {}
    try:
        if not required(scope) or len(rows) != 1 or assessment is None:
            raise ValueError('Unexpected safety audit')
        row = rows[0]
        run = connection.execute('SELECT * FROM runs WHERE id=?', (scope.run_id,)).fetchone()
        owner = connection.execute('SELECT owner_id FROM plans WHERE id=?', (scope.plan_id,)).fetchone()
        log_row = connection.execute("SELECT * FROM assessments WHERE run_id=? AND kind='LOGISTICS'", (scope.run_id,)).fetchone()
        logistics = StoredAssessment.model_validate(decode(log_row['payload']))
        stored = StoredAssessment.model_validate(decode(assessment['payload']))
        confirmed = ConfirmedContext.model_validate(decode(run['confirmed_context']))
        body = decode(row['payload'])
        if set(body) != {'audit_contract_version','plan','trace','input_json','rule_facts_json','selection_json','save_attempt_id'} or body['audit_contract_version'] != '1.0':
            raise ValueError('Invalid audit envelope')
        input = SafetyInput.model_validate(decode(body['input_json']))
        baseline = SafetyResult.model_validate(decode(body['rule_facts_json']))
        selection = TripEvidenceSelection.model_validate(decode(body['selection_json']))
        check_facts(scope, confirmed, version, logistics, input, baseline, selection)
        if (row['owner_id'] != owner['owner_id'] or row['plan_id'] != scope.plan_id
                or row['run_id'] != scope.run_id or row['version_id'] != version.version_context.plan_version_id
                or row['assessment_id'] != assessment['id'] or assessment['id'] != stored.assessment_id
                or assessment['version_id'] != row['version_id'] or stored.version_context != version.version_context
                or stored.kind != 'SAFETY' or stored.gear_checklist_id is not None
                or assessment['depends_on_id'] != logistics.assessment_id
                or stored.depends_on_assessment_id != logistics.assessment_id
                or row['depends_on_assessment_id'] != logistics.assessment_id
                or log_row['id'] != logistics.assessment_id or log_row['version_id'] != row['version_id']
                or not row['attempt_id'] or row['attempt_id'] != body['save_attempt_id']
                or row['input_fingerprint'] != version.version_context.input_fingerprint
                or input.model_dump_json() != body['input_json'] or baseline.model_dump_json() != body['rule_facts_json']):
            raise ValueError('Safety audit association differs')
        plan, trace = replay(scope, input, baseline, stored.result, body['plan'], body['trace'], selection)
        hashed = payload(version.version_context, stored.result, body['plan'], body['trace'])
        receipt = connection.execute('SELECT * FROM write_receipts WHERE run_id=? AND write_key=?', (scope.run_id,scope.write_keys['safety'])).fetchone()
        if (row['configuration_fingerprint'] != trace.configuration_fingerprint or row['payload_sha256'] != hashed
                or trace.input_sha256 != digest(body['input_json']) or trace.rule_facts_sha256 != digest(body['rule_facts_json'])
                or not receipt or receipt['operation'] != 'safety' or receipt['input_hash'] != hashed
                or StoredAssessment.model_validate(decode(receipt['result'])) != stored):
            raise ValueError('Safety receipt or trace differs')
        return {'SAFETY':{'audit_contract_version':'1.0','audit_id':row['id'],'kind':'SAFETY',
            'plan_id':row['plan_id'],'run_id':row['run_id'],'plan_version_id':row['version_id'],
            'assessment_id':row['assessment_id'],'depends_on_assessment_id':row['depends_on_assessment_id'],
            'attempt_id':row['attempt_id'],'input_fingerprint':row['input_fingerprint'],
            'configuration_fingerprint':row['configuration_fingerprint'],'payload_sha256':row['payload_sha256'],
            'created_at':row['created_at'],'plan':plan.model_dump(mode='json'),'trace':trace.model_dump(mode='json')}}
    except (ContractFailure, ValidationError, ValueError, TypeError, KeyError, AttributeError, ImportError, UnicodeError, RecursionError):
        integrity()


async def save(port, context, result, raw_plan, raw_trace, write_key):
    from ..storage.repository import Repository, encode, now
    from .logistics_audit import load_audits as load_logistics
    if not port.attempt_id or not required(port.scope):
        fail(ErrorCode.CONTRACT_INVALID, 'Model safety requires a registered claimed persistence port.')
    if write_key != port.scope.write_keys['safety']:
        fail(ErrorCode.IDEMPOTENCY_CONFLICT, 'Write key does not belong to safety.')
    try:
        context = VersionContext.model_validate(context)
        result = SafetyResult.model_validate(result)
        hashed = payload(context, result, raw_plan, raw_trace)
    except (ValidationError, ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        fail(ErrorCode.CONTRACT_INVALID, 'Invalid safety payload type, encoding or size.')
    with port.db.transaction() as connection:
        _, run = port.active(connection, writing=True)
        _, _, version = port.context(connection, context)
        load_logistics(connection, port.scope, version)
        previous = connection.execute('SELECT * FROM write_receipts WHERE run_id=? AND write_key=?', (context.run_id,write_key)).fetchone()
        if previous:
            load_audits(connection, port.scope, version, must_exist=True)
            if previous['operation'] != 'safety' or previous['input_hash'] != hashed:
                fail(ErrorCode.IDEMPOTENCY_CONFLICT, 'Safety key cannot save changed model artifacts.')
            return StoredAssessment.model_validate(decode(previous['result']))
        if (connection.execute('SELECT 1 FROM model_safety_audits WHERE run_id=?', (context.run_id,)).fetchone()
                or connection.execute("SELECT 1 FROM assessments WHERE run_id=? AND kind='SAFETY'", (context.run_id,)).fetchone()):
            integrity()
        if run['status'] != 'RUNNING':
            fail(ErrorCode.INVALID_STATE, 'Safety must be saved during the current running attempt.')
        provider = port.workflow.safety_facts_provider
        if provider is None:
            fail(ErrorCode.CONTRACT_INVALID, 'Authoritative safety facts provider is not registered.')
        confirmed = ConfirmedContext.model_validate_json(run['confirmed_context'])
        log_row = connection.execute("SELECT payload FROM assessments WHERE run_id=? AND kind='LOGISTICS'", (context.run_id,)).fetchone()
        if not log_row:
            fail(ErrorCode.STALE_CONTEXT, 'Save the current logistics assessment before safety.')
        logistics = StoredAssessment.model_validate_json(log_row['payload'])
        try:
            input, baseline, selection = provider(port.scope, confirmed, version, logistics)
            input, baseline = SafetyInput.model_validate(input), SafetyResult.model_validate(baseline)
            selection = TripEvidenceSelection.model_validate(selection)
            check_facts(port.scope, confirmed, version, logistics, input, baseline, selection)
            if result != baseline:
                raise ValueError('Formal safety result differs from complete rules baseline')
            plan, trace = replay(port.scope,input,baseline,result,raw_plan,raw_trace,selection,new_write=True)
        except (ContractFailure, ValidationError, ValueError, TypeError, KeyError, AttributeError, ImportError, UnicodeError, RecursionError):
            fail(ErrorCode.CONTRACT_INVALID, 'Safety artifacts differ from registered facts, identity or replay protocol.')
        port.active(connection, writing=True)
        assessment_id, audit_id, timestamp = uuid4().hex, uuid4().hex, now()
        stored = StoredAssessment(assessment_id=assessment_id,version_context=context,kind='SAFETY',result=result,
            gear_checklist_id=None,depends_on_assessment_id=logistics.assessment_id)
        connection.execute('INSERT INTO assessments VALUES(?,?,?,?,?,?,?)',
            (assessment_id,context.run_id,context.plan_version_id,'SAFETY',encode(stored),logistics.assessment_id,timestamp))
        body = {'audit_contract_version':'1.0','plan':plan.model_dump(mode='json'),'trace':trace.model_dump(mode='json'),
                'input_json':input.model_dump_json(),'rule_facts_json':baseline.model_dump_json(),
                'selection_json':selection.model_dump_json(),'save_attempt_id':port.attempt_id}
        connection.execute('INSERT INTO model_safety_audits VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (audit_id,port.owner_id,context.plan_id,context.run_id,context.plan_version_id,assessment_id,logistics.assessment_id,
             port.attempt_id,context.input_fingerprint,trace.configuration_fingerprint,hashed,timestamp,canonical(body)))
        connection.execute('INSERT INTO write_receipts VALUES(?,?,?,?,?)', (context.run_id,write_key,'safety',hashed,encode(stored)))
        load_audits(connection,port.scope,version,must_exist=True)
        return stored
