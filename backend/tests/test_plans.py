from fastapi.testclient import TestClient
import pytest

from app.auth import User
from app.config import Settings
from app.main import create_app
from app.contracts.dto import RecommendCampsitesResult
from app.storage.plan_queries import PlanQueries
from app.storage.database import Database
from app.storage.repository import Repository
from plan_fixtures import create, call
from test_accounts import login


@pytest.fixture
def view_client():
    app=create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        login(client)
        yield client,app,User('camper-a','camper.a','Camper A','CAMPER')


def test_partial_progress_uses_saved_artifacts_and_survives_restart(view_client):
    client,app,user=view_client
    assert client.get('/api/v1/plans').json()=={'plans':[]}
    scope,version=create(app.state.repository,user,'partial')
    result=client.get('/api/v1/plans/'+scope.plan_id).json()
    assert result['run']['status']=='RUNNING'
    assert result['run']['stage']=='ASSESSING_LOGISTICS'
    assert result['version']['version_context']['run_id']==scope.run_id
    assert len(result['assessments'])==1 and result['assessments'][0]['kind']=='LOGISTICS'
    assert result['route'] is None and not result['eligibility']['eligible']
    assert result['events'][-1]['stage']=='ASSESSING_LOGISTICS'
    assert result['planning_available'] is False and result['finalisation_available'] is False
    assert 'write_keys' not in str(result)
    assert 'owner_id' not in str(result)
    row=client.get('/api/v1/plans').json()['plans'][0]
    assert row['plan_id']==scope.plan_id and row['version_number']==1
    restarted=Database(app.state.database.path); restarted.initialize()
    assert PlanQueries(restarted).detail(user,scope.plan_id)==result


@pytest.mark.parametrize('case',['unknown','closed','complete'])
def test_costs_safety_and_route_are_distinct_from_execution_success(view_client,case):
    client,app,user=view_client
    scope,version=create(app.state.repository,user,case,case)
    response=client.get('/api/v1/runs/'+scope.run_id)
    assert response.status_code==200
    result=response.json()
    assert result['run']['status']=='SUCCEEDED'
    assert result['plan']['final_version_id'] is None and result['version']['status']!='FINALISED'
    assert len(result['assessments'])==2
    logistics=next(item['result'] for item in result['assessments'] if item['kind']=='LOGISTICS')
    assert logistics['cost_breakdown'][0]['quantity']=='1.5'
    assert logistics['cost_breakdown'][0]['subtotal_cents']==152
    assert logistics['cost_breakdown'][1]['subtotal_cents']==0
    if case=='unknown':
        assert logistics['total_cents'] is None and logistics['known_subtotal_cents']==152
        assert logistics['budget_difference_cents'] is None
        assert result['version']['status']=='BLOCKED'
    elif case=='closed':
        assert result['version']['status']=='BLOCKED'
        assert any(item['code']=='ROAD_UNAVAILABLE' for item in result['eligibility']['blocking_reasons'])
    else:
        assert result['eligibility']['eligible']


def test_no_match_is_saved_business_outcome_not_fake_failure(view_client):
    client,app,user=view_client
    scope,_=create(app.state.repository,user,'no-match','no-match')
    result=client.get('/api/v1/plans/'+scope.plan_id).json()
    assert result['run']['status']=='SUCCEEDED' and result['run']['error'] is None
    assert result['recommendations']['result']['search_outcome']=='NO_MATCH'
    assert result['version'] is None and result['assessments']==[] and result['eligibility'] is None
    row=next(item for item in client.get('/api/v1/plans').json()['plans'] if item['plan_id']==scope.plan_id)
    assert row['search_outcome']=='NO_MATCH' and row['version_number'] is None
    assert (row['start_date'],row['end_date'])==('2026-10-20','2026-10-22')


def test_list_new_pending_run_does_not_show_previous_versions_result(view_client):
    client,app,user=view_client
    original,version=create(app.state.repository,user,'previous-blocked','closed')
    app.state.repository.begin_run(user,original.request_id,original.demo_context,original.dataset_context,
        plan_id=original.plan_id,operation='REVISE',expected_current_version_id=version.version_context.plan_version_id)
    row=next(item for item in client.get('/api/v1/plans').json()['plans'] if item['plan_id']==original.plan_id)
    assert row['run_status']=='PENDING' and row['version_status'] is None
    assert row['version_number'] is None and row['search_outcome'] is None


def test_technical_failure_preserves_recommendations(view_client):
    client,app,user=view_client
    scope,_=create(app.state.repository,user,'failure','failure')
    result=client.get('/api/v1/plans/'+scope.plan_id).json()
    assert result['run']['status']=='FAILED'
    assert result['run']['error']['code']=='AGENT_FAILURE'
    assert result['recommendations'] is not None and result['version'] is None


def test_reassessment_read_never_mixes_old_and_new_evidence(view_client):
    client,app,user=view_client
    scope,version=create(app.state.repository,user,'history','complete')
    original=client.get('/api/v1/plans/'+scope.plan_id).json()
    changed=scope.dataset_context.model_copy(update={'file_digests':{'display-test-only':'b'*64}})
    newer=app.state.repository.begin_run(user,scope.request_id,scope.demo_context,changed,plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=version.version_context.plan_version_id)
    current=client.get('/api/v1/plans/'+scope.plan_id).json()
    assert current['assessments']==[] and current['recommendations'] is None and current['route'] is None
    assert not current['eligibility']['eligible']
    assert current['version']['version_context']['input_fingerprint']!=original['version']['version_context']['input_fingerprint']
    historical=client.get('/api/v1/plans/'+scope.plan_id,params={'run_id':scope.run_id}).json()
    assert not historical['run']['is_active'] and historical['eligibility'] is None
    assert historical['assessments']==original['assessments']
    assert historical['version']['status']=='ELIGIBLE_FOR_FINALISATION'
    assert client.get('/api/v1/runs/'+scope.run_id).json()==historical
    other,_=create(app.state.repository,user,'other')
    assert client.get('/api/v1/plans/'+scope.plan_id,params={'run_id':other.run_id}).status_code==404
    assert len(current['run_history'])==2 and current['run']['run_id']==newer.run_id


def test_private_plan_and_run_endpoints(view_client):
    client,app,user=view_client
    scope,_=create(app.state.repository,user,'private')
    login(client,'camper.b','CampMate-B-2026!')
    assert client.get('/api/v1/plans').json()=={'plans':[]}
    for path in ('/plans/'+scope.plan_id,'/runs/'+scope.run_id,'/plans/'+scope.plan_id+'/versions'):
        assert client.get('/api/v1'+path).status_code==404
    login(client,'founder','CampMate-Founder-2026!')
    assert client.get('/api/v1/plans/'+scope.plan_id).status_code==403
    assert client.get('/api/v1/runs/'+scope.run_id).status_code==403


def test_no_match_cannot_complete_after_version_exists(view_client):
    client,app,user=view_client
    original,version=create(app.state.repository,user,'invalid-no-match')
    scope=app.state.repository.begin_run(user,original.request_id,original.demo_context,original.dataset_context)
    port=app.state.repository.bind_port(user,scope.run_id)
    call(port.save_recommendations(RecommendCampsitesResult(execution_mode='deterministic_demo',search_outcome='NO_MATCH',candidates=[]),scope.write_keys['recommendations']))
    call(port.append_plan_version(None,version.content,scope.request_id,'Contradictory test input',scope.write_keys['version']))
    # The ordinary route requirement still applies when an itinerary exists.
    from app.contracts.errors import ContractFailure
    with pytest.raises(ContractFailure):
        call(port.report_stage('COMPLETED','SUCCEEDED',None))


@pytest.mark.parametrize(('case','status'),[('overbudget','REVISION_REQUIRED'),('review','ESCALATED'),('missing','BLOCKED'),('stale','BLOCKED'),('conflict','BLOCKED')])
def test_revision_review_and_evidence_quality_survive_read(view_client,case,status):
    client,app,user=view_client
    scope,_=create(app.state.repository,user,case,case)
    detail=client.get('/api/v1/plans/'+scope.plan_id).json()
    assert detail['version']['status']==status
    assert not detail['eligibility']['eligible']
    safety=next(item['result'] for item in detail['assessments'] if item['kind']=='SAFETY')
    if case=='review':
        assert safety['risk_level']=='HIGH' and safety['confidence']=='LOW'
    elif case in {'missing','stale','conflict'}:
        assert safety['data_quality']['WEATHER']=={'missing':'MISSING','stale':'STALE','conflict':'CONFLICTING'}[case]
