"""Offline request semantics protocol and host boundaries; no campus calls."""
import asyncio
import json

import httpx
import pytest

from app.agents.hybrid_planning_agent import HybridPlanningAgent, build_hybrid_configuration
from app.contracts.dto import InterpretRequestInput, TripRequirements
from app.contracts.errors import ContractFailure
from app.llm.client import CampusModelClient
from app.llm.coordinator import PlanningCoordinator
from app.llm import request_interpretation
from llm_fixtures import completion, model_input, model_settings


def mention(quote, canonical, *, polarity='positive', strength='soft', ambiguous=False):
    return dict(quote=quote, canonical=canonical, polarity=polarity, strength=strength, ambiguous=ambiguous)


def setup(raw, mappings=None, *, explicit=None, mutate=None, response=None):
    dataset, itinerary = model_input()
    fields = itinerary.confirmed_requirements.model_dump()
    fields.update(preferences=['\u5373\u98df\u9910\u98df'], mandatory_constraints=[])
    if explicit:
        fields.update(explicit)
    input = InterpretRequestInput(raw_text=raw, explicit_fields=TripRequirements.model_validate(fields),
        profile_snapshot=itinerary.profile_snapshot, demo_context=itinerary.demo_context)
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if response is not None:
            return response
        payload = json.loads(body['messages'][-1]['content'])
        clauses = []
        for source in payload['sources']:
            entries = (mappings or {}).get(source['text'], [])
            if source['text'] == '\u5373\u98df\u9910\u98df' and source['source'] == 'preferences':
                entries = [mention('\u5373\u98df\u9910\u98df', 'ready-to-eat meals')]
            clauses.append(dict(source=source['source'], index=source['index'], quote=source['text'],
                mentions=entries, unresolved=False))
        proposal = {'clauses': clauses}
        if mutate:
            mutate(proposal)
        return httpx.Response(200, json=completion(proposal))

    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(handler))
    coordinator = PlanningCoordinator(dataset, client)
    configuration = build_hybrid_configuration(dataset, coordinator)
    agent = HybridPlanningAgent(dataset, coordinator, workflow_configuration=configuration,
        request_interpretation=True)
    return agent, input, requests


def interpreted(agent, input):
    return asyncio.run(agent.interpret_request_with_observation(input))


@pytest.mark.parametrize('raw,mappings', [
    ('\u9700\u8981\u6d17\u6fa1。\u800c\u4e14\u5e0c\u671b\u5468\u56f4\u6e05\u9759\u4e00\u4e9b。', {
        '\u9700\u8981\u6d17\u6fa1。': [mention('\u9700\u8981\u6d17\u6fa1', 'showers', strength='hard')],
        '\u800c\u4e14\u5e0c\u671b\u5468\u56f4\u6e05\u9759\u4e00\u4e9b。': [mention('\u5e0c\u671b\u5468\u56f4\u6e05\u9759\u4e00\u4e9b', 'quiet')],
    }),
    ('We need showers and prefer quiet.', {
        'We need showers and prefer quiet.': [mention('need showers', 'showers', strength='hard'),
            mention('prefer quiet', 'quiet')],
    }),
])
def test_bilingual_semantics_preserve_scalar_authority_and_use_one_completion(raw, mappings):
    agent, input, requests = setup(raw, mappings)
    original = input.model_dump(mode='json')
    outcome = interpreted(agent, input)
    result = outcome.result
    assert result.extracted_requirements.mandatory_constraints == ['showers']
    assert set(result.extracted_requirements.preferences) == {'quiet', 'ready-to-eat meals'}
    assert result.extracted_requirements.budget_cents == input.explicit_fields.budget_cents
    assert result.extracted_requirements.start_date == input.explicit_fields.start_date
    assert not result.field_errors and not result.clarifications
    assert input.model_dump(mode='json') == original
    assert len(requests) == 1
    assert outcome.observation == {'identity': agent.request_interpretation_identity,
        'attempts': 1, 'usage': {'prompt_tokens': 100, 'completion_tokens': 60, 'total_tokens': 160}}
    assert set(outcome.observation['identity']) == {
        'component_version', 'prompt_sha256', 'schema_version', 'configuration_fingerprint', 'requested_model'}
    assert '10.167.60.148' not in json.dumps(outcome.observation)
    assert 'unit-only-school-secret' not in json.dumps(outcome.observation)


@pytest.mark.parametrize('raw,phrase', [
    ('\u4e0d\u9700\u8981\u6dcb\u6d74。', '\u4e0d\u9700\u8981\u6dcb\u6d74'),
    ('We do not need showers.', 'do not need showers'),
    ('Showers are optional.', 'Showers are optional'),
])
def test_optional_showers_never_become_positive_requirement(raw, phrase):
    agent, input, _ = setup(raw, {raw: [mention(phrase, 'showers', polarity='not_required', strength='hard')]})
    result = interpreted(agent, input).result
    assert 'showers' not in result.extracted_requirements.preferences
    assert 'showers' not in result.extracted_requirements.mandatory_constraints
    assert not result.field_errors


@pytest.mark.parametrize('raw,phrase', [('\u4e0d\u8981\u751f\u706b。', '\u4e0d\u8981\u751f\u706b'), ('No campfires.', 'No campfires')])
def test_negative_campfire_uses_existing_no_fires_constraint(raw, phrase):
    agent, input, _ = setup(raw, {raw: [mention(phrase, 'campfire', polarity='negative', strength='hard')]})
    result = interpreted(agent, input).result
    assert result.extracted_requirements.mandatory_constraints == ['no_fires']
    assert 'campfire' not in result.extracted_requirements.preferences
    assert not result.field_errors


@pytest.mark.parametrize('raw,entry', [
    ('\u4e0d\u9700\u8981\u6dcb\u6d74。', mention('\u6dcb\u6d74', 'showers', strength='hard')),
    ('We do not need showers.', mention('showers', 'showers', strength='hard')),
    ('We need showers.', mention('need showers', 'showers', strength='soft')),
    ('We need showers.', mention('need showers', 'showers', polarity='not_required', strength='hard')),
    ('We prefer showers.', mention('prefer showers', 'showers', strength='hard')),
    ('\u53ef\u80fd\u9700\u8981\u6d17\u6fa1。', mention('\u53ef\u80fd\u9700\u8981\u6d17\u6fa1', 'showers', strength='hard')),
])
def test_host_asks_about_negation_reversal_and_incorrect_obligation(raw, entry):
    agent, input, requests = setup(raw, {raw: [entry]})
    result = interpreted(agent, input).result
    assert result.clarifications
    assert 'showers' not in result.extracted_requirements.mandatory_constraints
    assert len(requests) == 1


def test_host_rejects_unrelated_canonical_for_a_known_phrase():
    raw = '\u9700\u8981\u6dcb\u6d74。'
    agent, input, _ = setup(raw, {raw: [mention('\u9700\u8981\u6dcb\u6d74', 'public_transport_access', strength='hard')]})
    with pytest.raises(ContractFailure) as error:
        interpreted(agent, input)
    assert error.value.error.code == 'CONTRACT_INVALID'


@pytest.mark.parametrize('mutation', [
    lambda value: value['clauses'][0].update(quote='fabricated user wording'),
    lambda value: value['clauses'][0]['mentions'][0].update(quote='not in the original'),
    lambda value: value['clauses'][0]['mentions'][0].update(canonical='wifi'),
    lambda value: value.update(budget_cents=1),
    lambda value: value['clauses'].pop(),
    lambda value: value['clauses'].append(dict(value['clauses'][0])),
])
def test_strict_protocol_rejects_fabrication_unknown_canonical_missing_sources_and_scalar_edits(mutation):
    raw = '\u5fc5\u987b\u6709\u6dcb\u6d74。'
    agent, input, _ = setup(raw, {raw: [mention('\u5fc5\u987b\u6709\u6dcb\u6d74', 'showers', strength='hard')]}, mutate=mutation)
    with pytest.raises(ContractFailure) as error:
        interpreted(agent, input)
    assert error.value.error.code == 'CONTRACT_INVALID'


def test_explicit_natural_terms_are_normalized_without_overwriting_original_input():
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', {'\u9700\u8981\u6d17\u6fa1': [mention('\u9700\u8981\u6d17\u6fa1', 'showers', strength='hard')]},
        explicit={'mandatory_constraints': ['\u9700\u8981\u6d17\u6fa1']})
    result = interpreted(agent, input).result
    assert result.extracted_requirements.mandatory_constraints == ['showers']
    assert input.explicit_fields.mandatory_constraints == ['\u9700\u8981\u6d17\u6fa1']
    assert not result.field_errors


def test_raw_scalar_conflicts_cannot_change_explicit_dates_budget_or_profile():
    raw = 'AUD 1 from 2026-01-01 for nine nights. We are ten people.'
    agent, input, _ = setup(raw)
    result = interpreted(agent, input).result
    assert result.extracted_requirements.budget_cents == input.explicit_fields.budget_cents
    assert result.extracted_requirements.start_date == input.explicit_fields.start_date
    assert result.extracted_requirements.duration_nights == input.explicit_fields.duration_nights
    assert any(error.field == 'profile.group_size' for error in result.field_errors)


def test_unresolved_raw_obligation_cannot_be_silently_confirmed():
    agent, input, _ = setup('We must have wifi.')
    result = interpreted(agent, input).result
    assert result.clarifications
    assert any(error.field == 'mandatory_constraints' for error in result.field_errors)


def test_explicit_entry_cannot_be_silently_omitted_by_model():
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', explicit={'mandatory_constraints': ['wifi']})
    with pytest.raises(ContractFailure) as error:
        interpreted(agent, input)
    assert error.value.error.code == 'CONTRACT_INVALID'


@pytest.mark.parametrize('source,polarity', [
    ('mandatory_constraints', 'not_required'), ('mandatory_constraints', 'negative'),
    ('raw_text', 'not_required'), ('raw_text', 'negative'),
])
def test_neutral_evidence_cannot_erase_or_negate_explicit_or_raw_requirement(source, polarity):
    entry = mention('showers', 'showers', polarity=polarity, strength='hard')
    if source == 'mandatory_constraints':
        agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', {'showers': [entry]},
            explicit={'mandatory_constraints': ['showers']})
    else:
        agent, input, _ = setup('showers', {'showers': [entry]})
    result = interpreted(agent, input).result
    assert result.clarifications


def test_rules_semantic_guess_cannot_override_model_soft_hard_classification():
    raw = 'Showers are optional.'
    agent, input, _ = setup(raw, {raw: [mention('Showers are optional', 'showers',
        polarity='not_required', strength='soft')]})
    result = interpreted(agent, input).result
    assert result.extracted_requirements.mandatory_constraints == []
    assert result.extracted_requirements.preferences == ['ready-to-eat meals']


@pytest.mark.parametrize('raw,quoted', [
    ('We must have toilets and a swimming pool.', 'must have toilets'),
    ('We must have toilets and a swimming pool.', 'must have toilets and a swimming pool'),
])
def test_compound_raw_hard_condition_cannot_hide_an_unmapped_remainder(raw, quoted):
    agent, input, _ = setup(raw, {raw: [mention(quoted, 'toilets', strength='hard')]})
    result = interpreted(agent, input).result
    assert result.clarifications
    assert any(error.field == 'mandatory_constraints' for error in result.field_errors)


@pytest.mark.parametrize('quoted', ['\u9700\u8981\u6d17\u6fa1', '\u9700\u8981\u6d17\u6fa1\u5e76\u4e14\u8981\u6cf3\u6c60'])
def test_explicit_compound_cannot_hide_unknown_condition_with_partial_or_whole_quote(quoted):
    text = '\u9700\u8981\u6d17\u6fa1\u5e76\u4e14\u8981\u6cf3\u6c60'
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', {text: [mention(quoted, 'showers', strength='hard')]},
        explicit={'mandatory_constraints': [text]})
    result = interpreted(agent, input).result
    assert result.clarifications


@pytest.mark.parametrize('raw,phrase', [
    ('\u4e0d\u80fd\u6ca1\u6709\u5395\u6240。', '\u4e0d\u80fd\u6ca1\u6709\u5395\u6240'),
    ("I don't want a site without toilets.", "don't want a site without toilets"),
])
def test_double_negative_returns_actionable_clarification_without_protocol_failure(raw, phrase):
    agent, input, _ = setup(raw, {raw: [mention(phrase, 'toilets', strength='hard')]})
    result = interpreted(agent, input).result
    assert result.clarifications
    assert result.extracted_requirements.mandatory_constraints == []


def test_registered_meal_alias_with_negative_word_is_a_positive_meal_mode():
    text = '\u65e0\u9700\u70f9\u996a\u7684\u9910\u98df'
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', {text: [mention(text, 'ready-to-eat meals')]},
        explicit={'preferences': [text]})
    result = interpreted(agent, input).result
    assert result.extracted_requirements.preferences == ['ready-to-eat meals']
    assert not result.field_errors


def test_not_noisy_can_mean_quiet_without_negation_reversal():
    raw = 'I prefer somewhere not noisy.'
    agent, input, _ = setup(raw, {raw: [mention('not noisy', 'quiet')]})
    result = interpreted(agent, input).result
    assert set(result.extracted_requirements.preferences) == {'quiet', 'ready-to-eat meals'}
    assert not result.field_errors


def test_optional_hot_shower_does_not_create_an_unsupported_hot_shower_requirement():
    raw = '\u4e0d\u9700\u8981\u70ed\u6c34\u6dcb\u6d74。'
    agent, input, _ = setup(raw, {raw: [mention('\u4e0d\u9700\u8981\u70ed\u6c34\u6dcb\u6d74', 'showers',
        polarity='not_required', strength='hard')]})
    result = interpreted(agent, input).result
    assert not result.field_errors
    assert result.extracted_requirements.mandatory_constraints == []


@pytest.mark.parametrize('raw,canonical,phrase', [
    ('\u5fc5\u987b\u6709\u65e0\u969c\u788d\u5395\u6240。', 'toilets', '\u5fc5\u987b\u6709\u65e0\u969c\u788d\u5395\u6240'),
    ('\u5fc5\u987b\u6709\u65e0\u53f0\u9636\u901a\u9053。', 'wheelchair_accessible', '\u5fc5\u987b\u6709\u65e0\u53f0\u9636\u901a\u9053'),
])
def test_accessibility_details_cannot_be_reduced_to_generic_facility(raw, canonical, phrase):
    agent, input, _ = setup(raw, {raw: [mention(phrase, canonical, strength='hard')]})
    result = interpreted(agent, input).result
    assert result.clarifications
    assert not result.extracted_requirements.mandatory_constraints


def test_optional_fire_cannot_become_a_hard_fire_ban():
    raw = 'I do not need a campfire.'
    agent, input, _ = setup(raw, {raw: [mention('do not need a campfire', 'no_fires', strength='hard')]})
    result = interpreted(agent, input).result
    assert result.clarifications
    assert 'no_fires' not in result.extracted_requirements.mandatory_constraints


@pytest.mark.parametrize('explicit', [False, True])
def test_soft_negative_campfire_stays_soft(explicit):
    text = '\u4e0d\u8981\u751f\u706b' if explicit else '\u6700\u597d\u4e0d\u8981\u751f\u706b。'
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。' if explicit else text,
        {text: [mention(text.rstrip('。'), 'campfire', polarity='negative')]},
        explicit={'preferences': ['\u5373\u98df\u9910\u98df', text]} if explicit else None)
    result = interpreted(agent, input).result
    assert 'no_fires' not in result.extracted_requirements.mandatory_constraints
    assert text.rstrip('。') in result.extracted_requirements.preferences
    assert not result.field_errors


def test_scalar_only_need_sentence_does_not_create_a_facility_clarification():
    agent, input, _ = setup('I need two nights.')
    result = interpreted(agent, input).result
    assert not result.field_errors


@pytest.mark.parametrize('raw,quote', [
    ('\u51c6\u5907\u548c\u7537\u670b\u53cb\u4e00\u8d77\u53bb，\u60f3\u627e\u4e2a\u5b89\u9759\u7684\u5730\u65b9。', '\u60f3\u627e\u4e2a\u5b89\u9759\u7684\u5730\u65b9'),
    ('\u51c6\u5907\u548c\u6211\u7537\u670b\u53cb\u4e00\u8d77\u53bb，\u60f3\u627e\u4e2a\u5b89\u9759\u7684\u5730\u65b9', '\u60f3\u627e\u4e2a\u5b89\u9759\u7684\u5730\u65b9'),
    ('\u51c6\u5907\u548c\u6211\u7537\u670b\u53cb\u4e00\u8d77\u53bb，\u60f3\u627e\u4e2a\u5b89\u9759\u7684\u5730\u65b9', '\u5b89\u9759'),
])
def test_background_in_same_unsplit_sentence_is_not_an_omitted_condition(raw, quote):
    agent, input, requests = setup(raw, {raw: [mention(quote, 'quiet')]})
    result = interpreted(agent, input).result
    payload = json.loads(requests[0]['messages'][-1]['content'])
    assert len([source for source in payload['sources'] if source['source'] == 'raw_text']) == 1
    assert not result.field_errors and not result.clarifications
    assert set(result.extracted_requirements.preferences) == {'quiet', 'ready-to-eat meals'}


def test_unmapped_subjective_raw_description_is_retained_without_blocking_confirmation():
    raw = '\u5e0c\u671b\u73af\u5883\u5b89\u9759\u53c8\u80fd\u770b\u770b\u661f\u661f，\u9002\u5408\u548c\u7537\u670b\u53cb\u4e00\u8d77\u5f85\u7740。'
    agent, input, _ = setup(raw, {raw: [mention('\u5b89\u9759', 'quiet')]})
    result = interpreted(agent, input).result
    assert not result.field_errors and not result.clarifications
    assert set(result.extracted_requirements.preferences) == {'quiet', 'ready-to-eat meals'}
    assert any(raw in value for value in result.uncertainties)


def test_explicit_soft_remainder_is_preserved_as_unverified_preference():
    text = '\u5b89\u9759\u4e14\u9002\u5408\u770b\u661f\u661f'
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', {text: [mention('\u5b89\u9759', 'quiet')]},
        explicit={'preferences': ['\u5373\u98df\u9910\u98df', text]})
    result = interpreted(agent, input).result
    assert not result.field_errors and not result.clarifications
    assert text in result.extracted_requirements.preferences
    assert 'quiet' in result.extracted_requirements.preferences


@pytest.mark.parametrize('text,entry', [
    ('\u70ed\u6c34\u6dcb\u6d74', mention('\u70ed\u6c34\u6dcb\u6d74', 'showers', strength='hard')),
    ('private showers', mention('private showers', 'showers', strength='hard')),
    ('wifi', mention('wifi', None, strength='hard')),
])
def test_unverified_hard_modifiers_and_unknown_conditions_require_clarification(text, entry):
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', {text: [entry]}, explicit={'mandatory_constraints': [text]})
    result = interpreted(agent, input).result
    assert any(error.field == 'mandatory_constraints' and error.code == 'UNSUPPORTED' for error in result.field_errors)
    assert result.clarifications


def test_ambiguous_obligation_is_a_question_without_promoting_a_hard_constraint():
    raw = '\u540c\u884c\u7684\u4eba\u53ef\u80fd\u9700\u8981\u6d17\u6fa1。'
    agent, input, _ = setup(raw, {raw: [mention('\u53ef\u80fd\u9700\u8981\u6d17\u6fa1', 'showers', strength='uncertain', ambiguous=True)]})
    result = interpreted(agent, input).result
    assert result.clarifications
    assert 'showers' not in result.extracted_requirements.mandatory_constraints


def test_model_failure_propagates_without_rules_fallback():
    agent, input, requests = setup('\u9700\u8981\u6d17\u6fa1。', response=httpx.Response(503))
    with pytest.raises(ContractFailure) as error:
        interpreted(agent, input)
    assert error.value.error.code == 'AGENT_FAILURE'
    assert len(requests) == 1


def test_interpreter_identity_drift_during_completion_is_rejected(monkeypatch):
    raw = '\u9700\u8981\u6d17\u6fa1。'
    def drift(_):
        monkeypatch.setattr(request_interpretation, 'SYSTEM_PROMPT', request_interpretation.SYSTEM_PROMPT + '\nchanged')
    agent, input, _ = setup(raw, {raw: [mention('\u9700\u8981\u6d17\u6fa1', 'showers', strength='hard')]}, mutate=drift)
    with pytest.raises(ContractFailure) as error:
        interpreted(agent, input)
    assert error.value.error.code == 'STALE_CONTEXT'


def test_request_identity_does_not_change_planning_or_workflow_identity(monkeypatch):
    agent, _, _ = setup('\u9732\u8425\u5b89\u6392。')
    planner = agent.coordinator
    planning_identity = planner.identity
    context = agent.workflow_configuration.context.model_dump(mode='json')
    request_identity = planner.interpreter_identity
    monkeypatch.setattr(request_interpretation, 'SYSTEM_PROMPT', request_interpretation.SYSTEM_PROMPT + '\nchanged')
    assert planner.interpreter_identity != request_identity
    assert planner.identity == planning_identity
    assert agent.workflow_configuration.context.model_dump(mode='json') == context
    agent._check_configuration()
    legacy = HybridPlanningAgent(agent.dataset, planner, workflow_configuration=agent.workflow_configuration)
    assert legacy.model_request_terms is False
    assert legacy.request_interpretation_identity is None


@pytest.mark.parametrize('meal', ['ready-to-eat meals', 'self-catered meals'])
@pytest.mark.parametrize('canonical', ['known', 'unknown'])
def test_positive_meal_mode_is_not_an_unsupported_campsite_requirement(meal, canonical):
    raw = f'Two people camping near Sydney, {meal}.'
    agent, input, requests = setup(raw, {
        raw: [mention(meal, meal if canonical == 'known' else None, strength='hard')],
        meal: [mention(meal, meal)],
    }, explicit={'preferences': [meal]})
    original = input.model_dump(mode='json')
    result = interpreted(agent, input).result
    assert result.extracted_requirements.preferences == [meal]
    assert result.extracted_requirements.mandatory_constraints == []
    assert not result.field_errors and not result.clarifications
    assert input.model_dump(mode='json') == original and len(requests) == 1


@pytest.mark.parametrize('text,meal', [
    ('\u5fc5\u987b\u5373\u98df\u9910\u98df', 'ready-to-eat meals'),
    ('We need self-catered meals', 'self-catered meals'),
    ('\u65e0\u9700\u70f9\u996a\u7684\u9910\u98df', 'ready-to-eat meals'),
])
def test_explicit_meal_arrangement_can_be_required_without_becoming_a_facility(text, meal):
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', {text: [mention(text, meal, strength='hard')]},
        explicit={'preferences': [], 'mandatory_constraints': [text]})
    result = interpreted(agent, input).result
    assert result.extracted_requirements.preferences == [meal]
    assert result.extracted_requirements.mandatory_constraints == []
    assert not result.field_errors and not result.clarifications


def test_meal_mode_does_not_relax_separate_hard_facilities():
    raw = 'We need showers and ready-to-eat meals.'
    agent, input, _ = setup(raw, {raw: [mention('need showers', 'showers', strength='hard'),
        mention('ready-to-eat meals', 'ready-to-eat meals', strength='hard')]})
    result = interpreted(agent, input).result
    assert result.extracted_requirements.mandatory_constraints == ['showers']
    assert result.extracted_requirements.preferences == ['ready-to-eat meals']
    assert not result.field_errors and not result.clarifications


def test_conflicting_meal_modes_still_require_a_choice():
    raw = 'We need self-catered meals.'
    agent, input, _ = setup(raw, {raw: [mention('need self-catered meals', 'self-catered meals', strength='hard')]})
    result = interpreted(agent, input).result
    assert any(e.field == 'preferences' and e.code == 'CONFLICTING' for e in result.field_errors)
    assert result.clarifications


@pytest.mark.parametrize('polarity', ['negative', 'not_required'])
def test_negative_meal_mode_is_not_converted_to_a_positive_choice(polarity):
    raw = 'We do not need ready-to-eat meals.'
    agent, input, _ = setup(raw, {raw: [mention('do not need ready-to-eat meals',
        'ready-to-eat meals', polarity=polarity, strength='hard')]}, explicit={'preferences': []})
    result = interpreted(agent, input).result
    assert 'ready-to-eat meals' not in result.extracted_requirements.preferences
    assert result.clarifications


def test_required_dietary_details_are_not_dropped_when_routing_meal_mode():
    text = 'gluten-free ready-to-eat meals'
    agent, input, _ = setup('\u9732\u8425\u5b89\u6392。', {text: [mention(text, 'ready-to-eat meals', strength='hard')]},
        explicit={'preferences': [], 'mandatory_constraints': [text]})
    result = interpreted(agent, input).result
    assert result.clarifications
    assert any(e.field == 'mandatory_constraints' for e in result.field_errors)


def test_known_meal_quote_cannot_be_assigned_an_unrelated_hard_facility():
    raw = 'We need ready-to-eat meals.'
    agent, input, _ = setup(raw, {raw: [mention('ready-to-eat meals', 'showers', strength='hard')]})
    with pytest.raises(ContractFailure) as caught:
        interpreted(agent, input)
    assert caught.value.error.code == 'CONTRACT_INVALID'
