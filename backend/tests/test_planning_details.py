"""Pinned onsite catalogue, real planning component and isolated HTTP; no paid IO."""
import asyncio
from copy import deepcopy
from datetime import date, timedelta
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from app.adapters import planning_reference as ref
from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.agents.rules import planning, logistics, safety
from app.application.datasets import inspect_dataset
from app.contracts.dto import (DemoContext, ItineraryInput, RecommendCampsitesInput, LogisticsInput, SafetyInput)
from app.contracts.errors import ContractFailure
from app.llm.client import CampusModelClient
from app.llm.coordinator import PlanningCoordinator
from app.llm.planning_schema import validated_itinerary, parse_action
from app.llm.tools import CampsiteToolset
from app.main import create_app
from app.workflow import WorkflowConfiguration
from llm_fixtures import model_input, model_settings, completion, tool_action, final_action
from rule_fixtures import requirements, full_profile, stored_logistics, VERSION
from safety_runtime_fixtures import mock_safety_runtime, role_counts
from test_sydney_catalogue import settings, PACKAGE
from test_sydney_model_safety import settings as model_app_settings, begin, wait_run
from test_requests import sign_in
from test_plan_changes import change
from test_finalisation import command as final_command
from test_model_logistics_wiring import wrap_port
from test_rule_orchestration import FailOnce
from test_planning_entry import retry


def source(tmp_path, *, policy=ref.POLICY_VERSION):
    descriptor = inspect_dataset(settings(tmp_path))
    context = ref.register_reference(descriptor.context.model_copy(update={
        'selection_config':{**descriptor.context.selection_config,ref.POLICY_KEY:policy}}))
    dataset = SyntheticDatasetV2Adapter(PACKAGE).load(expected_context=context)
    ref.bind_reference(dataset, context)
    req = requirements(destination='Sydney & Surrounds',start_date=date(2026,10,27),budget_cents=100000,
        mandatory_constraints=['showers'])
    profile = full_profile(group=3,water=40).model_copy(update={'children_count':0})
    demo = DemoContext(mode='agent',demo_today='2026-10-26',dataset_version='2.2.0')
    recs = planning.recommend(dataset, RecommendCampsitesInput(confirmed_requirements=req,profile_snapshot=profile,demo_context=demo))
    return dataset, ItineraryInput(confirmed_requirements=req,profile_snapshot=profile,recommendations=recs,demo_context=demo),context


def proposal(input,site='bonnie-vale'):
    nights=[(input.confirmed_requirements.start_date+timedelta(days=i)).isoformat() for i in range(input.confirmed_requirements.duration_nights)]
    return {'campsite_id':site,'nights':nights,'decision_summary':'Select from registered facilities and compare campsite fees; other checks remain required.',
        'daily_plan':[{'date':night,'activity_id':site+('-settle' if i==0 else '-quiet-leisure')} for i,night in enumerate(nights)]}


def test_catalogue_is_pinned_and_existing_campsite_facts_are_not_replaced(tmp_path,monkeypatch):
    dataset,input,context=source(tmp_path)
    assert ref.REFERENCE_KEY in context.file_digests
    tool=CampsiteToolset(dataset,input).search_campsites()
    bonnie=next(item for item in tool['candidates'] if item['campsite_id']=='bonnie-vale')
    assert bonnie['max_group_size']==4 and bonnie['showers'] is True
    assert bonnie['public_transport_access'] is True
    assert len(bonnie['onsite_activities'])==2
    assert any(item['code']=='GROUP_CAPACITY' and item['expected']==3 and item['actual']==4 for item in bonnie['match_facts'])
    saved=next(item for item in input.recommendations.candidates if item.campsite_id=='bonnie-vale')
    assert any('this trip has 3 people' in text and 'recorded capacity is 4 people' in text for text in saved.reasons)
    assert any('AUD 85.00' in text and 'AUD 170.00' in text for text in saved.reasons)
    assert any('Showers' in text for text in saved.reasons)
    changed=tmp_path/'changed.json'
    changed.write_bytes(ref.REFERENCE_PATH.read_bytes()+b' ')
    monkeypatch.setattr(ref,'REFERENCE_PATH',changed)
    with pytest.raises(ContractFailure): ref.register_reference(context)
    with pytest.raises(ContractFailure): ref.bind_reference(dataset,context)


@pytest.mark.parametrize('mutation',['unknown_id','other_site','date_missing','date_duplicate','date_order','extra_day','unknown_field'])
def test_model_cannot_invent_or_omit_daily_choices(tmp_path,mutation):
    dataset,input,_=source(tmp_path)
    value=proposal(input)
    if mutation=='unknown_id': value['daily_plan'][0]['activity_id']='invented-hike'
    elif mutation=='other_site': value['daily_plan'][0]['activity_id']='lane-cove-facilities'
    elif mutation=='date_missing': value['daily_plan'].pop()
    elif mutation=='date_duplicate': value['daily_plan'][1]['date']=value['daily_plan'][0]['date']
    elif mutation=='date_order': value['daily_plan'].reverse()
    elif mutation=='extra_day': value['daily_plan'].append({'date':input.confirmed_requirements.end_date.isoformat(),'activity_id':'bonnie-vale-settle'})
    else: value['daily_plan'][0]['cost_cents']=0
    with pytest.raises(ContractFailure): validated_itinerary(dataset,input,value,[row.campsite_id for row in input.recommendations.candidates])


def test_actual_two_turn_component_saves_bounded_source_backed_entries_and_preserves_legacy_protocol(tmp_path):
    dataset,input,_=source(tmp_path)
    calls=[]
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json=completion(tool_action() if len(calls)==1 else {'action':'final','proposal':proposal(input)}))
    coordinator=PlanningCoordinator(dataset,CampusModelClient(model_settings(),transport=httpx.MockTransport(respond)))
    outcome=asyncio.run(coordinator.plan(input))
    assert len(calls)==outcome.trace.turns==2
    assert outcome.trace.tool_version=='campsite-tool-daily-1'
    entries=outcome.itinerary.itinerary_entries
    assert sum(row.entry_kind=='CAMP' for row in entries)==2
    assert sum(row.entry_kind=='ACTIVITY' for row in entries)==3
    assert 'Pack up and prepare for return' in entries[-1].description
    assert all(a.end_at<=b.start_at for a,b in zip(entries,entries[1:]))
    assert any(row.dataset_file==ref.REFERENCE_KEY for row in outcome.itinerary.source_refs)
    assert input.confirmed_requirements.budget_cents==100000
    legacy,_=model_input()
    old=PlanningCoordinator(legacy,CampusModelClient(model_settings()))
    assert old.identity['tool_version']=='b04-campsite-tool-1'
    assert old.identity['prompt_sha256']!=coordinator.identity['prompt_sha256']
    assert parse_action(json.dumps(final_action())).proposal.campsite_id=='demo-wattle-rest'
    with pytest.raises(ContractFailure): parse_action(json.dumps(final_action()),detailed=True)


def test_unknown_activity_still_requires_review_and_missing_source_cannot_be_cleared(tmp_path):
    dataset,input,context=source(tmp_path)
    content=validated_itinerary(dataset,input,proposal(input),[row.campsite_id for row in input.recommendations.candidates])
    log=logistics.assess(dataset,LogisticsInput(version_context=VERSION,saved_itinerary=content,
        confirmed_requirements=input.confirmed_requirements,profile_snapshot=input.profile_snapshot,demo_context=input.demo_context),expected_mode='agent')
    scenario=WorkflowConfiguration(dataset,registered_context=context).resolve_trip_evidence(input.confirmed_requirements,['bonnie-vale'],input.demo_context).scenario_context
    def check(itinerary):
        return safety.assess(dataset,SafetyInput(version_context=VERSION,saved_itinerary=itinerary,
            saved_logistics_assessment=stored_logistics(log),confirmed_requirements=input.confirmed_requirements,
            scenario_context=scenario,demo_context=input.demo_context),expected_mode='agent')
    assert not any('Unclassified activity' in row for row in check(content).hazards)
    changed=content.model_copy(update={'itinerary_entries':[content.itinerary_entries[0].model_copy(
        update={'description':'Swim across the basin.'}),*content.itinerary_entries[1:]]},deep=True)
    assert any('Unclassified activity' in row for row in check(changed).hazards)
    missing=content.model_copy(update={'source_refs':[]},deep=True)
    assert any('Unclassified activity' in row for row in check(missing).hazards)


def test_no_activity_data_is_explicit_and_never_borrows_another_campsite(tmp_path):
    dataset,input,_=source(tmp_path,policy=ref.LEGACY_POLICY_VERSION)
    value=proposal(input,'cattai');value['daily_plan']=[]
    content=validated_itinerary(dataset,input,value,[row.campsite_id for row in input.recommendations.candidates])
    assert all(ref.LEGACY_REFERENCE_KEY!=row.dataset_file for row in content.source_refs)
    candidate=next(item for item in input.recommendations.candidates if item.campsite_id=='cattai')
    assert any('No applicable activity data' in text for text in candidate.material_uncertainties)


def test_http_save_final_revision_reassessment_recovery_and_restart(tmp_path,monkeypatch):
    calls,control=mock_safety_runtime(monkeypatch);control['site']='bonnie-vale'
    config=model_app_settings(tmp_path)
    used=[]
    def fail_after_save(port):
        if not used:
            used.append(True);return FailOnce(port,'append_model_plan',after=True)
        return port
    wrap_port(monkeypatch,fail_after_save)
    with TestClient(create_app(config)) as client:
        headers=sign_in(client)
        failed=wait_run(client,begin(client,headers),'FAILED')
        assert failed['version']
        stored=deepcopy(failed['version']['content']);before=role_counts(calls)['PLANNING']
        assert retry(client,headers,failed).status_code==202
        initial=wait_run(client,failed['run']['run_id'],'SUCCEEDED')
        assert initial['version']['content']==stored and role_counts(calls)['PLANNING']==before
        assert initial['finalisation_available']
        raw=client.get('/api/v1/plans/'+initial['plan']['plan_id']).json()
        assert 'model_diagnostics' not in raw and 'model_planning_trace' not in raw
        assert any('Group size' in reason for reason in raw['recommendations']['result']['candidates'][0]['reasons'])
        final=client.post('/api/v1/plans/'+initial['plan']['plan_id']+'/finalise',headers=headers,json=final_command(initial))
        assert final.status_code==200,final.text
        path='/api/v1/plans/'+initial['plan']['plan_id']+'/finals/'+final.json()['final_id']
        snapshot=client.get(path).json()['final_record']
        assert snapshot['content']==stored
        current=client.get('/api/v1/plans/'+initial['plan']['plan_id']).json()
        control['site']='lane-cove'
        response=change(client,headers,current,'revise',feedback='change campsite',key='daily-plan-revise-command')
        assert response.status_code==202,response.text
        revised=wait_run(client,response.json()['run_id'],'SUCCEEDED')
        assert revised['version']['content']['selected_campsite_ids']==['lane-cove']
        assert 'Explore facilities and settle in' in revised['version']['content']['itinerary_entries'][0]['description']
        before=role_counts(calls)['PLANNING']
        response=change(client,headers,revised,key='daily-plan-reassess-command')
        assert response.status_code==202,response.text
        reassessed=wait_run(client,response.json()['run_id'],'SUCCEEDED')
        assert reassessed['version']['content']==revised['version']['content']
        assert role_counts(calls)['PLANNING']==before
    count=len(calls)
    with TestClient(create_app(config)) as client:
        sign_in(client)
        final=client.get(path).json()['final_record']
        assert final['content']==stored
        assert final['planning_explanation']==snapshot['planning_explanation']
        assert len(calls)==count


def test_old_scope_does_not_upgrade_and_warm_cache_checks_saved_activity_bytes(tmp_path,monkeypatch):
    with TestClient(create_app(settings(tmp_path))) as client:
        runtime=client.app.state.runtime
        old=runtime.resolve(planning_policy=None)
        old_scope=SimpleNamespace(dataset_context=old.dataset,demo_context=old.demo)
        assert ref.POLICY_KEY not in runtime.for_scope(old_scope).dataset.selection_config
        new=runtime.resolve()
        assert new.dataset.selection_config[ref.POLICY_KEY]==ref.POLICY_VERSION
        scope=SimpleNamespace(dataset_context=new.dataset,demo_context=new.demo)
        assert runtime.for_scope(scope).dataset==new.dataset
        changed=tmp_path/'changed-catalogue.json'
        changed.write_bytes(ref.REFERENCE_PATH.read_bytes()+b' ')
        monkeypatch.setattr(ref,'REFERENCE_PATH',changed)
        with pytest.raises(ContractFailure): runtime.for_scope(scope)
        assert runtime.for_scope(old_scope).dataset==old.dataset


def test_catalogue_parser_rejects_duplicate_ids_unknown_fields_and_paid_activities(tmp_path,monkeypatch):
    original=json.loads(ref.REFERENCE_PATH.read_bytes())
    for mutation in ('duplicate','paid','equipment','wrong_period','unknown_field'):
        value=deepcopy(original)
        if mutation=='duplicate': value['activities'].append(value['activities'][0])
        elif mutation=='paid': value['activities'][0]['additional_cost_cents']=10
        elif mutation=='equipment': value['activities'][0]['additional_equipment']=['kayak']
        elif mutation=='wrong_period': value['activities'][0]['valid_to']='2026-01-01'
        else: value['activities'][0]['verified_safe']=True
        path=tmp_path/(mutation+'.json');path.write_text(json.dumps(value))
        monkeypatch.setattr(ref,'REFERENCE_PATH',path)
        with pytest.raises(ContractFailure): ref.read_reference()


@pytest.mark.parametrize('site',['bents-basin','bonnie-vale','cattai','cockatoo-island','euroka',
    'lane-cove','little-beach','putty-beach','tallow-beach','the-basin'])
def test_expanded_catalogue_covers_every_campsite_with_saved_bounded_daily_entries(tmp_path,site):
    dataset,input,_=source(tmp_path)
    activities=ref.available_activities(dataset,site,input.confirmed_requirements)
    assert len(activities)==2
    assert all(row.intensity=='LOW' and row.additional_cost_cents==0 and not row.requires_booking
        and not row.additional_equipment and row.availability=='SUGGESTION_ONLY' for row in activities)
    choices=[SimpleNamespace(date=input.confirmed_requirements.start_date+timedelta(days=i),
        activity_id=activities[i%2].activity_id) for i in range(input.confirmed_requirements.duration_nights)]
    entries,refs=ref.daily_entries(dataset,dataset.get_campsite(site),input.confirmed_requirements,choices)
    assert len(entries)==5
    assert len({row.record_id for row in refs})==3
    assert all(row.dataset_file==ref.REFERENCE_KEY for row in refs)
    assert all(row.campsite_id==site for row in entries)
    assert all(left.end_at<=right.start_at for left,right in zip(entries,entries[1:]))
    content=SimpleNamespace(source_refs=refs)
    for entry in entries:
        if entry.entry_kind=='ACTIVITY':
            assert 'Simulated activity suggestion' in entry.description
            assert ref.known_activity(dataset,entry,content,input.confirmed_requirements)
    wrong=entries[0].model_copy(update={'description':entries[0].description+' Extra unregistered activity.'})
    assert not ref.known_activity(dataset,wrong,content,input.confirmed_requirements)


def test_the_basin_model_uses_actual_catalogue_activities(tmp_path):
    dataset,input,_=source(tmp_path)
    profile=full_profile(group=3,mode='PUBLIC_TRANSPORT',water=40).model_copy(update={'children_count':0})
    recs=planning.recommend(dataset,RecommendCampsitesInput(confirmed_requirements=input.confirmed_requirements,
        profile_snapshot=profile,demo_context=input.demo_context))
    input=input.model_copy(update={'profile_snapshot':profile,'recommendations':recs})
    assert 'the-basin' in {row.campsite_id for row in recs.candidates}
    activities=ref.available_activities(dataset,'the-basin',input.confirmed_requirements)
    value=proposal(input,'the-basin')
    value['daily_plan']=[{'date':night,'activity_id':activities[i%2].activity_id} for i,night in enumerate(value['nights'])]
    calls=[]
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json=completion(tool_action() if len(calls)==1 else {'action':'final','proposal':value}))
    result=asyncio.run(PlanningCoordinator(dataset,CampusModelClient(model_settings(),transport=httpx.MockTransport(respond))).plan(input))
    assert len(calls)==2
    assert result.itinerary.execution_mode=='agent'
    assert 'Nature observation and casual photography' in result.itinerary.itinerary_entries[0].description
    assert 'Storytelling and campsite leisure' in result.itinerary.itinerary_entries[2].description
    assert 'Pack up and prepare for return' in result.itinerary.itinerary_entries[-1].description
    assert not any('free-time block' in row.description for row in result.itinerary.itinerary_entries)


def test_legacy_catalogue_keeps_its_exact_bytes_content_and_source_identity(tmp_path):
    reference,digest=ref.read_reference(ref.LEGACY_POLICY_VERSION)
    assert digest=='da0028a43cbb056e247a442a4bcf50b948f2517c41b935fdfbc4d5dfaca0a230'
    assert len(reference.activities)==9
    old,input,context=source(tmp_path,policy=ref.LEGACY_POLICY_VERSION)
    assert ref.LEGACY_REFERENCE_KEY in context.file_digests
    assert ref.REFERENCE_KEY not in context.file_digests
    content=validated_itinerary(old,input,proposal(input),[row.campsite_id for row in input.recommendations.candidates])
    entry=content.itinerary_entries[0]
    assert ref.known_activity(old,entry,content,input.confirmed_requirements)
    assert all(row.dataset_file!=ref.REFERENCE_KEY for row in content.source_refs)
    current,_,_=source(tmp_path)
    assert not ref.known_activity(current,entry,content,input.confirmed_requirements)
    with TestClient(create_app(settings(tmp_path))) as client:
        runtime=client.app.state.runtime
        saved=runtime.resolve(planning_policy=ref.LEGACY_POLICY_VERSION)
        scope=SimpleNamespace(dataset_context=saved.dataset,demo_context=saved.demo)
        assert runtime.for_scope(scope).dataset==saved.dataset
        assert runtime.for_scope(scope).dataset.selection_config[ref.POLICY_KEY]==ref.LEGACY_POLICY_VERSION
        assert runtime.resolve().dataset.selection_config[ref.POLICY_KEY]==ref.POLICY_VERSION


def test_catalogue_version_cannot_be_relabelled_or_replaced_with_legacy_bytes(tmp_path,monkeypatch):
    dataset,_,context=source(tmp_path)
    changed=tmp_path/'relabelled.json'
    value=json.loads(ref.REFERENCE_PATH.read_bytes())
    value['version']=ref.LEGACY_POLICY_VERSION
    changed.write_text(json.dumps(value))
    monkeypatch.setattr(ref,'REFERENCE_PATH',changed)
    with pytest.raises(ContractFailure): ref.register_reference(context)
    with pytest.raises(ContractFailure): ref.bind_reference(dataset,context)
