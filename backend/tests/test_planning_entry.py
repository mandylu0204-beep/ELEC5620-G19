"""A HTTP/supervisor acceptance tests. Agents here are independent test doubles.

These tests do not demonstrate B's implementation or validate synthetic scenarios.
"""
import asyncio
from datetime import datetime, timezone
import shutil
from threading import Event
import time

from fastapi.testclient import TestClient
import pytest

from app.auth import User
from app.config import Settings
from app.contracts.dto import ConfirmedContext, ConfirmedRequirements, ProfileSnapshot, RecommendCampsitesResult, RunResult
from app.contracts.errors import ContractFailure
from app.contracts.enums import ExecutionMode
from app.main import BUSINESS_FILES, create_app
from test_requests import sign_in
from test_storage import logistics, safety, call
from test_workflows import itinerary


class TestOnlyAgent:
    __test__ = False

    def __init__(self, *, fail_once=False, gate=None, malformed=None, no_match=False, closed=False):
        self.fail_once, self.gate, self.malformed, self.no_match, self.closed = fail_once, gate, malformed, no_match, closed
        self.calls = 0
        self.saved = Event()
        self.ports = []

    async def orchestrate(self, input, persistence):
        self.calls += 1
        self.ports.append(persistence)
        scope = input.run_scope
        checkpoint = await persistence.load_checkpoint()
        if checkpoint['recommendations'] is None:
            await persistence.save_recommendations(RecommendCampsitesResult(execution_mode='deterministic_demo',
                search_outcome='NO_MATCH' if self.no_match else 'MATCHES',
                candidates=[] if self.no_match else [{'campsite_id':'camp-test','rank':1,'reasons':['Independent test double']}]), scope.write_keys['recommendations'])
        if not self.no_match:
            version = checkpoint['version'] or await persistence.append_plan_version(None, itinerary(), scope.request_id, 'Test', scope.write_keys['version'])
            stored = next((item for item in checkpoint['assessments'] if item.kind == 'LOGISTICS'), None)
            stored = stored or await persistence.save_assessment(version.version_context, 'LOGISTICS', logistics(version.version_context), scope.write_keys['logistics'])
            route = checkpoint['route']
            if route is None:
                await persistence.report_stage('ASSESSING_SAFETY', 'RUNNING', None)
                if self.fail_once and self.calls == 1:
                    raise RuntimeError('Independent injected failure')
                if not any(item.kind == 'SAFETY' for item in checkpoint['assessments']):
                    await persistence.save_assessment(version.version_context, 'SAFETY', safety(version.version_context, stored.assessment_id, closed=self.closed), scope.write_keys['safety'])
                await persistence.report_stage('ROUTING', 'RUNNING', None)
                route = await persistence.route_assessed_version(version.version_context, 'ELIGIBLE_FOR_FINALISATION', 'Test', scope.write_keys['route'])
        await persistence.report_stage('COMPLETED', 'SUCCEEDED', None)
        self.saved.set()
        if self.gate:
            while not self.gate.is_set():
                await asyncio.sleep(.01)
        result = RunResult(run_id=scope.run_id, execution_mode='deterministic_demo', run_status='SUCCEEDED', stage='COMPLETED',
            route=None if self.no_match else route.status,
            artifact_refs={} if self.no_match else {'version':version.version_context.plan_version_id,'logistics':stored.assessment_id})
        if self.malformed == 'run':
            return result.model_copy(update={'run_id':'different-run'})
        if self.malformed == 'mode':
            return result.model_copy(update={'execution_mode':'stub'})
        if self.malformed == 'artifact':
            return result.model_copy(update={'artifact_refs':{'version':'fabricated-id'}})
        if self.malformed == 'route':
            return result.model_copy(update={'route':'ELIGIBLE_FOR_FINALISATION'})
        if self.malformed == 'unfinished':
            return result.model_copy(update={'run_status':'RUNNING'})
        return result


@pytest.fixture
def web(tmp_path):
    source = Settings(_env_file=None).dataset_path
    dataset = tmp_path / 'data-package'
    (dataset / 'data').mkdir(parents=True)
    for name in BUSINESS_FILES:
        shutil.copyfile(source / 'data' / name, dataset / 'data' / name)
    config = Settings(_env_file=None, database_path=tmp_path/'planning.sqlite3', dataset_path=dataset,
                      execution_mode='deterministic_demo', planning_enabled=True)
    app = create_app(config)
    app.state.agent = TestOnlyAgent()
    with TestClient(app) as client:
        headers = sign_in(client)
        seed_request(app)
        yield app, client, headers


def seed_request(app, request_id='request-entry'):
    demo, dataset = app.state.dispatcher.context()
    app.state.repository.record_confirmed_request(User('camper-a','camper.a','Camper A','CAMPER'), 'Independent confirmed fixture',
        ConfirmedContext(request_id=request_id, confirmed_at=datetime.now(timezone.utc),
            requirements=ConfirmedRequirements(destination='Independent test area', start_date='2026-10-08', end_date='2026-10-10', duration_nights=2, duration_days=3, budget_cents=1000),
            profile_snapshot=ProfileSnapshot(group_size=2), demo_context=demo, dataset_context=dataset))


def start(client, headers, *, key='start-planning-123456', revision=1, request_id='request-entry'):
    return client.post(f'/api/v1/requests/{request_id}/plan', headers=headers,
                       json={'command_key':key,'expected_request_revision':revision})


def wait_run(client, run_id, status):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get('/api/v1/runs/' + run_id)
        assert response.status_code == 200, response.text
        data = response.json()
        if data['run']['status'] == status:
            return data
        time.sleep(.01)
    pytest.fail(f'Run did not reach {status}: {data}')


def retry(client, headers, data, *, key='retry-planning-123456'):
    return client.post('/api/v1/runs/' + data['run']['run_id'] + '/retry', headers=headers,
        json={'command_key':key,'expected_run_revision':data['run']['revision']})


@pytest.mark.parametrize('disabled', ['stub','unregistered','setting'])
def test_unavailable_does_not_register_ghost_runs(web, disabled):
    app, client, headers = web
    if disabled == 'stub': app.state.settings.execution_mode = ExecutionMode.STUB
    if disabled == 'unregistered': app.state.agent = None
    if disabled == 'setting': app.state.settings.planning_enabled = False
    assert client.get('/api/v1/meta').json()['features']['planning'] is False
    assert client.get('/api/v1/request-context').json()['planning_available'] is False
    assert start(client,headers).status_code == 503
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0


def test_confirmation_revision_csrf_and_input_boundary(web):
    app, client, headers = web
    draft = client.post('/api/v1/requests', headers=headers, json={'raw_text':'Unconfirmed test'}).json()
    assert start(client,headers,request_id=draft['request_id']).status_code == 409
    assert start(client,headers,revision=2).json()['error']['code'] == 'VERSION_CONFLICT'
    assert start(client,{}).status_code == 403
    for extra in ({'run_id':'spoof'}, {'expected_request_revision':True}, {'command_key':' '*20}):
        assert client.post('/api/v1/requests/request-entry/plan',headers=headers,
            json={'command_key':'valid-command-123456','expected_request_revision':1,**extra}).status_code == 422
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0


def test_start_receipt_duplicate_and_existing_plan_navigation(web):
    app, client, headers = web
    response = start(client,headers)
    assert response.status_code == 202
    ids = response.json()
    result = wait_run(client,ids['run_id'],'SUCCEEDED')
    assert result['finalisation_available']
    assert start(client,headers).json() == ids
    assert start(client,headers,key='different-command-123456').status_code == 409
    request = client.get('/api/v1/requests/request-entry').json()
    assert request['planning_plan_id'] == ids['plan_id']
    assert request['planning_available'] is True
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM plans').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 1
    assert app.state.agent.calls == 1


def test_cross_user_role_and_logout_guard(web):
    app, client, headers = web
    ids = start(client,headers).json()
    wait_run(client,ids['run_id'],'SUCCEEDED')
    other = sign_in(client,'camper.b','CampMate-B-2026!')
    assert start(client,other).status_code == 404
    assert client.get('/api/v1/runs/'+ids['run_id']).status_code == 404
    body = {'command_key':'retry-other-123456','expected_run_revision':0}
    assert client.post('/api/v1/runs/'+ids['run_id']+'/retry',headers=other,json=body).status_code == 404
    founder = sign_in(client,'founder','CampMate-Founder-2026!')
    assert start(client,founder).status_code == 403
    assert client.post('/api/v1/runs/'+ids['run_id']+'/retry',headers=founder,json=body).status_code == 403
    assert client.post('/api/v1/auth/logout',headers=founder).status_code == 204
    assert start(client,founder).status_code == 401


def test_retry_keeps_checkpoint_and_fences_old_attempt(web):
    app, client, headers = web
    agent = app.state.agent = TestOnlyAgent(fail_once=True)
    ids = start(client,headers).json()
    failed = wait_run(client,ids['run_id'],'FAILED')
    assert failed['retry_available'] and len(failed['assessments']) == 1
    version_id = failed['version']['version_context']['plan_version_id']
    assert retry(client,headers,failed).json() == ids
    done = wait_run(client,ids['run_id'],'SUCCEEDED')
    assert done['version']['version_context']['plan_version_id'] == version_id
    assert len(done['assessments']) == 2 and done['finalisation_available']
    assert retry(client,headers,failed).json() == ids  # Lost HTTP response replay.
    assert agent.calls == 2
    with pytest.raises(ContractFailure) as exc:
        call(agent.ports[0].save_recommendations(RecommendCampsitesResult(execution_mode='deterministic_demo',search_outcome='NO_MATCH',candidates=[]),agent.ports[0].scope.write_keys['recommendations']))
    assert exc.value.error.code == 'STALE_CONTEXT'
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM gear_checklists').fetchone()[0] == 1


@pytest.mark.parametrize('change', ['data','clock','selection'])
def test_current_inputs_changed_cannot_retry(web, change):
    app, client, headers = web
    app.state.agent = TestOnlyAgent(fail_once=True)
    ids = start(client,headers).json()
    failed = wait_run(client,ids['run_id'],'FAILED')
    if change == 'data':
        path = app.state.settings.dataset_path/'data'/BUSINESS_FILES[0]
        path.write_bytes(path.read_bytes()+b'\n')
    if change == 'clock': app.state.settings.demo_today = app.state.settings.demo_today.replace(day=9)
    if change == 'selection': app.state.settings.dataset_selection = {'scenario':'changed'}
    assert retry(client,headers,failed).json()['error']['code'] == 'STALE_CONTEXT'
    data = client.get('/api/v1/runs/'+ids['run_id']).json()
    assert not data['retry_available'] and data['retry_unavailable_reason']
    assert data['run']['status'] == 'FAILED'


@pytest.mark.parametrize('malformed', ['run','mode','artifact','unfinished','route'])
def test_return_validation_prevents_provisional_success(web, malformed):
    app, client, headers = web
    gate = Event()
    agent = app.state.agent = TestOnlyAgent(gate=gate, malformed=malformed, closed=malformed=='route')
    ids = start(client,headers).json()
    assert agent.saved.wait(3)
    pending = client.get('/api/v1/runs/'+ids['run_id']).json()
    assert pending['run']['status'] == 'RUNNING' and not pending['finalisation_available']
    gate.set()
    failed = wait_run(client,ids['run_id'],'FAILED')
    assert failed['run']['error']['code'] == 'CONTRACT_INVALID'
    assert not failed['retry_available'] and not failed['finalisation_available']


def test_no_match_is_business_completion_not_failure(web):
    app, client, headers = web
    app.state.agent = TestOnlyAgent(no_match=True)
    ids = start(client,headers).json()
    done = wait_run(client,ids['run_id'],'SUCCEEDED')
    assert done['recommendations']['result']['search_outcome'] == 'NO_MATCH'
    assert done['version'] is None and not done['finalisation_available'] and not done['retry_available']


def test_shutdown_records_failure_and_restart_retry_recovers(web):
    app, client, headers = web
    gate = Event()
    agent = app.state.agent = TestOnlyAgent(gate=gate)
    ids = start(client,headers).json()
    assert agent.saved.wait(3)
    client.portal.call(app.state.dispatcher.close)
    failed = client.get('/api/v1/runs/'+ids['run_id']).json()
    assert failed['run']['status'] == 'FAILED' and failed['run']['error']['recoverable']
    restarted = create_app(app.state.settings)
    restarted.state.agent = TestOnlyAgent()
    with TestClient(restarted) as other:
        auth = sign_in(other)
        failed = other.get('/api/v1/runs/'+ids['run_id']).json()
        assert failed['retry_available']
        assert retry(other,auth,failed).status_code == 202
        assert wait_run(other,ids['run_id'],'SUCCEEDED')['finalisation_available']


def test_restart_dispatches_pending_durable_command(web):
    app, client, headers = web
    user = User('camper-a','camper.a','Camper A','CAMPER')
    demo, dataset = app.state.dispatcher.context()
    scope = app.state.workflows.start(user,'request-entry',demo,dataset,command_key='pending-test')
    restarted = create_app(app.state.settings)
    restarted.state.agent = TestOnlyAgent(no_match=True)
    with TestClient(restarted) as other:
        sign_in(other)
        done = wait_run(other,scope.run_id,'SUCCEEDED')
        assert done['recommendations']['result']['search_outcome'] == 'NO_MATCH'


def test_expired_crashed_run_becomes_retryable_without_stealing_live_lease(web):
    app, client, headers = web
    user = User('camper-a','camper.a','Camper A','CAMPER')
    clock = [1000]
    app.state.workflows.clock = lambda:clock[0]
    demo, dataset = app.state.dispatcher.context()
    scope = app.state.workflows.start(user,'request-entry',demo,dataset,command_key='expired-test')
    attempt = app.state.workflows.claim(user,scope.run_id,demo,dataset)
    assert client.get('/api/v1/runs/'+scope.run_id).json()['run']['status'] == 'RUNNING'
    clock[0] += 121
    failed = client.get('/api/v1/runs/'+scope.run_id).json()
    assert failed['run']['status'] == 'FAILED' and failed['retry_available']
    assert retry(client,headers,failed).status_code == 202
    wait_run(client,scope.run_id,'SUCCEEDED')
    with pytest.raises(ContractFailure):
        call(app.state.workflows.port(user,attempt).load_confirmed_context())


def test_input_changes_before_completion_stop_writes_and_finalisation(web):
    app, client, headers = web
    gate = Event()
    agent = app.state.agent = TestOnlyAgent(gate=gate)
    ids = start(client,headers).json()
    assert agent.saved.wait(3)
    app.state.settings.dataset_selection = {'scenario':'new-evidence'}
    with pytest.raises(ContractFailure) as exc:
        call(agent.ports[0].load_confirmed_context())
    assert exc.value.error.code == 'STALE_CONTEXT'
    gate.set()
    failed = wait_run(client,ids['run_id'],'FAILED')
    assert failed['run']['error']['code'] == 'STALE_CONTEXT'
    assert not failed['finalisation_available'] and not failed['retry_available']


def test_supervisor_heartbeats_during_long_agent_call(web):
    app, client, headers = web
    gate = Event()
    agent = app.state.agent = TestOnlyAgent(gate=gate)
    app.state.workflows.lease_seconds = .9
    ids = start(client,headers).json()
    assert agent.saved.wait(3)
    with app.state.database.transaction(write=False) as connection:
        first = connection.execute('SELECT expires_at FROM run_leases WHERE run_id=?',(ids['run_id'],)).fetchone()[0]
    deadline = time.monotonic() + 3
    renewed = first
    while renewed <= first and time.monotonic() < deadline:
        time.sleep(.05)
        with app.state.database.transaction(write=False) as connection:
            renewed = connection.execute('SELECT expires_at FROM run_leases WHERE run_id=?',(ids['run_id'],)).fetchone()[0]
    assert renewed > first
    assert client.get('/api/v1/runs/'+ids['run_id']).json()['run']['status'] == 'RUNNING'
    gate.set()
    wait_run(client,ids['run_id'],'SUCCEEDED')


def test_retry_during_previous_worker_cleanup_is_dispatched(web):
    app, client, headers = web
    cleanup = Event()
    stopping = Event()

    class SlowCleanupAgent(TestOnlyAgent):
        async def orchestrate(self, input, persistence):
            if self.calls == 0:
                self.calls += 1
                await persistence.report_stage('RECOMMENDING','FAILED',{
                    'code':'AGENT_FAILURE','message':'Independent slow cleanup failure',
                    'recoverable':True,'allowed_actions':['RETRY']})
                stopping.set()
                while not cleanup.is_set():
                    await asyncio.sleep(.01)
                return RunResult(run_id=input.run_scope.run_id,execution_mode='deterministic_demo',
                    run_status='FAILED',stage='RECOMMENDING',error={
                        'code':'AGENT_FAILURE','message':'Independent slow cleanup failure',
                        'recoverable':True,'allowed_actions':['RETRY']})
            return await super().orchestrate(input,persistence)

    app.state.agent = SlowCleanupAgent(no_match=True)
    ids = start(client,headers).json()
    assert stopping.wait(3)
    failed = wait_run(client,ids['run_id'],'FAILED')
    assert retry(client,headers,failed).status_code == 202
    cleanup.set()
    done = wait_run(client,ids['run_id'],'SUCCEEDED')
    assert done['recommendations']['result']['search_outcome'] == 'NO_MATCH'
    assert app.state.agent.calls == 2


def test_http_start_receipt_failure_rolls_back_and_can_be_resubmitted(web):
    app, client, headers = web
    with app.state.database.transaction() as connection:
        connection.execute("CREATE TRIGGER fail_start BEFORE INSERT ON workflow_commands BEGIN SELECT RAISE(ABORT,'test-only'); END")
    assert start(client,headers).json()['error']['code'] == 'PERSISTENCE_FAILURE'
    with app.state.database.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM plans').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0
        connection.execute('DROP TRIGGER fail_start')
    ids = start(client,headers).json()
    wait_run(client,ids['run_id'],'SUCCEEDED')
