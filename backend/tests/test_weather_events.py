"""Versioned forecast inputs, legacy replay and risk review; no live HTTP."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.application import weather_events as weather
from app.application.agent_runtime import AgentRuntime
from app.application.daily_snapshot import effective_settings
from app.application.synthetic_generation import build
from app.config import Settings
from app.contracts.errors import ContractFailure
from app.application.datasets import inspect_dataset
from app.main import create_app
from safety_runtime_fixtures import mock_safety_runtime
from test_requests import sign_in
from test_reviews import command as review_command
from test_finalisation import command as final_command
from test_trip_evidence_http import wait_run

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT/'data/sydney_surrounds_v2_2'
DAY = date(2026,11,4)


def settings(tmp_path, **changes):
    return Settings(_env_file=None, **{'dataset_path':PACKAGE,'execution_mode':'deterministic_demo',
        'planning_enabled':True,'clock_mode':'fixed','demo_today':DAY,'synthetic_evidence_mode':'rolling',
        'database_path':tmp_path/'weather.sqlite3','snapshot_cache_path':tmp_path/'snapshots',
        'dataset_selection':{},'dataset_scenario_files':[],'workflow_safety_case_ids':[],**changes})


@pytest.mark.parametrize('day',[date(2026,11,3),DAY,date(2026,11,5)])
def test_forecast_event_only_changes_bonnie_weather_on_its_registered_day(day):
    periods=[(day.isoformat(),(day+timedelta(days=30)).isoformat())]
    old=build(PACKAGE,periods,rolling_day=day)
    new=build(PACKAGE,periods,rolling_day=day,weather_events=weather.read_reference())
    old_rows=json.loads(old['data/runtime_safety_evidence.json'])
    new_rows=json.loads(new['data/runtime_safety_evidence.json'])
    changes=[(a,b) for a,b in zip(old_rows,new_rows) if a!=b]
    assert len(changes)==(1 if day==DAY else 0)
    if changes:
        before,after=changes[0]
        assert after['campsite_id']=='bonnie-vale' and after['active_kinds']==['WEATHER']
        assert after['weather']['summary']=='Heavy rain in synthetic forecast.'
        assert after['weather']['valid_from']=='2026-11-04' and after['weather']['valid_until']=='2026-11-10'
        assert after['evidence_facts']['forecast_rain_mm']==60 and after['evidence_facts']['wind_kph']==35
        assert after['origin_case_ids']==['bonnie-vale-rain-2026-11-04']
        for key in before.keys()-{'weather','evidence_facts','origin_case_ids'}:
            assert before[key]==after[key]
    assert new[weather.SNAPSHOT_FILE]==weather.read_reference().payload
    if day==DAY:
        assert hashlib.sha256(old['manifest.json']).hexdigest()=='8fe62304ca7dad2e4659add0374899f1646f4e9829ef4bfe9605746a55c2d081'


def test_legacy_scope_replays_original_bytes_and_new_scope_checks_reference_on_warm_cache(tmp_path,monkeypatch):
    cfg=settings(tmp_path)
    base=inspect_dataset(cfg)
    old_settings=effective_settings(cfg,DAY,weather_policy=None)
    original=(old_settings.dataset_path/'data/runtime_safety_evidence.json').read_bytes()
    runtime=AgentRuntime(SimpleNamespace(settings=cfg))
    legacy=runtime.resolve(weather_policy=None)
    current=runtime.resolve()
    old_scope=SimpleNamespace(dataset_context=legacy.dataset,demo_context=legacy.demo)
    new_scope=SimpleNamespace(dataset_context=current.dataset,demo_context=current.demo)
    assert weather.POLICY_KEY not in legacy.dataset.selection_config
    assert current.dataset.selection_config[weather.POLICY_KEY]==weather.POLICY_VERSION
    assert current.dataset.selection_config[weather.DIGEST_KEY]==weather.read_reference().sha256
    assert runtime.for_scope(old_scope).dataset==legacy.dataset
    assert runtime.for_scope(new_scope).dataset==current.dataset
    assert inspect_dataset(cfg)==base
    assert (old_settings.dataset_path/'data/runtime_safety_evidence.json').read_bytes()==original
    cfg.demo_today=DAY+timedelta(days=1)
    assert weather.POLICY_KEY not in runtime.resolve().dataset.selection_config
    assert runtime.for_scope(new_scope).dataset==current.dataset
    assert runtime.for_scope(old_scope).dataset==legacy.dataset
    path=tmp_path/'changed-reference'/'data'/weather.REFERENCE_FILE
    path.parent.mkdir(parents=True)
    path.write_bytes(weather.read_reference().payload+b'\n')
    monkeypatch.setattr(weather,'APP_ROOT',tmp_path/'changed-reference')
    with pytest.raises(ContractFailure): runtime.for_scope(new_scope)
    assert runtime.for_scope(old_scope).dataset==legacy.dataset
    with pytest.raises(ContractFailure): runtime.resolve(weather_policy='unknown-forecast-policy')


@pytest.mark.parametrize('day',[date(2026,11,3),date(2026,11,5)])
def test_other_days_keep_legacy_snapshot_identity(tmp_path,day):
    cfg=settings(tmp_path,demo_today=day)
    current=effective_settings(cfg,day)
    legacy=effective_settings(cfg,day,weather_policy=None)
    assert current.dataset_path==legacy.dataset_path
    assert current.dataset_selection==legacy.dataset_selection
    assert weather.POLICY_KEY not in current.dataset_selection


@pytest.mark.parametrize('mutation',['unknown_field','duplicate_event','wrong_dates','wrong_source','noninteger_fact',
    'unknown_campsite','missing_file'])
def test_invalid_forecast_reference_fails_closed(tmp_path,monkeypatch,mutation):
    value=json.loads(weather.read_reference().payload)
    if mutation=='unknown_field': value['events'][0]['risk_level']='HIGH'
    elif mutation=='duplicate_event': value['events'].append(deepcopy(value['events'][0]))
    elif mutation=='wrong_dates': value['events'][0]['valid_to']='2026-12-31'
    elif mutation=='wrong_source': value['provenance']['source_type']='REAL'
    elif mutation=='noninteger_fact': value['events'][0]['facts']['forecast_rain_mm']='60'
    elif mutation=='unknown_campsite': value['events'][0]['campsite_id']='unknown-campsite'
    path=tmp_path/'data'/weather.REFERENCE_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value),encoding='utf-8')
    if mutation=='missing_file': path.unlink()
    monkeypatch.setattr(weather,'APP_ROOT',tmp_path)
    with pytest.raises(ContractFailure): effective_settings(settings(tmp_path),DAY)


def test_resealed_generated_forecast_reference_is_rejected(tmp_path):
    cfg=settings(tmp_path)
    effective=effective_settings(cfg,DAY)
    target=effective.dataset_path/weather.SNAPSHOT_FILE
    target.write_bytes(target.read_bytes()+b'\n')
    manifest=effective.dataset_path/'manifest.json'
    value=json.loads(manifest.read_bytes())
    value['files_sha256'][weather.SNAPSHOT_FILE]=hashlib.sha256(target.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ContractFailure): effective_settings(cfg,DAY)


def profile():
    counts={'tent':1,'groundsheet':1,'tent_repair_kit':1,'sleeping_bag':2,'sleeping_mat':2,
        'warm_liner':2,'warm_layers':2,'rain_jacket':2,'drinking_water':20,'meal_supplies':18,
        'first_aid_kit':1,'torch':2,'hand_sanitiser':1,'vehicle':1}
    return {'group_size':2,'experience_level':'INTERMEDIATE','has_children':False,'children_count':0,
        'accessibility_requirements':[],
        'transport':{'transport_type':'CAR','vehicle_count':1,'estimated_km':None,'assumptions':[]},
        'equipment':[{'item_key':key,'label':key,'quantity':n,'confirmed':True,
            'unit':'litre' if key=='drinking_water' else 'portion' if key=='meal_supplies' else 'vehicle' if key=='vehicle' else 'item',
            'capacity_persons':2 if key in {'tent','vehicle'} else None} for key,n in counts.items()]}


@pytest.mark.parametrize('models',[False,True])
def test_complete_weather_risk_review_approval_and_final_save(tmp_path,monkeypatch,models):
    if models:
        _,control=mock_safety_runtime(monkeypatch)
        control['site']='bonnie-vale'
    cfg=settings(tmp_path,execution_mode='agent' if models else 'deterministic_demo',
        logistics_execution='model' if models else 'rules',safety_execution='model' if models else 'rules',
        safety_protocol='compact' if models else 'standard')
    with TestClient(create_app(cfg)) as client:
        headers=sign_in(client)
        saved=client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':profile()})
        assert saved.status_code==200,saved.text
        created=client.post('/api/v1/requests',headers=headers,json={
            'raw_text':'Two adults want a quiet campsite and ready-to-eat meals.',
            'explicit_fields':{'destination':'Sydney & Surrounds','start_date':'2026-11-05',
                'duration_nights':2,'budget_cents':100000,'preferences':['quiet','ready-to-eat meals'],
                'mandatory_constraints':['toilets','showers','potable_water','vehicle_access']}})
        assert created.status_code==201,created.text
        record=created.json();path='/api/v1/requests/'+record['request_id']
        summary=client.post(path+'/interpret',headers=headers,json={'expected_revision':record['revision']})
        assert summary.status_code==200,summary.text
        record=summary.json();assert record['status']=='AWAITING_CONFIRMATION',record
        confirmed=client.post(path+'/confirm',headers=headers,json={'expected_revision':record['revision'],
            'acknowledged':True,'command_key':'weather-event-confirm-command'})
        assert confirmed.status_code==200,confirmed.text
        started=client.post(path+'/plan',headers=headers,json={'expected_request_revision':confirmed.json()['revision'],
            'command_key':'weather-event-plan-command'})
        assert started.status_code==202,started.text
        detail=wait_run(client,started.json()['run_id'],'SUCCEEDED')
        assert detail['version']['content']['selected_campsite_ids']==['bonnie-vale']
        assert detail['version']['status']=='ESCALATED'
        assert {b['code'] for b in detail['eligibility']['blocking_reasons']}=={'REVIEW_REQUIRED'}
        safe=next(a['result'] for a in detail['assessments'] if a['kind']=='SAFETY')
        assert safe['risk_level']=='HIGH' and safe['outcome']=='REVIEW' and not safe['mandatory_blockers']
        assert set(safe['data_quality'].values())=={'AVAILABLE'}
        assert not detail['finalisation_available']
        plan_path='/api/v1/plans/'+detail['plan']['plan_id']
        assert client.post(plan_path+'/finalise',headers=headers,json=final_command(detail)).status_code==409
        founder=sign_in(client,'founder','CampMate-Founder-2026!')
        review_path='/api/v1/review/'+detail['plan']['plan_id']
        review=client.get(review_path).json()
        assert review['review_available']
        approved=client.post(review_path,headers=founder,json=review_command(review))
        assert approved.status_code==200,approved.text
        assert approved.json()['eligibility']['eligible']
        headers=sign_in(client)
        ready=client.get(plan_path).json()
        assert ready['finalisation_available']
        final=client.post(plan_path+'/finalise',headers=headers,json=final_command(ready))
        assert final.status_code==200,final.text
        assert client.get(plan_path+'/finals/'+final.json()['final_id']).status_code==200
