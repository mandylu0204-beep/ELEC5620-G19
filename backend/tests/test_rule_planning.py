from datetime import date

import pytest

from app.application.agent_registry import AGENT_FACTORIES
from app.contracts.dto import (
    DemoContext, InterpretRequestInput, ItineraryInput, ProfileSnapshot,
    RecommendCampsitesInput, RecommendCampsitesResult, TripRequirements,
)
from app.contracts.enums import ErrorCode, ExecutionMode, FieldErrorCode
from app.contracts.errors import ContractFailure
from rule_fixtures import DEMO, call, draft, full_profile, make_agent, previous_version, requirements


@pytest.fixture
def agent():
    return make_agent()


def interpret(agent, text, **kwargs):
    return call(agent.interpret_request(InterpretRequestInput(raw_text=text, profile_snapshot=full_profile(), demo_context=DEMO, **kwargs)))


def test_interpret_git_request_uses_nights_not_v1_days_or_expected_status(agent):
    result = call(agent.interpret_request(agent.dataset.request_input('request-01', DEMO)))
    assert not result.field_errors
    assert result.extracted_requirements.duration_nights == 2
    assert result.extracted_requirements.duration_days == 3
    assert result.extracted_requirements.end_date == date(2026, 10, 22)
    assert result.extracted_requirements.budget_cents == 32000
    assert result.extracted_requirements.preferences == ['quiet']
    assert 'CONFIRMED' not in result.model_dump_json()


def test_request_three_missing_duration_stays_missing(agent):
    result = call(agent.interpret_request(agent.dataset.request_input('request-03', DEMO)))
    fields = {item.field for item in result.field_errors}
    assert {'start_date', 'duration_nights'}.issubset(fields)
    assert result.extracted_requirements.duration_nights is None


@pytest.mark.parametrize('request_id,field,code', [
    ('request-02', 'destination', FieldErrorCode.MISSING),
    ('request-04', 'budget_cents', FieldErrorCode.MISSING),
    ('request-05', 'budget_cents', FieldErrorCode.INVALID),
    ('request-06', 'profile.group_size', FieldErrorCode.INVALID),
    ('request-07', 'destination', FieldErrorCode.UNSUPPORTED),
])
def test_original_invalid_requests_are_not_repaired_from_profile_defaults(agent, request_id, field, code):
    result = call(agent.interpret_request(agent.dataset.request_input(request_id, DEMO)))
    assert any(item.field == field and item.code == code for item in result.field_errors)


def test_only_days_does_not_implicitly_become_nights(agent):
    result = interpret(agent, 'Two campers in CampMate Demo Region from 2026-10-20 for two days, AUD 300.')
    assert result.extracted_requirements.duration_days == 2
    assert result.extracted_requirements.duration_nights is None
    assert any(item.field == 'duration_nights' for item in result.clarifications)


@pytest.mark.parametrize('text,field,code', [
    ('CampMate Demo Region from 2026-02-30 for two nights, AUD 300.', 'start_date', 'INVALID'),
    ('CampMate Demo Region from 2026-10-07 for two nights, AUD 300.', 'start_date', 'INVALID'),
    ('CampMate Demo Region from 2026-10-20 for zero nights, AUD 300.', 'duration_nights', 'INVALID'),
    ('CampMate Demo Region from 2026-10-20 for two nights or three nights, AUD 300.', 'duration_nights', 'CONFLICTING'),
    ('CampMate Demo Region from 2026-10-20 for two nights, AUD 300 or AUD 400.', 'budget_cents', 'CONFLICTING'),
    ('CampMate Demo Region from 2026-10-20 to 2026-10-21 for two nights, AUD 300.', 'end_date', 'CONFLICTING'),
    ('Three campers in CampMate Demo Region from 2026-10-20 for two nights, AUD 300.', 'profile.group_size', 'CONFLICTING'),
])
def test_parser_exposes_invalid_and_conflicting_original_values(agent, text, field, code):
    assert any(item.field == field and item.code == code for item in interpret(agent, text).field_errors)


def test_explicit_fields_override_text_and_half_up_budget_is_decimal(agent):
    result = interpret(agent, 'CampMate Demo Region from 2026-10-20 for two nights, AUD -50.', explicit_fields=TripRequirements(budget_cents=12345, preferences=['ready-to-eat meals']))
    assert result.extracted_requirements.budget_cents == 12345
    assert result.extracted_requirements.preferences == ['ready-to-eat meals']
    assert not any(item.field == 'budget_cents' for item in result.field_errors)
    assert interpret(agent, 'CampMate Demo Region from 2026-10-20 for two nights, AUD 1.225.').extracted_requirements.budget_cents == 123


def test_parser_missing_profile_is_not_filled_from_fixture(agent):
    result = call(agent.interpret_request(InterpretRequestInput(raw_text='Two campers in CampMate Demo Region from 2026-10-20 for two nights, AUD 300.', demo_context=DEMO)))
    assert any(item.field == 'profile.group_size' for item in result.field_errors)


def test_no_campfire_and_meal_preferences_are_not_confused(agent):
    result = interpret(agent, 'CampMate Demo Region from 2026-10-20 for two nights, AUD 300; ready-to-eat meals, no campfire.')
    assert 'campfire' not in result.extracted_requirements.preferences
    assert 'ready-to-eat meals' in result.extracted_requirements.preferences
    assert result.extracted_requirements.mandatory_constraints == ['no_fires']


def test_known_mandatory_clause_is_preserved_as_hard_constraint(agent):
    result = interpret(agent, 'CampMate Demo Region from 2026-10-20 for two nights, AUD 300. We must have toilets.')
    assert result.extracted_requirements.mandatory_constraints == ['toilets']
    assert not result.field_errors


@pytest.mark.parametrize('clause', ['do not use a campfire', 'must not light a campfire', 'avoid campfire'])
def test_negated_campfire_is_not_interpreted_as_a_requested_fire(agent, clause):
    result = interpret(agent, f'CampMate Demo Region from 2026-10-20 for two nights, AUD 300. We {clause}.')
    assert 'campfire' not in result.extracted_requirements.preferences
    assert result.extracted_requirements.mandatory_constraints == ['no_fires']
    assert not result.field_errors


def test_negated_meal_preference_does_not_select_the_rejected_mode(agent):
    result = interpret(agent, "CampMate Demo Region from 2026-10-20 for two nights, AUD 300. We do not want ready-to-eat meals; we want self-catered meals.")
    assert result.extracted_requirements.preferences == ['self-catered meals']


@pytest.mark.parametrize('clause', ['must have wifi', 'must have toilets and wifi', 'must have toilets. We must have wifi'])
def test_unsupported_mandatory_clause_cannot_be_hidden_by_a_known_one(agent, clause):
    result = interpret(agent, f'CampMate Demo Region from 2026-10-20 for two nights, AUD 300. We {clause}.')
    assert any(item.field == 'mandatory_constraints' and item.code == 'UNSUPPORTED' for item in result.field_errors)


def test_request_transport_conflict_is_not_replaced_by_profile_default(agent):
    result = interpret(agent, 'Two campers in CampMate Demo Region from 2026-10-20 for two nights, AUD 300, using public transport.')
    assert any(item.field == 'profile.transport.transport_type' and item.code == 'CONFLICTING' for item in result.field_errors)


def test_unsupported_accessibility_need_is_not_treated_as_wheelchair_access(agent):
    profile = full_profile().model_copy(update={'accessibility_requirements': ['hearing loop']})
    result = call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=requirements(), profile_snapshot=profile, demo_context=DEMO)))
    assert result.search_outcome == 'NO_MATCH'


def test_recommendation_is_stable_and_hard_constraints_exclude(agent):
    input = RecommendCampsitesInput(confirmed_requirements=requirements(mandatory_constraints=['toilets']), profile_snapshot=full_profile(), demo_context=DEMO)
    first, second = call(agent.recommend_campsites(input)), call(agent.recommend_campsites(input))
    assert first == second
    assert [item.rank for item in first.candidates] == list(range(1, len(first.candidates) + 1))
    assert first.candidates[0].campsite_id == 'demo-moonlit-field'
    assert 'demo-fern-walk' in {item.campsite_id for item in first.excluded_candidates}
    assert all(any(ref.record_id == item.campsite_id for ref in first.source_refs) for item in first.candidates)


def test_accessibility_and_public_transport_are_hard_profile_requirements(agent):
    profile = full_profile(mode='PUBLIC_TRANSPORT').model_copy(update={'accessibility_requirements': ['wheelchair-accessible toilet', 'step-free path']})
    result = call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=requirements(), profile_snapshot=profile, demo_context=DEMO)))
    assert {item.campsite_id for item in result.candidates} == {'demo-river-flat', 'demo-lake-meadow'}


def test_group_capacity_and_cross_season_are_checked(agent):
    result = call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=requirements(start_date=date(2027, 5, 31)), profile_snapshot=full_profile(group=9), demo_context=DEMO)))
    assert 'demo-pine-camp' in {item.campsite_id for item in result.excluded_candidates}
    assert all(agent.dataset.get_campsite(item.campsite_id).max_group_size >= 9 for item in result.candidates)


def test_real_no_match_is_not_adapter_failure(agent):
    result = call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=requirements(budget_cents=2500), profile_snapshot=full_profile(), demo_context=DEMO)))
    assert result.search_outcome == 'NO_MATCH'
    assert not result.candidates and len(result.excluded_candidates) == 10


@pytest.mark.parametrize('constraints', [['unimplemented hard constraint'], ['campfire', 'no_fires']])
def test_unsupported_or_conflicting_hard_constraint_is_not_silently_ignored(agent, constraints):
    with pytest.raises(ContractFailure) as failure:
        call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=requirements(mandatory_constraints=constraints), profile_snapshot=full_profile(), demo_context=DEMO)))
    assert failure.value.error.code == ErrorCode.INPUT_INVALID


def test_quiet_signal_does_not_claim_quietness_or_booking(agent):
    result = call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=requirements(preferences=['quiet', 'unverified view']), profile_snapshot=full_profile(), demo_context=DEMO)))
    assert result.candidates[0].campsite_id == 'demo-lake-meadow'
    assert any('quietness' in text for text in result.candidates[0].material_uncertainties)
    assert any('no verified' in text for text in result.candidates[0].material_uncertainties)


def test_itinerary_uses_confirmed_dates_and_sydney_timezone_without_ids(agent):
    result = draft(agent)
    assert result.selected_campsite_ids == ['demo-pine-camp']
    camps = [entry for entry in result.itinerary_entries if entry.entry_kind == 'CAMP']
    assert len(camps) == 2
    assert camps[0].start_at.date() == date(2026, 10, 20)
    assert camps[-1].end_at.date() == date(2026, 10, 22)
    assert all(entry.start_at.utcoffset().total_seconds() == 11 * 3600 for entry in result.itinerary_entries)
    assert 'version_context' not in result.model_dump()


def test_no_match_cannot_generate_fake_itinerary(agent):
    input = ItineraryInput(confirmed_requirements=requirements(), profile_snapshot=full_profile(), recommendations=RecommendCampsitesResult(execution_mode='deterministic_demo', search_outcome='NO_MATCH', candidates=[]), demo_context=DEMO)
    with pytest.raises(ContractFailure):
        call(agent.generate_or_revise_itinerary(input))


def test_cheaper_revision_uses_real_candidate_and_does_not_change_budget(agent):
    req, profile = requirements(), full_profile()
    recommendations = call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=req, profile_snapshot=profile, demo_context=DEMO)))
    previous = previous_version(draft(agent))
    result = call(agent.generate_or_revise_itinerary(ItineraryInput(confirmed_requirements=req, profile_snapshot=profile, recommendations=recommendations, previous_version=previous, feedback='cheaper campsite', demo_context=DEMO)))
    assert result.selected_campsite_ids == ['demo-moonlit-field']
    assert result.requested_requirement_changes is None
    assert previous.content.selected_campsite_ids == ['demo-pine-camp']


def test_removing_mandatory_campfire_is_a_proposal_not_silent_confirmation(agent):
    req = requirements(preferences=['campfire', 'ready-to-eat meals'], mandatory_constraints=['campfire'])
    recommendations = call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=req, profile_snapshot=full_profile(), demo_context=DEMO)))
    result = call(agent.generate_or_revise_itinerary(ItineraryInput(confirmed_requirements=req, profile_snapshot=full_profile(), recommendations=recommendations, previous_version=previous_version(draft(agent, req)), feedback='remove campfire', demo_context=DEMO)))
    assert result.requested_requirement_changes.mandatory_constraints == ['no_fires']
    assert 'campfire' not in result.requested_requirement_changes.preferences
    assert req.mandatory_constraints == ['campfire']


@pytest.mark.parametrize('feedback', ['change budget to AUD 999', 'pick an imaginary campsite'])
def test_unsupported_revision_feedback_requires_structured_confirmation(agent, feedback):
    req, profile = requirements(), full_profile()
    recommendations = call(agent.recommend_campsites(RecommendCampsitesInput(confirmed_requirements=req, profile_snapshot=profile, demo_context=DEMO)))
    with pytest.raises(ContractFailure):
        call(agent.generate_or_revise_itinerary(ItineraryInput(confirmed_requirements=req, profile_snapshot=profile, recommendations=recommendations, previous_version=previous_version(draft(agent)), feedback=feedback, demo_context=DEMO)))


@pytest.mark.parametrize('mode', ['stub', 'agent'])
def test_rule_agent_cannot_impersonate_other_execution_modes(agent, mode):
    with pytest.raises(ContractFailure) as failure:
        call(agent.interpret_request(InterpretRequestInput(raw_text='Test', demo_context=DemoContext(mode=mode, demo_today=DEMO.demo_today))))
    assert failure.value.error.code == ErrorCode.AGENT_FAILURE


def test_rule_agent_registration_still_requires_a_and_orchestration_requires_recovery_port(agent):
    assert ExecutionMode.DETERMINISTIC_DEMO not in AGENT_FACTORIES
    with pytest.raises(ContractFailure) as failure:
        call(agent.orchestrate(None, None))
    assert failure.value.error.code == ErrorCode.CONTRACT_INVALID


def test_wrong_dataset_and_invalid_contract_are_rejected(agent):
    with pytest.raises(ContractFailure) as failure:
        call(agent.interpret_request(InterpretRequestInput(raw_text='Test', demo_context=DEMO.model_copy(update={'dataset_version': 'v2'}))))
    assert failure.value.error.code == ErrorCode.STALE_CONTEXT
    with pytest.raises(ContractFailure) as failure:
        call(agent.interpret_request({'raw_text': '', 'demo_context': DEMO.model_dump()}))
    assert failure.value.error.code == ErrorCode.CONTRACT_INVALID
