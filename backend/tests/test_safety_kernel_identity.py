"""R-S01: full A35 baseline, closed identity pairs and authentic old replay.

All requests use MockTransport. Role combinations exercise component identity
composition, not production safety registration, persistence or activation.
"""
import asyncio
from copy import deepcopy

import pytest

from app.adapters.synthetic_dataset_v2 import V2_RULES_VERSION
from app.agents.hybrid_planning_agent import build_hybrid_configuration
from app.agents.rules.common import RULES_VERSION, LEGACY_RULES_VERSION, meal_mode
from app.agents.rules.safety import propose_route
from app.application.logistics_audit import identity_seed as logistics_seed
from app.contracts.errors import ContractFailure
from app.llm.coordinator import PlanningCoordinator, digest
from app.llm.logistics_agent import LogisticsAgent
from app.llm.safety_contract import safety_contract_document
from app.llm.safety_identity import (SafetyIdentitySeed, SUPPORTED_KERNEL_RULE_PAIRS,
    compose_safety_identity, validate_safety_identity)
from app.llm.safety_schema import canonical
from app.llm.safety_validation import safety_validator_for
from safety_fixtures import safety_fixture, safety_agent_fixture, saved_safety_archive

OLD_KERNEL = 'b02-v1-rules-2'
NEW_KERNEL = 'b02-v1-rules-2/a-meal-clarification-v1'
OLD_RULES = 'b02-v2-rules-2/trip-evidence-selection-1'
NEW_RULES = 'b02-v2-rules-2/a-meal-clarification-v1/trip-evidence-selection-1'
PROMPT_V2 = '348dcee55454f9d25f65e9e4d128858be182e512bc22dabf79f2d286c0865d31'


@pytest.fixture(scope='module')
def normal():
    return safety_fixture()


def test_actual_shared_baseline_registers_current_values_without_relabelling(normal):
    dataset,input,config,baseline,_ = normal
    assert RULES_VERSION == NEW_KERNEL and LEGACY_RULES_VERSION == OLD_KERNEL
    assert V2_RULES_VERSION == 'b02-v2-rules-2/a-meal-clarification-v1'
    assert dataset.rules_version == NEW_RULES
    agent,requests = safety_agent_fixture(dataset,config)
    seed = agent.identity_seed
    assert seed['kernel_version'] == NEW_KERNEL
    assert seed['dataset_rules_version'] == NEW_RULES
    assert seed['prompt_sha256'] == PROMPT_V2
    outcome = asyncio.run(agent.assess_safety_with_trace(input))
    assert len(requests) == 3 and outcome.assessment == baseline
    assert outcome.trace.configuration_fingerprint == agent.identity['configuration_fingerprint']
    agent.validate_safety_artifacts(input,baseline,outcome.plan.model_dump(mode='json'),
        outcome.trace.model_dump(mode='json'))


@pytest.mark.parametrize('kernel,rules',[(OLD_KERNEL,OLD_RULES),(NEW_KERNEL,NEW_RULES)])
def test_exact_supported_pairs_validate_and_roundtrip_without_coercion(normal,kernel,rules):
    agent,_ = safety_agent_fixture(normal[0],normal[2])
    seed = {**agent.identity_seed,'kernel_version':kernel,'dataset_rules_version':rules}
    assert SafetyIdentitySeed.model_validate(seed).model_dump(mode='json',exclude_none=True) == seed
    identity = compose_safety_identity(seed,normal[2].context)
    assert validate_safety_identity(identity) == identity
    # Seed validation is not permission to register or replay against this
    # unrelated context; A supplies the trusted saved identity at that boundary.


@pytest.mark.parametrize('field,value',[
    ('kernel_version','unknown-kernel'),('kernel_version',NEW_KERNEL+'/future'),
    ('kernel_version','b02-v1-rules-20'),('kernel_version',True),
    ('dataset_rules_version','unknown-rules'),('dataset_rules_version',NEW_RULES+'/future'),
    ('dataset_rules_version','b02-v2-rules-2'),('dataset_rules_version',False),
    ('kernel_version',OLD_KERNEL),('dataset_rules_version',OLD_RULES),
])
def test_unknown_values_and_cross_paired_identities_fail_closed(normal,field,value):
    agent,_ = safety_agent_fixture(normal[0],normal[2])
    seed = {**agent.identity_seed,field:value}
    with pytest.raises(ValueError):
        SafetyIdentitySeed.model_validate(seed)
    with pytest.raises(ValueError):
        compose_safety_identity(seed,normal[2].context)


def test_identity_schema_records_the_same_closed_pairs_and_extra_key_guard(normal):
    schema = SafetyIdentitySeed.model_json_schema()
    expected = [(OLD_KERNEL,OLD_RULES),(NEW_KERNEL,NEW_RULES)]
    assert list(SUPPORTED_KERNEL_RULE_PAIRS) == expected
    assert schema['additionalProperties'] is False
    assert schema['anyOf'] == [{'properties':{'kernel_version':{'const':kernel},
        'dataset_rules_version':{'const':rules}}} for kernel,rules in expected]
    assert schema['properties']['kernel_version']['enum'] == [OLD_KERNEL,NEW_KERNEL]
    assert schema['properties']['dataset_rules_version']['enum'] == [OLD_RULES,NEW_RULES]
    assert safety_contract_document()['supported_kernel_rule_pairs'] == [
        {'kernel_version':kernel,'dataset_rules_version':rules} for kernel,rules in expected]
    agent,_ = safety_agent_fixture(normal[0],normal[2])
    with pytest.raises(ValueError):
        SafetyIdentitySeed.model_validate({**agent.identity_seed,'unregistered':True})


@pytest.mark.parametrize('kernel,rules',[
    ('unknown-kernel',NEW_RULES),(OLD_KERNEL,NEW_RULES),(NEW_KERNEL,OLD_RULES),
    (NEW_KERNEL,'unknown-rules')])
def test_unsupported_live_registration_fails_before_inference(normal,monkeypatch,kernel,rules):
    from app.llm import safety_identity
    dataset,_,config,_,_ = deepcopy(normal)
    dataset.rules_version = rules
    monkeypatch.setattr(safety_identity,'RULES_VERSION',kernel)
    # Construction rejects rather than silently substituting an old identity.
    # The MockTransport is never invoked by component construction.
    with pytest.raises(ContractFailure) as exc:
        safety_agent_fixture(dataset,config)
    assert exc.value.error.code == 'CONTRACT_INVALID'


@pytest.mark.parametrize('version',['v1','v2'])
def test_saved_old_kernel_archives_replay_unchanged_without_live_dataset(version):
    input,baseline,plan,trace,identity,selection = saved_safety_archive(version)
    before = canonical({'input':input.model_dump(mode='json'),'baseline':baseline.model_dump(mode='json'),
        'plan':plan,'trace':trace,'identity':identity,'selection':selection.model_dump(mode='json')})
    assert identity['kernel_version'] == OLD_KERNEL and identity['dataset_rules_version'] == OLD_RULES
    replay = safety_validator_for(identity['validation_version'])
    restored_plan,restored_trace = replay(input,baseline,baseline,plan,trace,
        identity=identity,selection=selection)
    assert restored_plan.model_dump(mode='json') == plan
    assert restored_trace.model_dump(mode='json') == trace
    assert canonical({'input':input.model_dump(mode='json'),'baseline':baseline.model_dump(mode='json'),
        'plan':plan,'trace':trace,'identity':identity,'selection':selection.model_dump(mode='json')}) == before


@pytest.mark.parametrize('version',['v1','v2'])
@pytest.mark.parametrize('mutation',['kernel','fingerprint','source','refs','input','baseline','selection'])
def test_old_replay_still_rejects_tampering(version,mutation):
    input,baseline,plan,trace,identity,selection = saved_safety_archive(version)
    if mutation == 'kernel':
        identity['kernel_version'] = 'unknown-kernel'
        values = {key:value for key,value in identity.items() if key != 'configuration_fingerprint'}
        identity['configuration_fingerprint'] = trace['configuration_fingerprint'] = digest(canonical(values))
    elif mutation == 'fingerprint': identity['configuration_fingerprint'] = 'f'*64
    elif mutation == 'source': plan['source_refs'] = []
    elif mutation == 'refs': plan['findings'][0]['fact_refs'] = ['/unregistered']
    elif mutation == 'input':
        input = input.model_copy(update={'version_context':input.version_context.model_copy(update={'run_id':'other-run'})})
    elif mutation == 'baseline': baseline = baseline.model_copy(update={'recommended_actions':['Changed baseline.']})
    else: selection = selection.model_copy(update={'selected_case_ids':['unregistered-case']})
    with pytest.raises(ContractFailure):
        safety_validator_for(identity['validation_version'])(input,baseline,baseline,plan,trace,
            identity=identity,selection=selection)


def test_old_v2_trace_cannot_be_relabelled_as_current_outcome(normal):
    input,baseline,plan,trace,identity,selection = saved_safety_archive('v2')
    current,_ = safety_agent_fixture(normal[0],normal[2])
    assert identity['prompt_sha256'] == current.identity['prompt_sha256'] == PROMPT_V2
    assert identity['configuration_fingerprint'] != current.identity['configuration_fingerprint']
    assert identity['workflow_context'] != current.identity['workflow_context']
    with pytest.raises(ContractFailure):
        safety_validator_for(identity['validation_version'])(input,baseline,baseline,plan,trace,
            identity=current.identity,selection=selection)


@pytest.mark.parametrize('logistics_model,safety_model',[(False,False),(True,False),(False,True),(True,True)])
def test_all_role_combinations_collect_seeds_then_bind_one_final_context(normal,logistics_model,safety_model):
    dataset,_,base,_,_ = normal
    temporary_safety,_ = safety_agent_fixture(dataset,base)
    client = temporary_safety.client
    temporary_logistics = LogisticsAgent(dataset,client,workflow_configuration=base)
    seeds = {'LOGISTICS':logistics_seed(temporary_logistics),'SAFETY':temporary_safety.identity_seed}
    choices = dict(base.context.selection_config)
    suffixes = []
    for enabled,role in ((logistics_model,'LOGISTICS'),(safety_model,'SAFETY')):
        if enabled:
            name = role.lower()
            choices.update({f'a_{name}_mode':'model',f'a_{name}_audit_required':'1',
                f'a_{name}_audit_contract':'1.0',f'a_{name}_identity_seed':canonical(seeds[role])})
            suffixes.append(f'/a-model-{name}-audit-v1')
    registered = dataset.context.model_copy(update={'selection_config':choices,
        'rules_version':dataset.context.rules_version+''.join(suffixes)})
    coordinator = PlanningCoordinator(dataset,client)
    final = build_hybrid_configuration(dataset,coordinator,registered_context=registered)
    current_safety,_ = safety_agent_fixture(dataset,final)
    current_logistics = LogisticsAgent(dataset,client,workflow_configuration=final)
    context = final.context.model_dump(mode='json')
    assert current_safety.identity['workflow_context'] == current_logistics.identity['workflow_context'] == context
    for agent,role in ((current_safety,'SAFETY'),(current_logistics,'LOGISTICS')):
        assert agent.identity['kernel_version'] == NEW_KERNEL
        assert agent.identity['dataset_rules_version'] == NEW_RULES
        assert agent.identity['configuration_fingerprint'] == digest(canonical({**seeds[role],'workflow_context':context}))
    assert current_safety.identity_seed == seeds['SAFETY']
    assert logistics_seed(current_logistics) == seeds['LOGISTICS']
    assert ('a_safety_identity_seed' in context['selection_config']) is safety_model
    assert ('a_logistics_identity_seed' in context['selection_config']) is logistics_model
    if logistics_model and safety_model:
        # Appending safety markers after registering logistics is NOT equivalent.
        assert current_logistics.identity['configuration_fingerprint'] != temporary_logistics.identity['configuration_fingerprint']
    assert current_safety.identity['configuration_fingerprint'] != current_logistics.identity['configuration_fingerprint']


def test_new_meal_clarification_remains_unresolved_in_safety_advice():
    dataset,input,config,baseline,_ = safety_fixture(preferences=[])
    assert meal_mode(input.confirmed_requirements) is None
    assert any(item.field == 'meal_mode' for item in input.saved_logistics_assessment.result.clarifications)
    assert propose_route(input.saved_logistics_assessment,baseline) == 'REVISION_REQUIRED'
    agent,_ = safety_agent_fixture(dataset,config)
    outcome = asyncio.run(agent.assess_safety_with_trace(input))
    assert outcome.assessment == baseline
    assert any(item.action_code == 'RESOLVE_LOGISTICS' for item in outcome.plan.findings)
    assert propose_route(input.saved_logistics_assessment,outcome.assessment) == 'REVISION_REQUIRED'
