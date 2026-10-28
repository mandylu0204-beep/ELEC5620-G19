"""Form-only summaries preserve old prose and never call interpretation models."""
from copy import deepcopy
from datetime import date,timedelta
import json
from fastapi.testclient import TestClient
import pytest
from app.main import create_app
from app.storage.repository import encode
from test_requests import web,sign_in,FIELDS,confirm_body
from test_request_interpretation_lifecycle import observed_web

FIELDS_READY=FIELDS|{'preferences':['ready-to-eat meals','希望安静'],'mandatory_constraints':['需要洗澡']}

def create(client,headers,fields=None,**extra):
    if fields is None:
        fields=deepcopy(FIELDS_READY)
        fields['start_date']=(date.fromisoformat(client.get('/api/v1/request-context').json()['demo_today'])+timedelta(days=2)).isoformat()
    reply=client.post('/api/v1/requests',headers=headers,json={'explicit_fields':fields,**extra})
    assert reply.status_code==201,reply.text
    assert reply.json()['raw_text']==extra.get('raw_text','')
    return reply.json()

def summary(client,headers,row):
    reply=client.post('/api/v1/requests/'+row['request_id']+'/interpret',headers=headers,json={'expected_revision':row['revision']})
    assert reply.status_code==200,reply.text
    return reply.json()

def test_empty_source_is_real_absence_and_required_scalars_are_still_checked(web):
    app,client,headers=web
    row=create(client,headers,{})
    current=summary(client,headers,row)
    assert current['status']=='NEEDS_CLARIFICATION'
    assert current['summary_origin']=='STRUCTURED_FORM'
    fields={error['field'] for error in current['summary']['field_errors']}
    assert {'destination','start_date','duration_nights','budget_cents','preferences'}<=fields
    assert client.post('/api/v1/requests/'+row['request_id']+'/confirm',headers=headers,json=confirm_body(current)).status_code==409
    assert client.get('/api/v1/requests/'+row['request_id']).json()['raw_text']==''
    listing=client.get('/api/v1/requests').json()['requests']
    assert listing[0]['raw_text']=='' and listing[0]['explicit_fields']=={}


def test_agent_mode_form_summary_and_confirmation_do_not_touch_the_model(observed_web,monkeypatch):
    app,client,headers,agent=observed_web
    async def forbidden(*args):pytest.fail('Structured forms must not invoke interpretation or another model')
    monkeypatch.setattr(agent,'interpret_request',forbidden)
    monkeypatch.setattr(agent,'interpret_request_with_observation',forbidden)
    row=create(client,headers)
    first=summary(client,headers,row)
    assert first['status']=='AWAITING_CONFIRMATION' and first['summary_origin']=='STRUCTURED_FORM'
    assert first['summary']['execution_mode']=='agent'
    assert first['summary']['extracted_requirements']['preferences']==['ready-to-eat meals','quiet']
    assert first['summary']['extracted_requirements']['mandatory_constraints']==['showers']
    assert 'structured_summary_metadata' not in json.dumps(first) and 'interpretation_metadata' not in json.dumps(first)
    confirmed=client.post('/api/v1/requests/'+row['request_id']+'/confirm',headers=headers,json=confirm_body(first))
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()['raw_text']=='' and agent.calls==[]
    again=client.post('/api/v1/requests/'+row['request_id']+'/confirm',headers=headers,json=confirm_body(first))
    assert again.json()==confirmed.json()


@pytest.mark.parametrize('fields,expected',[
    (FIELDS_READY|{'start_date':'2000-01-01'},'start_date'),
    (FIELDS_READY|{'duration_days':8},'duration_days'),
    (FIELDS_READY|{'end_date':'2026-12-31'},'end_date'),
    (FIELDS_READY|{'mandatory_constraints':['no_fires','fire_allowed']},'mandatory_constraints'),
    (FIELDS_READY|{'preferences':[]},'preferences'),
    (FIELDS_READY|{'destination':'Unregistered region'},'destination'),
])
def test_form_summary_keeps_dates_meal_conflicts_and_supported_region_guards(web,fields,expected):
    app,client,headers=web;row=create(client,headers,fields)
    current=summary(client,headers,row)
    assert current['status']!='AWAITING_CONFIRMATION'
    assert expected in {item['field'] for item in current['summary']['field_errors']}


def test_other_requirements_remain_on_assistance_path_without_source_prose(web):
    app,client,headers=web;row=create(client,headers,FIELDS_READY|{'mandatory_constraints':['私人热水淋浴']})
    assert row['requirement_help']['needed']
    reply=client.post('/api/v1/requests/'+row['request_id']+'/interpret',headers=headers,json={'expected_revision':row['revision']})
    assert reply.status_code==409
    reply=client.post('/api/v1/requests/'+row['request_id']+'/requirement-help',headers=headers,
        json={'expected_revision':row['revision'],'expected_profile_revision':row['requirement_help']['profile_revision'],'command_key':'form-assistance-command-0001'})
    assert reply.status_code==201 and reply.json()['snapshot']['raw_text']==''


@pytest.mark.parametrize('mutation',['binding','version','missing'])
def test_form_summary_private_identity_must_match_exact_saved_input(web,mutation):
    app,client,headers=web;row=create(client,headers);current=summary(client,headers,row)
    with app.state.database.transaction() as db:
        saved=json.loads(db.execute('SELECT result FROM request_summaries WHERE request_id=?',(row['request_id'],)).fetchone()[0])
        if mutation=='binding':saved['structured_summary_metadata']['input_sha256']='0'*64
        elif mutation=='version':saved['structured_summary_metadata']['component_version']='unregistered-2'
        else:saved.pop('structured_summary_metadata')
        db.execute('UPDATE request_summaries SET result=? WHERE request_id=?',(encode(saved),row['request_id']))
    reply=client.post('/api/v1/requests/'+row['request_id']+'/confirm',headers=headers,json=confirm_body(current))
    assert reply.status_code==409 and reply.json()['error']['code']=='STALE_CONTEXT'


def test_form_edit_without_source_keeps_legacy_prose_exactly(web):
    app,client,headers=web
    legacy='需要洗澡。\n希望安静，原文需保留。'
    row=create(client,headers,raw_text=legacy)
    reply=client.patch('/api/v1/requests/'+row['request_id'],headers=headers,json={'expected_revision':row['revision'],'explicit_fields':FIELDS_READY})
    assert reply.status_code==200 and reply.json()['raw_text']==legacy


def test_form_summary_survives_restart_and_profile_conflict_without_extra_model_calls(web):
    app,client,headers=web;row=create(client,headers);current=summary(client,headers,row)
    with TestClient(create_app(app.state.settings)) as restarted:
        new_headers=sign_in(restarted)
        assert restarted.get('/api/v1/requests/'+row['request_id']).json()['summary']==current['summary']
        assert restarted.put('/api/v1/profile',headers=new_headers,json={'expected_revision':1,'profile':{'group_size':3}}).status_code==200
        reply=restarted.post('/api/v1/requests/'+row['request_id']+'/confirm',headers=new_headers,json=confirm_body(current))
        assert reply.status_code==409


def test_new_form_still_runs_all_three_registered_model_roles_and_replays_final_after_restart(tmp_path,monkeypatch):
    from safety_runtime_fixtures import application,mock_safety_runtime,role_counts,wait_run,INPUTS,CASES
    from test_finalisation import command
    requests,_=mock_safety_runtime(monkeypatch)
    settings_app=application(tmp_path)
    with TestClient(settings_app) as client:
        headers=sign_in(client)
        assert client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':INPUTS['profile']}).status_code==200
        row=create(client,headers,deepcopy(CASES['normal']['request']['explicit_fields']))
        current=summary(client,headers,row)
        assert current['status']=='AWAITING_CONFIRMATION' and requests==[]
        response=client.post('/api/v1/requests/'+row['request_id']+'/confirm',headers=headers,json=confirm_body(current))
        assert response.status_code==200,response.text
        record=response.json()
        launched=client.post('/api/v1/requests/'+row['request_id']+'/plan',headers=headers,
            json={'expected_request_revision':record['revision'],'command_key':'structured-three-role-plan-0001'})
        assert launched.status_code==202,launched.text
        detail=wait_run(client,launched.json()['run_id'],'SUCCEEDED')
        assert detail['finalisation_available']
        assert role_counts(requests)=={'PLANNING':2,'LOGISTICS':3,'SAFETY':3}
        assert not any(item['role']=='INTERPRETATION' for item in requests)
        saved=client.post('/api/v1/plans/'+detail['plan']['plan_id']+'/finalise',headers=headers,json=command(detail))
        assert saved.status_code in {200,201},saved.text
        result=saved.json();url='/api/v1/plans/'+detail['plan']['plan_id']+'/finals/'+result['final_id']
        snapshot=client.get(url).json()
        count=len(requests)
    with TestClient(create_app(settings_app.state.settings)) as client:
        sign_in(client)
        assert client.get(url).json()==snapshot
        assert len(requests)==count
