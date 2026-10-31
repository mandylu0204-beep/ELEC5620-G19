"""Guidance is an owner-scoped comparison, never an eligible candidate or plan."""
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.application.near_matches import guidance
from app.agents.rules.planning import recommend
from app.contracts.dto import ConfirmedContext, RecommendCampsitesInput
from rule_fixtures import make_agent, requirements, full_profile, DEMO
from test_requests import sign_in
from test_extended_demo import confirm_saved
from test_planning_entry import start,wait_run
from test_v2_http_demo import application, INPUTS, CASES

def comparison(camps,req=None,profile=None):
    dataset=make_agent().dataset
    req,profile=req or requirements(budget_cents=100),profile or full_profile()
    fake=SimpleNamespace(campsites=camps,v2_policy=None,has_v2_policy=False)
    result=recommend(fake,RecommendCampsitesInput(confirmed_requirements=req,profile_snapshot=profile,demo_context=DEMO))
    confirmed=ConfirmedContext(request_id='near-unit-request',confirmed_at=datetime.now(timezone.utc),requirements=req,
        profile_snapshot=profile,demo_context=DEMO,dataset_context=dataset.context)
    data={'recommendations':{'result':result.model_dump(mode='json')},'confirmed_context':confirmed.model_dump(mode='json')}
    return data,guidance(data,fake)

def base_camp(**updates):
    return make_agent().dataset.campsites[0].model_copy(update={'region':'CampMate Demo Region','supported_seasons':['all'],
        'vehicle_access':True,'max_group_size':8,'nightly_fee_cents':3000,**updates})

def test_closest_budget_gap_is_ranked_before_soft_preference_and_never_enters_candidates():
    camps=[base_camp(campsite_id='far',nightly_fee_cents=5000,quiet_environment=True),
        base_camp(campsite_id='closest',nightly_fee_cents=2000,quiet_environment=False),
        base_camp(campsite_id='two-issues',nightly_fee_cents=1000,max_group_size=1)]
    data,value=comparison(camps,requirements(budget_cents=100,preferences=['quiet']))
    assert data['recommendations']['result']['search_outcome']=='NO_MATCH' and data['recommendations']['result']['candidates']==[]
    assert [item['campsite_id'] for item in value['near_matches']]==['closest','far','two-issues']
    first=value['near_matches'][0]
    assert first['campsite_subtotal_cents']==4000 and first['budget_excess_cents']==3900
    assert first['issues'][0]['expected']=='Total group budget AUD 1.00'
    assert 'AUD 39.00' in first['issues'][0]['detail'] and 'are additional' in first['issues'][0]['detail']

def test_cap_limit_is_three_and_ties_are_stable_not_dataset_order():
    camps=[base_camp(campsite_id=key) for key in ['d','c','b','a']]
    _,value=comparison(camps)
    assert value['excluded_count']==4 and [i['campsite_id'] for i in value['near_matches']]==['a','b','c']

def test_known_missing_and_unknown_feature_remain_distinct_and_price_unknown_is_not_zero():
    req=requirements(budget_cents=50000,mandatory_constraints=['showers'])
    _,value=comparison([base_camp(campsite_id='absent',showers=False),base_camp(campsite_id='unknown',showers=None,nightly_fee_cents=None)],req)
    absent,unknown=value['near_matches']
    assert absent['issues'][0]['status']=='MISMATCH' and absent['issues'][0]['actual']=='Explicitly not provided'
    assert unknown['issues'][0]['status']=='UNVERIFIED' and unknown['campsite_subtotal_cents'] is None
    assert unknown['budget_excess_cents'] is None

def test_group_and_season_gaps_are_specific_without_advising_fictitious_profile_changes():
    req=requirements(budget_cents=50000)
    _,value=comparison([base_camp(max_group_size=1,supported_seasons=['winter'])],req)
    issues={i['field']:i for i in value['near_matches'][0]['issues']}
    assert issues['profile.group_size']['expected']=='2 people' and 'Capacity shortfall:  1 people' in issues['profile.group_size']['detail']
    assert 'actual group size changes' in issues['profile.group_size']['suggestion']
    assert 'Winter' in issues['start_date']['actual']

def test_stale_metadata_uses_saved_exclusions_and_does_not_replace_old_price_or_reasons():
    data,_=comparison([base_camp()])
    value=guidance(data,None,metadata_note='changed')
    assert value['near_matches'][0]['campsite_subtotal_cents'] is None and value['metadata_note']=='changed'
    changed=SimpleNamespace(campsites=[base_camp(nightly_fee_cents=0)],v2_policy=None,has_v2_policy=False)
    value=guidance(data,changed)
    assert value['near_matches'][0]['nightly_fee_cents'] is None
    assert value['near_matches'][0]['issues'][0]['original_reason']=='Campsite fee alone exceeds the confirmed group budget.'

def test_matches_do_not_offer_ineligible_alternatives():
    data,value=comparison([base_camp()],requirements(budget_cents=50000))
    assert value is None and data['recommendations']['result']['search_outcome']=='MATCHES'

def test_explicit_false_accessibility_is_not_presented_as_merely_unknown():
    profile=full_profile().model_copy(update={'accessibility_requirements':['step-free path']})
    _,value=comparison([base_camp(step_free_path=False,wheelchair_accessible=True,facilities=['accessible path'])],requirements(budget_cents=50000),profile)
    issue=value['near_matches'][0]['issues'][0]
    assert issue['status']=='MISMATCH' and issue['actual']=='Explicitly not provided'
    assert 'Keep actual accessibility needs' in issue['suggestion']

def launch_no_match(client):
    headers=sign_in(client)
    assert client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':INPUTS['profile']}).status_code==200
    draft=client.post('/api/v1/requests',headers=headers,json=CASES['no_match']['request']).json()
    confirmed=confirm_saved(client,headers,draft,'a18-confirm-123456')
    started=start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
    assert started.status_code==202
    return headers,wait_run(client,started.json()['run_id'],'SUCCEEDED')

def test_http_no_match_old_snapshot_permissions_no_write_and_adjustable_copy(tmp_path):
    with TestClient(application('no_match',tmp_path)) as client:
        headers,detail=launch_no_match(client)
        value=detail['recommendation_guidance']
        assert len(value['near_matches'])==3 and value['near_matches'][0]['name']=='Demo Moonlit Field'
        assert detail['version'] is None and detail['assessments']==[] and not detail['finalisation_available']
        # A new Profile must not rewrite the confirmed inputs behind suggestions.
        assert client.put('/api/v1/profile',headers=headers,json={'expected_revision':1,'profile':INPUTS['profile']|{'group_size':9}}).status_code==200
        reread=client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()
        assert reread['recommendation_guidance']==value
        original=client.get('/api/v1/requests/'+detail['plan']['request_id']).json()
        assert original['status']=='CONFIRMED' and original['explicit_fields']['budget_cents']==100
        with client.app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==1
            for table in ('versions','assessments','final_records'):
                assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
        sign_in(client,'camper.b','CampMate-B-2026!')
        assert client.get('/api/v1/plans/'+detail['plan']['plan_id']).status_code==404

def test_model_no_match_comparison_does_not_call_model_and_handles_context_change(tmp_path,monkeypatch):
    from campus_http_fixtures import mock_campus,application as model_application
    from request_semantics_fixtures import role_requests
    calls,_=mock_campus(monkeypatch)
    with TestClient(model_application(tmp_path,'no_match')) as client:
        _,detail=launch_no_match(client)
        assert len(detail['recommendation_guidance']['near_matches'])==3
        assert len(role_requests(calls,'INTERPRETATION'))==1 and not role_requests(calls,'PLANNING')
        client.app.state.settings.demo_today=DEMO.demo_today
        current=client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()
        assert current['current_inputs_error'] and current['recommendation_guidance']['metadata_note']
        assert all(i['nightly_fee_cents'] is None for i in current['recommendation_guidance']['near_matches'])
        assert len(role_requests(calls,'INTERPRETATION'))==1 and not role_requests(calls,'PLANNING')
        assert current['version'] is None
