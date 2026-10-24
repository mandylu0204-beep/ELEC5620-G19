"""Request text merging and confirmation-time hard-condition validation."""
from datetime import date

import pytest

from app.agents.rules.request_terms import canonical_term, merge_explicit_terms, term_issues
from app.application.request_rules import normalize
from app.contracts.dto import InterpretRequestInput, InterpretRequestResult, ProfileSnapshot, TripRequirements
from rule_fixtures import DEMO, call, full_profile, make_agent, requirements


@pytest.mark.parametrize('text', ['需要洗澡', '需要淋浴', '必须有淋浴', 'must have showers', 'need a shower'])
def test_shower_phrases_are_whole_conditions(text):
    assert canonical_term(text, 'constraint') == 'showers'


@pytest.mark.parametrize('text', ['需要热水淋浴', 'must have hot showers', '不需要淋浴', 'no showers', 'showers and wifi'])
def test_qualifiers_negation_and_compounds_are_not_reduced_to_showers(text):
    assert canonical_term(text, 'constraint') is None


def test_meal_selection_and_empty_constraint_box_do_not_erase_prose():
    prefs, hard = merge_explicit_terms(['quiet'], ['showers'],
        TripRequirements(preferences=['即食餐食'], mandatory_constraints=[]))
    assert prefs == ['quiet', 'ready-to-eat meals']
    assert hard == ['showers']


def test_scalar_authority_and_semantic_lists_have_separate_merge_rules():
    proposed = InterpretRequestResult(execution_mode='stub', extracted_requirements=requirements(
        start_date=date(2026, 10, 20), budget_cents=1, preferences=['quiet'], mandatory_constraints=['showers']))
    explicit = TripRequirements(start_date=date(2026, 10, 20), budget_cents=50000,
        preferences=['即食餐食'], mandatory_constraints=[])
    result, status = normalize(proposed, explicit, full_profile(), ['CampMate Demo Region'])
    assert status == 'AWAITING_CONFIRMATION'
    assert result.extracted_requirements.budget_cents == 50000
    assert result.extracted_requirements.preferences == ['quiet', 'ready-to-eat meals']
    assert result.extracted_requirements.mandatory_constraints == ['showers']


def test_canonical_model_lists_are_not_replaced_by_the_original_words():
    proposed = InterpretRequestResult(execution_mode='agent', extracted_requirements=requirements(
        preferences=['quiet', 'ready-to-eat meals'], mandatory_constraints=['showers']))
    explicit = TripRequirements(preferences=['即食餐食'], mandatory_constraints=['需要洗澡'])
    result, status = normalize(proposed, explicit, full_profile(), ['CampMate Demo Region'], interpreted_terms=True)
    assert status == 'AWAITING_CONFIRMATION'
    assert result.extracted_requirements.mandatory_constraints == ['showers']
    assert explicit.mandatory_constraints == ['需要洗澡']


def test_unknown_hard_condition_is_clarified_before_confirmation():
    proposed = InterpretRequestResult(execution_mode='stub', extracted_requirements=requirements())
    result, status = normalize(proposed, TripRequirements(mandatory_constraints=['必须有私人热水浴室']),
        full_profile(), ['CampMate Demo Region'])
    assert status == 'NEEDS_CLARIFICATION'
    assert result.extracted_requirements.mandatory_constraints == ['必须有私人热水浴室']
    assert any('私人热水浴室' in item.question for item in result.clarifications)


def test_unknown_soft_preference_stays_visible_without_becoming_hard():
    proposed = InterpretRequestResult(execution_mode='stub', extracted_requirements=requirements())
    result, status = normalize(proposed, TripRequirements(preferences=['适合看星星']),
        full_profile(), ['CampMate Demo Region'])
    assert status == 'AWAITING_CONFIRMATION'
    assert '适合看星星' in result.extracted_requirements.preferences
    assert not result.extracted_requirements.mandatory_constraints


def test_fire_and_meal_conflicts_cannot_be_merged_away():
    errors, questions = term_issues(['ready-to-eat meals', 'self-catered meals'], ['no_fires', 'fire_allowed'])
    assert {(item.field, item.code) for item in errors} == {
        ('preferences', 'CONFLICTING'), ('mandatory_constraints', 'CONFLICTING')}
    assert len(questions) == 2


@pytest.mark.parametrize('text', ['想找个安静的地方，需要洗澡。', 'We prefer quiet. We need showers.'])
def test_rules_merge_meals_with_common_bilingual_prose_without_erasing_constraints(text):
    agent = make_agent()
    original = InterpretRequestInput(raw_text=text,
        explicit_fields=TripRequirements(destination='CampMate Demo Region', start_date=date(2026, 10, 20),
            duration_nights=2, budget_cents=50000, preferences=['即食餐食'], mandatory_constraints=[]),
        profile_snapshot=full_profile(), demo_context=DEMO)
    result = call(agent.interpret_request(original))
    assert {'quiet', 'ready-to-eat meals'} <= set(result.extracted_requirements.preferences)
    assert result.extracted_requirements.mandatory_constraints == ['showers']
    assert not result.field_errors
    assert original.explicit_fields.mandatory_constraints == []


@pytest.mark.parametrize('text', ["We do not need showers.", '不需要洗澡。'])
def test_rules_do_not_invert_negated_shower_statements(text):
    result = call(make_agent().interpret_request(InterpretRequestInput(raw_text=text,
        explicit_fields=TripRequirements(destination='CampMate Demo Region', start_date=date(2026, 10, 20),
            duration_nights=2, budget_cents=50000, preferences=['ready-to-eat meals'], mandatory_constraints=[]),
        profile_snapshot=full_profile(), demo_context=DEMO)))
    assert 'showers' not in result.extracted_requirements.mandatory_constraints
    assert 'showers' not in result.extracted_requirements.preferences


def test_understood_showers_still_require_a_positive_facility_fact():
    from app.contracts.dto import RecommendCampsitesInput
    agent = make_agent()
    result = call(agent.recommend_campsites(RecommendCampsitesInput(
        confirmed_requirements=requirements(mandatory_constraints=['showers']),
        profile_snapshot=full_profile(), demo_context=DEMO)))
    assert result.candidates
    for item in result.candidates:
        assert agent.dataset.get_campsite(item.campsite_id).showers is True
    assert any(agent.dataset.get_campsite(item.campsite_id).showers is not True for item in result.excluded_candidates)
