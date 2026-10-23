"""Queue projections use the active run, preserve unknowns, and stay Founder-only."""
import pytest

from app.contracts.dto import LogisticsResult, SafetyResult
from app.contracts.errors import ContractFailure
from plan_fixtures import create, call
from test_reviews import review_client


@pytest.mark.parametrize('case', ['review', 'unknown', 'overbudget', 'closed'])
def test_queue_projects_saved_review_facts_without_profile_or_scope(review_client, case):
    client, app, camper, _ = review_client
    scope, _ = create(app.state.repository, camper, 'summary-' + case, case)
    if case=='review':
        item = client.get('/api/v1/review-queue').json()['reviews'][0]
        assert client.get('/api/v1/assistance-queue').json()['plans']==[]
    else:
        assert client.get('/api/v1/review-queue').json()['reviews']==[]
        item = client.get('/api/v1/assistance-queue').json()['plans'][0]
    detail = client.get('/api/v1/review/' + scope.plan_id).json()
    summary = item['summary']
    logistics = next(a['result'] for a in detail['assessments'] if a['kind'] == 'LOGISTICS')
    safety = next(a['result'] for a in detail['assessments'] if a['kind'] == 'SAFETY')
    assert item['owner_display_name'] == detail['owner_display_name'] == 'Camper A'
    assert summary['campsite_ids'] == ['display-camp']
    assert (summary['start_date'], summary['end_date']) == ('2026-10-20', '2026-10-22')
    assert summary['total_cents'] == logistics['total_cents']
    assert summary['budget_difference_cents'] == logistics['budget_difference_cents']
    assert summary['risk_level'] == safety['risk_level']
    assert summary['data_quality'] == safety['data_quality']
    # Routing is saved before COMPLETED. The queue must not repeat its former
    # RUN_NOT_SUCCEEDED hint; mutable version state has its own card badge.
    assert {b['code'] for b in summary['blocking_reasons']} == {b['code'] for b in detail['eligibility']['blocking_reasons'] if b['code'] != 'VERSION_STATE'}
    assert 'RUN_NOT_SUCCEEDED' not in {b['code'] for b in summary['blocking_reasons']}
    assert not {'content', 'confirmed_context', 'profile_snapshot', 'scope'} & item.keys()
    if case == 'unknown':
        assert summary['total_cents'] is None and summary['budget_difference_cents'] is None
    if case == 'closed':
        assert {'ROAD_CLOSED', 'ROAD_UNAVAILABLE'} & {b['code'] for b in summary['blocking_reasons']}
    with pytest.raises(ContractFailure):
        app.state.reviews.queue(camper)


def test_reassessment_queue_does_not_mix_original_high_risk_or_known_cost(review_client):
    client, app, camper, _ = review_client
    scope, version = create(app.state.repository, camper, 'original-high-risk', 'review')
    original = client.get('/api/v1/review/' + scope.plan_id).json()
    newer = app.state.repository.begin_run(camper, scope.request_id, scope.demo_context, scope.dataset_context,
        plan_id=scope.plan_id, operation='REASSESS', expected_current_version_id=version.version_context.plan_version_id)
    port = app.state.repository.bind_port(camper, newer.run_id)
    with app.state.database.transaction(write=False) as connection:
        context = app.state.repository.stored_version(connection, newer).version_context
    old_logistics = next(a['result'] for a in original['assessments'] if a['kind'] == 'LOGISTICS')
    logistics = LogisticsResult.model_validate(old_logistics | {
        'version_context': context.model_dump(mode='json'), 'total_cents': None,
        'budget_difference_cents': None, 'outcome': 'REVISION',
        'cost_breakdown': [line | {'unit_price_cents': None, 'subtotal_cents': None} if line['category'] == 'WATER' else line for line in old_logistics['cost_breakdown']],
    })
    saved = call(port.save_assessment(context, 'LOGISTICS', logistics, newer.write_keys['logistics']))
    old_safety = next(a['result'] for a in original['assessments'] if a['kind'] == 'SAFETY')
    safety = SafetyResult.model_validate(old_safety | {'version_context': context.model_dump(mode='json'),
        'depends_on_assessment_id': saved.assessment_id, 'risk_level': 'LOW', 'confidence': 'HIGH',
        'requires_human_review': False, 'outcome': 'PASSED', 'hazards': []})
    call(port.save_assessment(context, 'SAFETY', safety, newer.write_keys['safety']))
    call(port.route_assessed_version(context, 'ELIGIBLE_FOR_FINALISATION', 'independent reassessment fixture', newer.write_keys['route']))
    call(port.report_stage('COMPLETED', 'SUCCEEDED', None))
    assert client.get('/api/v1/review-queue').json()['reviews']==[]
    row = client.get('/api/v1/assistance-queue').json()['plans'][0]
    assert row['run_id'] == newer.run_id and row['plan_version_id'] == version.version_context.plan_version_id
    assert row['summary']['risk_level'] == 'LOW'
    assert row['summary']['total_cents'] is None
    assert row['summary']['budget_difference_cents'] is None
    assert row['status'] == 'BLOCKED'
    assert client.get('/api/v1/review/' + scope.plan_id).json()['owner_display_name'] == 'Camper A'
