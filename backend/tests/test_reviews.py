from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from app.auth import User
from app.config import Settings
from app.main import create_app
from app.storage.database import Database
from app.storage.reviews import ReviewInput, ReviewService
from app.contracts.errors import ContractFailure
from app.contracts.enums import ReviewDecision
from plan_fixtures import create, call
from test_accounts import login, CLIENT_HEADER


@pytest.fixture
def review_client():
    app=create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        camper=User('camper-a','camper.a','Camper A','CAMPER')
        session=login(client,'founder','CampMate-Founder-2026!')
        yield client,app,camper,{**CLIENT_HEADER,'X-CSRF-Token':session['csrf_token']}


def command(detail,decision='APPROVE',key='review-command'):
    return {'command_key':key,'version_context':detail['version']['version_context'],
        'assessment_ids':[item['assessment_id'] for item in detail['assessments']],
        'expected_version_revision':detail['version']['revision'],
        'expected_run_revision':detail['run']['revision'],'decision':decision,'reason':'独立测试：核对当前证据及风险。'}


@pytest.mark.parametrize(('decision','status','eligible'),[('APPROVE','ELIGIBLE_FOR_FINALISATION',True),('REJECT','REJECTED',False),('REQUEST_REVISION','REVISION_REQUIRED',False)])
def test_decision_is_persisted_once_with_exact_evidence(review_client,decision,status,eligible):
    client,app,camper,headers=review_client
    scope,_=create(app.state.repository,camper,decision,'review')
    path='/api/v1/review/'+scope.plan_id
    detail=client.get(path).json()
    assert detail['review_available'] and len(detail['assessments'])==2
    assert len(client.get('/api/v1/review-queue').json()['reviews'])==1
    body=command(detail,decision)
    first=client.post(path,headers=headers,json=body)
    assert first.status_code==200,first.text
    result=first.json()
    assert result['status']==status and result['eligibility']['eligible']==eligible
    assert result['review']['reviewer_user_id']=='founder'
    assert result['review']['version_context']==body['version_context']
    assert sorted(result['review']['assessment_ids'])==sorted(body['assessment_ids'])
    assert result['finalisation_available'] is False and result['revision_execution_available'] is False
    assert client.post(path,headers=headers,json=body).json()==result
    assert client.post(path,headers=headers,json={**body,'reason':'不同理由'}).status_code==409
    assert client.post(path,headers=headers,json={**body,'command_key':'different'}).status_code==409
    updated=client.get(path).json()
    assert not updated['review_available'] and len(updated['reviews'])==1
    assert updated['version']['status']==status and updated['plan']['final_version_id'] is None
    assert client.get('/api/v1/review-queue').json()=={'reviews':[]}
    restarted=Database(app.state.database.path);restarted.initialize()
    founder=User('founder','founder','Founder','FOUNDER')
    from app.application.presentation import plan_response
    assert plan_response(ReviewService(restarted).detail(founder,scope.plan_id),founder)==updated
    login(client)
    own=client.get('/api/v1/plans/'+scope.plan_id).json()
    assert own['reviews']==updated['reviews'] and own['eligibility']['eligible']==eligible


@pytest.mark.parametrize('case',['closed','missing','stale','conflict','unknown','overbudget'])
def test_approval_never_overrides_blocker_or_required_revision(review_client,case):
    client,app,camper,headers=review_client
    scope,_=create(app.state.repository,camper,case,case)
    path='/api/v1/review/'+scope.plan_id
    detail=client.get(path).json()
    assert not detail['review_available'] and detail['review_scope']=='CORRECTION'
    assert client.get('/api/v1/review-queue').json()=={'reviews':[]}
    assert client.get('/api/v1/assistance-queue').json()['plans'][0]['plan_id']==scope.plan_id
    blocked=client.post(path,headers=headers,json=command(detail))
    assert blocked.status_code==409
    unchanged=client.get(path).json()
    assert unchanged==detail and not unchanged['eligibility']['eligible']
    revised=client.post(path,headers=headers,json=command(detail,'REQUEST_REVISION','revision'))
    assert revised.status_code==409
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==0


def test_roles_csrf_input_validation_and_incomplete_run(review_client):
    client,app,camper,headers=review_client
    scope,_=create(app.state.repository,camper,'roles','review')
    path='/api/v1/review/'+scope.plan_id
    body=command(client.get(path).json())
    assert client.post(path,headers=CLIENT_HEADER,json=body).status_code==403
    for change in ({'reason':'   '},{'reviewer_user_id':'camper-a'},{'expected_run_revision':True}):
        assert client.post(path,headers=headers,json=body|change).status_code==422
    for change in ({'assessment_ids':['wrong','wrong']},{'expected_version_revision':999},{'expected_run_revision':999},{'version_context':body['version_context']|{'input_fingerprint':'f'*64}}):
        assert client.post(path,headers=headers,json=body|change).status_code==409
    partial,_=create(app.state.repository,camper,'partial-review')
    assert client.get('/api/v1/review/'+partial.plan_id).status_code==409
    normal,_=create(app.state.repository,camper,'normal-no-review','complete')
    assert client.get('/api/v1/review/'+normal.plan_id).status_code==403
    assert client.get('/api/v1/review/missing').status_code==404
    for username,password in [('camper.a','CampMate-A-2026!'),('camper.b','CampMate-B-2026!')]:
        session=login(client,username,password)
        assert client.get(path).status_code==403
        assert client.get('/api/v1/review-queue').status_code==403
        assert client.post(path,headers={**CLIENT_HEADER,'X-CSRF-Token':session['csrf_token']},json=body).status_code==403
    client.cookies.clear()
    assert client.get(path).status_code==401


def test_new_evidence_rejects_old_approval_and_replay(review_client):
    client,app,camper,headers=review_client
    scope,version=create(app.state.repository,camper,'stale-approval','review')
    path='/api/v1/review/'+scope.plan_id
    old=command(client.get(path).json())
    assert client.post(path,headers=headers,json=old).status_code==200
    changed=scope.dataset_context.model_copy(update={'file_digests':{'display-test-only':'b'*64}})
    newer=app.state.repository.begin_run(camper,scope.request_id,scope.demo_context,changed,plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=version.version_context.plan_version_id)
    assert newer.run_id!=scope.run_id
    assert client.post(path,headers=headers,json=old).status_code==409
    port=app.state.repository.bind_port(camper,newer.run_id)
    stored=app.state.repository.stored_version
    with app.state.database.transaction(write=False) as connection:
        context=stored(connection,newer).version_context
    assert call(port.load_review_result(context,old['assessment_ids'])) is None
    assert not call(port.evaluate_eligibility(context)).eligible


def test_save_failure_rolls_back_review_and_status(review_client):
    client,app,camper,headers=review_client
    scope,_=create(app.state.repository,camper,'rollback','review')
    path='/api/v1/review/'+scope.plan_id
    detail=client.get(path).json();body=command(detail)
    with app.state.database.transaction() as connection:
        connection.execute("CREATE TRIGGER fail_review_receipt BEFORE INSERT ON review_commands BEGIN SELECT RAISE(ABORT, 'injected save fault'); END")
    assert client.post(path,headers=headers,json=body).json()['error']['code']=='PERSISTENCE_FAILURE'
    assert client.get(path).json()==detail
    with app.state.database.transaction() as connection:
        connection.execute('DROP TRIGGER fail_review_receipt')
    assert client.post(path,headers=headers,json=body).status_code==200


def test_new_version_rejects_old_review_page(review_client):
    client,app,camper,headers=review_client
    scope,version=create(app.state.repository,camper,'new-version','review')
    path='/api/v1/review/'+scope.plan_id
    old=command(client.get(path).json())
    newer=app.state.repository.begin_run(camper,scope.request_id,scope.demo_context,scope.dataset_context,
        plan_id=scope.plan_id,operation='REVISE',expected_current_version_id=version.version_context.plan_version_id)
    port=app.state.repository.bind_port(camper,newer.run_id)
    content=version.content.model_copy(update={'revision_reason':'独立测试：新版本'})
    saved=call(port.append_plan_version(version.version_context.plan_version_id,content,scope.request_id,'test',newer.write_keys['version']))
    assert saved.version_number==2
    assert client.post(path,headers=headers,json=old).status_code==409
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==0


def test_concurrent_duplicate_and_competing_review(review_client):
    client,app,camper,_=review_client
    scope,_=create(app.state.repository,camper,'concurrent','review')
    body=ReviewInput.model_validate(command(client.get('/api/v1/review/'+scope.plan_id).json()))
    founder=User('founder','founder','Founder','FOUNDER')
    def submit(value):
        try:return app.state.reviews.submit(founder,scope.plan_id,value)
        except ContractFailure as failure:return failure.error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,[body,body]))
    assert results[0]==results[1] and isinstance(results[0],dict)
    scope,_=create(app.state.repository,camper,'competing','review')
    body=ReviewInput.model_validate(command(client.get('/api/v1/review/'+scope.plan_id).json(),key='competing-a'))
    other=body.model_copy(update={'command_key':'competing-b','decision':ReviewDecision.REJECT})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,[body,other]))
    assert sum(isinstance(item,dict) for item in results)==1
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM reviews WHERE run_id=?',(scope.run_id,)).fetchone()[0]==1
