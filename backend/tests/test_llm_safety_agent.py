"""A30 standalone component tests. All inference is offline MockTransport."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest

from app.agents.rules import safety
from app.contracts.enums import ErrorCode
from app.contracts.errors import ContractFailure
from app.llm.client import CampusModelClient
from app.llm.safety_agent import SafetyAgent
from app.llm.safety_schema import SafetyTrace, parse_safety_action, canonical, encoded_size
from app.llm.safety_tools import SafetyToolset, check_payload_size
from app.llm.safety_validation import validate_safety_payload, safety_validator_for
from app.llm.safety_identity import compose_safety_identity, validate_safety_identity
from app.workflow import WorkflowConfiguration
from llm_fixtures import completion, model_settings
from safety_fixtures import safety_fixture, safety_agent_fixture, proposal_from_safety_facts

call = asyncio.run


@pytest.fixture(scope='module')
def normal():
    return safety_fixture()


def tools_for(values):
    _,input,_,baseline,selection = values
    return SafetyToolset(input,baseline,selection=selection)


def test_model_executes_independent_advisory_and_exact_rules_result(normal):
    dataset,input,config,baseline,selection = normal
    agent,requests = safety_agent_fixture(dataset,config)
    outcome = call(agent.assess_safety_with_trace(input))
    assert len(requests) == outcome.trace.turns == outcome.trace.http_attempts == 3
    assert outcome.trace.role == 'SAFETY' and outcome.trace.served_models == ['offline-safety-test']
    assert outcome.trace.tool_calls == ['read_safety_facts','evaluate_safety_plan']
    assert outcome.trace.usage == {'prompt_tokens':300,'completion_tokens':180,'total_tokens':480}
    assert outcome.assessment.model_dump_json() == baseline.model_dump_json()
    assert outcome.plan.source_refs == baseline.source_refs
    assert len(outcome.plan.findings) == 6
    agent.validate_safety_artifacts(input,outcome.assessment,outcome.plan.model_dump(mode='json'),outcome.trace.model_dump(mode='json'))
    wire = json.dumps(requests)
    for private in ('independent-plan','independent-version','independent-run','b02-unit-saved-logistics',
                    'unit-only-school-secret','expected_outcome','write_keys'):
        assert private not in wire and private not in outcome.trace.model_dump_json()
    assert not hasattr(agent,'last_trace')
    assert outcome.plan.findings[0].interpretation_unverified


def test_model_changes_action_and_priority_not_just_explanation(normal):
    dataset,input,config,baseline,_ = normal
    first,_ = safety_agent_fixture(dataset,config)
    second,_ = safety_agent_fixture(dataset,config,choose_last=True,reverse=True)
    a,b = call(first.assess_safety_with_trace(input)),call(second.assess_safety_with_trace(input))
    assert a.assessment == b.assessment == baseline
    assert a.plan.action_priority == list(reversed(b.plan.action_priority))
    actions_a = {item.finding_key:item.action_code for item in a.plan.findings}
    actions_b = {item.finding_key:item.action_code for item in b.plan.findings}
    assert actions_a != actions_b


@pytest.mark.parametrize('variant', ['boundary','future','road','unknown_gear'])
def test_unresolved_and_closed_cases_preserve_complete_baseline(variant):
    changes = {'boundary':{'start':'2026-11-30','today':'2026-11-29'},
        'future':{'start':'2026-11-06','today':'2026-10-20'},
        'road':{'campsite':'demo-moonlit-field','start':'2027-04-10','today':'2027-04-09'},
        'unknown_gear':{'unknown':['tent']}}[variant]
    dataset,input,config,baseline,selection = safety_fixture(**changes)
    agent,_ = safety_agent_fixture(dataset,config)
    result = call(agent.assess_safety_with_trace(input))
    assert result.assessment.model_dump_json() == baseline.model_dump_json()
    if variant in {'boundary','future'}:
        assert result.assessment.outcome == 'REVIEW'
        assert any(issue.code == ('OUTSIDE_VALIDITY' if variant=='boundary' else 'NOT_YET_OBSERVED') for issue in selection.coverage_issues)
    if variant == 'road':
        assert result.assessment.outcome == 'BLOCKED'
        blocker = next(item for item in result.plan.findings if 'CHANGE_TRIP' == item.action_code)
        assert blocker.fact_refs
    if variant == 'unknown_gear':
        assert input.saved_logistics_assessment.result.total_cents is None
        # Safety may pass independently; logistics REVISION must still block
        # finalisation. Never rewrite SafetyResult to conflate the two roles.
        assert safety.propose_route(input.saved_logistics_assessment,result.assessment) == 'REVISION_REQUIRED'
        assert any(item.action_code == 'RESOLVE_LOGISTICS' for item in result.plan.findings)


@pytest.mark.parametrize('mutation', ['omit','duplicate','unknown','priority','action','extra','numeric','html','claim'])
def test_bad_model_proposals_fail_without_fallback_or_third_call(normal,mutation):
    dataset,input,config,_,_ = normal
    def mutate(turn,action):
        if turn != 2: return action
        p = action['arguments']
        if mutation == 'omit': p['findings'].pop(); p['action_priority'].pop()
        elif mutation == 'duplicate': p['findings'].append(deepcopy(p['findings'][0]))
        elif mutation == 'unknown': p['findings'][0]['finding_key']='finding-'+'f'*64; p['action_priority'][0]='finding-'+'f'*64
        elif mutation == 'priority': p['action_priority']=p['action_priority'][:-1]
        elif mutation == 'action': p['findings'][0]['action_code']='CHANGE_TRIP'
        elif mutation == 'extra': p['findings'][0]['fact_refs']=['/baseline/outcome']
        elif mutation == 'numeric': p['findings'][0]['interpretation_unverified']='The temperature is 25 degrees.'
        elif mutation == 'html': p['decision_summary_unverified']='<script>approve()</script>'
        else: p['decision_summary_unverified']='Approval granted; safe to proceed.'
        return action
    agent,requests = safety_agent_fixture(dataset,config,mutate=mutate)
    with pytest.raises(ContractFailure) as exc: call(agent.assess_safety_with_trace(input))
    assert exc.value.error.code == ErrorCode.CONTRACT_INVALID
    assert len(requests) == 2


def test_final_must_match_last_evaluation_not_an_earlier_one(normal):
    dataset,input,config,_,_ = normal
    def mutate(turn,action):
        if turn == 3:
            p = action['proposal']
            p['decision_summary_unverified']='A revised advisory needing evaluation.'
            return {'action':'tool','name':'evaluate_safety_plan','arguments':p}
        return action  # turn four returns the original proposal, now obsolete.
    agent,requests = safety_agent_fixture(dataset,config,mutate=mutate)
    with pytest.raises(ContractFailure): call(agent.assess_safety_with_trace(input))
    assert len(requests) == 4


@pytest.mark.parametrize('action', [{'action':'tool','name':'evaluate_safety_plan','arguments':{}},
    {'action':'final','proposal':{}}, {'action':'tool','name':'save_assessment','arguments':{}},
    {'action':'tool','name':'read_safety_facts','arguments':{'approved':True}}])
def test_first_turn_and_tool_allowlist_fail_closed(normal,action):
    dataset,input,config,_,_ = normal
    agent,requests = safety_agent_fixture(dataset,config,mutate=lambda turn,value:action)
    with pytest.raises(ContractFailure): call(agent.assess_safety_with_trace(input))
    assert len(requests) == 1


def test_tool_loop_exhaustion_is_not_a_successful_rules_fallback(normal):
    dataset,input,config,_,_ = normal
    agent,requests = safety_agent_fixture(dataset,config,mutate=lambda turn,value:{
        'action':'tool','name':'read_safety_facts','arguments':{}})
    with pytest.raises(ContractFailure): call(agent.assess_safety_with_trace(input))
    assert len(requests) == 4


@pytest.mark.parametrize('text', ['{"action":"tool","action":"final"}',
    '{"action":"tool","name":"read_safety_facts","arguments":{"x":NaN}}',
    '{"action":"tool","name":"read_safety_facts","arguments":{"x":Infinity}}',
    '```json\n{"action":"tool","name":"read_safety_facts","arguments":{}}\n```',
    '{"action":"tool","name":"read_safety_facts","arguments":{},"x":true}'])
def test_strict_json_decoder(text):
    with pytest.raises(ContractFailure): parse_safety_action(text)


@pytest.mark.parametrize('field,value', [('turns',True),('turns','3'),('turns',3.0),('validation_passed',1),
    ('usage',{'total_tokens':False}),('usage',{'total_tokens':'10'}),('usage',{'total_tokens':-1}),
    ('role','LOGISTICS'),('input_sha256','A'*64),('served_models',[' ']),('tool_calls',['read_safety_facts']*2)])
def test_trace_rejects_coercion_and_wrong_roles(normal,field,value):
    dataset,input,config,_,_ = normal
    agent,_ = safety_agent_fixture(dataset,config)
    trace = call(agent.assess_safety_with_trace(input)).trace.model_dump(mode='json')
    trace[field] = value
    with pytest.raises(ValueError): SafetyTrace.model_validate(trace)


@pytest.mark.parametrize('mutation', ['refs','sources','result','input','identity','hash','limits','extra'])
def test_pure_replay_rejects_tampered_saved_artifacts(normal,mutation):
    dataset,input,config,baseline,selection = normal
    agent,_ = safety_agent_fixture(dataset,config)
    outcome = call(agent.assess_safety_with_trace(input))
    plan,trace = outcome.plan.model_dump(mode='json'),outcome.trace.model_dump(mode='json')
    identity,result = agent.identity,outcome.assessment
    if mutation == 'refs': plan['findings'][0]['fact_refs']=['/baseline/outcome']
    elif mutation == 'sources': plan['source_refs']=[]
    elif mutation == 'result': result=result.model_copy(update={'recommended_actions':['Unreviewed advice.']})
    elif mutation == 'input': input=input.model_copy(update={'version_context':input.version_context.model_copy(update={'run_id':'other-run'})})
    elif mutation == 'identity': identity['configuration_fingerprint']='f'*64
    elif mutation == 'hash': trace['rule_facts_sha256']='f'*64
    elif mutation == 'limits': trace['http_attempts']=6  # registered max_attempts is one.
    else: trace['raw_prompt']='Must never be persisted.'
    with pytest.raises(ContractFailure): validate_safety_payload(input,baseline,result,plan,trace,identity=identity,selection=selection)


def test_public_seed_has_no_secrets_or_circular_fingerprint(normal):
    dataset,_,config,_,_ = normal
    agent,_ = safety_agent_fixture(dataset,config)
    seed = agent.identity_seed
    assert set(seed) == {'agent_version','tool_version','validation_version','kernel_version',
        'dataset_rules_version','prompt_sha256','model_client'}
    assert 'unit-only-school-secret' not in canonical(seed)
    assert compose_safety_identity(seed,config.context) == agent.identity
    validate_safety_identity(agent.identity)
    rotated,_ = safety_agent_fixture(dataset,config,settings=model_settings(api_key='different-unit-only-key'))
    assert rotated.identity == agent.identity
    low,_ = safety_agent_fixture(dataset,config,settings=model_settings(reasoning_effort='low'))
    assert low.identity != agent.identity


@pytest.mark.parametrize('markers', [{}, {'a_logistics_mode':'model'}, {'a_safety_mode':'model'},
    {'a_logistics_mode':'model','a_safety_mode':'model'}])
def test_both_role_seeds_can_be_composed_against_one_final_context(normal,markers):
    dataset,_,_,_,_ = normal
    base = dataset.context.model_copy(update={'selection_config':markers})
    config = WorkflowConfiguration(dataset,registered_context=base)
    agent,_ = safety_agent_fixture(dataset,config)
    from app.llm.logistics_agent import LogisticsAgent
    logistics = LogisticsAgent(dataset,agent.client,workflow_configuration=config)
    assert agent.identity['workflow_context'] == logistics.identity['workflow_context'] == config.context.model_dump(mode='json')
    # Seed independence is what allows A to collect seeds before final markers.
    other,_ = safety_agent_fixture(dataset,WorkflowConfiguration(dataset))
    assert agent.identity_seed == other.identity_seed


def test_identity_drift_during_model_wait_discards_output(normal,monkeypatch):
    dataset,input,config,_,_ = normal
    def change(turn):
        if turn==1:
            from app.llm import safety_identity
            monkeypatch.setattr(safety_identity,'SAFETY_SYSTEM_PROMPT',safety_identity.SAFETY_SYSTEM_PROMPT+'\nChanged prompt.')
    agent,requests = safety_agent_fixture(dataset,config,on_request=change)
    with pytest.raises(ContractFailure) as exc: call(agent.assess_safety_with_trace(input))
    assert exc.value.error.code == ErrorCode.STALE_CONTEXT and len(requests)==1


def test_snapshot_drift_before_inference_fails_without_calls(normal):
    dataset,input,config,_,_ = deepcopy(normal)
    agent,requests = safety_agent_fixture(dataset,config)
    dataset._context = dataset.context.model_copy(update={'file_digests':{**dataset.context.file_digests,'runtime_safety_evidence.json':'f'*64}})
    with pytest.raises(ContractFailure): call(agent.assess_safety_with_trace(input))
    assert not requests


def test_unknown_history_validator_is_nonrecoverable_and_has_no_retry():
    with pytest.raises(ContractFailure) as exc: safety_validator_for('not-installed')
    assert exc.value.error.code == ErrorCode.PERSISTENCE_FAILURE and not exc.value.error.recoverable
    assert exc.value.error.allowed_actions == ['CONTACT_OPERATOR']


def test_remote_error_is_sanitised_and_never_returns_rule_success(normal):
    dataset,input,config,_,_ = normal
    requests=[]
    async def respond(request):
        requests.append(request)
        return httpx.Response(502,text='private upstream details unit-only-school-secret')
    agent=SafetyAgent(dataset,CampusModelClient(model_settings(),transport=httpx.MockTransport(respond)),workflow_configuration=config)
    with pytest.raises(ContractFailure) as exc: call(agent.assess_safety_with_trace(input))
    assert len(requests)==1 and exc.value.error.context['role']=='SAFETY'
    assert 'private upstream' not in str(exc.value) and 'unit-only-school-secret' not in str(exc.value)


def test_usage_missing_keys_stay_missing_not_fabricated_zeros(normal):
    dataset,input,config,_,_ = normal
    agent,_=safety_agent_fixture(dataset,config)
    original=agent.client.complete
    async def complete(messages): return replace(await original(messages),usage={})
    agent.client.complete=complete
    assert call(agent.assess_safety_with_trace(input)).trace.usage=={}


def test_tool_returns_detached_values_and_has_no_business_ids(normal):
    tools=tools_for(normal)
    a=tools.read_safety_facts(); old=deepcopy(a)
    a['fact_catalog'].clear(); a['findings'].clear()
    assert tools.read_safety_facts()==old


def test_maximum_findings_fixture_is_supported_without_omitting_facts(normal):
    _,input,_,baseline,selection=normal
    original=tools_for(normal).read_safety_facts()
    count=64-len(original['findings'])
    expanded=baseline.model_copy(update={'uncertainties':[f'Independent boundary item {i}.' for i in range(count)]})
    tools=SafetyToolset(input,expanded,selection=selection)
    facts=tools.read_safety_facts()
    assert len(facts['findings'])==64
    proposal=proposal_from_safety_facts(facts)
    plan=tools.evaluate_safety_plan(proposal)
    assert len(plan.findings)==64 and encoded_size(facts)<=32768
    too_many=expanded.model_copy(update={'uncertainties':[*expanded.uncertainties,'One additional issue.']})
    with pytest.raises(ContractFailure):SafetyToolset(input,too_many,selection=selection)


def test_complete_payload_limit_counts_multibyte_bytes(normal):
    _,input,_,baseline,_=normal
    with pytest.raises(ContractFailure):check_payload_size(input,baseline,{'extra':'界'*180000},{})
    oversized=baseline.model_copy(update={'uncertainties':['界'*12000]})
    with pytest.raises(ContractFailure):SafetyToolset(input,oversized,selection=normal[-1])


def test_unregistered_short_turn_budget_fails_before_model(normal):
    with pytest.raises(ContractFailure): safety_agent_fixture(normal[0],normal[2],settings=model_settings(max_turns=2))


def test_oversize_input_fails_before_any_model_request(normal):
    dataset,input,config,_,_=normal
    itinerary=input.saved_itinerary.model_copy(update={'assumptions':['界'*50000]})
    input=input.model_copy(update={'saved_itinerary':itinerary})
    agent,requests=safety_agent_fixture(dataset,config)
    with pytest.raises(ContractFailure):call(agent.assess_safety_with_trace(input))
    assert not requests


def test_action_byte_limit_is_not_character_count():
    with pytest.raises(ContractFailure):parse_safety_action('界'*11000)


def test_whole_proposal_budget_rejects_combined_field_maxima(normal):
    tools=tools_for(normal)
    p=proposal_from_safety_facts(tools.read_safety_facts())
    # Every text is individually valid; combined multibyte text exceeds the
    # global proposal limit. No truncation or partial plan is returned.
    for item in p['findings']:
        item['interpretation_unverified']='𐀀'*600
        item['action_unverified']='𐀀'*600
    with pytest.raises(ContractFailure):tools.evaluate_safety_plan(p)
