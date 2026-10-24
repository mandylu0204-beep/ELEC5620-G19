"""A36–A38 + real B Hybrid/Orchestrator; isolated SQLite, never campus calls."""
import asyncio
from copy import deepcopy
from datetime import date, timedelta
from threading import Event

from fastapi.testclient import TestClient
import pytest

from app.application.agent_runtime import DATASET_AGENT_FACTORIES
from app.contracts.enums import ErrorCode
from app.contracts.errors import ContractFailure
from app.contracts.dto import OrchestrateInput
from app.workflow.configuration import failure
from app.workflow.orchestration import Orchestrator
from safety_runtime_fixtures import application, mock_safety_runtime, role_counts, db_counts, launch, wait_run, confirmed_request
from test_campus_http import KEY
from test_model_logistics_wiring import wrap_port
from test_plan_changes import change
from test_planning_entry import start, retry
from test_requests import sign_in
from test_finalisation import command as final_command
from test_rule_orchestration import Proxy, FailOnce
from test_v2_http_demo import assessment, finalise


from audit_test_reads import internal_audit_reads, json_with_internal_audits

# These tests verify private persistence; public role-scoped reads are tested separately.
wait_run = internal_audit_reads(wait_run)
launch = internal_audit_reads(launch)
finalise = internal_audit_reads(finalise)


def assert_safety_audit(detail, *, logistics=True):
    audits = detail['model_assessment_audits']
    assert set(audits) == ({'LOGISTICS','SAFETY'} if logistics else {'SAFETY'})
    safe,log = assessment(detail,'SAFETY'),assessment(detail,'LOGISTICS')
    audit = audits['SAFETY']
    assert audit['kind'] == audit['trace']['role'] == 'SAFETY'
    assert audit['assessment_id'] == safe['assessment_id']
    assert audit['depends_on_assessment_id'] == safe['depends_on_assessment_id'] == log['assessment_id']
    assert audit['run_id'] == detail['run']['run_id']
    assert audit['plan_version_id'] == detail['version']['version_context']['plan_version_id']
    assert audit['input_fingerprint'] == detail['version']['version_context']['input_fingerprint']
    assert audit['configuration_fingerprint'] == audit['trace']['configuration_fingerprint']
    assert audit['trace']['turns'] == 3 and audit['trace']['tool_calls'] == ['read_safety_facts','evaluate_safety_plan']
    assert audit['trace']['served_models'] == ['offline-safety-runtime']
    assert safe['gear_checklist_id'] is None
    assert not {'owner_id','input_json','rule_facts_json','selection_json'} & audit.keys()
    assert not any('not an LLM' in text for text in safe['result']['assumptions'])
    if logistics:
        assert audits['LOGISTICS']['trace']['role'] == 'LOGISTICS'
        assert audits['LOGISTICS']['audit_id'] != audit['audit_id']
    return audit


@pytest.mark.parametrize('logistics_mode,safety_mode',[
    ('rules','rules'),('model','rules'),('rules','model'),('model','model')])
def test_actual_http_factory_all_four_role_combinations(tmp_path,monkeypatch,logistics_mode,safety_mode):
    requests,_ = mock_safety_runtime(monkeypatch)
    with TestClient(application(tmp_path,logistics=logistics_mode,safety=safety_mode)) as client:
        assert client.get('/api/v1/health/ready').status_code == 200
        meta = json_with_internal_audits(client, client.get('/api/v1/meta'))
        assert meta['planning_stages']['safety'] == safety_mode
        assert meta['features']['model_safety'] is (safety_mode == 'model')
        assert not requests
        headers = sign_in(client)
        detail = launch(client,headers,'normal')
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3 if logistics_mode=='model' else 0,
            'SAFETY':3 if safety_mode=='model' else 0}
        assert sum(item['role']=='INTERPRETATION' for item in requests) == 1
        expected = {name for name,mode in (('LOGISTICS',logistics_mode),('SAFETY',safety_mode)) if mode=='model'}
        assert set(detail['model_assessment_audits']) == expected
        if safety_mode == 'model':
            assert_safety_audit(detail,logistics=logistics_mode=='model')
        assert detail['finalisation_available']
        _,snapshot = finalise(client,headers,detail)
        assert set(snapshot.get('model_assessment_audits',{})) == expected


@pytest.mark.parametrize('case,outcome,eligible',[
    ('normal','PASSED',True),('budget_revision','PASSED',False),
    ('missing_evidence','REVIEW',False),('road_closure','BLOCKED',False)])
def test_four_scenarios_run_real_safety_component_without_changing_rules(tmp_path,monkeypatch,case,outcome,eligible):
    requests,control = mock_safety_runtime(monkeypatch)
    control['site'] = {'normal':'demo-wattle-rest','budget_revision':'demo-wattle-rest',
        'missing_evidence':'demo-river-flat','road_closure':'demo-moonlit-field'}[case]
    # Normal 2.1 no longer loads v2's old safety-02 missing-weather fixture.
    # Use an actual confirmed trip beyond the sealed index's validity instead.
    options = {'demo_today':'2026-11-29'} if case=='missing_evidence' else {}
    with TestClient(application(tmp_path,case,**options)) as client:
        headers = sign_in(client)
        detail = launch(client,headers,case,**({'start':'2026-11-30'} if case=='missing_evidence' else {}))
        audit = assert_safety_audit(detail)
        assert assessment(detail,'SAFETY')['result']['outcome'] == outcome
        if case == 'missing_evidence':
            assert assessment(detail,'SAFETY')['result']['data_quality']['WEATHER'] == 'MISSING'
        assert detail['finalisation_available'] is eligible
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':3}
        if eligible:
            _,snapshot = finalise(client,headers,detail)
            assert snapshot['model_assessment_audits']['SAFETY'] == audit
        else:
            response = client.post('/api/v1/plans/'+detail['plan']['plan_id']+'/finalise',
                headers=headers,json=final_command(detail))
            assert response.status_code == 409 and json_with_internal_audits(client, response)['error']['code'] == 'FINALISATION_BLOCKED'


@pytest.mark.parametrize('logistics_mode',['rules','model'])
def test_no_match_never_calls_downstream_models_or_requires_audits(tmp_path,monkeypatch,logistics_mode):
    requests,_ = mock_safety_runtime(monkeypatch)
    with TestClient(application(tmp_path,'no_match',logistics=logistics_mode)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers,'no_match')
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        detail = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'SUCCEEDED')
        assert detail['version'] is None and detail['assessments'] == []
        assert detail.get('model_assessment_audits',{}) == {}
        assert [item['role'] for item in requests] == ['INTERPRETATION']
        assert all(value == 0 for value in db_counts(client.app).values())


@pytest.mark.parametrize('logistics_mode',['rules','model'])
def test_revise_and_reassess_create_new_safety_not_a_new_origin_trace(tmp_path,monkeypatch,logistics_mode):
    requests,_ = mock_safety_runtime(monkeypatch)
    with TestClient(application(tmp_path,'budget_revision',logistics=logistics_mode)) as client:
        headers = sign_in(client)
        old = launch(client,headers,'budget_revision')
        response = change(client,headers,old,'revise',feedback='cheaper campsite')
        assert response.status_code == 202,response.text
        revised = wait_run(client,json_with_internal_audits(client, response)['run_id'],'SUCCEEDED')
        old_audit = assert_safety_audit(old,logistics=logistics_mode=='model')
        revised_audit = assert_safety_audit(revised,logistics=logistics_mode=='model')
        assert revised_audit['audit_id'] != old_audit['audit_id']
        assert revised['version']['version_number'] == 2 and revised['finalisation_available']
        path,snapshot = finalise(client,headers,revised)
        current = json_with_internal_audits(client, client.get('/api/v1/plans/'+revised['plan']['plan_id']))
        response = change(client,headers,current,key='safety-reassess-independent')
        assert response.status_code == 202,response.text
        reassessed = wait_run(client,json_with_internal_audits(client, response)['run_id'],'SUCCEEDED')
        audit = assert_safety_audit(reassessed,logistics=logistics_mode=='model')
        assert reassessed['version']['content'] == revised['version']['content']
        assert reassessed['model_planning_trace'] == revised['model_planning_trace']
        assert audit['plan_version_id'] == revised_audit['plan_version_id']
        assert audit['run_id'] != revised_audit['run_id'] and audit['assessment_id'] != revised_audit['assessment_id']
        assert audit['trace']['input_sha256'] != revised_audit['trace']['input_sha256']
        assert json_with_internal_audits(client, client.get(path))['final_record'] == snapshot
        assert role_counts(requests) == {'PLANNING':4,'LOGISTICS':9 if logistics_mode=='model' else 0,'SAFETY':9}
        assert db_counts(client.app)['model_safety_audits'] == 3


@pytest.mark.parametrize('logistics_mode',['rules','model'])
@pytest.mark.parametrize('method,after,safety_calls',[
    ('save_model_safety_assessment',True,3),('save_model_safety_assessment',False,6),
    ('route_assessed_version',True,3)])
def test_restart_reuses_committed_safety_and_retries_only_unsaved_steps(tmp_path,monkeypatch,logistics_mode,method,after,safety_calls):
    requests,_ = mock_safety_runtime(monkeypatch)
    used = []
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port,method,after=after)
        return port
    wrap_port(monkeypatch,once)
    with TestClient(application(tmp_path,logistics=logistics_mode)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        assert failed['retry_available']
        saved_audits = deepcopy(failed['model_assessment_audits'])
        content,origin = failed['version']['content'],failed['model_planning_trace']
    with TestClient(application(tmp_path,logistics=logistics_mode)) as client:
        headers = sign_in(client)
        failed = json_with_internal_audits(client, client.get('/api/v1/runs/'+failed['run']['run_id']))
        assert retry(client,headers,failed).status_code == 202
        restored = wait_run(client,failed['run']['run_id'],'SUCCEEDED')
        audit = assert_safety_audit(restored,logistics=logistics_mode=='model')
        for role,old in saved_audits.items():
            assert restored['model_assessment_audits'][role] == old
        assert restored['version']['content'] == content and restored['model_planning_trace'] == origin
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3 if logistics_mode=='model' else 0,'SAFETY':safety_calls}
        assert db_counts(client.app)['model_safety_audits'] == 1
        assert audit['attempt_id']


@pytest.mark.parametrize('table',['assessments','model_safety_audits','write_receipts'])
def test_atomic_safety_rollback_keeps_logistics_then_retries_only_safety(tmp_path,monkeypatch,table):
    requests,_ = mock_safety_runtime(monkeypatch)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        condition = " WHEN NEW.kind='SAFETY'" if table=='assessments' else " WHEN NEW.operation='safety'" if table=='write_receipts' else ''
        with client.app.state.database.transaction() as db:
            db.execute(f"CREATE TRIGGER offline_safety_failure BEFORE INSERT ON {table}{condition} BEGIN SELECT RAISE(ABORT,'offline temporary failure'); END")
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        assert failed['retry_available'] and set(failed['model_assessment_audits']) == {'LOGISTICS'}
        old_log = failed['model_assessment_audits']['LOGISTICS']
        assert db_counts(client.app)['assessments'] == 1 and db_counts(client.app)['model_safety_audits'] == 0
        with client.app.state.database.transaction() as db:
            assert db.execute("SELECT COUNT(*) FROM write_receipts WHERE operation='safety'").fetchone()[0] == 0
            db.execute('DROP TRIGGER offline_safety_failure')
        assert retry(client,headers,failed).status_code == 202
        restored = wait_run(client,failed['run']['run_id'],'SUCCEEDED')
        assert_safety_audit(restored)
        assert restored['model_assessment_audits']['LOGISTICS'] == old_log
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':6}


@pytest.mark.parametrize('mode,recoverable',[('invalid',False),('unavailable',True)])
def test_safety_failure_never_falls_back_to_rules_or_replans(tmp_path,monkeypatch,mode,recoverable):
    requests,control = mock_safety_runtime(monkeypatch)
    control[mode] = True
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        assert failed['run']['stage'] == 'ASSESSING_SAFETY'
        assert failed['run']['error']['recoverable'] is recoverable
        assert db_counts(client.app)['assessments'] == 1 and db_counts(client.app)['model_safety_audits'] == 0
        assert set(failed['model_assessment_audits']) == {'LOGISTICS'}
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':1}


def test_missing_safety_save_capability_fails_before_any_model_or_business_write(tmp_path,monkeypatch):
    requests,_ = mock_safety_runtime(monkeypatch)
    class MissingSafetySave(Proxy):
        save_model_safety_assessment = None
    wrap_port(monkeypatch,MissingSafetySave)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        assert failed['run']['error']['code'] == 'CONTRACT_INVALID'
        assert [item['role'] for item in requests] == ['INTERPRETATION']
        assert all(value == 0 for value in db_counts(client.app).values())


@pytest.mark.parametrize('mutation',[
    'missing','unexpected','dependency','association','attempt','hash','trace','plan'])
def test_corrupt_checkpoint_is_terminal_and_never_regenerates_safety(tmp_path,monkeypatch,mutation):
    requests,_ = mock_safety_runtime(monkeypatch)
    used = []
    class BrokenCheckpoint(Proxy):
        async def load_checkpoint(self):
            value = await self.port.load_checkpoint()
            audit = value['model_assessment_audits']['SAFETY']
            if mutation == 'missing': del value['model_assessment_audits']['SAFETY']
            elif mutation == 'unexpected': value['model_assessment_audits']['PLANNING'] = deepcopy(audit)
            elif mutation == 'dependency': audit['depends_on_assessment_id'] = 'other-logistics'
            elif mutation == 'association': audit['assessment_id'] = 'other-assessment'
            elif mutation == 'attempt': audit['attempt_id'] = ''
            elif mutation == 'hash': audit['payload_sha256'] = '0'*64
            elif mutation == 'trace': audit['trace']['role'] = 'LOGISTICS'
            else: audit['plan']['source_refs'] = []
            return value
    def transform(port):
        if not used:
            used.append(True)
            return FailOnce(port,'save_model_safety_assessment',after=True)
        return BrokenCheckpoint(port)
    wrap_port(monkeypatch,transform)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        saved = deepcopy(failed['model_assessment_audits']['SAFETY'])
        assert retry(client,headers,failed).status_code == 202
        broken = wait_run(client,failed['run']['run_id'],'FAILED')
        error = broken['run']['error']
        assert error['code'] == 'PERSISTENCE_FAILURE' and not error['recoverable']
        assert error['allowed_actions'] == ['CONTACT_OPERATOR'] and not broken['retry_available']
        assert broken['model_assessment_audits']['SAFETY'] == saved
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':3}


@pytest.mark.parametrize('step',['save_model_safety_assessment','load_checkpoint'])
def test_permanent_integrity_error_stays_terminal_through_dispatcher(tmp_path,monkeypatch,step):
    requests,_ = mock_safety_runtime(monkeypatch)
    class PermanentFailure(Proxy):
        def __getattr__(self,name):
            if name != step:
                return getattr(self.port,name)
            async def fail(*args,**kwargs):
                raise failure(ErrorCode.PERSISTENCE_FAILURE,'Offline permanent safety integrity failure.')
            return fail
    wrap_port(monkeypatch,PermanentFailure)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        assert failed['run']['error']['code'] == 'PERSISTENCE_FAILURE'
        assert not failed['run']['error']['recoverable'] and not failed['retry_available']
        assert failed['run']['error']['allowed_actions'] == ['CONTACT_OPERATOR']
        assert role_counts(requests)['SAFETY'] == (3 if step=='save_model_safety_assessment' else 0)


def fast_heartbeat(monkeypatch):
    factory = DATASET_AGENT_FACTORIES[KEY]
    def fast(settings,descriptor):
        binding = factory(settings,descriptor)
        binding.agent.heartbeat_interval = .005
        return binding
    monkeypatch.setitem(DATASET_AGENT_FACTORIES,KEY,fast)


def test_safety_wait_keeps_lease_alive_without_exact_heartbeat_counts(tmp_path,monkeypatch):
    requests,control = mock_safety_runtime(monkeypatch)
    released,observed = Event(),Event()
    async def block(role):
        if role == 'SAFETY' and not released.is_set():
            while not released.is_set():
                await asyncio.sleep(.001)
    control['on_request'] = block
    class RenewSafety(Proxy):
        async def heartbeat(self):
            await self.port.heartbeat()
            if any(item['role']=='SAFETY' for item in requests) and not released.is_set():
                with self.port.db.transaction(write=False) as db:
                    lease = db.execute('SELECT * FROM run_leases WHERE run_id=?',(self.port.scope.run_id,)).fetchone()
                    assert lease['attempt_id'] == self.port.attempt_id and lease['expires_at'] > self.port.clock()
                observed.set()
                released.set()
    fast_heartbeat(monkeypatch)
    wrap_port(monkeypatch,RenewSafety)
    try:
        with TestClient(application(tmp_path)) as client:
            detail = launch(client,sign_in(client),'normal')
            assert_safety_audit(detail)
            assert observed.is_set()
    finally:
        released.set()


def test_lost_lease_cancels_inflight_safety_and_rejects_late_artifacts(tmp_path,monkeypatch):
    requests,control = mock_safety_runtime(monkeypatch)
    entered,cancelled = Event(),Event()
    async def block(role):
        if role == 'SAFETY':
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
                raise failure(ErrorCode.STALE_CONTEXT,'Offline safety lease lost.')
            await self.port.heartbeat()
    fast_heartbeat(monkeypatch)
    wrap_port(monkeypatch,LoseLease)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        assert cancelled.is_set() and failed['run']['error']['code'] == 'STALE_CONTEXT'
        assert db_counts(client.app)['assessments'] == 1 and db_counts(client.app)['model_safety_audits'] == 0
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':1}


def test_hybrid_rejects_registered_safety_identity_drift_during_wait(tmp_path,monkeypatch):
    requests,control = mock_safety_runtime(monkeypatch)
    async def drift(role):
        if role == 'SAFETY':
            client = control['active_client']
            client.settings = client.settings.model_copy(update={'max_completion_tokens':4096})
    control['on_request'] = drift
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        assert failed['run']['error']['code'] == 'STALE_CONTEXT'
        assert db_counts(client.app)['model_safety_audits'] == 0
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':1}


def test_restart_historical_reads_and_owner_isolation_need_no_new_safety_model(tmp_path,monkeypatch):
    from app.llm import safety_identity
    requests,_ = mock_safety_runtime(monkeypatch)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        detail = launch(client,headers,'normal')
        audit = assert_safety_audit(detail)
        path,snapshot = finalise(client,headers,detail)
        sign_in(client,'camper.b','CampMate-B-2026!')
        assert client.get('/api/v1/plans/'+detail['plan']['plan_id']).status_code == 404
        assert client.get(path).status_code == 404
    monkeypatch.setattr(safety_identity,'SAFETY_SYSTEM_PROMPT',safety_identity.SAFETY_SYSTEM_PROMPT+'\nFuture prompt revision.')
    with TestClient(application(tmp_path)) as client:
        sign_in(client)
        restored = client.get('/api/v1/plans/'+detail['plan']['plan_id'])
        assert restored.status_code == 200
        assert json_with_internal_audits(client, restored)['model_assessment_audits']['SAFETY'] == audit
        assert json_with_internal_audits(client, client.get(path))['final_record'] == snapshot
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':3}


@pytest.mark.parametrize('logistics_mode',['rules','model'])
def test_exact_audit_role_sets_for_empty_partial_and_complete_checkpoints(tmp_path,monkeypatch,logistics_mode):
    requests,_ = mock_safety_runtime(monkeypatch)
    captured = []
    class CaptureSafety(Proxy):
        async def save_model_safety_assessment(self,*args,**kwargs):
            saved = await self.port.save_model_safety_assessment(*args,**kwargs)
            captured.append((self.port.scope,await self.port.load_checkpoint()))
            return saved
    wrap_port(monkeypatch,CaptureSafety)
    with TestClient(application(tmp_path,logistics=logistics_mode)) as client:
        launch(client,sign_in(client),'normal')
        scope,value = captured[0]
        agent = client.app.state.runtime.for_scope(scope).agent
        raw = OrchestrateInput(run_scope=scope,confirmed_context=value['confirmed_context'])
        for kinds in (set(),{'LOGISTICS'},{'LOGISTICS','SAFETY'}):
            checkpoint = deepcopy(value)
            checkpoint['assessments'] = [item for item in checkpoint['assessments'] if item.kind in kinds]
            expected = {'SAFETY'} & kinds
            if logistics_mode == 'model': expected |= {'LOGISTICS'} & kinds
            checkpoint['model_assessment_audits'] = {key:audit for key,audit in checkpoint['model_assessment_audits'].items() if key in expected}
            orchestrator = Orchestrator(agent,agent.workflow_configuration,None)
            _,_,_,log,safe,_ = orchestrator.checkpoint(raw,checkpoint)
            assert (log is not None) is ('LOGISTICS' in kinds)
            assert (safe is not None) is ('SAFETY' in kinds)
        # A saved audit cannot be present before its assessment, even if the
        # role is enabled. Do not demand or fabricate an unsaved SAFETY audit.
        broken = deepcopy(value)
        broken['assessments'] = [item for item in broken['assessments'] if item.kind == 'LOGISTICS']
        with pytest.raises(ContractFailure) as exc:
            Orchestrator(agent,agent.workflow_configuration,None).checkpoint(raw,broken)
        assert exc.value.error.code == 'PERSISTENCE_FAILURE' and not exc.value.error.recoverable
        assert role_counts(requests)['SAFETY'] == 3


def test_daily_midnight_recovery_keeps_original_safety_snapshot_and_audit(tmp_path,monkeypatch):
    day = [date(2026,10,16)]
    monkeypatch.setattr('app.config.sydney_today',lambda:day[0])
    requests,_ = mock_safety_runtime(monkeypatch)
    used = []
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port,'save_model_safety_assessment',after=True)
        return port
    wrap_port(monkeypatch,once)
    with TestClient(application(tmp_path,clock_mode='current',synthetic_evidence_mode='rolling',dataset_selection={},
            snapshot_cache_path=tmp_path/'daily-snapshots')) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        failed = wait_run(client,json_with_internal_audits(client, begun)['run_id'],'FAILED')
        audit = assert_safety_audit(failed)
        old_context = failed['confirmed_context']['dataset_context']
        count = role_counts(requests)
        day[0] += timedelta(days=1)
        current = json_with_internal_audits(client, client.get('/api/v1/runs/'+failed['run']['run_id']))
        assert current['retry_available'] and current['current_inputs_state'] == 'CHANGED'
        assert retry(client,headers,current).status_code == 202
        restored = wait_run(client,failed['run']['run_id'],'SUCCEEDED')
        assert restored['model_assessment_audits']['SAFETY'] == audit
        assert restored['confirmed_context']['dataset_context'] == old_context
        assert restored['confirmed_context']['demo_context']['demo_today'] == '2026-10-16'
        assert role_counts(requests) == count and not restored['finalisation_available']


def test_logical_plan_deletion_preserves_safety_audit_but_denies_reads(tmp_path,monkeypatch):
    requests,_ = mock_safety_runtime(monkeypatch)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        detail = launch(client,headers,'normal')
        audit = assert_safety_audit(detail)
        path,_ = finalise(client,headers,detail)
        plan = '/api/v1/plans/'+detail['plan']['plan_id']
        assert client.delete(plan,headers=headers).status_code == 204
        assert client.get(plan).status_code == client.get(path).status_code == 404
        with client.app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT id FROM model_safety_audits').fetchone()[0] == audit['audit_id']
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':3}
