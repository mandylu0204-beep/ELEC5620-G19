from datetime import date

import pytest

from app.agents.rules.safety import propose_route
from app.contracts.dto import (
    Evidence, ItineraryEntry, ItineraryResult, LogisticsInput, SafetyInput, ScenarioContext,
)
from app.contracts.enums import ErrorCode
from app.contracts.errors import ContractFailure
from rule_fixtures import (
    DEMO, VERSION, call, complete_scenario, full_profile, logistics_input, make_agent,
    requirements, stored_logistics,
)


@pytest.fixture
def agent():
    return make_agent()


def safety_input(agent, req=None, profile=None, campsite_id='demo-pine-camp', scenario=None):
    req = req or requirements()
    profile = profile or full_profile()
    log_input = logistics_input(agent, req, profile, campsite_id)
    log = call(agent.assess_gear_and_logistics(log_input))
    return SafetyInput(
        version_context=VERSION, saved_itinerary=log_input.saved_itinerary,
        confirmed_requirements=req, saved_logistics_assessment=stored_logistics(log),
        scenario_context=scenario or complete_scenario(req, [campsite_id]), demo_context=DEMO,
    )


def replace_evidence(scenario, kind, **changes):
    evidence = [Evidence.model_validate(item.model_dump() | changes) if item.kind == kind else item for item in scenario.evidence]
    return scenario.model_copy(update={'evidence': evidence})


def test_complete_independent_facts_can_pass_without_copying_precomputed_risk(agent):
    input = safety_input(agent)
    result = call(agent.assess_safety(input))
    assert result.outcome == 'PASSED'
    assert result.risk_level == 'LOW' and result.confidence == 'HIGH'
    assert result.requires_human_review is False
    assert not result.mandatory_blockers
    assert result.depends_on_assessment_id == input.saved_logistics_assessment.assessment_id
    assert result.version_context == VERSION
    assert set(result.data_quality.values()) == {'AVAILABLE'}
    assert propose_route(input.saved_logistics_assessment, result) == 'ELIGIBLE_FOR_FINALISATION'


def test_unmodified_v1_safety_with_unknown_intervals_never_passes(agent):
    scenario = agent.dataset.get_safety('safety-01').scenario_context
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'REVIEW'
    assert result.risk_level == 'UNKNOWN' and result.requires_human_review is True
    assert set(result.data_quality.values()) == {'MISSING'}


@pytest.mark.parametrize('kind', ['WEATHER', 'FIRE', 'ROAD', 'RESTRICTION'])
def test_each_required_evidence_kind_must_be_present(agent, kind):
    scenario = complete_scenario()
    scenario = scenario.model_copy(update={'evidence': [item for item in scenario.evidence if item.kind != kind]})
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'REVIEW' and result.requires_human_review is True
    assert result.data_quality[kind] == 'MISSING'


@pytest.mark.parametrize('status', ['MISSING', 'STALE', 'CONFLICTING'])
def test_explicit_quality_cannot_be_upgraded_by_valid_dates(agent, status):
    scenario = replace_evidence(complete_scenario(), 'WEATHER', status=status)
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'REVIEW' and result.data_quality['WEATHER'] == status
    if status == 'CONFLICTING':
        assert result.unresolved_conflicts


@pytest.mark.parametrize('changes', [
    {'source_date': None}, {'source_date': date(2026, 10, 9)},
    {'valid_from': None}, {'valid_to': None},
    {'valid_from': date(2026, 10, 21)}, {'valid_to': date(2026, 10, 21)},
    {'summary': None},
])
def test_future_or_incomplete_evidence_cannot_pass(agent, changes):
    scenario = replace_evidence(complete_scenario(), 'WEATHER', **changes)
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'REVIEW' and result.data_quality['WEATHER'] == 'MISSING'


def test_scenario_interval_itself_must_cover_trip(agent):
    scenario = complete_scenario().model_copy(update={'valid_to': date(2026, 10, 21)})
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'REVIEW' and set(result.data_quality.values()) == {'MISSING'}


def test_source_reference_narrower_interval_cannot_be_overridden_by_evidence(agent):
    scenario = complete_scenario()
    reference = scenario.evidence[0].source_refs[0].model_copy(update={'valid_from': date(2026, 10, 20), 'valid_to': date(2026, 10, 21)})
    scenario = replace_evidence(scenario, 'WEATHER', source_refs=[reference])
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'REVIEW' and result.data_quality['WEATHER'] == 'MISSING'


def test_wrong_campsite_or_source_cannot_be_silently_reused(agent):
    with pytest.raises(ContractFailure) as failure:
        call(agent.assess_safety(safety_input(agent, scenario=complete_scenario(campsite_ids=['demo-river-flat']))))
    assert failure.value.error.code == ErrorCode.INPUT_INVALID
    scenario = replace_evidence(complete_scenario(), 'WEATHER', source_refs=[{'dataset_file': 'independent-facts.json', 'record_id': 'demo-river-flat'}])
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'REVIEW' and result.data_quality['WEATHER'] == 'MISSING'


@pytest.mark.parametrize('summary', ['Synthetic extreme heat expected.', 'Strong wind in synthetic forecast.', 'Heavy rain in synthetic forecast.'])
def test_known_high_weather_hazard_requires_review_with_complete_evidence(agent, summary):
    scenario = replace_evidence(complete_scenario(), 'WEATHER', summary=summary)
    input = safety_input(agent, scenario=scenario)
    result = call(agent.assess_safety(input))
    assert result.risk_level == 'HIGH' and result.outcome == 'REVIEW'
    assert result.requires_human_review is True
    assert result.hazards
    assert propose_route(input.saved_logistics_assessment, result) == 'ESCALATED'


def test_cold_is_qualitative_not_a_fabricated_numeric_forecast(agent):
    scenario = replace_evidence(complete_scenario(), 'WEATHER', summary='Cold synthetic forecast.')
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.risk_level == 'MEDIUM'
    assert 'temperature_max' not in result.model_dump_json()
    assert result.outcome == 'PASSED'


@pytest.mark.parametrize('kind,summary,expected_quality', [
    ('WEATHER', 'It might be okay.', 'MISSING'),
    ('WEATHER', 'Synthetic sources conflict.', 'CONFLICTING'),
    ('WEATHER', 'Synthetic weather is stale.', 'STALE'),
    ('FIRE', 'Probably allowed.', 'MISSING'),
    ('RESTRICTION', 'No restrictions listed; completeness is unverified.', 'MISSING'),
])
def test_available_label_does_not_override_unknown_or_conflicting_content(agent, kind, summary, expected_quality):
    scenario = replace_evidence(complete_scenario(), kind, summary=summary)
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'REVIEW' and result.data_quality[kind] == expected_quality


def test_conflicting_duplicate_sources_do_not_choose_the_convenient_one(agent):
    scenario = complete_scenario()
    high = Evidence.model_validate(scenario.evidence[0].model_dump() | {'summary': 'Synthetic extreme heat expected.'})
    scenario = scenario.model_copy(update={'evidence': [*scenario.evidence, high]})
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.data_quality['WEATHER'] == 'CONFLICTING'
    assert result.unresolved_conflicts and result.requires_human_review


def test_closed_road_is_mandatory_blocker_even_with_complete_weather_and_logistics(agent):
    scenario = replace_evidence(complete_scenario(), 'ROAD', road_state='CLOSED', summary='closed in synthetic scenario')
    input = safety_input(agent, scenario=scenario)
    result = call(agent.assess_safety(input))
    assert result.outcome == 'BLOCKED' and result.risk_level == 'HIGH'
    assert any(item.code == 'ROAD_CLOSED' for item in result.mandatory_blockers)
    assert propose_route(input.saved_logistics_assessment, result) == 'BLOCKED'


def test_open_flag_does_not_override_closed_road_summary(agent):
    scenario = replace_evidence(complete_scenario(), 'ROAD', road_state='OPEN', summary='closed in synthetic scenario')
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.data_quality['ROAD'] == 'CONFLICTING'
    assert result.outcome == 'BLOCKED' and result.unresolved_conflicts


def test_unknown_road_is_not_open(agent):
    scenario = replace_evidence(complete_scenario(), 'ROAD', road_state='UNKNOWN', summary='unknown in synthetic scenario')
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.data_quality['ROAD'] == 'MISSING'
    assert result.outcome == 'REVIEW'


def test_campsite_closure_cannot_be_overridden_by_complete_other_facts(agent):
    scenario = replace_evidence(complete_scenario(), 'RESTRICTION', summary='synthetic campsite closure')
    result = call(agent.assess_safety(safety_input(agent, scenario=scenario)))
    assert result.outcome == 'BLOCKED'
    assert any(item.code == 'CAMPSITE_CLOSED' for item in result.mandatory_blockers)


def test_requested_campfire_respects_static_no_fire_rule_even_if_evidence_is_missing(agent):
    req = requirements(preferences=['ready-to-eat meals', 'campfire'])
    scenario = complete_scenario(req, ['demo-ridge-lookout']).model_copy(update={'evidence': []})
    result = call(agent.assess_safety(safety_input(agent, req, full_profile(water=16), 'demo-ridge-lookout', scenario)))
    assert result.outcome == 'BLOCKED'
    assert any(item.code == 'FIRE_PROHIBITED' for item in result.mandatory_blockers)


def test_planned_campfire_is_checked_even_when_not_in_preferences(agent):
    input = safety_input(agent, profile=full_profile(water=16), campsite_id='demo-ridge-lookout')
    entries = [entry.model_copy(update={'description': 'Light a campfire.'}) if entry.entry_kind == 'ACTIVITY' else entry for entry in input.saved_itinerary.itinerary_entries]
    input = input.model_copy(update={'saved_itinerary': input.saved_itinerary.model_copy(update={'itinerary_entries': entries})})
    result = call(agent.assess_safety(input))
    assert any(item.code == 'FIRE_PROHIBITED' for item in result.mandatory_blockers)


def test_fire_inside_camp_description_is_also_checked(agent):
    input = safety_input(agent, profile=full_profile(water=16), campsite_id='demo-ridge-lookout')
    entries = [entry.model_copy(update={'description': 'Overnight stay with a campfire.'}) if entry.entry_kind == 'CAMP' else entry for entry in input.saved_itinerary.itinerary_entries]
    input = input.model_copy(update={'saved_itinerary': input.saved_itinerary.model_copy(update={'itinerary_entries': entries})})
    assert any(item.code == 'FIRE_PROHIBITED' for item in call(agent.assess_safety(input)).mandatory_blockers)


def test_unclassified_activity_is_not_automatically_declared_safe(agent):
    input = safety_input(agent)
    entries = [entry.model_copy(update={'description': 'Try abseiling at an unverified cliff.'}) if entry.entry_kind == 'ACTIVITY' else entry for entry in input.saved_itinerary.itinerary_entries]
    input = input.model_copy(update={'saved_itinerary': input.saved_itinerary.model_copy(update={'itinerary_entries': entries})})
    result = call(agent.assess_safety(input))
    assert result.outcome == 'REVIEW' and result.risk_level == 'UNKNOWN'
    assert result.requires_human_review and any('Unclassified' in text for text in result.hazards)


def test_risky_activity_cannot_hide_in_camp_entry_description(agent):
    input = safety_input(agent)
    entries = [entry.model_copy(update={'description': 'Overnight stay and abseiling at an unverified cliff.'}) if entry.entry_kind == 'CAMP' else entry for entry in input.saved_itinerary.itinerary_entries]
    input = input.model_copy(update={'saved_itinerary': input.saved_itinerary.model_copy(update={'itinerary_entries': entries})})
    result = call(agent.assess_safety(input))
    assert result.outcome == 'REVIEW' and result.requires_human_review


def test_safe_ready_meals_at_no_fire_site_do_not_create_false_fire_blocker(agent):
    input = safety_input(agent, profile=full_profile(water=16), campsite_id='demo-ridge-lookout')
    result = call(agent.assess_safety(input))
    assert result.outcome == 'PASSED'
    assert not any(item.code == 'FIRE_PROHIBITED' for item in result.mandatory_blockers)


def test_high_risk_escalation_has_priority_over_overbudget_revision_in_b_proposal(agent):
    req = requirements(budget_cents=10000)
    scenario = replace_evidence(complete_scenario(req), 'WEATHER', summary='Synthetic extreme heat expected.')
    input = safety_input(agent, req=req, scenario=scenario)
    assert input.saved_logistics_assessment.result.outcome == 'REVISION'
    result = call(agent.assess_safety(input))
    assert propose_route(input.saved_logistics_assessment, result) == 'ESCALATED'


def test_logistics_gear_blocker_remains_visible_after_safety_assessment(agent):
    profile = full_profile().model_copy(update={'equipment': [item for item in full_profile().equipment if item.item_key != 'first_aid_kit']})
    input = safety_input(agent, profile=profile)
    result = call(agent.assess_safety(input))
    assert any(item.code == 'ESSENTIAL_GEAR_MISSING' for item in result.mandatory_blockers)
    assert result.outcome == 'REVISION'
    assert propose_route(input.saved_logistics_assessment, result) == 'BLOCKED'


def test_route_checks_actual_saved_logistics_dependency(agent):
    input = safety_input(agent)
    result = call(agent.assess_safety(input))
    wrong = result.model_copy(update={'depends_on_assessment_id': 'wrong-assessment-id'})
    with pytest.raises(ContractFailure):
        propose_route(input.saved_logistics_assessment, wrong)
    wrong = result.model_copy(update={'version_context': VERSION.model_copy(update={'run_id': 'old-run'})})
    with pytest.raises(ContractFailure):
        propose_route(input.saved_logistics_assessment, wrong)


def test_safety_input_cannot_mix_run_and_logistics_version(agent):
    input = safety_input(agent).model_copy(update={'version_context': VERSION.model_copy(update={'run_id': 'different-run'})})
    with pytest.raises(ContractFailure) as failure:
        call(agent.assess_safety(input))
    assert failure.value.error.code == ErrorCode.CONTRACT_INVALID


def test_multiple_campsites_each_need_all_four_kinds(agent):
    req, profile = requirements(), full_profile()
    itinerary = ItineraryResult(
        execution_mode='deterministic_demo', selected_campsite_ids=['demo-pine-camp', 'demo-river-flat'], revision_reason='Independent two-site input.',
        itinerary_entries=[
            ItineraryEntry(entry_kind='CAMP', start_at='2026-10-20T12:00:00+11:00', end_at='2026-10-21T08:00:00+11:00', campsite_id='demo-pine-camp', description='Synthetic overnight stay at Demo Pine Camp; no booking implied.'),
            ItineraryEntry(entry_kind='CAMP', start_at='2026-10-21T17:00:00+11:00', end_at='2026-10-22T10:00:00+11:00', campsite_id='demo-river-flat', description='Synthetic overnight stay at Demo River Flat; no booking implied.'),
        ],
    )
    log = call(agent.assess_gear_and_logistics(LogisticsInput(version_context=VERSION, saved_itinerary=itinerary, confirmed_requirements=req, profile_snapshot=profile, demo_context=DEMO)))
    scenario = complete_scenario(req, ['demo-pine-camp', 'demo-river-flat'])
    input = SafetyInput(version_context=VERSION, saved_itinerary=itinerary, confirmed_requirements=req, saved_logistics_assessment=stored_logistics(log), scenario_context=scenario, demo_context=DEMO)
    assert call(agent.assess_safety(input)).outcome == 'PASSED'
    scenario = scenario.model_copy(update={'evidence': [item for item in scenario.evidence if not (item.kind == 'FIRE' and item.source_refs[0].record_id == 'demo-river-flat')]})
    result = call(agent.assess_safety(input.model_copy(update={'scenario_context': scenario})))
    assert result.outcome == 'REVIEW' and result.data_quality['FIRE'] == 'MISSING'


def test_safety_result_round_trips_through_shared_schema(agent):
    from app.contracts.dto import SafetyResult
    result = call(agent.assess_safety(safety_input(agent)))
    assert SafetyResult.model_validate_json(result.model_dump_json()) == result
