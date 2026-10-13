"""A16 auth/dispatcher/trace/restore integration. All model HTTP is simulated."""
from dataclasses import replace
from pydantic import SecretStr

from fastapi.testclient import TestClient
import pytest

from app.application.agent_runtime import DATASET_AGENT_FACTORIES
from app.contracts.errors import ContractFailure
from app.contracts.enums import ExecutionMode
from campus_http_fixtures import mock_campus, application
from test_v2_http_demo import launch, assessment, finalise, INPUTS, CASES
from test_extended_demo import confirm_saved
from test_requests import sign_in
from test_planning_entry import wait_run, retry, start
from test_plan_changes import change
from test_rule_orchestration import FailOnce

KEY = (ExecutionMode.AGENT, 'CampMate Synthetic Demo Dataset v2')


def counts(app):
    with app.state.database.transaction(write=False) as db:
        return {name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
            ['plans','runs','versions','model_planning_traces','final_records']}


def test_actual_campus_components_through_http_save_trace_and_immutable_final(tmp_path, monkeypatch):
    requests, _ = mock_campus(monkeypatch)
    app = application(tmp_path)
    with TestClient(app) as client:
        meta = client.get('/api/v1/meta').json()
        assert meta['supported_operations'] == ['PLAN', 'REASSESS', 'REVISE'] and meta['features']['model_planning']
        assert meta['planning_stages']['itinerary']=='model' and meta['planning_stages']['safety']=='rules'
        assert requests == []  # readiness/meta must never probe the model
        headers=sign_in(client)
        detail=launch(client,headers,'normal')
        assert len(requests)==2
        trace=detail['model_planning_trace']
        assert trace['run_id']==detail['run']['run_id']
        assert trace['version_id']==detail['version']['version_context']['plan_version_id']
        assert trace['input_fingerprint']==detail['version']['version_context']['input_fingerprint']
        assert trace['trace']['configuration_fingerprint']==detail['confirmed_context']['dataset_context']['selection_config']['hybrid_planning_fingerprint']
        assert trace['trace']['served_models']==['offline-test-only']
        assert detail['finalisation_available'] and detail['revision_available'] and detail['reassessment_available']
        assert all(row['result']['execution_mode']=='agent' for row in detail['assessments'])
        path, record=finalise(client,headers,detail)
        assert record['model_planning_trace']==trace
        other=sign_in(client,'camper.b','CampMate-B-2026!')
        assert client.get('/api/v1/plans/'+detail['plan']['plan_id']).status_code==404
        assert client.get(path).status_code==404
        with app.state.database.transaction(write=False) as db:
            payload=db.execute('SELECT payload FROM model_planning_traces').fetchone()[0]
            assert 'unit-only-school-secret' not in payload and 'Authorization' not in payload


def test_atomic_trace_insert_failure_rolls_back_version_then_retry_generates_again(tmp_path,monkeypatch):
    requests,_=mock_campus(monkeypatch)
    app=application(tmp_path)
    with TestClient(app) as client:
        with app.state.database.transaction() as db:
            db.execute("CREATE TRIGGER test_trace_failure BEFORE INSERT ON model_planning_traces BEGIN SELECT RAISE(ABORT,'injected'); END")
        # launch() expects success; perform the actual confirmed/start steps separately.
        headers=sign_in(client)
        request=confirmed_request(client,headers)
        begun=start(client,headers,request_id=request['request_id'],revision=request['revision'])
        assert begun.status_code==202
        failed=wait_run(client,begun.json()['run_id'],'FAILED')
        assert failed['retry_available'] and len(requests)==2
        assert counts(app)['versions']==counts(app)['model_planning_traces']==0
        with app.state.database.transaction() as db:
            assert db.execute("SELECT COUNT(*) FROM write_receipts WHERE operation='version'").fetchone()[0]==0
            assert db.execute('SELECT current_version_id FROM plans').fetchone()[0] is None
            db.execute('DROP TRIGGER test_trace_failure')
        assert retry(client,headers,failed).status_code==202
        saved=wait_run(client,failed['run']['run_id'],'SUCCEEDED')
        assert len(requests)==4 and saved['model_planning_trace'] and saved['finalisation_available']


def confirmed_request(client,headers,case='normal'):
    assert client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':INPUTS['profile']}).status_code==200
    saved=client.post('/api/v1/requests',headers=headers,json=CASES[case]['request'])
    assert saved.status_code==201,saved.text
    return confirm_saved(client,headers,saved.json(),'a16-confirm-request-123456')


def test_lost_model_save_receipt_restarts_without_regenerating_or_replacing_trace(tmp_path,monkeypatch):
    requests,_=mock_campus(monkeypatch)
    factory=DATASET_AGENT_FACTORIES[KEY]
    control={'failed':False}
    class LoseReceipt:
        def __init__(self,agent): self.agent=agent
        def __getattr__(self,name): return getattr(self.agent,name)
        async def orchestrate(self,input,port):
            if not control['failed']:
                control['failed']=True
                port=FailOnce(port,'append_model_plan',after=True)
            return await self.agent.orchestrate(input,port)
    def wrapped(settings,descriptor):
        binding=factory(settings,descriptor)
        return replace(binding,agent=LoseReceipt(binding.agent))
    monkeypatch.setitem(DATASET_AGENT_FACTORIES,KEY,wrapped)
    app=application(tmp_path)
    with TestClient(app) as client:
        headers=sign_in(client)
        request=confirmed_request(client,headers)
        begun=start(client,headers,request_id=request['request_id'],revision=request['revision'])
        failed=wait_run(client,begun.json()['run_id'],'FAILED')
        trace=failed['model_planning_trace'];content=failed['version']['content']
        assert trace and len(requests)==2
    # Same database/new supervisor, not an in-memory replay of a model result.
    with TestClient(application(tmp_path)) as client:
        headers=sign_in(client)
        failed=client.get('/api/v1/runs/'+failed['run']['run_id']).json()
        assert retry(client,headers,failed).status_code==202
        saved=wait_run(client,failed['run']['run_id'],'SUCCEEDED')
        assert len(requests)==2 and saved['version']['content']==content
        assert saved['model_planning_trace']==trace
        assert counts(client.app)['versions']==counts(client.app)['model_planning_traces']==1


def test_no_match_does_not_invent_a_model_call_or_trace(tmp_path,monkeypatch):
    requests,_=mock_campus(monkeypatch)
    with TestClient(application(tmp_path,'no_match')) as client:
        headers=sign_in(client);request=confirmed_request(client,headers,'no_match')
        begun=start(client,headers,request_id=request['request_id'],revision=request['revision'])
        result=wait_run(client,begun.json()['run_id'],'SUCCEEDED')
        assert result['recommendations']['result']['search_outcome']=='NO_MATCH'
        assert requests==[] and result['version'] is None and not result.get('model_planning_trace')


def test_model_may_select_another_valid_candidate_but_cannot_clear_missing_evidence(tmp_path,monkeypatch):
    requests,_=mock_campus(monkeypatch,site='demo-river-flat')
    with TestClient(application(tmp_path)) as client:
        result=launch(client,sign_in(client),'normal')
        assert result['version']['content']['selected_campsite_ids']==['demo-river-flat']
        assert assessment(result,'SAFETY')['result']['data_quality']['WEATHER']=='MISSING'
        assert not result['finalisation_available'] and result['model_planning_trace']


def test_changed_model_configuration_blocks_old_finalisation_without_live_probe(tmp_path,monkeypatch):
    from app.llm import config
    from test_finalisation import command as final_command
    requests,settings=mock_campus(monkeypatch)
    with TestClient(application(tmp_path)) as client:
        headers=sign_in(client);saved=launch(client,headers,'normal')
        monkeypatch.setattr(config,'CampusModelSettings',lambda:settings.model_copy(update={'timeout_seconds':6}))
        current=client.get('/api/v1/plans/'+saved['plan']['plan_id']).json()
        assert current['current_inputs_error'] and not current['finalisation_available']
        response=client.post('/api/v1/plans/'+saved['plan']['plan_id']+'/finalise',headers=headers,json=final_command(saved))
        assert response.status_code==409 and response.json()['error']['code']=='STALE_CONTEXT'
        assert len(requests)==2


def test_missing_model_key_is_not_ready_and_never_registers_a_run(tmp_path,monkeypatch):
    from app.llm import config
    requests,settings=mock_campus(monkeypatch)
    monkeypatch.setattr(config,'CampusModelSettings',lambda:settings.model_copy(update={'api_key':SecretStr('')}))
    app=application(tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/v1/health/ready').status_code==503
        assert not client.get('/api/v1/meta').json()['features']['planning']
        headers=sign_in(client)
        response=start(client,headers,request_id='missing-request')
        assert response.status_code==404  # owner/existence guard still runs first
        assert counts(app)['runs']==0 and requests==[]


def test_more_than_thirty_nights_is_rejected_before_a_model_run(tmp_path,monkeypatch):
    requests,_=mock_campus(monkeypatch)
    with TestClient(application(tmp_path)) as client:
        headers=sign_in(client)
        assert client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':INPUTS['profile']}).status_code==200
        body={'raw_text':'Two people in CampMate Demo Region from 2026-11-06 for 31 nights, AUD 5000. We want ready-to-eat meals.',
            'explicit_fields':{'destination':'CampMate Demo Region','start_date':'2026-11-06','duration_nights':31,'budget_cents':500000,'preferences':['ready-to-eat meals']}}
        saved=client.post('/api/v1/requests',headers=headers,json=body)
        request=confirm_saved(client,headers,saved.json(),'a16-long-confirm-123456')
        response=start(client,headers,request_id=request['request_id'],revision=request['revision'])
        assert response.status_code==422 and counts(client.app)['runs']==0 and requests==[]


def test_model_save_receipt_is_idempotent_and_trace_changes_are_rejected(tmp_path,monkeypatch):
    mock_campus(monkeypatch)
    factory=DATASET_AGENT_FACTORIES[KEY]; checks=[]
    class AgentProxy:
        def __init__(self,agent):self.agent=agent
        def __getattr__(self,name):return getattr(self.agent,name)
        async def orchestrate(self,input,port):
            class PortProxy:
                def __getattr__(self,name):return getattr(port,name)
                async def append_model_plan(self,*args):
                    first=await port.append_model_plan(*args)
                    assert await port.append_model_plan(*args)==first
                    changed=list(args);changed[4]={**args[4],'decision_summary':'Different summary under same write key.'}
                    with pytest.raises(ContractFailure) as error:
                        await port.append_model_plan(*changed)
                    assert error.value.error.code=='IDEMPOTENCY_CONFLICT'
                    with pytest.raises(ContractFailure) as error:
                        await port.append_plan_version(args[0],args[1],args[2],args[3],args[5])
                    assert error.value.error.code=='CONTRACT_INVALID'
                    checks.append(True)
                    return first
            return await self.agent.orchestrate(input,PortProxy())
    def wrapped(settings,descriptor):
        binding=factory(settings,descriptor)
        return replace(binding,agent=AgentProxy(binding.agent))
    monkeypatch.setitem(DATASET_AGENT_FACTORIES,KEY,wrapped)
    app=application(tmp_path)
    with TestClient(app) as client:
        detail=launch(client,sign_in(client),'normal')
        assert checks==[True] and detail['finalisation_available']
        assert counts(app)['versions']==counts(app)['model_planning_traces']==1


@pytest.mark.parametrize('patch,code',[
    ({'validation_passed':False},'CONTRACT_INVALID'),
    ({'configuration_fingerprint':'0'*64},'STALE_CONTEXT'),
    ({'candidate_ids':['unregistered-site']},'CONTRACT_INVALID'),
    ({'Authorization':'test-only-not-a-real-secret'},'CONTRACT_INVALID'),
])
def test_invalid_trace_never_creates_a_model_version(tmp_path,monkeypatch,patch,code):
    mock_campus(monkeypatch)
    factory=DATASET_AGENT_FACTORIES[KEY]
    class AgentProxy:
        def __init__(self,agent):self.agent=agent
        def __getattr__(self,name):return getattr(self.agent,name)
        async def orchestrate(self,input,port):
            class PortProxy:
                def __getattr__(self,name):return getattr(port,name)
                async def append_model_plan(self,*args):
                    values=list(args);values[4]={**args[4],**patch}
                    return await port.append_model_plan(*values)
            return await self.agent.orchestrate(input,PortProxy())
    def wrapped(settings,descriptor):
        binding=factory(settings,descriptor)
        return replace(binding,agent=AgentProxy(binding.agent))
    monkeypatch.setitem(DATASET_AGENT_FACTORIES,KEY,wrapped)
    app=application(tmp_path)
    with TestClient(app) as client:
        headers=sign_in(client);request=confirmed_request(client,headers)
        begun=start(client,headers,request_id=request['request_id'],revision=request['revision'])
        failed=wait_run(client,begun.json()['run_id'],'FAILED')
        assert failed['run']['error']['code']==code
        assert counts(app)['versions']==counts(app)['model_planning_traces']==0


def test_missing_required_trace_blocks_finalisation(tmp_path,monkeypatch):
    from test_finalisation import command as final_command
    mock_campus(monkeypatch);app=application(tmp_path)
    with TestClient(app) as client:
        headers=sign_in(client);saved=launch(client,headers,'normal')
        with app.state.database.transaction() as db:
            db.execute('DROP TRIGGER no_delete_model_trace')
            db.execute('DELETE FROM model_planning_traces')
        response=client.post('/api/v1/plans/'+saved['plan']['plan_id']+'/finalise',headers=headers,json=final_command(saved))
        assert response.status_code==503 and counts(app)['final_records']==0
        assert counts(app)['versions']==1  # integrity failure is not auto-regenerated


def test_upgrade_from_schema_five_preserves_existing_profiles_and_adds_empty_audit(tmp_path):
    from app.storage.database import Database, execute_migration, MIGRATION_1, MIGRATION_2, MIGRATION_3, MIGRATION_4, MIGRATION_5
    db=Database(tmp_path/'old-five.sqlite3')
    with db.transaction() as connection:
        for number,migration in enumerate([MIGRATION_1,MIGRATION_2,MIGRATION_3,MIGRATION_4,MIGRATION_5],1):
            execute_migration(connection,migration)
            connection.execute('INSERT INTO schema_migrations VALUES(?,?)',(number,'historical'))
        connection.execute("INSERT INTO users VALUES('old-owner','old.user','Old Camper','CAMPER','old-hash')")
        connection.execute('INSERT INTO profiles VALUES(?,?,?,?,?)',('old-owner','old-profile','{"group_size":2}',1,'historical'))
    db.initialize()
    with db.transaction(write=False) as connection:
        assert connection.execute('SELECT payload FROM profiles').fetchone()[0]=='{"group_size":2}'
        assert connection.execute('SELECT COUNT(*) FROM model_planning_traces').fetchone()[0]==0
        assert connection.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==6
    assert db.ready()
