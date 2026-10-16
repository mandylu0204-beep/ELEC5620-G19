from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from app.auth import User, AuthService
from app.config import Settings
from app.main import create_app
from app.contracts.dto import LogisticsResult, SafetyResult, ProfileSnapshot
from app.contracts.enums import ExecutionMode
from app.contracts.errors import ContractFailure
from app.storage.database import Database, execute_migration, MIGRATION_1, MIGRATION_2, MIGRATION_3
from app.storage.finalisation import FinaliseInput, FinalisationService
from app.storage.plan_queries import PlanQueries
from app.storage.repository import Repository
from app.storage.reviews import ReviewInput
from plan_fixtures import create, call
from test_accounts import login, CLIENT_HEADER
from test_reviews import command as review_command


@pytest.fixture
def final_client():
    app=create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        session=login(client)
        yield client,app,User('camper-a','camper.a','Camper A','CAMPER'),{**CLIENT_HEADER,'X-CSRF-Token':session['csrf_token']}


def command(detail,key='final-command'):
    return {'command_key':key,'version_context':detail['version']['version_context'],
        'assessment_ids':[item['assessment_id'] for item in detail['assessments']],
        'expected_review_id':detail['eligibility']['valid_review_id'] if detail['eligibility'] else None,
        'expected_version_revision':detail['version']['revision'], 'expected_run_revision':detail['run']['revision'], 'acknowledged':True}


def finish_new_run(app,camper,scope,original):
    port=app.state.repository.bind_port(camper,scope.run_id)
    with app.state.database.transaction(write=False) as connection:
        context=Repository.stored_version(connection,scope).version_context
    call(port.report_stage('ASSESSING_LOGISTICS','RUNNING',None))
    log=next(item['result'] for item in original['assessments'] if item['kind']=='LOGISTICS')
    stored=call(port.save_assessment(context,'LOGISTICS',LogisticsResult.model_validate(log|{'version_context':context.model_dump(mode='json'),'execution_mode':scope.demo_context.mode.value}),scope.write_keys['logistics']))
    call(port.report_stage('ASSESSING_SAFETY','RUNNING',None))
    safe=next(item['result'] for item in original['assessments'] if item['kind']=='SAFETY')
    call(port.save_assessment(context,'SAFETY',SafetyResult.model_validate(safe|{'version_context':context.model_dump(mode='json'),'depends_on_assessment_id':stored.assessment_id,'execution_mode':scope.demo_context.mode.value}),scope.write_keys['safety']))
    call(port.report_stage('ROUTING','RUNNING',None))
    call(port.route_assessed_version(context,'ELIGIBLE_FOR_FINALISATION','independent finalisation test',scope.write_keys['route']))
    call(port.report_stage('COMPLETED','SUCCEEDED',None))


@pytest.mark.parametrize('case',['complete','review'])
def test_final_snapshot_atomic_idempotent_and_restart(final_client,case):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'final-'+case,case)
    path='/api/v1/plans/'+scope.plan_id
    if case=='review':
        founder=User('founder','founder','Founder','FOUNDER')
        detail=app.state.reviews.detail(founder,scope.plan_id)
        app.state.reviews.submit(founder,scope.plan_id,ReviewInput.model_validate(review_command(detail)))
    detail=client.get(path).json();body=command(detail)
    assert detail['finalisation_available'] and detail['last_final'] is None
    response=client.post(path+'/finalise',headers=headers,json=body)
    assert response.status_code==200,response.text
    saved=response.json()
    assert saved['status']=='FINALISED' and saved['version_context']==body['version_context']
    assert client.post(path+'/finalise',headers=headers,json=body).json()==saved
    conflict=client.post(path+'/finalise',headers=headers,json=body|{'expected_version_revision':body['expected_version_revision']+1})
    assert conflict.status_code==409 and conflict.json()['error']['code']=='IDEMPOTENCY_CONFLICT'
    finalpath=path+'/finals/'+saved['final_id']
    record=client.get(finalpath).json()
    assert record['is_current'] and record['final_record']['content']==detail['version']['content']
    assert record['final_record']['assessments']==detail['assessments']
    assert record['final_record']['confirmed_context']==detail['confirmed_context']
    assert record['final_record']['eligibility_at_finalisation']['eligible']
    assert (record['final_record']['review'] is not None)==(case=='review')
    assert 'write_keys' not in str(record)
    updated=client.get(path).json()
    assert updated['version']['status']=='FINALISED' and updated['eligibility'] is None
    assert not updated['finalisation_available'] and updated['last_final']['is_current']
    assert len(updated['final_history'])==1
    assert client.get('/api/v1/plans').json()['plans'][0]['last_final']['final_id']==saved['final_id']
    duplicate=command(updated,'different-command')
    assert client.post(path+'/finalise',headers=headers,json=duplicate).status_code==409
    restarted=Database(app.state.database.path);restarted.initialize()
    assert FinalisationService(restarted).detail(camper,scope.plan_id,saved['final_id'])==record
    assert PlanQueries(restarted).detail(camper,scope.plan_id)==updated
    app.state.repository.save_profile(camper,ProfileSnapshot(group_size=5),0)
    assert client.get(finalpath).json()==record
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM final_records').fetchone()[0]==1


@pytest.mark.parametrize('case',['closed','missing','stale','conflict','unknown','overbudget','review'])
def test_required_problems_never_finalise(final_client,case):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'blocked-'+case,case)
    path='/api/v1/plans/'+scope.plan_id
    original=client.get(path).json()
    assert not original['finalisation_available']
    response=client.post(path+'/finalise',headers=headers,json=command(original))
    assert response.status_code==409 and response.json()['error']['code']=='FINALISATION_BLOCKED'
    assert client.get(path).json()==original
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM final_records').fetchone()[0]==0


@pytest.mark.parametrize('state',['DRAFT','ASSESSING','REJECTED','BLOCKED','REVISION_REQUIRED'])
def test_finalisation_requires_explicit_eligible_status(final_client,state):
    client,app,camper,headers=final_client
    scope,version=create(app.state.repository,camper,'state-'+state,'complete')
    with app.state.database.transaction() as connection:
        connection.execute('UPDATE versions SET status=? WHERE id=?',(state,version.version_context.plan_version_id))
    path='/api/v1/plans/'+scope.plan_id
    assert client.post(path+'/finalise',headers=headers,json=command(client.get(path).json())).status_code==409


def test_confirmation_roles_csrf_and_exact_context(final_client):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'permissions','complete')
    path='/api/v1/plans/'+scope.plan_id
    detail=client.get(path).json();body=command(detail)
    assert client.post(path+'/finalise',headers=CLIENT_HEADER,json=body).status_code==403
    for change in ({'acknowledged':False},{'acknowledged':1},{'owner_id':'camper-b'},{'expected_version_revision':True}):
        assert client.post(path+'/finalise',headers=headers,json=body|change).status_code==422
    for change in ({'expected_review_id':'fake'},{'assessment_ids':['fake','fake']},{'expected_run_revision':999},{'expected_version_revision':999},{'version_context':body['version_context']|{'input_fingerprint':'f'*64}}):
        assert client.post(path+'/finalise',headers=headers,json=body|change).status_code==409
    for status in ('FAILED','PENDING'):
        with app.state.database.transaction() as connection:
            connection.execute('UPDATE runs SET status=? WHERE id=?',(status,scope.run_id))
        assert client.post(path+'/finalise',headers=headers,json=body).status_code==409
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE runs SET status='SUCCEEDED' WHERE id=?",(scope.run_id,))
    result=client.post(path+'/finalise',headers=headers,json=body).json()
    finalpath=path+'/finals/'+result['final_id']
    for username,password,status in [('camper.b','CampMate-B-2026!',404),('founder','CampMate-Founder-2026!',403)]:
        session=login(client,username,password)
        assert client.get(finalpath).status_code==status
        assert client.post(path+'/finalise',headers={**CLIENT_HEADER,'X-CSRF-Token':session['csrf_token']},json=body).status_code==status
    login(client)
    other,_=create(app.state.repository,camper,'other-final','complete')
    assert client.get('/api/v1/plans/'+other.plan_id+'/finals/'+result['final_id']).status_code==404
    client.cookies.clear()
    assert client.get(finalpath).status_code==401


@pytest.mark.parametrize('operation',['REASSESS','REVISE'])
def test_new_run_or_version_preserves_old_final_as_history(final_client,operation):
    client,app,camper,headers=final_client
    scope,version=create(app.state.repository,camper,'history-'+operation,'complete')
    path='/api/v1/plans/'+scope.plan_id
    original=client.get(path).json();body=command(original)
    first=client.post(path+'/finalise',headers=headers,json=body).json()
    finalpath=path+'/finals/'+first['final_id'];snapshot=client.get(finalpath).json()['final_record']
    changed=scope.dataset_context.model_copy(update={'file_digests':{'display-test-only':'b'*64}})
    newer=app.state.repository.begin_run(camper,scope.request_id,scope.demo_context,changed,plan_id=scope.plan_id,operation=operation,expected_current_version_id=version.version_context.plan_version_id)
    if operation=='REVISE':
        port=app.state.repository.bind_port(camper,newer.run_id)
        call(port.append_plan_version(version.version_context.plan_version_id,version.content.model_copy(update={'revision_reason':'Independent revised version'}),scope.request_id,'test',newer.write_keys['version']))
    current=client.get(path).json()
    assert current['last_final']['is_current'] is False and not current['finalisation_available']
    assert current['assessments']==[] and current['reviews']==[]
    assert client.post(path+'/finalise',headers=headers,json=body).status_code==409
    historical=client.get(path,params={'run_id':scope.run_id}).json()
    assert historical['version']['status']=='FINALISED' and historical['eligibility'] is None
    assert not historical['finalisation_available']
    assert client.get(finalpath).json()['final_record']==snapshot
    assert client.get(finalpath).json()['is_current'] is False
    finish_new_run(app,camper,newer,original)
    updated=client.get(path).json()
    second=client.post(path+'/finalise',headers=headers,json=command(updated,'new-final')).json()
    assert second['final_id']!=first['final_id']
    latest=client.get(path).json()
    assert len(latest['final_history'])==2 and latest['last_final']['is_current']
    assert latest['last_final']['run_id']==newer.run_id
    assert client.get(finalpath).json()['final_record']==snapshot


def test_missing_output_and_stub_cannot_finalise(final_client):
    client,app,camper,headers=final_client
    for case in ('partial','no-match','failure'):
        scope,_=create(app.state.repository,camper,'incomplete-'+case,case)
        path='/api/v1/plans/'+scope.plan_id
        detail=client.get(path).json()
        body={'command_key':case,'version_context':{'plan_id':scope.plan_id,'plan_version_id':detail['version']['version_context']['plan_version_id'] if detail['version'] else 'fake','run_id':scope.run_id,'input_fingerprint':detail['version']['version_context']['input_fingerprint'] if detail['version'] else 'a'*64},'assessment_ids':['fake','fake2'],'expected_review_id':None,'expected_version_revision':0,'expected_run_revision':detail['run']['revision'],'acknowledged':True}
        assert client.post(path+'/finalise',headers=headers,json=body).status_code==409
    scope,version=create(app.state.repository,camper,'stub-base','complete')
    original=client.get('/api/v1/plans/'+scope.plan_id).json()
    demo=scope.demo_context.model_copy(update={'mode':ExecutionMode.STUB})
    newer=app.state.repository.begin_run(camper,scope.request_id,demo,scope.dataset_context,plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=version.version_context.plan_version_id)
    finish_new_run(app,camper,newer,original)
    path='/api/v1/plans/'+scope.plan_id
    assert client.post(path+'/finalise',headers=headers,json=command(client.get(path).json())).status_code==409


def test_new_evidence_cannot_reuse_old_founder_approval(final_client):
    client,app,camper,headers=final_client
    scope,version=create(app.state.repository,camper,'approval-history','review')
    path='/api/v1/plans/'+scope.plan_id
    founder=User('founder','founder','Founder','FOUNDER')
    reviewed=app.state.reviews.submit(founder,scope.plan_id,ReviewInput.model_validate(review_command(app.state.reviews.detail(founder,scope.plan_id))))
    original=client.get(path).json()
    changed=scope.dataset_context.model_copy(update={'file_digests':{'display-test-only':'c'*64}})
    newer=app.state.repository.begin_run(camper,scope.request_id,scope.demo_context,changed,plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=version.version_context.plan_version_id)
    finish_new_run(app,camper,newer,original)
    current=client.get(path).json();body=command(current)
    assert current['reviews']==[] and current['eligibility']['valid_review_id'] is None
    assert client.post(path+'/finalise',headers=headers,json=body|{'expected_review_id':reviewed['review']['review_id']}).json()['error']['code']=='STALE_CONTEXT'
    assert client.post(path+'/finalise',headers=headers,json=body).json()['error']['code']=='FINALISATION_BLOCKED'


def test_transaction_rolls_back_all_finalisation_writes(final_client):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'save-failure','complete')
    path='/api/v1/plans/'+scope.plan_id;before=client.get(path).json();body=command(before)
    with app.state.database.transaction() as connection:
        connection.execute("CREATE TRIGGER fail_final_receipt BEFORE INSERT ON final_commands BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    failed=client.post(path+'/finalise',headers=headers,json=body)
    assert failed.status_code==503 and failed.json()['error']['code']=='PERSISTENCE_FAILURE'
    assert client.get(path).json()==before
    with app.state.database.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM final_records').fetchone()[0]==0
        connection.execute('DROP TRIGGER fail_final_receipt')
    assert client.post(path+'/finalise',headers=headers,json=body).status_code==200
    with pytest.raises(ContractFailure):
        with app.state.database.transaction() as connection:
            connection.execute("UPDATE final_records SET payload='{}'")
    with pytest.raises(ContractFailure):
        with app.state.database.transaction() as connection:
            connection.execute('DELETE FROM final_records')


def test_concurrent_duplicate_and_competing_finalisation(final_client):
    client,app,camper,_=final_client
    scope,_=create(app.state.repository,camper,'concurrent','complete')
    body=FinaliseInput.model_validate(command(client.get('/api/v1/plans/'+scope.plan_id).json()))
    def submit(value):
        try:return app.state.finalisation.submit(camper,scope.plan_id,value)
        except ContractFailure as failure:return failure.error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,[body,body]))
    assert results[0]==results[1] and isinstance(results[0],dict)
    scope,_=create(app.state.repository,camper,'competing','complete')
    body=FinaliseInput.model_validate(command(client.get('/api/v1/plans/'+scope.plan_id).json(),'competing-a'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,[body,body.model_copy(update={'command_key':'competing-b'})]))
    assert sum(isinstance(item,dict) for item in results)==1
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM final_records WHERE plan_id=?',(scope.plan_id,)).fetchone()[0]==1


def test_upgrade_from_review_schema_keeps_existing_data(tmp_path):
    source=Database(tmp_path/'fixture.sqlite3');source.initialize()
    AuthService(source,8).seed_demo_accounts()
    camper=User('camper-a','camper.a','Camper A','CAMPER')
    create(Repository(source),camper,'legacy','review')
    db=Database(tmp_path/'upgrade3.sqlite3')
    with db.transaction() as connection:
        for number,script in enumerate((MIGRATION_1,MIGRATION_2,MIGRATION_3),1):
            execute_migration(connection,script)
            connection.execute('INSERT INTO schema_migrations VALUES(?,?)',(number,'test'))
    # Populate the old schema as stored rows, without invoking current ports
    # against a database which has not yet gained the required lease table.
    with source.transaction(write=False) as fixture, db.transaction() as connection:
        connection.execute('PRAGMA defer_foreign_keys=ON')
        for table in ('users','requests','plans','runs','versions','run_versions','recommendations','assessments','gear_checklists','run_events','write_receipts'):
            columns = [row['name'] for row in connection.execute('PRAGMA table_info('+table+')')]
            rows=[tuple(row) for row in fixture.execute('SELECT '+','.join(columns)+' FROM '+table)]
            if rows:
                connection.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows)
    with db.transaction(write=False) as connection:
        before=[tuple(row) for row in connection.execute('SELECT * FROM assessments')]
    db.initialize();db.initialize()
    assert db.ready()
    with db.transaction(write=False) as connection:
        assert [tuple(row) for row in connection.execute('SELECT * FROM assessments')]==before
        assert connection.execute('SELECT status FROM versions').fetchone()[0]=='ESCALATED'
        assert connection.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==9


def test_fingerprint_is_recalculated_from_registered_input(final_client):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'fingerprint-corruption','complete')
    # Fault injection in an isolated test DB; normal writes cannot alter bindings.
    with app.state.database.transaction() as connection:
        connection.execute('DROP TRIGGER immutable_run_binding')
        connection.execute('UPDATE run_versions SET fingerprint=? WHERE run_id=?',('b'*64,scope.run_id))
    path='/api/v1/plans/'+scope.plan_id
    response=client.post(path+'/finalise',headers=headers,json=command(client.get(path).json()))
    assert response.status_code==409 and response.json()['error']['code']=='STALE_CONTEXT'
