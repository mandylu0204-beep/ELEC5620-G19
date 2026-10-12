"""R-02: explicit step-free booleans override legacy text in both rule paths."""
import pytest

from app.contracts.dto import (
    DemoContext, ItineraryInput, LogisticsInput, RecommendCampsitesInput,
    RecommendCampsitesResult,
)
from app.agents.rules.planning import violations
from rule_fixtures import VERSION, call, full_profile, make_agent, requirements
from test_synthetic_dataset_v2 import bound_agent


@pytest.mark.parametrize('version', ['v1', 'v2'])
@pytest.mark.parametrize('step_free,wheelchair,facilities,supported', [
    (True, False, [], True),
    (False, True, ['accessible path'], False),
    (False, False, [], False),
    (None, True, ['accessible path'], True),
    (None, True, [], False),
    (None, False, ['accessible path'], False),
])
def test_step_free_tristate_is_consistent_for_recommendation_and_logistics(
        version, step_free, wheelchair, facilities, supported):
    agent = make_agent() if version == 'v1' else bound_agent(['safety-02'])[1].agent
    demo = DemoContext(mode='deterministic_demo', demo_today='2026-10-08',
        dataset_version=agent.dataset.context.dataset_version)
    req = requirements()
    baseline = full_profile()
    profile = baseline.model_copy(update={'accessibility_requirements': ['step-free path']})
    original = agent.dataset.get_campsite('demo-river-flat')
    campsite = type(original).model_validate(original.model_dump() | {
        'step_free_path': step_free, 'wheelchair_accessible': wheelchair, 'facilities': facilities})
    # Isolated contradictory source attributes; no sealed business data is edited.
    agent.dataset._campsites[campsite.campsite_id] = campsite
    problems = violations(campsite, req, profile)
    assert (not problems) == supported
    recommendations = call(agent.recommend_campsites(RecommendCampsitesInput(
        confirmed_requirements=req, profile_snapshot=profile, demo_context=demo)))
    assert (campsite.campsite_id in {item.campsite_id for item in recommendations.candidates}) == supported
    if not supported:
        excluded = next(item for item in recommendations.excluded_candidates if item.campsite_id == campsite.campsite_id)
        assert any('step-free path' in reason for reason in excluded.reasons)
    # Evaluate a previously generated itinerary against the new hard profile
    # constraint. Logistics must not trust a previously accepted recommendation.
    content = call(agent.generate_or_revise_itinerary(ItineraryInput(
        confirmed_requirements=req, profile_snapshot=baseline, demo_context=demo,
        recommendations=RecommendCampsitesResult(execution_mode='deterministic_demo',
            search_outcome='MATCHES', candidates=[{'campsite_id': campsite.campsite_id,
                'rank': 1, 'reasons': ['Explicit independent accessibility unit input.']}]))))
    result = call(agent.assess_gear_and_logistics(LogisticsInput(version_context=VERSION,
        saved_itinerary=content, confirmed_requirements=req, profile_snapshot=profile, demo_context=demo)))
    hard = [item for item in result.mandatory_blockers if item.code == 'HARD_CONSTRAINT']
    assert (not hard) == supported
    if not supported:
        assert any('step-free path' in item.message for item in hard)
