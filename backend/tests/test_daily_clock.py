"""Live Sydney clock + daily simulated inputs. No external model/network calls."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.application.daily_snapshot import effective_settings
from app.application.datasets import inspect_dataset
from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.contracts.errors import ContractFailure
from app.main import create_app
from test_requests import sign_in
from test_trip_evidence_http import wait_run
from test_v2_http_demo import INPUTS, CASES, assessment, finalise
from test_finalisation import command as final_command
from test_plan_changes import change
from test_planning_entry import retry
from test_rule_orchestration import FailOnce
from test_model_logistics_wiring import mock_roles, role_counts, wrap_port

ROOT=Path(__file__).resolve().parents[2]
PACKAGE=ROOT/'data/synthetic_demo_v2_1'


def settings(tmp_path,**overrides):
    return Settings(_env_file=None,**{
        'clock_mode':'current','demo_today':'2026-11-05','execution_mode':'deterministic_demo',
        'planning_enabled':True,'dataset_path':PACKAGE,'database_path':tmp_path/'live.sqlite3',
        'snapshot_cache_path':tmp_path/'snapshots','dataset_selection':{},
        'dataset_scenario_files':[],'workflow_safety_case_ids':[],**overrides})


def launch(client,headers,*,start='2026-10-22',nights=4):
    profile=deepcopy(INPUTS['profile'])
    for item in profile['equipment']:
        if item['item_key']=='meal_supplies': item['quantity']=60
        if item['item_key']=='drinking_water': item['quantity']=40
    response=client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':profile})
    assert response.status_code==200,response.text
    payload=deepcopy(CASES['normal']['request'])
    payload['raw_text']=f'Two campers, {nights} nights from {start}, ready-to-eat meals, AUD 1000.'
    payload['explicit_fields'].update(start_date=start,duration_nights=nights,budget_cents=100000)
    record=client.post('/api/v1/requests',headers=headers,json=payload).json()
    path='/api/v1/requests/'+record['request_id']
    analysed=client.post(path+'/interpret',headers=headers,json={'expected_revision':record['revision']})
    assert analysed.status_code==200,analysed.text
    assert analysed.json()['status']=='AWAITING_CONFIRMATION',analysed.text
    confirmed=client.post(path+'/confirm',headers=headers,json={'expected_revision':analysed.json()['revision'],
        'command_key':'daily-confirm-123456','acknowledged':True})
    assert confirmed.status_code==200,confirmed.text
    response=client.post(path+'/plan',headers=headers,json={'expected_request_revision':confirmed.json()['revision'],
        'command_key':'daily-start-123456'})
    assert response.status_code==202,response.text
    return response.json()['run_id']


def test_legacy_env_date_does_not_freeze_current_clock(tmp_path,monkeypatch):
    monkeypatch.setattr('app.config.sydney_today',lambda:date(2026,10,16))
    env=tmp_path/'old.env'; env.write_text('CAMPMATE_DEMO_TODAY=2026-11-05\n')
    config=Settings(_env_file=env)
    assert config.clock_mode=='current' and config.checking_date()==date(2026,10,16)
    assert Settings(_env_file=None,demo_today='2026-11-05').checking_date()==date(2026,11,5)
    assert settings(tmp_path,clock_mode='fixed').checking_date()==date(2026,11,5)


def test_sydney_clock_uses_sydney_timezone(monkeypatch):
    from datetime import datetime, timezone
    class Boundary:
        @staticmethod
        def now(zone):
            return datetime(2026,10,15,14,30,tzinfo=timezone.utc).astimezone(zone)
    monkeypatch.setattr('app.config.datetime',Boundary)
    assert Settings(_env_file=None).checking_date()==date(2026,10,16)


def test_daily_generation_is_reproducible_independent_and_has_adverse_weather(tmp_path):
    before=inspect_dataset(settings(tmp_path))
    config=effective_settings(settings(tmp_path),date(2026,10,16))
    again=effective_settings(settings(tmp_path),date(2026,10,16))
    assert config.dataset_path==again.dataset_path and config.dataset_path!=PACKAGE
    assert inspect_dataset(settings(tmp_path))==before
    descriptor=inspect_dataset(config)
    dataset=SyntheticDatasetV2Adapter(config.dataset_path).load(expected_context=descriptor.context)
    assert len(dataset.campsites)==10 and dataset.trip_evidence_selector
    rows=json.loads((config.dataset_path/'data/runtime_safety_evidence.json').read_bytes())
    weather=[row for row in rows if row['active_kinds']==['WEATHER']]
    assert len(weather)==10
    assert all(row['weather']['valid_from']=='2026-10-16' and row['weather']['valid_until']=='2026-10-22' for row in weather)
    assert any(row['weather']['summary']!='Mild synthetic conditions.' for row in weather)
    tomorrow=effective_settings(settings(tmp_path),date(2026,10,17))
    assert tomorrow.dataset_path!=config.dataset_path
    assert inspect_dataset(tomorrow).context!=descriptor.context


def test_resealed_cache_corruption_is_rejected_not_repaired(tmp_path):
    config=effective_settings(settings(tmp_path),date(2026,10,16))
    path=config.dataset_path/'data/runtime_safety_evidence.json'
    original=path.read_bytes(); changed=original+b'\n'; path.write_bytes(changed)
    manifest_path=config.dataset_path/'manifest.json'
    manifest=json.loads(manifest_path.read_bytes())
    manifest['files_sha256']['data/runtime_safety_evidence.json']=hashlib.sha256(changed).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ContractFailure):effective_settings(settings(tmp_path),date(2026,10,16))
    assert path.read_bytes()==changed


def test_fixed_default_keeps_sealed_source_and_daily_rejects_scenario_mixing(tmp_path):
    fixed=settings(tmp_path,clock_mode='fixed')
    assert effective_settings(fixed,date(2026,11,5)).dataset_path==PACKAGE
    with pytest.raises(ContractFailure):
        effective_settings(settings(tmp_path,workflow_safety_case_ids=['safety-18']),date(2026,10,16))


def test_oct22_is_allowed_on_oct16_but_future_weather_is_not_fabricated(tmp_path,monkeypatch):
    monkeypatch.setattr('app.config.sydney_today',lambda:date(2026,10,16))
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get('/api/v1/meta').json()['demo_today']=='2026-10-16'
        headers=sign_in(client)
        detail=wait_run(client,launch(client,headers),'SUCCEEDED')
        assert detail['version'] and not detail['finalisation_available']
        assert assessment(detail,'SAFETY')['result']['data_quality']['WEATHER']=='MISSING'
        coverage=detail['trip_evidence_coverage']
        assert coverage['next_weather_check_on']=='2026-10-20'
        assert coverage['weather_forecast_window']=={'start':'2026-10-16','end':'2026-10-22'}
        assert not coverage['weather_requires_staged_checks']
        assert not any(item['kind']!='WEATHER' for item in coverage['issues'])


@pytest.mark.parametrize('model',[False,True])
def test_next_day_reassessment_uses_new_snapshot_keeps_itinerary_and_origin(tmp_path,monkeypatch,model):
    day=[date(2026,10,16)]
    monkeypatch.setattr('app.config.sydney_today',lambda:day[0])
    calls,_=mock_roles(monkeypatch) if model else ([],{})
    app=create_app(settings(tmp_path,execution_mode='agent' if model else 'deterministic_demo',
        logistics_execution='model' if model else 'rules'))
    with TestClient(app) as client:
        headers=sign_in(client)
        old=wait_run(client,launch(client,headers),'SUCCEEDED')
        origin=old['model_planning_trace']
        day[0]=date(2026,10,20)
        stale=client.get('/api/v1/runs/'+old['run']['run_id']).json()
        assert stale['current_inputs_state']=='CHANGED' and not stale['finalisation_available']
        response=change(client,headers,stale)
        assert response.status_code==202,response.text
        new=wait_run(client,response.json()['run_id'],'SUCCEEDED')
        assert new['version']['content']==old['version']['content']
        assert new['version']['version_context']['plan_version_id']==old['version']['version_context']['plan_version_id']
        assert new['confirmed_context']['demo_context']['demo_today']=='2026-10-20'
        assert new['confirmed_context']['dataset_context']!=old['confirmed_context']['dataset_context']
        assert assessment(new,'SAFETY')['result']['data_quality']['WEATHER']=='AVAILABLE'
        assert new['model_planning_trace']==origin
        if model: assert role_counts(calls)['PLANNING']==2


def test_recovery_after_midnight_reuses_saved_products_and_old_snapshot(tmp_path,monkeypatch):
    day=[date(2026,10,16)]
    monkeypatch.setattr('app.config.sydney_today',lambda:day[0])
    calls,_=mock_roles(monkeypatch)
    used=[]
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port,'save_model_logistics_assessment',after=True)
        return port
    wrap_port(monkeypatch,once)
    app=create_app(settings(tmp_path,execution_mode='agent',logistics_execution='model'))
    with TestClient(app) as client:
        headers=sign_in(client)
        failed=wait_run(client,launch(client,headers),'FAILED')
        audit=failed['model_assessment_audits']['LOGISTICS']; count=role_counts(calls)
        day[0]+=timedelta(days=1)
        current=client.get('/api/v1/runs/'+failed['run']['run_id']).json()
        assert current['retry_available'] and current['current_inputs_state']=='CHANGED'
        assert retry(client,headers,current).status_code==202
        recovered=wait_run(client,failed['run']['run_id'],'SUCCEEDED')
        assert recovered['model_assessment_audits']['LOGISTICS']==audit and role_counts(calls)==count
        assert recovered['confirmed_context']['demo_context']['demo_today']=='2026-10-16'
        assert not recovered['finalisation_available']


def test_known_road_closure_survives_daily_generation(tmp_path,monkeypatch):
    monkeypatch.setattr('app.config.sydney_today',lambda:date(2027,4,9))
    app=create_app(settings(tmp_path))
    with TestClient(app) as client:
        headers=sign_in(client)
        # Match the registered road-closure input's actual recommendation.
        profile=deepcopy(INPUTS['profile'])
        assert client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':profile}).status_code==200
        record=client.post('/api/v1/requests',headers=headers,json=CASES['road_closure']['request']).json()
        path='/api/v1/requests/'+record['request_id']
        analysed=client.post(path+'/interpret',headers=headers,json={'expected_revision':record['revision']}).json()
        confirmed=client.post(path+'/confirm',headers=headers,json={'expected_revision':analysed['revision'],
            'command_key':'daily-road-confirm-1234','acknowledged':True})
        assert confirmed.status_code==200,confirmed.text
        run=client.post(path+'/plan',headers=headers,json={'expected_request_revision':confirmed.json()['revision'],
            'command_key':'daily-road-start-1234'}).json()
        detail=wait_run(client,run['run_id'],'SUCCEEDED')
        assert detail['version']['content']['selected_campsite_ids']==['demo-moonlit-field']
        assert assessment(detail,'SAFETY')['result']['outcome']=='BLOCKED'
        assert not detail['finalisation_available']


def test_long_trip_remains_draft_with_staged_weather_guidance(tmp_path,monkeypatch):
    monkeypatch.setattr('app.config.sydney_today',lambda:date(2026,10,16))
    with TestClient(create_app(settings(tmp_path))) as client:
        headers=sign_in(client)
        detail=wait_run(client,launch(client,headers,start='2026-10-17',nights=8),'SUCCEEDED')
        assert detail['version'] and not detail['finalisation_available']
        assert detail['trip_evidence_coverage']['weather_requires_staged_checks']
        assert detail['trip_evidence_coverage']['next_weather_check_on'] is None


def test_past_date_error_names_the_actual_checking_date(tmp_path,monkeypatch):
    monkeypatch.setattr('app.config.sydney_today',lambda:date(2026,10,16))
    with TestClient(create_app(settings(tmp_path))) as client:
        headers=sign_in(client)
        assert client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':INPUTS['profile']}).status_code==200
        payload=deepcopy(CASES['normal']['request']); payload['explicit_fields']['start_date']='2026-10-15'
        record=client.post('/api/v1/requests',headers=headers,json=payload).json()
        response=client.post('/api/v1/requests/'+record['request_id']+'/interpret',headers=headers,json={'expected_revision':record['revision']})
        assert response.status_code==200 and response.json()['status']=='NEEDS_CLARIFICATION'
        errors=response.json()['summary']['field_errors']
        assert any(item['field']=='start_date' and '2026-10-16' in item['message'] for item in errors)


def test_midnight_invalidates_unsaved_eligibility_but_preserves_final_snapshot(tmp_path,monkeypatch):
    day=[date(2026,10,16)]
    monkeypatch.setattr('app.config.sydney_today',lambda:day[0])
    with TestClient(create_app(settings(tmp_path))) as client:
        headers=sign_in(client)
        detail=wait_run(client,launch(client,headers,start='2026-10-18',nights=2),'SUCCEEDED')
        assert detail['finalisation_available']
        saved_path,saved=finalise(client,headers,detail)
        # Reassessment reuses v1 but creates a new unsaved evaluation.
        current=client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()
        response=change(client,headers,current)
        assert response.status_code==202,response.text
        current=wait_run(client,response.json()['run_id'],'SUCCEEDED')
        assert current['finalisation_available']
        day[0]+=timedelta(days=1)
        response=client.post('/api/v1/plans/'+detail['plan']['plan_id']+'/finalise',headers=headers,
            json=final_command(current,key='daily-stale-final'))
        assert response.status_code==409 and response.json()['error']['code']=='STALE_CONTEXT'
        assert client.get(saved_path).json()['final_record']==saved


def test_missing_weather_cannot_be_finalised_via_direct_http(tmp_path,monkeypatch):
    monkeypatch.setattr('app.config.sydney_today',lambda:date(2026,10,16))
    with TestClient(create_app(settings(tmp_path))) as client:
        headers=sign_in(client)
        detail=wait_run(client,launch(client,headers),'SUCCEEDED')
        response=client.post('/api/v1/plans/'+detail['plan']['plan_id']+'/finalise',headers=headers,
            json=final_command(detail,key='daily-missing-final'))
        assert response.status_code==409
        assert response.json()['error']['code']=='FINALISATION_BLOCKED'
