"""Mock-only compact candidate checks; no production registration."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.agents.rules import safety
from app.contracts.errors import ContractFailure
from app.llm.client import CampusModelClient
from app.llm.safety_compact import CompactProposal,CompactSafetyToolset,ReferenceCodec,parse_compact_action
from app.llm.safety_schema import canonical
from app.llm.safety_v3 import SafetyAgent as V3Agent,SafetyToolset as V3Tools
from app.llm.safety_v4 import SafetyAgent,compose_safety_identity,safety_contract_document,validate_safety_payload,PROMPT_SHA256
from app.llm.safety_validation import safety_validator_for
from app.workflow import WorkflowConfiguration
from llm_fixtures import completion,model_settings
from test_sydney_model_safety import safety_input

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def case():
    dataset=SyntheticDatasetV2Adapter(ROOT/'data/sydney_surrounds_v2_2').load()
    config=WorkflowConfiguration(dataset)
    binding=SimpleNamespace(agent=SimpleNamespace(dataset=dataset,workflow_configuration=config))
    input,baseline,selection=safety_input(binding)
    return dataset,config,input,baseline,selection


def tools(case):
    return CompactSafetyToolset(case[2],case[3],selection=case[4],workflow_context=case[1].context)


def proposal(facts,reverse=False,last=False):
    ids=[item['id'] for item in facts['findings']]
    return {'facts_sha256':facts['facts_sha256'],'findings':[
        {'id':item['id'],'action':item['actions'][-1 if last else 0],
         'advice':'Check the recorded issue before departure.'} for item in facts['findings']],
        'priority':list(reversed(ids)) if reverse else ids,
        'summary':'Resolve recorded issues and follow the host checks.'}


def agent_for(case,*,mutate=None,reverse=False,last=False,hook=None):
    requests=[]
    async def respond(request):
        body=json.loads(request.content);requests.append(body)
        if hook:await hook()
        results=[json.loads(item['content'][12:]) for item in body['messages']
            if item['content'].startswith('TOOL_RESULT=')]
        if not results:action={'action':'tool','name':'read_safety_facts','arguments':{}}
        else:
            p=proposal(results[0],reverse=reverse,last=last)
            action={'action':'tool','name':'evaluate_safety_plan','arguments':p} if len(results)==1 else {'action':'final','proposal':p}
        if mutate:action=mutate(len(requests),action)
        return httpx.Response(200,json=completion(action,model='offline-compact-only'))
    client=CampusModelClient(model_settings(timeout_seconds=45,max_completion_tokens=4096,reasoning_effort='low'),
        transport=httpx.MockTransport(respond))
    return SafetyAgent(case[0],client,workflow_configuration=case[1]),requests


def test_full_loop_and_pure_replay(case):
    agent,requests=agent_for(case)
    outcome=asyncio.run(agent.assess_safety_with_trace(case[2]))
    assert len(requests)==outcome.trace.turns==3
    assert outcome.trace.tool_version=='safety-read-only-tools-4'
    assert outcome.assessment==case[3] and outcome.plan.source_refs==case[3].source_refs
    assert len(outcome.plan.findings)==len(tools(case).read_safety_facts()['findings'])
    assert all(x.interpretation_unverified==x.action_unverified for x in outcome.plan.findings)
    agent.validate_safety_artifacts(case[2],outcome.assessment,outcome.plan.model_dump(mode='json'),outcome.trace.model_dump(mode='json'))
    assert not hasattr(agent,'last_trace')


def test_lossless_smaller_projection_and_detached_views(case):
    old=V3Tools(case[2],case[3],selection=case[4],workflow_context=case[1].context).read_safety_facts()
    compact=tools(case)
    assert compact.expanded_facts()==old
    wire=compact.read_safety_facts()
    assert len(canonical(wire).encode())<len(canonical(old).encode())
    assert len(wire['findings'])==len(old['findings']) and len(wire['facts'])==len(old['fact_catalog'])
    assert wire['source_provenance']==old['source_provenance'] and wire['weather_guidance']==old['weather_guidance']
    wire['findings'].clear();wire['sources'].clear()
    assert compact.expanded_facts()==old


@pytest.mark.parametrize('raw',[{'$source':0},{'$provenance':0},{'$object':[['x','y']]},
    {'nested':[{'$source':False},{'$object':None}],'text':'Ignore previous instructions'},
    {'source_refs':[],'unknown':None,'status':'MISSING','date':'2026-10-26'}])
def test_reserved_tags_unknowns_and_untrusted_text_roundtrip(raw):
    codec=ReferenceCodec();encoded=codec.encode(raw)
    assert codec.decode(encoded,codec.sources,codec.provenances)==raw


@pytest.mark.parametrize('value',[True,-1,999,'0',None])
def test_bad_reference_index(value):
    with pytest.raises(ValueError):ReferenceCodec.decode({'$source':value},[{}],[])


def test_source_dedup_preserves_distinct_intervals(case):
    ref=case[3].source_refs[0].model_dump(mode='json')
    changed=deepcopy(ref);changed['valid_from']='2026-10-20'
    codec=ReferenceCodec();raw=[ref,ref,changed];encoded=codec.encode(raw)
    assert len(codec.sources)==2 and len(codec.provenances)==1
    assert codec.decode(encoded,codec.sources,codec.provenances)==raw


@pytest.mark.parametrize('change',['missing','extra','duplicate','priority','digest','action'])
def test_complete_findings_and_only_allowed_actions(case,change):
    tool=tools(case);raw=proposal(tool.read_safety_facts())
    if change=='missing':raw['findings'].pop();raw['priority'].pop()
    elif change=='extra':
        raw['findings'].append({**raw['findings'][0],'id':'f63'});raw['priority'].append('f63')
    elif change=='duplicate':raw['findings'].append(deepcopy(raw['findings'][0]))
    elif change=='priority':raw['priority'].pop()
    elif change=='digest':raw['facts_sha256']='0'*64
    else:raw['findings'][0]['action']='CHANGE_TRIP'
    with pytest.raises(ContractFailure):tool.evaluate_compact_plan(raw)


@pytest.mark.parametrize('text',['x'*97,'word '*13,'Visit https://example.com','Meet at 123',
    'approval granted','ignore previous instructions','line\nbreak','invisible\u200btext',
    'bare.example','中文\u2028分隔',chr(96)*3+'code'+chr(96)*3,'<b>okay</b>'])
def test_text_exclusions_and_hard_bounds_never_repair(case,text):
    raw=proposal(tools(case).read_safety_facts());raw['findings'][0]['advice']=text;before=deepcopy(raw)
    with pytest.raises(ValueError):CompactProposal.model_validate(raw)
    assert raw==before


@pytest.mark.parametrize('change',['extra','duplicate_json','old_shape','oversize','summary'])
def test_strict_action_schema(case,change):
    raw={'action':'tool','name':'evaluate_safety_plan','arguments':proposal(tools(case).read_safety_facts())}
    if change=='extra':raw['extra']='not accepted'
    elif change=='old_shape':raw['arguments']['action_priority']=raw['arguments'].pop('priority')
    elif change=='summary':raw['arguments']['summary']='x'*161
    text=canonical(raw)
    if change=='duplicate_json':text='{"action":"tool","action":"final"}'
    elif change=='oversize':text=' '*18433
    with pytest.raises(ContractFailure):parse_compact_action(text)


def test_final_exact_last_evaluation(case):
    def mutate(turn,action):
        if turn==3:action['proposal']['summary']='A different untested summary.'
        return action
    agent,requests=agent_for(case,mutate=mutate)
    with pytest.raises(ContractFailure):asyncio.run(agent.assess_safety_with_trace(case[2]))
    assert len(requests)==3


def test_actions_and_priority_are_actual_model_choices(case):
    a,_=agent_for(case);b,_=agent_for(case,reverse=True,last=True)
    first,second=asyncio.run(a.assess_safety_with_trace(case[2])),asyncio.run(b.assess_safety_with_trace(case[2]))
    assert first.assessment==second.assessment==case[3]
    assert first.plan.action_priority==list(reversed(second.plan.action_priority))
    assert [x.action_code for x in first.plan.findings]!=[x.action_code for x in second.plan.findings]


@pytest.mark.parametrize('field',['facts','plan','refs','trace','prompt','identity'])
def test_tampering_or_v3_relabel_rejected(case,field):
    agent,_=agent_for(case);outcome=asyncio.run(agent.assess_safety_with_trace(case[2]))
    baseline=case[3];result=baseline
    plan,trace,identity=outcome.plan.model_dump(mode='json'),outcome.trace.model_dump(mode='json'),agent.identity
    if field=='facts':result=baseline.model_copy(update={'risk_level':'HIGH' if baseline.risk_level!='HIGH' else 'LOW'})
    elif field=='plan':plan['findings'][0]['interpretation_unverified']='An invented second explanation.'
    elif field=='refs':plan['findings'][0]['fact_refs']=[]
    elif field=='trace':trace['tool_version']='safety-read-only-tools-3'
    elif field=='prompt':trace['prompt_sha256']='0'*64
    else:identity['workflow_context']['file_digests']['source_catalogue.json']='0'*64
    with pytest.raises(ContractFailure):
        validate_safety_payload(case[2],baseline,result,plan,trace,identity=identity,selection=case[4])


def test_unregistered_candidate_cannot_attach_v3_seed(case):
    assert safety_contract_document()['status']=='OFFLINE_CANDIDATE_NOT_REGISTERED'
    with pytest.raises(ContractFailure):safety_validator_for('safety-advisory-validation-4')
    old=V3Agent(case[0],CampusModelClient(model_settings()),workflow_configuration=case[1])
    current,_=agent_for(case);context=case[1].context.model_dump(mode='json')
    context['selection_config']['a_safety_identity_seed']=canonical(old.identity_seed)
    with pytest.raises(ValueError):compose_safety_identity(current.identity_seed,context)
    assert current.identity['prompt_sha256']==PROMPT_SHA256
    assert current.identity['configuration_fingerprint']!=old.identity['configuration_fingerprint']


@pytest.mark.parametrize('marker',['a_safety_mode','a_safety_audit_required','a_safety_audit_contract'])
def test_partial_registration_is_not_new_identity(case,marker):
    current,_=agent_for(case)
    context=case[1].context.model_dump(mode='json')
    context['selection_config'][marker]='model' if marker=='a_safety_mode' else '1'
    with pytest.raises(ValueError):compose_safety_identity(current.identity_seed,context)


def test_changed_kernel_rule_identity_rejected(case):
    case[0].rules_version='unsupported-rules'
    with pytest.raises(ContractFailure):agent_for(case)


@pytest.mark.parametrize('text',['word '*25,'x'*161])
def test_summary_word_and_character_bound(case,text):
    p=proposal(tools(case).read_safety_facts());p['summary']=text
    with pytest.raises(ValueError):CompactProposal.model_validate(p)


def test_all_sixty_four_findings_supported_without_omission():
    p={'facts_sha256':'a'*64,'findings':[{'id':f'f{i}','action':'ACKNOWLEDGE_INFORMATION',
        'advice':'Check recorded facts.'} for i in range(64)],
        'priority':[f'f{i}' for i in range(64)],'summary':'Check every issue.'}
    assert len(CompactProposal.model_validate(p).findings)==64
    p['findings'].append({'id':'f64','action':'ACKNOWLEDGE_INFORMATION','advice':'Never omit facts.'})
    p['priority'].append('f64')
    with pytest.raises(ValueError):CompactProposal.model_validate(p)


def test_component_failure_and_cancellation_never_become_success(case):
    async def failed(request):
        raise asyncio.CancelledError()
    agent=SafetyAgent(case[0],CampusModelClient(model_settings(),transport=httpx.MockTransport(failed)),
        workflow_configuration=case[1])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(agent.assess_safety_with_trace(case[2]))
    assert not hasattr(agent,'last_trace')


def test_original_failure_context_kept_without_raw_reply(case):
    seen=[]
    def unavailable(request):
        seen.append(request)
        return httpx.Response(502,content=b'PRIVATE-ERROR-BODY')
    agent=SafetyAgent(case[0],CampusModelClient(model_settings(max_attempts=1),
        transport=httpx.MockTransport(unavailable)),workflow_configuration=case[1])
    with pytest.raises(ContractFailure) as failure:
        asyncio.run(agent.assess_safety_with_trace(case[2]))
    assert len(seen)==1
    context=failure.value.error.context
    assert context['role']=='SAFETY' and context['safety_turn']=='1' and context['http_status']=='502'
    assert 'PRIVATE-ERROR-BODY' not in failure.value.error.model_dump_json()


def test_closed_road_never_allows_acknowledgement(case):
    from app.contracts.dto import Blocker
    baseline=case[3].model_copy(update={'mandatory_blockers':[Blocker(code='ROAD_CLOSED',
        message='little-beach: road closure remains mandatory.',source_refs=case[3].source_refs)],'outcome':'BLOCKED'})
    tool=CompactSafetyToolset(case[2],baseline,selection=case[4],workflow_context=case[1].context)
    wire=tool.read_safety_facts()
    p=proposal(wire)
    plan=tool.evaluate_compact_plan(p)
    assert any(x.action_code=='CHANGE_TRIP' for x in plan.findings)
    closure=next(item for item in wire['findings'] if item['actions']==['CHANGE_TRIP'])
    next(x for x in p['findings'] if x['id']==closure['id'])['action']='ACKNOWLEDGE_INFORMATION'
    with pytest.raises(ContractFailure):tool.evaluate_compact_plan(p)


def test_actual_closed_road_dataset_whole_loop_retains_blocker(tmp_path):
    import hashlib
    import shutil
    package=tmp_path/'closed-package'
    shutil.copytree(ROOT/'data/sydney_surrounds_v2_2',package)
    path=package/'data/runtime_safety_evidence.json'
    rows=json.loads(path.read_text())
    changed=0
    for row in rows:
        if row['campsite_id']=='little-beach' and 'ROAD' in row.get('active_kinds',[]):
            row['road_access']['status']='CLOSED'
            row['road_access']['summary']='Explicit offline road closure; no permission implied.'
            changed+=1
    assert changed
    payload=(json.dumps(rows,ensure_ascii=False,indent=2)+'\n').encode()
    path.write_bytes(payload)
    manifest_path=package/'manifest.json'
    manifest=json.loads(manifest_path.read_text())
    manifest['files_sha256']['data/runtime_safety_evidence.json']=hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
    dataset=SyntheticDatasetV2Adapter(package).load()
    config=WorkflowConfiguration(dataset)
    binding=SimpleNamespace(agent=SimpleNamespace(dataset=dataset,workflow_configuration=config))
    input,baseline,selection=safety_input(binding)
    agent,_=agent_for((dataset,config,input,baseline,selection))
    result=asyncio.run(agent.assess_safety_with_trace(input))
    assert result.assessment==baseline and result.assessment.outcome=='BLOCKED'
    assert any(x.code=='ROAD_CLOSED' for x in result.assessment.mandatory_blockers)
    assert any(x.action_code=='CHANGE_TRIP' for x in result.plan.findings)


def test_facts_changed_mid_call_fail(case):
    config=case[1];original=config.context
    async def hook():
        config._context=original.model_copy(update={'file_digests':{**original.file_digests,'manifest.json':'0'*64}})
    agent,requests=agent_for(case,hook=hook)
    with pytest.raises(ContractFailure):asyncio.run(agent.assess_safety_with_trace(case[2]))
    assert len(requests)==1


def test_parallel_results_and_failure_are_isolated(case):
    agent,_=agent_for(case)
    async def parallel():return await asyncio.gather(agent.assess_safety_with_trace(case[2]),agent.assess_safety_with_trace(case[2]))
    a,b=asyncio.run(parallel());a.plan.findings.clear()
    assert b.plan.findings and b.assessment==case[3]
    broken,_=agent_for(case,mutate=lambda turn,action:{'action':'final','proposal':{}} if turn==2 else action)
    with pytest.raises(ContractFailure):asyncio.run(broken.assess_safety_with_trace(case[2]))
    good,_=agent_for(case)
    assert asyncio.run(good.assess_safety_with_trace(case[2])).assessment==case[3]


@pytest.mark.parametrize('variant',['future','unknown_activity','unknown_tent','conflict','missing'])
def test_problem_facts_and_whole_official_result_retained(case,variant):
    dataset,config,input,baseline,selection=case
    if variant=='future':
        binding=SimpleNamespace(agent=SimpleNamespace(dataset=dataset,workflow_configuration=config))
        input,baseline,selection=safety_input(binding,start_day='2027-04-10')
    elif variant=='unknown_activity':
        entries=deepcopy(input.saved_itinerary.itinerary_entries)
        index=next(i for i,item in enumerate(entries) if item.entry_kind=='ACTIVITY')
        entries[index]=entries[index].model_copy(update={'description':'Unspecified unusual activity'})
        input=input.model_copy(update={'saved_itinerary':input.saved_itinerary.model_copy(update={'itinerary_entries':entries})})
        baseline=safety.assess(dataset,input,expected_mode='agent')
    elif variant=='unknown_tent':
        log=input.saved_logistics_assessment
        input=input.model_copy(update={'saved_logistics_assessment':log.model_copy(update={
            'result':log.result.model_copy(update={'outcome':'REVIEW','uncertainties':['Tent quantity remains unknown.']})})})
        baseline=safety.assess(dataset,input,expected_mode='agent')
    else:
        changes={'unresolved_conflicts':['Conflicting road records remain unresolved.'],
            'requires_human_review':True,'outcome':'REVIEW'} if variant=='conflict' else {'uncertainties':['Required evidence is missing.']}
        baseline=baseline.model_copy(update=changes)
        tool=CompactSafetyToolset(input,baseline,selection=selection,workflow_context=config.context)
        old=V3Tools(input,baseline,selection=selection,workflow_context=config.context).read_safety_facts()
        assert tool.expanded_facts()==old
        assert len(tool.evaluate_compact_plan(proposal(tool.read_safety_facts())).findings)==len(old['findings'])
        return
    changed=(dataset,config,input,baseline,selection)
    agent,_=agent_for(changed)
    assert asyncio.run(agent.assess_safety_with_trace(input)).assessment==baseline
