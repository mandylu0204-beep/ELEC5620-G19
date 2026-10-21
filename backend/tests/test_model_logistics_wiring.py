"""Two real role components + HTTP/SQLite; all campus responses are offline."""
import asyncio
from dataclasses import replace
from datetime import date, timedelta
from copy import deepcopy
import json
from threading import Event

from fastapi.testclient import TestClient
import httpx
from pydantic import ValidationError
import pytest

from app.agents.hybrid_planning_agent import HybridPlanningAgent
from app.application.agent_runtime import DATASET_AGENT_FACTORIES
from app.config import Settings
from app.contracts.errors import ContractFailure
from app.contracts.enums import ErrorCode
from app.llm.client import CampusModelClient
from app.llm.logistics_agent import LogisticsTrace
from app.llm.logistics_tools import ValidatedLogisticsPlan
from app.llm.logistics_validation import validate_logistics_payload
from app.main import create_app
from app.workflow.configuration import failure
from llm_fixtures import completion, final_action, model_settings, tool_action
from test_campus_http import KEY, confirmed_request
from test_llm_logistics_agent import agent_fixture, baseline, input_fixture, proposal_from_facts
from test_plan_changes import change
from test_planning_entry import retry, start, wait_run
from test_requests import sign_in
from test_rule_orchestration import FailOnce, Proxy
from test_v2_http_demo import CASES, ROOT, assessment, finalise, launch


from audit_test_reads import internal_audit_reads, json_with_internal_audits

# These tests verify private persistence; public role-scoped reads are tested separately.
wait_run = internal_audit_reads(wait_run)
launch = internal_audit_reads(launch)
finalise = internal_audit_reads(finalise)


def mock_roles(monkeypatch, *, settings=None):
    from app.llm import client, config
    requests, control = [], {}
    async def respond(request):
        payload = json.loads(request.content)
        messages = payload['messages']
        role = 'LOGISTICS' if 'LogisticsAgent' in messages[0]['content'] else 'PLANNING'
        requests.append({'role': role, 'body': payload})
        if control.get('on_request'):
            await control['on_request'](role)
        if role == 'LOGISTICS':
            if control.get('unavailable'):
                return httpx.Response(503, json={'error': 'offline unavailable'})
            tools = [json.loads(item['content'][12:]) for item in messages if item['content'].startswith('TOOL_RESULT=')]
            if not tools:
                action = {'action': 'tool', 'name': 'read_logistics_facts', 'arguments': {}}
            else:
                proposal = proposal_from_facts(tools[0], methods=control.get('methods'))
                action = {'action': 'tool', 'name': 'evaluate_logistics_plan', 'arguments': proposal} if len(tools) == 1 else {
                    'action': 'final', 'proposal': proposal}
            if control.get('invalid'):
                action = {'action': 'final', 'proposal': {}}
        else:
            input = json.loads(messages[1]['content'])
            if not messages[-1]['content'].startswith('TOOL_RESULT='):
                action = tool_action()
            else:
                site = control.get('site') or ('demo-moonlit-field' if input.get('revision_feedback') == 'cheaper campsite' else 'demo-wattle-rest')
                req = input['confirmed_requirements']
                first = date.fromisoformat(req['start_date'])
                action = final_action(campsite_id=site, nights=[(first + timedelta(days=i)).isoformat()
                    for i in range(req['duration_nights'])])
        return httpx.Response(200, json=completion(action, model='offline-two-role-test'))
    settings = settings or model_settings()
    class ActiveClient(CampusModelClient):
        async def complete(self, messages):
            control['active_client'] = self
            return await super().complete(messages)
    monkeypatch.setattr(config, 'CampusModelSettings', lambda: settings)
    monkeypatch.setattr(client, 'CampusModelClient', lambda values: ActiveClient(values, transport=httpx.MockTransport(respond)))
    return requests, control


def application(tmp_path, case='normal'):
    values = CASES[case]['settings'] | {'execution_mode': 'agent', 'logistics_execution': 'model'}
    values['dataset_path'] = ROOT / values['dataset_path']
    return create_app(Settings(_env_file=None, database_path=tmp_path/'two-role.sqlite3', **values))


def role_counts(requests):
    return {role: sum(item['role'] == role for item in requests) for role in ('PLANNING', 'LOGISTICS')}


def db_counts(app):
    with app.state.database.transaction(write=False) as db:
        return {name: db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
            ('versions', 'assessments', 'gear_checklists', 'model_planning_traces', 'model_logistics_audits')}


def assert_audit(detail):
    audit = detail['model_assessment_audits']['LOGISTICS']
    logistics = assessment(detail, 'LOGISTICS')
    context = detail['version']['version_context']
    assert audit['run_id'] == detail['run']['run_id'] == context['run_id']
    assert audit['assessment_id'] == logistics['assessment_id']
    assert audit['plan_version_id'] == context['plan_version_id']
    assert audit['gear_checklist_id'] == logistics['gear_checklist_id']
    assert audit['input_fingerprint'] == context['input_fingerprint']
    assert audit['trace']['role'] == 'LOGISTICS' and audit['trace']['turns'] == 3
    assert audit['trace']['usage']['total_tokens'] == 480
    assert not {'owner_id', 'input_json', 'rule_facts_json'} & audit.keys()
    assert assessment(detail, 'SAFETY')['depends_on_assessment_id'] == logistics['assessment_id']
    return audit


@pytest.mark.parametrize('case,safety_outcome,eligible', [
    ('normal', 'PASSED', True), ('budget_revision', 'PASSED', False),
    ('missing_evidence', 'REVIEW', False), ('road_closure', 'BLOCKED', False),
])
def test_four_http_scenarios_use_both_registered_roles(tmp_path, monkeypatch, case, safety_outcome, eligible):
    requests, control = mock_roles(monkeypatch)
    control['site'] = {'normal': 'demo-wattle-rest', 'budget_revision': 'demo-wattle-rest',
        'missing_evidence': 'demo-river-flat', 'road_closure': 'demo-moonlit-field'}[case]
    with TestClient(application(tmp_path, case)) as client:
        assert client.get('/api/v1/health/ready').status_code == 200
        meta = json_with_internal_audits(client, client.get('/api/v1/meta'))
        assert meta['planning_stages']['logistics'] == meta['planning_stages']['itinerary'] == 'model'
        assert meta['planning_stages']['safety'] == 'rules' and requests == []
        headers = sign_in(client)
        detail = launch(client, headers, case)
        audit = assert_audit(detail)
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3}
        assert assessment(detail, 'SAFETY')['result']['outcome'] == safety_outcome
        assert detail['finalisation_available'] is eligible
        assert audit['trace']['served_models'] == ['offline-two-role-test']
        assert db_counts(client.app) == dict(versions=1, assessments=2, gear_checklists=1,
            model_planning_traces=1, model_logistics_audits=1)
        if eligible:
            _, record = finalise(client, headers, detail)
            assert record['model_assessment_audits']['LOGISTICS'] == audit


def test_revision_and_reassessment_have_new_logistics_not_new_origin_trace(tmp_path, monkeypatch):
    requests, _ = mock_roles(monkeypatch)
    with TestClient(application(tmp_path, 'budget_revision')) as client:
        headers = sign_in(client)
        old = launch(client, headers, 'budget_revision')
        response = change(client, headers, old, 'revise', feedback='cheaper campsite')
        assert response.status_code == 202, response.text
        revised = wait_run(client, json_with_internal_audits(client, response)['run_id'], 'SUCCEEDED')
        assert revised['finalisation_available'] and revised['version']['version_number'] == 2
        original_audit, revised_audit = assert_audit(old), assert_audit(revised)
        assert original_audit['audit_id'] != revised_audit['audit_id']
        assert role_counts(requests) == {'PLANNING': 4, 'LOGISTICS': 6}
        path, snapshot = finalise(client, headers, revised)
        current = json_with_internal_audits(client, client.get('/api/v1/plans/'+revised['plan']['plan_id']))
        response = change(client, headers, current, key='two-role-reassess-123456')
        assert response.status_code == 202, response.text
        reassessed = wait_run(client, json_with_internal_audits(client, response)['run_id'], 'SUCCEEDED')
        audit = assert_audit(reassessed)
        assert role_counts(requests) == {'PLANNING': 4, 'LOGISTICS': 9}
        assert reassessed['version']['content'] == revised['version']['content']
        assert audit['plan_version_id'] == revised_audit['plan_version_id']
        assert audit['run_id'] != revised_audit['run_id'] and audit['assessment_id'] != revised_audit['assessment_id']
        assert audit['trace']['input_sha256'] != revised_audit['trace']['input_sha256']
        assert reassessed['model_planning_trace'] == revised['model_planning_trace']
        assert json_with_internal_audits(client, client.get(path))['final_record'] == snapshot
        assert db_counts(client.app)['model_logistics_audits'] == 3


def test_saved_audit_and_final_readback_survive_new_logistics_prompt(tmp_path, monkeypatch):
    from app.llm import logistics_agent
    requests, _ = mock_roles(monkeypatch)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        detail = launch(client, headers, 'normal')
        path, snapshot = finalise(client, headers, detail)
        old_audit = assert_audit(detail)
    monkeypatch.setattr(logistics_agent, 'LOGISTICS_SYSTEM_PROMPT', logistics_agent.LOGISTICS_SYSTEM_PROMPT + '\nNew prompt identity.')
    with TestClient(application(tmp_path)) as client:
        sign_in(client)
        saved = client.get('/api/v1/runs/'+detail['run']['run_id'])
        assert saved.status_code == 200
        assert json_with_internal_audits(client, saved)['model_assessment_audits']['LOGISTICS'] == old_audit
        assert json_with_internal_audits(client, client.get(path))['final_record'] == snapshot
    assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3}


def wrap_port(monkeypatch, transform):
    original = DATASET_AGENT_FACTORIES[KEY]
    class Wrapped:
        def __init__(self, agent): self.agent = agent
        def __getattr__(self, name): return getattr(self.agent, name)
        async def orchestrate(self, input, port):
            return await self.agent.orchestrate(input, transform(port))
    def factory(settings, descriptor):
        binding = original(settings, descriptor)
        return replace(binding, agent=Wrapped(binding.agent))
    monkeypatch.setitem(DATASET_AGENT_FACTORIES, KEY, factory)


@pytest.mark.parametrize('method,after,expected_logistics', [
    ('save_model_logistics_assessment', True, 3), ('save_model_logistics_assessment', False, 6),
    ('save_assessment', True, 3), ('route_assessed_version', True, 3),
])
def test_restart_after_failed_save_resumes_only_missing_steps(tmp_path, monkeypatch, method, after, expected_logistics):
    requests, _ = mock_roles(monkeypatch)
    used = []
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port, method, after=after)
        return port
    wrap_port(monkeypatch, once)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        failed = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'FAILED')
        assert failed['retry_available']
        old_audit = failed['model_assessment_audits'].get('LOGISTICS')
        content, origin = failed['version']['content'], failed['model_planning_trace']
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        failed = json_with_internal_audits(client, client.get('/api/v1/runs/'+failed['run']['run_id']))
        assert retry(client, headers, failed).status_code == 202
        result = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        audit = assert_audit(result)
        if old_audit:
            assert audit == old_audit
        assert result['version']['content'] == content and result['model_planning_trace'] == origin
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': expected_logistics}
        assert db_counts(client.app)['model_logistics_audits'] == 1


@pytest.mark.parametrize('table', ['assessments', 'gear_checklists', 'model_logistics_audits', 'write_receipts'])
def test_atomic_logistics_failure_keeps_saved_planning_and_retries_only_logistics(tmp_path, monkeypatch, table):
    requests, _ = mock_roles(monkeypatch)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        with client.app.state.database.transaction() as db:
            condition = " WHEN NEW.operation='logistics'" if table == 'write_receipts' else ''
            db.execute(f"CREATE TRIGGER offline_logistics_failure BEFORE INSERT ON {table}{condition} BEGIN SELECT RAISE(ABORT,'injected temporary failure'); END")
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        failed = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'FAILED')
        assert failed['retry_available'] and failed['model_assessment_audits'] == {}
        assert db_counts(client.app) == dict(versions=1, assessments=0, gear_checklists=0,
            model_planning_traces=1, model_logistics_audits=0)
        with client.app.state.database.transaction() as db:
            assert db.execute("SELECT COUNT(*) FROM write_receipts WHERE operation='logistics'").fetchone()[0] == 0
            db.execute('DROP TRIGGER offline_logistics_failure')
        assert retry(client, headers, failed).status_code == 202
        result = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        assert_audit(result)
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 6}


def test_no_match_skips_both_models_and_audits(tmp_path, monkeypatch):
    requests, _ = mock_roles(monkeypatch)
    with TestClient(application(tmp_path, 'no_match')) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers, 'no_match')
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        result = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'SUCCEEDED')
        assert result['recommendations']['result']['search_outcome'] == 'NO_MATCH'
        assert result.get('model_assessment_audits', {}) == {} and result['version'] is None and requests == []
        assert db_counts(client.app)['model_logistics_audits'] == 0


@pytest.mark.parametrize('error_mode,recoverable', [('invalid', False), ('unavailable', True)])
def test_logistics_failure_keeps_real_plan_without_rules_fallback(tmp_path, monkeypatch, error_mode, recoverable):
    requests, control = mock_roles(monkeypatch)
    control[error_mode] = True
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        failed = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'FAILED')
        assert failed['run']['stage'] == 'ASSESSING_LOGISTICS'
        assert failed['run']['error']['recoverable'] is recoverable
        assert failed['assessments'] == [] and failed['model_assessment_audits'] == {}
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 1}
        assert db_counts(client.app)['model_planning_traces'] == 1


@pytest.mark.parametrize('checkpoint_error', ['missing', 'hash', 'association', 'plan'])
def test_corrupt_checkpoint_never_regenerates_or_becomes_retryable(tmp_path, monkeypatch, checkpoint_error):
    requests, _ = mock_roles(monkeypatch)
    used = []
    class BrokenCheckpoint(Proxy):
        async def load_checkpoint(self):
            value = await self.port.load_checkpoint()
            audit = value['model_assessment_audits']['LOGISTICS']
            if checkpoint_error == 'missing': value['model_assessment_audits'] = {}
            elif checkpoint_error == 'hash': audit['payload_sha256'] = '0'*64
            elif checkpoint_error == 'association': audit['assessment_id'] = 'another-assessment'
            else: audit['plan']['gear_actions'][0]['fact']['available_quantity'] = '999'
            return value
    def transform(port):
        if not used:
            used.append(True)
            return FailOnce(port, 'save_model_logistics_assessment', after=True)
        return BrokenCheckpoint(port)
    wrap_port(monkeypatch, transform)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        failed = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'FAILED')
        assert retry(client, headers, failed).status_code == 202
        broken = wait_run(client, failed['run']['run_id'], 'FAILED')
        error = broken['run']['error']
        assert error['code'] == 'PERSISTENCE_FAILURE' and error['recoverable'] is False
        assert error['allowed_actions'] == ['CONTACT_OPERATOR'] and not broken['retry_available']
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3}


@pytest.mark.parametrize('step', ['append_model_plan', 'save_model_logistics_assessment'])
def test_port_integrity_failure_is_not_promoted_to_retry(tmp_path, monkeypatch, step):
    requests, _ = mock_roles(monkeypatch)
    class PermanentFailure(Proxy):
        def __getattr__(self, name):
            if name != step: return getattr(self.port, name)
            async def fail(*args, **kwargs):
                raise failure(ErrorCode.PERSISTENCE_FAILURE, 'Offline permanent audit integrity failure.')
            return fail
    wrap_port(monkeypatch, PermanentFailure)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        failed = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'FAILED')
        assert failed['run']['error']['recoverable'] is False and not failed['retry_available']
        assert failed['run']['error']['allowed_actions'] == ['CONTACT_OPERATOR']


def test_missing_model_save_capability_fails_before_model_or_business_writes(tmp_path, monkeypatch):
    requests, _ = mock_roles(monkeypatch)
    class MissingSave(Proxy):
        save_model_logistics_assessment = None
    wrap_port(monkeypatch, MissingSave)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        failed = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'FAILED')
        assert failed['run']['error']['code'] == 'CONTRACT_INVALID' and requests == []
        assert db_counts(client.app)['versions'] == db_counts(client.app)['assessments'] == 0


@pytest.mark.parametrize('settings', [model_settings(api_key=''), model_settings(max_turns=2)])
def test_unready_model_mode_never_probes_or_falls_back(tmp_path, monkeypatch, settings):
    requests, _ = mock_roles(monkeypatch, settings=settings)
    with TestClient(application(tmp_path)) as client:
        assert client.get('/api/v1/health/ready').status_code == 503
        assert json_with_internal_audits(client, client.get('/api/v1/meta'))['planning_stages']['logistics'] != 'model'
        assert requests == []


@pytest.mark.parametrize('field,value', [('turns', '3'), ('turns', True), ('validation_passed', 'true'),
    ('http_attempts', 3.0), ('usage', {'total_tokens': True})])
def test_b_trace_schema_rejects_coercion(field, value):
    dataset, input, config = input_fixture()
    agent, _ = agent_fixture(dataset, config)
    outcome = asyncio.run(agent.assess_with_trace(input))
    with pytest.raises(ValidationError):
        LogisticsTrace.model_validate(outcome.trace.model_dump(mode='json') | {field: value})


@pytest.mark.parametrize('field,value', [('procurement_quantity', 0.5), ('confirmation_required', 'false'),
    ('estimated_cost_cents', True), ('reason_unverified', ' ')])
def test_b_pure_validator_rejects_bad_nested_types(field, value):
    dataset, input, config = input_fixture()
    agent, _ = agent_fixture(dataset, config)
    outcome = asyncio.run(agent.assess_with_trace(input))
    plan = outcome.plan.model_dump(mode='json')
    plan['gear_actions'][0][field] = value
    with pytest.raises(ContractFailure):
        validate_logistics_payload(input, baseline(dataset, input, config), outcome.assessment,
            plan, outcome.trace.model_dump(mode='json'), identity=agent.identity)


def test_default_hybrid_rejects_unregistered_logistics_instead_of_enabling_it():
    from app.llm.coordinator import PlanningCoordinator
    from app.agents.hybrid_planning_agent import build_hybrid_configuration
    dataset, _, config = input_fixture()
    role, requests = agent_fixture(dataset, config)
    coordinator = PlanningCoordinator(dataset, role.client)
    configuration = build_hybrid_configuration(dataset, coordinator)
    with pytest.raises(ContractFailure):
        HybridPlanningAgent(dataset, coordinator, workflow_configuration=configuration, logistics_agent=role)
    assert requests == []


def test_logistics_wait_renews_lease_with_event_not_timing_count(tmp_path, monkeypatch):
    requests, control = mock_roles(monkeypatch)
    released, observed = Event(), Event()
    async def block(role):
        if role == 'LOGISTICS' and not released.is_set():
            while not released.is_set():
                await asyncio.sleep(.001)
    control['on_request'] = block
    class RenewDuringModel(Proxy):
        async def heartbeat(self):
            await self.port.heartbeat()
            if any(item['role'] == 'LOGISTICS' for item in requests) and not released.is_set():
                with self.port.db.transaction(write=False) as db:
                    row = db.execute('SELECT * FROM run_leases WHERE run_id=?', (self.port.scope.run_id,)).fetchone()
                    assert row['attempt_id'] == self.port.attempt_id and row['expires_at'] > self.port.clock()
                observed.set()
                released.set()
    factory = DATASET_AGENT_FACTORIES[KEY]
    def fast_factory(settings, descriptor):
        binding = factory(settings, descriptor)
        binding.agent.heartbeat_interval = .005
        return binding
    monkeypatch.setitem(DATASET_AGENT_FACTORIES, KEY, fast_factory)
    wrap_port(monkeypatch, RenewDuringModel)
    try:
        with TestClient(application(tmp_path)) as client:
            detail = launch(client, sign_in(client), 'normal')
            assert_audit(detail)
            assert observed.is_set() and role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3}
    finally:
        released.set()


def test_lost_lease_cancels_logistics_and_rejects_late_artifacts(tmp_path, monkeypatch):
    requests, control = mock_roles(monkeypatch)
    entered, cancelled = Event(), Event()
    async def block(role):
        if role == 'LOGISTICS':
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
    control['on_request'] = block
    class LoseLease(Proxy):
        async def heartbeat(self):
            if entered.is_set():
                raise failure(ErrorCode.STALE_CONTEXT, 'Offline model worker lost its lease.')
            await self.port.heartbeat()
    factory = DATASET_AGENT_FACTORIES[KEY]
    def fast_factory(settings, descriptor):
        binding = factory(settings, descriptor)
        binding.agent.heartbeat_interval = .005
        return binding
    monkeypatch.setitem(DATASET_AGENT_FACTORIES, KEY, fast_factory)
    wrap_port(monkeypatch, LoseLease)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        failed = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'FAILED')
        assert cancelled.is_set() and failed['run']['error']['code'] == 'STALE_CONTEXT'
        assert db_counts(client.app)['assessments'] == db_counts(client.app)['model_logistics_audits'] == 0
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 1}


def test_foreign_owner_and_restarted_history_use_saved_two_role_audits(tmp_path, monkeypatch):
    requests, _ = mock_roles(monkeypatch)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        detail = launch(client, headers, 'normal')
        path, snapshot = finalise(client, headers, detail)
        audit = assert_audit(detail)
        sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get('/api/v1/plans/'+detail['plan']['plan_id']).status_code == 404
        assert client.get(path).status_code == 404
    with TestClient(application(tmp_path)) as client:
        sign_in(client)
        assert json_with_internal_audits(client, client.get(path))['final_record'] == snapshot
        restored = json_with_internal_audits(client, client.get('/api/v1/plans/'+detail['plan']['plan_id']))
        assert restored['model_assessment_audits']['LOGISTICS'] == audit
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3}


def test_hybrid_rejects_logistics_identity_drift_during_model_wait(tmp_path, monkeypatch):
    requests, control = mock_roles(monkeypatch)
    async def drift(name):
        if name == 'LOGISTICS':
            client = control['active_client']
            client.settings = client.settings.model_copy(
                update={'max_completion_tokens': 4096})
    control['on_request'] = drift
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        begun = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        failed = wait_run(client, json_with_internal_audits(client, begun)['run_id'], 'FAILED')
        assert failed['run']['error']['code'] == 'STALE_CONTEXT'
        assert db_counts(client.app)['model_logistics_audits'] == 0


@pytest.mark.parametrize('tamper', ['fact', 'summary', 'duplicate', 'trace_identity'])
def test_pure_validator_rejects_semantic_tampering(tamper):
    dataset, input, config = input_fixture()
    agent, _ = agent_fixture(dataset, config)
    outcome = asyncio.run(agent.assess_with_trace(input))
    plan, trace = outcome.plan.model_dump(mode='json'), outcome.trace.model_dump(mode='json')
    if tamper == 'fact': plan['gear_actions'][0]['fact']['available_quantity'] = '999'
    elif tamper == 'summary': plan['decision_summary_unverified'] = 'A different final decision'
    elif tamper == 'duplicate': plan['gear_actions'].append(plan['gear_actions'][0])
    else: trace['configuration_fingerprint'] = '0'*64
    with pytest.raises(ContractFailure):
        validate_logistics_payload(input, baseline(dataset, input, config), outcome.assessment,
            plan, trace, identity=agent.identity)


@pytest.mark.parametrize('collection,maximum', [('gear_actions', 64), ('budget_allocations', 128),
    ('projected_cost_breakdown', 128)])
def test_schema_list_boundaries_do_not_claim_fabricated_facts_are_valid(collection, maximum):
    dataset, input, config = input_fixture()
    agent, _ = agent_fixture(dataset, config)
    outcome = asyncio.run(agent.assess_with_trace(input))
    plan = outcome.plan.model_dump(mode='json')
    items = []
    for i in range(maximum):
        item = deepcopy(plan[collection][0])
        if collection == 'gear_actions':
            item['fact']['item_key'] = f'schema-only-{i}'
            item['reason_unverified'] = '营'*240
        elif collection == 'budget_allocations': item['line_id'] = f'schema-only-{i}'
        items.append(item)
    plan[collection] = items
    plan['decision_summary_unverified'] = '营'*1200
    ValidatedLogisticsPlan.model_validate(plan)  # Shape only, not business acceptance.
    with pytest.raises(ContractFailure):
        validate_logistics_payload(input, baseline(dataset, input, config), outcome.assessment,
            plan, outcome.trace.model_dump(mode='json'), identity=agent.identity)
    plan[collection].append(deepcopy(items[0]))
    with pytest.raises(ValidationError): ValidatedLogisticsPlan.model_validate(plan)


def test_full_save_payload_utf8_exact_limit_and_one_byte_over():
    from app.application.logistics_audit import LIMIT, canonical, payload
    dataset, input, config = input_fixture()
    agent, _ = agent_fixture(dataset, config)
    outcome = asyncio.run(agent.assess_with_trace(input))
    trace = outcome.trace.model_dump(mode='json')
    # Tests the encoding boundary separately from semantic shape validation.
    plan = {'padding': '营'*100}
    value, _ = payload(input.version_context, outcome.assessment, plan, trace)
    spare = LIMIT - len(canonical(value).encode('utf-8'))
    plan['padding'] += 'x'*spare
    value, _ = payload(input.version_context, outcome.assessment, plan, trace)
    assert len(canonical(value).encode('utf-8')) == LIMIT
    plan['padding'] += 'x'
    with pytest.raises(ValueError): payload(input.version_context, outcome.assessment, plan, trace)
