"""R-S02 text-policy v2, unchanged original text and frozen v1 replay."""
import asyncio
from copy import deepcopy
import json
import sys
import unicodedata

import pytest

from app.contracts.errors import ContractFailure
from app.llm.coordinator import digest
from app.llm.client import CampusModelClient
from app.llm.safety_schema import (SafetyProposal, parse_safety_action, check_advice,
    ADVICE_TEXT_POLICY, ADVICE_SCHEMA_POLICY, SAFETY_VALIDATION_VERSION)
from app.llm.safety_tools import ValidatedSafetyPlan
from app.llm.safety_validation import safety_validator_for, validate_safety_payload
from app.llm.safety_v1 import safety_schema as v1_schema
from app.llm.safety_v1.safety_identity import safety_identity_seed as v1_seed, compose_safety_identity as v1_identity
from app.llm.safety_v1.safety_tools import SafetyToolset as V1Toolset
from llm_fixtures import model_settings
from safety_fixtures import safety_fixture, safety_agent_fixture, proposal_from_safety_facts

FIELDS = ('interpretation_unverified','action_unverified','decision_summary_unverified')
CONTROL_SAMPLES = ('\x00','\x1b','\x7f','\x80','\x85','\x9f','\u00ad','\u061c',
    '\u200b','\u200d','\u200e','\u202a','\u202e','\u2066','\u2069','\ufeff','\u2028','\u2029')
LINK_SAMPLES = (
    'See www.example.com for guidance.',
    'See WWW.EXAMPLE.COM for guidance.',
    'See https://example.com for guidance.',
    'See HTTPS://EXAMPLE.COM for guidance.',
    'See http:example.com for guidance.',
    'See ftp://example.com for guidance.',
    'See sftp:example for guidance.',
    'See file:///guidance for guidance.',
    'See custom+guide://host for guidance.',
    'See mailto:guide@example.com for guidance.',
    'Contact guide@example.org for guidance.',
    'See example.com for guidance.',
    'See campmate.local/path for guidance.',
    'See //example.org/path for guidance.',
    'See data:text/plain,advice for guidance.',
    'See javascript:alert for guidance.',
    'See tel:contact for guidance.',
    'See [guide](/local-help) for guidance.',
    'See [guide](example.com) for guidance.',
    'See 例子.测试 for guidance.',
    'See café.example for guidance.',
    'See example。com for guidance.',
    'See example．com for guidance.',
    'See example｡com for guidance.',
)


def single_proposal(text,field):
    p={'findings':[{'finding_key':'finding-'+'a'*64,
        'interpretation_unverified':'Consider the recorded evidence.',
        'action_code':'ACKNOWLEDGE_INFORMATION','action_unverified':'Check the registered conditions.'}],
        'action_priority':['finding-'+'a'*64],'decision_summary_unverified':'Keep recorded checks unresolved where applicable.'}
    target=p if field=='decision_summary_unverified' else p['findings'][0]
    target[field]=text
    return p


@pytest.mark.parametrize('field',FIELDS)
@pytest.mark.parametrize('char',CONTROL_SAMPLES,ids=lambda value:'U+'+format(ord(value),'04X'))
def test_controls_formats_and_line_separators_rejected_in_every_text_field(field,char):
    p=single_proposal('Review'+char+'the registered evidence.',field)
    with pytest.raises(ValueError):SafetyProposal.model_validate(p)
    with pytest.raises(ContractFailure):parse_safety_action(json.dumps({'action':'final','proposal':p}))


def test_every_unicode_cc_cf_character_is_rejected_when_embedded():
    checked=0
    for code in range(sys.maxunicode+1):
        char=chr(code)
        if unicodedata.category(char) in {'Cc','Cf'}:
            with pytest.raises(ValueError):check_advice('Review'+char+'the registered evidence.')
            checked+=1
    assert checked>100


@pytest.mark.parametrize('field',FIELDS)
@pytest.mark.parametrize('text',LINK_SAMPLES)
def test_declared_link_forms_rejected_in_every_text_field(field,text):
    p=single_proposal(text,field)
    with pytest.raises(ValueError):SafetyProposal.model_validate(p)
    with pytest.raises(ContractFailure):parse_safety_action(json.dumps({'action':'tool',
        'name':'evaluate_safety_plan','arguments':p}))


@pytest.mark.parametrize('text',[
    'Review the registered evidence before departure.',
    'Café arrangements remain unconfirmed.',
    'Weather: check the host-provided forecast window.',
    'Use e.g. the recorded facts rather than guesses.',
    'Read the U.S. context as unverified source text.',
    '  Keep the original spacing unchanged.  ',
    'Review\u00a0the recorded evidence.',
])
@pytest.mark.parametrize('field',FIELDS)
def test_permitted_english_text_is_preserved_not_cleaned_or_ascii_only(text,field):
    p=single_proposal(text,field)
    model=SafetyProposal.model_validate(p)
    value=model.decision_summary_unverified if field=='decision_summary_unverified' else getattr(model.findings[0],field)
    assert value==text
    assert model.model_dump(mode='json')==p


@pytest.fixture(scope='module')
def normal():return safety_fixture()


@pytest.mark.parametrize('field',FIELDS)
@pytest.mark.parametrize('text',['Review\u0085the evidence.','Review\u202ethe evidence.',
    'See www.example.com for guidance.'])
@pytest.mark.parametrize('stage',[2,3])
def test_agent_rejects_invalid_evaluation_and_final_without_result_or_fallback(normal,field,text,stage):
    dataset,input,config,_,_=normal
    def mutate(turn,action):
        if turn==stage:
            p=action['arguments'] if stage==2 else action['proposal']
            target=p if field=='decision_summary_unverified' else p['findings'][0]
            target[field]=text
        return action
    agent,requests=safety_agent_fixture(dataset,config,mutate=mutate)
    with pytest.raises(ContractFailure) as exc:asyncio.run(agent.assess_safety_with_trace(input))
    assert exc.value.error.code=='CONTRACT_INVALID'
    assert len(requests)==stage


@pytest.mark.parametrize('field',FIELDS)
def test_validated_plan_cannot_bypass_new_text_policy(normal,field):
    dataset,input,config,_,_=normal
    agent,_=safety_agent_fixture(dataset,config)
    outcome=asyncio.run(agent.assess_safety_with_trace(input))
    raw=outcome.plan.model_dump(mode='json')
    target=raw if field=='decision_summary_unverified' else raw['findings'][0]
    target[field]='Review\u202ethe recorded evidence.'
    with pytest.raises(ValueError):ValidatedSafetyPlan.model_validate(raw)


def legacy_archive(normal):
    dataset,input,config,baseline,selection=normal
    # Explicit synthetic ARCHIVAL fixture, not a live model transcript. It
    # intentionally contains text allowed by v1 but forbidden for new requests.
    identity=v1_identity(v1_seed(dataset,CampusModelClient(model_settings()).identity),config.context)
    tools=V1Toolset(input,baseline,selection=selection)
    raw=proposal_from_safety_facts(tools.read_safety_facts())
    raw['decision_summary_unverified']='See www.example.com for guidance.'
    raw['findings'][0]['interpretation_unverified']='Review\u0085the registered evidence.'
    proposal=v1_schema.SafetyProposal.model_validate(raw)
    plan=tools.evaluate_safety_plan(proposal)
    trace=v1_schema.SafetyTrace(role='SAFETY',requested_model='campus-qwen',served_models=[],
        configuration_fingerprint=identity['configuration_fingerprint'],input_sha256=digest(input.model_dump_json()),
        rule_facts_sha256=digest(baseline.model_dump_json()),proposal_sha256=tools.proposal_hash(proposal),
        prompt_sha256=identity['prompt_sha256'],tool_version='safety-read-only-tools-1',turns=3,http_attempts=3,
        elapsed_ms=0,tool_calls=['read_safety_facts','evaluate_safety_plan'],response_sha256=['a'*64]*3,
        usage={},validation_passed=True)
    return input,baseline,plan.model_dump(mode='json'),trace.model_dump(mode='json'),identity,selection


def test_frozen_v1_replays_original_allowed_text_without_cleaning(normal):
    input,baseline,plan,trace,identity,selection=legacy_archive(normal)
    replay=safety_validator_for('safety-advisory-validation-1')
    restored,_=replay(input,baseline,baseline,plan,trace,identity=identity,selection=selection)
    assert restored.model_dump(mode='json')==plan
    assert '\u0085' in restored.findings[0].interpretation_unverified
    assert restored.decision_summary_unverified=='See www.example.com for guidance.'


def test_frozen_v1_still_rejects_tampered_artifacts(normal):
    input,baseline,plan,trace,identity,selection=legacy_archive(normal)
    plan['source_refs']=[]
    with pytest.raises(ContractFailure):safety_validator_for('safety-advisory-validation-1')(
        input,baseline,baseline,plan,trace,identity=identity,selection=selection)


def test_current_registration_and_validator_cannot_downgrade_to_v1(normal):
    input,baseline,plan,trace,identity,selection=legacy_archive(normal)
    with pytest.raises(ContractFailure):validate_safety_payload(input,baseline,baseline,plan,trace,
        identity=identity,selection=selection)
    agent,_=safety_agent_fixture(normal[0],normal[2])
    seed=agent.identity_seed
    assert seed['agent_version']=='campus-safety-advisory-agent-2'
    assert seed['tool_version']=='safety-read-only-tools-2'
    assert seed['validation_version']==SAFETY_VALIDATION_VERSION=='safety-advisory-validation-2'
    assert seed['prompt_sha256']!=identity['prompt_sha256']
    assert agent.identity['configuration_fingerprint']!=identity['configuration_fingerprint']
    assert safety_validator_for(SAFETY_VALIDATION_VERSION) is validate_safety_payload


def test_policy_metadata_binds_semantics_and_unicode_database():
    assert ADVICE_TEXT_POLICY['unicode_data_version']==unicodedata.unidata_version
    assert set(ADVICE_TEXT_POLICY['excluded_unicode_categories'])=={'Cc','Cf','Zl','Zp'}
    assert ADVICE_SCHEMA_POLICY['x-safety-text-policy']=='safety-advice-text-2'
    assert len(ADVICE_SCHEMA_POLICY['x-safety-text-policy-sha256'])==64
    props=SafetyProposal.model_json_schema()['properties']
    assert props['decision_summary_unverified']['x-safety-text-policy-sha256']==ADVICE_SCHEMA_POLICY['x-safety-text-policy-sha256']
