"""English UI output with exact legacy input and catalogue compatibility; offline only."""
import re
from copy import deepcopy
from app.application.requirement_choices import choices, recognized
from app.adapters import planning_reference as ref
from app.agents.rules.request_terms import canonical_term
from app.llm.client import CampusModelClient
from app.llm.coordinator import PlanningCoordinator
from llm_fixtures import model_settings
from test_planning_details import source
from test_requests import web

HAN=re.compile(r'[\u3400-\u9fff]')


def test_choice_labels_are_english_but_legacy_aliases_keep_their_meaning():
    catalogue=choices()
    for field, rows in catalogue['fields'].items():
        for row in rows:
            assert not HAN.search(row['label'])
            assert recognized(row['label'],field)==row['value']
    assert canonical_term('\u9700\u8981\u6d17\u6fa1','constraint')=='showers'
    assert canonical_term('need a shower','constraint')=='showers'
    assert canonical_term('must have private hot showers','constraint') is None
    assert recognized('\u9700\u8981\u65e0\u53f0\u9636\u901a\u9053\u3002','accessibility_requirements')=='step-free path'


def test_new_activity_catalogue_is_english_and_old_v2_still_replays_exactly():
    current,_=ref.read_reference()
    assert current.version=='camp-activities-3'
    assert all(not HAN.search(row.saved_description) for row in current.activities)
    assert all(row.additional_cost_cents==0 and not row.additional_equipment and not row.requires_booking for row in current.activities)
    old,digest=ref.read_reference(ref.PREVIOUS_POLICY_VERSION)
    assert digest=="617087ebf4cacea70da59c1d6e4e69334c6183e7391831f0cd247afbc43022dc"
    marker='\uff08\u6a21\u62df\u6d3b\u52a8\u5efa\u8bae\uff1b\u987b\u4ee5\u6b63\u5f0f\u5b89\u5168\u68c0\u67e5\u548c\u73b0\u573a\u6761\u4ef6\u4e3a\u51c6\u3002\uff09'
    assert old.activities[0].saved_description==old.activities[0].title+'\uff1a'+old.activities[0].description+marker
    assert ref.reference_key(old.version)=='planning/camp_activities_v2.json'


def test_english_generation_instruction_has_a_new_identity_without_changing_old_scope(tmp_path):
    current,_,_=source(tmp_path)
    old,_,_=source(tmp_path,policy=ref.PREVIOUS_POLICY_VERSION)
    client=CampusModelClient(model_settings())
    new_agent=PlanningCoordinator(current,client)
    old_agent=PlanningCoordinator(old,client)
    assert 'Write all user-facing explanations in English.' in new_agent.protocol[0]
    assert 'Write all user-facing explanations in English.' not in old_agent.protocol[0]
    assert new_agent.identity['coordinator_version']=='planning-coordinator-daily-en-1'
    assert old_agent.identity['coordinator_version']=='planning-coordinator-daily-1'
    assert new_agent.identity['prompt_sha256']!=old_agent.identity['prompt_sha256']


def test_raw_http_clarifications_and_errors_are_english_and_do_not_call_models(web):
    app,client,headers=web
    draft=client.post('/api/v1/requests',headers=headers,json={'explicit_fields':{}}).json()
    response=client.post('/api/v1/requests/'+draft['request_id']+'/interpret',headers=headers,json={'expected_revision':draft['revision']})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['status']=='NEEDS_CLARIFICATION'
    for row in result['summary']['clarifications']:
        assert not HAN.search(row['question']+row['reason'])
    for row in result['summary']['field_errors']:
        assert not HAN.search(row['message'])
    invalid=client.post('/api/v1/requests',headers=headers,json={'unexpected':'field'})
    assert invalid.status_code>=400
    assert not HAN.search(invalid.json()['error']['message'])
