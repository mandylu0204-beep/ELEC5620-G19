"""A persistence integration with real B tools and offline model transport only."""
import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.auth import User
from app.config import Settings
from app.main import create_app
from app.application.logistics_audit import canonical, identity_seed, integrity, load_audits, server_input
from app.agents.rules import logistics, safety
from app.contracts.dto import ConfirmedContext, SafetyInput
from app.contracts.errors import ContractFailure, ContractError
from app.storage.database import Database
from app.workflow import WorkflowConfiguration
from test_llm_logistics_agent import input_fixture, agent_fixture
from llm_fixtures import model_input
from test_requests import sign_in

call = asyncio.run


@pytest.fixture
def saved(tmp_path,request):
    options=getattr(request,'param',{})
    dataset, original, temp = input_fixture(**{key:value for key,value in options.items() if key!='methods'})
    prototype, _ = agent_fixture(dataset, temp)
    markers = {'a_logistics_mode':'model','a_logistics_audit_required':'1','a_logistics_audit_contract':'1.0',
               'a_logistics_identity_seed':canonical(identity_seed(prototype))}
    base = dataset.context.model_copy(update={'selection_config':markers,
        'rules_version':dataset.context.rules_version+'/a-model-logistics-audit-v1'})
    config = WorkflowConfiguration(dataset, safety_case_ids=['safety-15'], registered_context=base)
    app = create_app(Settings(_env_file=None, database_path=tmp_path/'audit.sqlite3'))
    with TestClient(app) as client:
        user = User('camper-a','camper.a','Camper A','CAMPER')
        wf = app.state.workflows
        # Test-only registered role pipeline; production Hybrid is still B's work.
        wf.context_provider = None
        wf.logistics_facts_provider = lambda scope,input: logistics.assess(dataset,input,expected_mode='agent',safety_case_ids=['safety-15'])
        confirmed = ConfirmedContext(request_id='independent-a24-request',confirmed_at=datetime.now(timezone.utc),
            requirements=original.confirmed_requirements,profile_snapshot=original.profile_snapshot,
            demo_context=original.demo_context,dataset_context=config.context)
        repo = app.state.repository
        repo.record_confirmed_request(user,'Independent offline persistence fixture',confirmed)
        scope = wf.start(user,confirmed.request_id,confirmed.demo_context,config.context,command_key='independent-a24-start')
        attempt = wf.claim(user,scope.run_id,scope.demo_context,scope.dataset_context)
        port = wf.port(user,attempt)
        recommendation = model_input()[1].recommendations
        call(port.save_recommendations(recommendation,scope.write_keys['recommendations']))
        version = call(port.append_plan_version(None,original.saved_itinerary,scope.request_id,
            'Independent saved planning fixture',scope.write_keys['version']))
        call(port.report_stage('ASSESSING_LOGISTICS','RUNNING',None))
        input = server_input(scope,confirmed,version)
        agent,calls = agent_fixture(dataset,config,methods=options.get('methods'))
        outcome = call(agent.assess_with_trace(input))
        yield SimpleNamespace(app=app,client=client,user=user,wf=wf,scope=scope,attempt=attempt,port=port,
            version=version,input=input,outcome=outcome,calls=calls,dataset=dataset,config=config)


def save(f,plan=None,trace=None,result=None,port=None):
    return call((port or f.port).save_model_logistics_assessment(f.version.version_context,
        result or f.outcome.assessment,plan or f.outcome.plan.model_dump(mode='json'),
        trace or f.outcome.trace.model_dump(mode='json'),f.scope.write_keys['logistics']))


def counts(f):
    with f.app.state.database.transaction(write=False) as db:
        return [db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
                ['assessments','gear_checklists','model_logistics_audits']]


def finish(f):
    stored=save(f)
    value=safety.assess(f.dataset,SafetyInput(version_context=f.version.version_context,
        saved_itinerary=f.version.content,confirmed_requirements=f.input.confirmed_requirements,saved_logistics_assessment=stored,
        scenario_context=f.config.scenario_for(f.version.content.selected_campsite_ids),demo_context=f.scope.demo_context),expected_mode='agent')
    call(f.port.report_stage('ASSESSING_SAFETY','RUNNING',None))
    call(f.port.save_assessment(f.version.version_context,'SAFETY',value,f.scope.write_keys['safety']))
    call(f.port.report_stage('ROUTING','RUNNING',None))
    route=call(f.port.route_assessed_version(f.version.version_context,'ELIGIBLE_FOR_FINALISATION','independent offline route',f.scope.write_keys['route']))
    call(f.port.report_stage('COMPLETED','SUCCEEDED',None))
    return stored,route


def test_atomic_success_receipt_and_checkpoint_reuse(saved):
    first=save(saved)
    assert save(saved)==first and len(saved.calls)==3
    audit=call(saved.port.load_checkpoint())['model_assessment_audits']['LOGISTICS']
    assert audit['assessment_id']==first.assessment_id and audit['attempt_id']==saved.attempt.attempt_id
    assert audit['plan']==saved.outcome.plan.model_dump(mode='json')
    assert not {'input_json','rule_facts_json','owner_id'} & audit.keys()
    assert counts(saved)==[1,1,1]
    with saved.app.state.database.transaction(write=False) as db:
        body=db.execute('SELECT payload FROM model_logistics_audits').fetchone()[0]
        assert 'unit-only-school-secret' not in body and 'Authorization' not in body


@pytest.mark.parametrize('table',['assessments','gear_checklists','model_logistics_audits','write_receipts'])
def test_each_insert_failure_rolls_back_all_four_products(saved,table):
    with saved.app.state.database.transaction() as db:
        db.execute(f"CREATE TRIGGER injected BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(ContractFailure): save(saved)
    assert counts(saved)==[0,0,0]
    with saved.app.state.database.transaction(write=False) as db:
        assert db.execute("SELECT COUNT(*) FROM write_receipts WHERE operation='logistics'").fetchone()[0]==0


@pytest.mark.parametrize('field,value',[('turns','3'),('turns',True),('validation_passed','true'),
    ('http_attempts',3.0),('role','PLANNING'),('response_sha256',[]),('usage',{'made_up_tokens':1})])
def test_wrong_trace_types_or_structure_never_save(saved,field,value):
    trace=saved.outcome.trace.model_dump(mode='json')|{field:value}
    with pytest.raises(ContractFailure) as exc: save(saved,trace=trace)
    assert exc.value.error.code=='CONTRACT_INVALID' and counts(saved)==[0,0,0]


@pytest.mark.parametrize('field,value',[('procurement_quantity',0.5),('confirmation_required','false'),
    ('estimated_cost_cents',True),('method','CONFIRMED_RENTAL')])
def test_wrong_action_types_never_save(saved,field,value):
    plan=saved.outcome.plan.model_dump(mode='json')
    plan['gear_actions'][0][field]=value
    with pytest.raises(ContractFailure): save(saved,plan=plan)
    assert counts(saved)==[0,0,0]


def test_changed_trace_with_same_key_conflicts_without_overwrite(saved):
    first=save(saved)
    trace=saved.outcome.trace.model_dump(mode='json')|{'elapsed_ms':saved.outcome.trace.elapsed_ms+1}
    with pytest.raises(ContractFailure) as exc: save(saved,trace=trace)
    assert exc.value.error.code=='IDEMPOTENCY_CONFLICT' and save(saved)==first


@pytest.mark.parametrize('corruption',['missing','hash','gear','receipt','duplicate_json'])
def test_corruption_blocks_checkpoint_receipt_routing_completion_and_http_read(saved,corruption):
    finish(saved)
    with saved.app.state.database.transaction() as db:
        if corruption=='missing':
            db.execute('DROP TRIGGER no_delete_logistics_audit')
            db.execute('DELETE FROM model_logistics_audits')
        elif corruption in {'hash','duplicate_json'}:
            db.execute('DROP TRIGGER immutable_logistics_audit')
            if corruption=='hash': db.execute("UPDATE model_logistics_audits SET payload_sha256=?",('0'*64,))
            else: db.execute("UPDATE model_logistics_audits SET payload=?",('{"plan":{},"plan":{}}',))
        elif corruption=='gear':
            db.execute("UPDATE gear_checklists SET payload='[]'")
        else: db.execute("DELETE FROM write_receipts WHERE operation='logistics'")
    for action in [lambda:save(saved),lambda:call(saved.port.load_checkpoint()),
        lambda:call(saved.port.route_assessed_version(saved.version.version_context,'ELIGIBLE_FOR_FINALISATION','independent offline route',saved.scope.write_keys['route'])),
        lambda:call(saved.port.evaluate_eligibility(saved.version.version_context))]:
        with pytest.raises(ContractFailure) as exc: action()
        assert not exc.value.error.recoverable
    sign_in(saved.client)
    response=saved.client.get('/api/v1/plans/'+saved.scope.plan_id)
    assert response.status_code==503 and response.json()['error']['allowed_actions']==['CONTACT_OPERATOR']


def test_saved_history_uses_archived_facts_without_current_provider_or_credentials(saved):
    finish(saved)
    saved.wf.logistics_facts_provider=lambda *args: pytest.fail('History recomputed current data')
    sign_in(saved.client)
    detail=saved.client.get('/api/v1/plans/'+saved.scope.plan_id)
    assert detail.status_code==200 and detail.json()['model_assessment_audits']['LOGISTICS']['trace']['role']=='LOGISTICS'
    assert len(saved.calls)==3


def test_missing_whole_step_is_valid_checkpoint_but_ordinary_save_cannot_bypass_audit(saved):
    assert call(saved.port.load_checkpoint())['model_assessment_audits']=={}
    with pytest.raises(ContractFailure) as exc:
        call(saved.port.save_assessment(saved.version.version_context,'LOGISTICS',saved.outcome.assessment,saved.scope.write_keys['logistics']))
    assert exc.value.error.code=='CONTRACT_INVALID' and counts(saved)==[0,0,0]


def test_lost_receipt_retries_new_attempt_without_model_and_rejects_old_worker(saved):
    first=save(saved)
    call(saved.port.report_stage('ASSESSING_LOGISTICS','FAILED',ContractError(code='PERSISTENCE_FAILURE',
        message='Independent lost receipt',recoverable=True,allowed_actions=['RETRY'])))
    with saved.app.state.database.transaction(write=False) as db:
        revision=db.execute('SELECT revision FROM runs WHERE id=?',(saved.scope.run_id,)).fetchone()[0]
    saved.wf.retry(saved.user,saved.scope.run_id,saved.scope.demo_context,saved.scope.dataset_context,
        command_key='independent-recovery',expected_run_revision=revision)
    next_attempt=saved.wf.claim(saved.user,saved.scope.run_id,saved.scope.demo_context,saved.scope.dataset_context)
    new_port=saved.wf.port(saved.user,next_attempt)
    checkpoint=call(new_port.load_checkpoint())
    assert checkpoint['assessments']==[first]
    assert checkpoint['model_assessment_audits']['LOGISTICS']['attempt_id']==saved.attempt.attempt_id
    assert save(saved,port=new_port)==first and len(saved.calls)==3
    with pytest.raises(ContractFailure) as exc: save(saved)
    assert exc.value.error.code=='STALE_CONTEXT' and counts(saved)==[1,1,1]


@pytest.mark.parametrize('operation',['REVISE','REASSESS'])
def test_new_operation_saves_new_logistics_audit_with_same_or_new_version(saved,operation):
    finish(saved)
    scope=saved.wf.start(saved.user,saved.scope.request_id,saved.scope.demo_context,saved.scope.dataset_context,
        command_key='independent-'+operation,operation=operation,plan_id=saved.scope.plan_id,
        expected_active_run_id=saved.scope.run_id,
        expected_current_version_id=saved.version.version_context.plan_version_id)
    attempt=saved.wf.claim(saved.user,scope.run_id,scope.demo_context,scope.dataset_context)
    port=saved.wf.port(saved.user,attempt)
    if operation=='REVISE':
        version=call(port.append_plan_version(saved.version.version_context.plan_version_id,saved.version.content,
            scope.request_id,'Independent revision persistence fixture',scope.write_keys['version']))
    else: version=call(port.load_checkpoint())['version']
    confirmed=call(port.load_confirmed_context())
    input=server_input(scope,confirmed,version)
    agent,calls=agent_fixture(saved.dataset,saved.config)
    outcome=call(agent.assess_with_trace(input))
    first=call(port.save_model_logistics_assessment(version.version_context,outcome.assessment,
        outcome.plan.model_dump(mode='json'),outcome.trace.model_dump(mode='json'),scope.write_keys['logistics']))
    audit=call(port.load_checkpoint())['model_assessment_audits']['LOGISTICS']
    assert audit['run_id']==scope.run_id and audit['assessment_id']==first.assessment_id and len(calls)==3
    assert (version.version_context.plan_version_id==saved.version.version_context.plan_version_id)==(operation=='REASSESS')
    with saved.app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM model_logistics_audits').fetchone()[0]==2
        old=load_audits(db,saved.scope,saved.version)['LOGISTICS']
        assert old['run_id']==saved.scope.run_id and old['assessment_id']!=first.assessment_id


def test_final_snapshot_isolated_read_and_corruption_guard(saved):
    from test_finalisation import command
    finish(saved)
    headers=sign_in(saved.client)
    detail=saved.client.get('/api/v1/plans/'+saved.scope.plan_id).json()
    assert detail['finalisation_available']
    response=saved.client.post('/api/v1/plans/'+saved.scope.plan_id+'/finalise',headers=headers,json=command(detail))
    assert response.status_code==200,response.text
    path='/api/v1/plans/'+saved.scope.plan_id+'/finals/'+response.json()['final_id']
    final=saved.client.get(path)
    assert final.status_code==200 and final.json()['final_record']['model_assessment_audits']==detail['model_assessment_audits']
    sign_in(saved.client,'camper.b','CampMate-B-2026!')
    assert saved.client.get(path).status_code==404 and saved.client.get('/api/v1/plans/'+saved.scope.plan_id).status_code==404
    sign_in(saved.client)
    with saved.app.state.database.transaction() as db:
        db.execute('DROP TRIGGER immutable_logistics_audit')
        db.execute("UPDATE model_logistics_audits SET payload_sha256=?",('0'*64,))
    assert saved.client.get(path).status_code==503


def test_dispatcher_preserves_nonrecoverable_integrity_error(saved):
    save(saved)
    call(saved.port.report_stage('ASSESSING_LOGISTICS','FAILED',ContractError(code='AGENT_FAILURE',message='Independent failure',recoverable=True,allowed_actions=['RETRY'])))
    with saved.app.state.database.transaction(write=False) as db:
        revision=db.execute('SELECT revision FROM runs WHERE id=?',(saved.scope.run_id,)).fetchone()[0]
    saved.wf.retry(saved.user,saved.scope.run_id,saved.scope.demo_context,saved.scope.dataset_context,
        command_key='dispatcher-integrity',expected_run_revision=revision)
    class BrokenAuditAgent:
        async def orchestrate(self,*args): integrity()
    saved.app.state.runtime.for_scope=lambda scope: SimpleNamespace(agent=BrokenAuditAgent(),demo=scope.demo_context,dataset=scope.dataset_context)
    call(saved.app.state.dispatcher.execute(saved.user,saved.scope.run_id))
    with saved.app.state.database.transaction(write=False) as db:
        row=db.execute('SELECT status,error FROM runs WHERE id=?',(saved.scope.run_id,)).fetchone()
        error=json.loads(row['error'])
        assert row['status']=='FAILED' and error['recoverable'] is False and error['allowed_actions']==['CONTACT_OPERATOR']


def test_current_factory_fails_explicit_model_mode_without_hybrid_wiring(tmp_path,monkeypatch):
    from app.agents.hybrid_planning_agent import HybridPlanningAgent
    from campus_http_fixtures import mock_campus
    from test_v2_http_demo import CASES,ROOT
    calls,_=mock_campus(monkeypatch)
    monkeypatch.setattr(HybridPlanningAgent, 'logistics_audit_contract', None)
    values=CASES['normal']['settings']|{'execution_mode':'agent','logistics_execution':'model'}
    values['dataset_path']=ROOT/values['dataset_path']
    app=create_app(Settings(_env_file=None,database_path=tmp_path/'not-ready.sqlite3',**values))
    with TestClient(app) as client:
        assert client.get('/api/v1/health/ready').status_code==503
        meta=client.get('/api/v1/meta').json()
        assert not meta['features']['planning'] and meta['planning_stages']['logistics']!='model'
        assert meta['agent_configuration_error'] and calls==[]


def test_non_agent_mode_cannot_advertise_model_logistics(tmp_path):
    app=create_app(Settings(_env_file=None,database_path=tmp_path/'wrong-mode.sqlite3',logistics_execution='model'))
    with TestClient(app) as client:
        assert client.get('/api/v1/health/ready').status_code==503
        assert not client.get('/api/v1/meta').json()['features']['planning']


@pytest.mark.parametrize('saved',[{'missing':('tent',),'methods':{'tent':'PROPOSE_BORROW'}}],indirect=True)
def test_borrowing_stays_unconfirmed_unknown_and_keeps_blocker(saved):
    stored=save(saved)
    action=next(item for item in saved.outcome.plan.gear_actions if item.fact.item_key=='tent')
    assert action.confirmation_required and action.estimated_cost_cents is None
    assert stored.result.total_cents is None and stored.result.outcome=='REVISION'
    assert any(item.code=='ESSENTIAL_GEAR_MISSING' for item in stored.result.mandatory_blockers)
    assert counts(saved)==[1,1,1]


def test_self_consistent_forged_gear_fact_is_rejected_against_server_facts(saved):
    plan=saved.outcome.plan.model_dump(mode='json')
    plan['gear_actions'][0]['fact']['available_quantity']='999'
    result=saved.outcome.assessment.model_dump(mode='json')
    result['gear_checklist'][0]=plan['gear_actions'][0]['fact']
    with pytest.raises(ContractFailure) as exc: save(saved,plan=plan,result=result)
    assert exc.value.error.code=='CONTRACT_INVALID' and counts(saved)==[0,0,0]


def test_utf8_limit_counts_bytes_and_never_truncates(saved):
    from app.application.logistics_audit import payload,LIMIT
    plan=saved.outcome.plan.model_dump(mode='json')
    plan['decision_summary_unverified']='营'*LIMIT
    with pytest.raises(ContractFailure) as exc: save(saved,plan=plan)
    assert exc.value.error.code=='CONTRACT_INVALID' and counts(saved)==[0,0,0]


def test_upgrade_from_six_keeps_old_user_without_backfilling_audits(tmp_path):
    from app.storage import database as module
    db=Database(tmp_path/'six.sqlite3')
    with db.transaction() as connection:
        for number in range(1,7):
            module.execute_migration(connection,getattr(module,'MIGRATION_'+str(number)))
            connection.execute('INSERT INTO schema_migrations VALUES(?,?)',(number,'historical'))
        connection.execute("INSERT INTO users VALUES('old-owner','old.user','Old Camper','CAMPER','old-hash')")
    db.initialize()
    assert db.ready()
    with db.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM model_logistics_audits').fetchone()[0]==0
        assert connection.execute('SELECT username FROM users').fetchone()[0]=='old.user'


def test_factory_seed_has_no_self_reference_and_matches_final_configuration(tmp_path,monkeypatch):
    from app.application.agent_runtime import build_v2_hybrid_binding
    from app.application.datasets import inspect_dataset
    from app.application.logistics_audit import digest,decode
    from campus_http_fixtures import mock_campus
    from test_v2_http_demo import CASES,ROOT
    calls,_=mock_campus(monkeypatch)
    values=CASES['normal']['settings']|{'execution_mode':'agent','logistics_execution':'model'}
    values['dataset_path']=ROOT/values['dataset_path']
    settings=Settings(_env_file=None,database_path=tmp_path/'factory.sqlite3',**values)
    binding=build_v2_hybrid_binding(settings,inspect_dataset(settings))
    seed=decode(binding.context.selection_config['a_logistics_identity_seed'])
    assert 'workflow_context' not in seed and 'configuration_fingerprint' not in seed
    assert 'api_key' not in seed['model_client'] and calls==[]
    assert binding.agent.logistics_agent.identity['configuration_fingerprint']==digest(canonical({
        **seed,'workflow_context':binding.context.model_dump(mode='json')}))
