"""A30 independent 2.1 inputs and mocked campus HTTP; no production wiring."""
from datetime import date, timedelta
import json

import httpx

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.agents.rules import logistics, safety
from app.contracts.dto import LogisticsInput, SafetyInput
from app.llm.client import CampusModelClient
from app.llm.safety_agent import SafetyAgent
from app.llm.planning_schema import validated_itinerary
from app.llm.tools import recommend_for_model
from app.contracts.dto import RecommendCampsitesInput
from app.workflow import WorkflowConfiguration
from llm_fixtures import ROOT, completion, model_input, model_settings, final_action
from rule_fixtures import stored_logistics
from test_llm_logistics_agent import input_fixture


def safety_fixture(*, dataset=None, today='2026-11-05', start='2026-11-06', nights=2,
                   campsite='demo-wattle-rest', missing=(), unknown=(), config_markers=None, preferences=None):
    dataset = dataset or SyntheticDatasetV2Adapter(ROOT/'data/synthetic_demo_v2_1').load()
    _,planning = model_input()
    _,log_input,_ = input_fixture(missing=missing,unknown=unknown)
    raw = planning.confirmed_requirements.model_dump()
    first = date.fromisoformat(start)
    raw.update(start_date=first,end_date=first+timedelta(days=nights),duration_nights=nights,duration_days=nights+1)
    if preferences is not None:
        raw['preferences']=preferences
    req = planning.confirmed_requirements.model_validate(raw)
    demo = planning.demo_context.model_copy(update={'dataset_version':'2.1.0','demo_today':date.fromisoformat(today)})
    recs = recommend_for_model(dataset,RecommendCampsitesInput(confirmed_requirements=req,
        profile_snapshot=log_input.profile_snapshot,demo_context=demo))
    planning = planning.model_copy(update={'confirmed_requirements':req,'demo_context':demo,'recommendations':recs,
        'profile_snapshot':log_input.profile_snapshot})
    content = validated_itinerary(dataset,planning,final_action(campsite_id=campsite,
        nights=[(first+timedelta(days=i)).isoformat() for i in range(nights)])['proposal'],
        [camp.campsite_id for camp in dataset.campsites])
    log_input = LogisticsInput(version_context=log_input.version_context,saved_itinerary=content,
        confirmed_requirements=req,profile_snapshot=log_input.profile_snapshot,demo_context=demo)
    context = dataset.context.model_copy(update={'selection_config':{
        **dataset.context.selection_config,**(config_markers or {})}})
    config = WorkflowConfiguration(dataset,registered_context=context)
    log = logistics.assess(dataset,log_input,expected_mode='agent')
    selection = config.resolve_trip_evidence(req,[campsite],demo)
    input = SafetyInput(version_context=log_input.version_context,saved_itinerary=content,
        confirmed_requirements=req,saved_logistics_assessment=stored_logistics(log),
        scenario_context=selection.scenario_context,demo_context=demo)
    baseline = safety.assess(dataset,input,expected_mode='agent')
    return dataset,input,config,baseline,selection


def proposal_from_safety_facts(facts, *, reverse=False, choose_last=False):
    keys = [item['finding_key'] for item in facts['findings']]
    return {'findings':[{'finding_key':item['finding_key'],
        'interpretation_unverified':'Consider the recorded trip implications.',
        'action_code':item['allowed_actions'][-1 if choose_last else 0],
        'action_unverified':'Follow the permitted next step.'} for item in (reversed(facts['findings']) if reverse else facts['findings'])],
        'action_priority':list(reversed(keys)) if reverse else keys,
        'decision_summary_unverified':'Resolve recorded issues before seeking finalisation.'}


def safety_agent_fixture(dataset,config,*,mutate=None,on_request=None,settings=None,choose_last=False,reverse=False):
    requests = []
    async def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if on_request:
            on_request(len(requests))
        feedback = [json.loads(item['content'][12:]) for item in body['messages'] if item['content'].startswith('TOOL_RESULT=')]
        if not feedback:
            action = {'action':'tool','name':'read_safety_facts','arguments':{}}
        else:
            proposal = proposal_from_safety_facts(feedback[0],reverse=reverse,choose_last=choose_last)
            action = {'action':'tool','name':'evaluate_safety_plan','arguments':proposal} if len(feedback)==1 else {
                'action':'final','proposal':proposal}
        if mutate:
            action = mutate(len(requests),action)
        return httpx.Response(200,json=completion(action,model='offline-safety-test'))
    client = CampusModelClient(settings or model_settings(),transport=httpx.MockTransport(respond))
    return SafetyAgent(dataset,client,workflow_configuration=config),requests


def maximum_safety_fixture():
    """Real pure kernel, 57 unclassified segments + one uncertainty = 64 facts.

    Deliberately unsupported activities remain REVIEW. Not normal demo data.
    """
    dataset,input,config,_,selection=safety_fixture()
    entries=list(input.saved_itinerary.itinerary_entries)
    index=next(i for i,item in enumerate(entries) if item.entry_kind=='ACTIVITY')
    rest=entries[index]
    pieces=[rest.model_copy(update={'start_at':rest.start_at+timedelta(minutes=i),
        'end_at':rest.start_at+timedelta(minutes=i+1),'description':f'Unknown segment {i}.'}) for i in range(57)]
    pieces.append(rest.model_copy(update={'start_at':rest.start_at+timedelta(minutes=57)}))
    input=input.model_copy(update={'saved_itinerary':input.saved_itinerary.model_copy(update={
        'itinerary_entries':entries[:index]+pieces+entries[index+1:]})})
    baseline=safety.assess(dataset,input,expected_mode='agent')
    return dataset,input,config,baseline,selection


def saved_safety_archive(version):
    """Captured under ba7d9e5 BEFORE merging A35, not relabelled new output.

    Explicit offline fixtures only; v1 contains a synthetic archival proposal,
    v2 contains a MockTransport component outcome. Neither is live evidence.
    """
    from app.contracts.dto import SafetyResult
    from app.agents.rules.trip_evidence import TripEvidenceSelection
    path=ROOT/'backend/tests/fixtures/safety_archives_pre_a35.json'
    raw=json.loads(path.read_text(encoding='utf-8'))[version]
    assert raw['fixture_kind']=='OFFLINE_SYNTHETIC_ARCHIVE_NOT_LIVE_INFERENCE'
    assert raw['source_commit']=='ba7d9e5' and raw['source_common_kernel']=='b02-v1-rules-2'
    return (SafetyInput.model_validate(raw['input']),SafetyResult.model_validate(raw['baseline']),
        raw['plan'],raw['trace'],raw['identity'],TripEvidenceSelection.model_validate(raw['selection']))
