"""A26 business/SQLite integration, real components with OFFLINE model HTTP."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import time

from fastapi.testclient import TestClient
import pytest

from app.application.agent_runtime import DATASET_AGENT_FACTORIES
from app.application.datasets import inspect_dataset
from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.config import Settings
from app.contracts.errors import ContractFailure
from app.main import create_app
from test_model_logistics_wiring import mock_roles, role_counts, assert_audit, wrap_port
from test_plan_changes import change
from test_planning_entry import retry
from test_requests import sign_in
from test_rule_orchestration import FailOnce
from test_v2_http_demo import INPUTS, CASES, finalise, assessment

ROOT=Path(__file__).resolve().parents[2]
PACKAGE=ROOT/'data/synthetic_demo_v2_1'


from audit_test_reads import internal_audit_reads, json_with_internal_audits

# Runtime audit assertions use internal reads, not the public Camper response.
finalise = internal_audit_reads(finalise)


def wait_run(client,run_id,status):
    # The expanded immutable index is verified on HTTP reads. Five seconds
    # from tiny legacy fixtures is flaky under concurrent CI load. This only
    # polls persisted state; it never submits RETRY or another model request.
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        response=client.get('/api/v1/runs/'+run_id)
        assert response.status_code==200,response.status_code
        data=json_with_internal_audits(client, response); run=data['run']
        if run['status']==status:
            return data
        if run['status'] in {'FAILED','CANCELLED','SUCCEEDED'}:
            pytest.fail(f"Unexpected terminal state: {run['status']} at {run['stage']}; error={run['error']}")
        time.sleep(.02)
    pytest.fail(f"Persisted run did not reach {status}; state={run['status']} stage={run['stage']}")


def app(tmp_path,case='normal',*,model=False,today=None,package=PACKAGE):
    return create_app(Settings(_env_file=None,execution_mode='agent' if model else 'deterministic_demo',
        logistics_execution='model' if model else 'rules',planning_enabled=True,dataset_path=package,
        database_path=tmp_path/'trip-evidence.sqlite3',demo_today=today or CASES[case]['settings']['demo_today'],
        workflow_safety_case_ids=[],dataset_scenario_files=[],dataset_selection={}))


def launch(client,headers,case='normal',*,start=None,unknown_tent=False):
    profile=deepcopy(INPUTS['profile'])
    if unknown_tent:
        next(item for item in profile['equipment'] if item['item_key']=='tent')['quantity']=None
    result=client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':profile})
    assert result.status_code==200,result.text
    payload=deepcopy(CASES[case]['request'])
    if start:
        old=payload['explicit_fields']['start_date']
        payload['explicit_fields']['start_date']=start
        payload['raw_text']=payload['raw_text'].replace(old,start)
    result=client.post('/api/v1/requests',headers=headers,json=payload)
    assert result.status_code==201,result.text
    request=json_with_internal_audits(client, result); path='/api/v1/requests/'+request['request_id']
    result=client.post(path+'/interpret',headers=headers,json={'expected_revision':request['revision']})
    assert result.status_code==200 and json_with_internal_audits(client, result)['status']=='AWAITING_CONFIRMATION',result.text
    result=client.post(path+'/confirm',headers=headers,json={'expected_revision':json_with_internal_audits(client, result)['revision'],
        'command_key':'trip-confirm-123456','acknowledged':True})
    assert result.status_code==200,result.text
    confirmed=json_with_internal_audits(client, result)
    result=client.post(path+'/plan',headers=headers,json={'expected_request_revision':confirmed['revision'],
        'command_key':'trip-plan-123456'})
    assert result.status_code==202,result.text
    return json_with_internal_audits(client, result)['run_id']


@pytest.mark.parametrize('model',[False,True])
def test_one_instance_revises_campsite_then_reassesses_without_switching_safety_case(tmp_path,monkeypatch,model):
    requests,_=mock_roles(monkeypatch) if model else ([],{})
    with TestClient(app(tmp_path,'budget_revision',model=model)) as client:
        headers=sign_in(client)
        old=wait_run(client,launch(client,headers,'budget_revision'),'SUCCEEDED')
        assert old['version']['content']['selected_campsite_ids']==['demo-wattle-rest']
        assert assessment(old,'SAFETY')['result']['outcome']=='PASSED'
        assert assessment(old,'LOGISTICS')['result']['total_cents']==25100
        assert not old['finalisation_available']
        response=change(client,headers,old,'revise',feedback='cheaper campsite')
        assert response.status_code==202,response.text
        revised=wait_run(client,json_with_internal_audits(client, response)['run_id'],'SUCCEEDED')
        assert revised['version']['content']['selected_campsite_ids']==['demo-moonlit-field']
        assert assessment(revised,'SAFETY')['result']['outcome']=='PASSED'
        assert revised['finalisation_available']
        choices=revised['confirmed_context']['dataset_context']['selection_config']
        assert choices['safety_case_ids']=='[]' and choices['b_evidence_policy']=='trip-evidence-selection-1'
        refs=assessment(revised,'LOGISTICS')['result']['source_refs']
        ids={item['record_id'] for item in refs if item['dataset_file']=='runtime_safety_evidence.json'}
        assert any(key.startswith('trip-demo-moonlit-field') for key in ids)
        assert not any(key.startswith('trip-demo-wattle-rest') for key in ids)
        path,snapshot=finalise(client,headers,revised)
        current=json_with_internal_audits(client, client.get('/api/v1/plans/'+old['plan']['plan_id']))
        response=change(client,headers,current,key='trip-reassess-123456')
        assert response.status_code==202,response.text
        reassessed=wait_run(client,json_with_internal_audits(client, response)['run_id'],'SUCCEEDED')
        assert reassessed['version']['version_context']['plan_version_id']==revised['version']['version_context']['plan_version_id']
        assert reassessed['version']['content']==revised['version']['content']
        assert json_with_internal_audits(client, client.get(path))['final_record']==snapshot
        if model:
            before,after=assert_audit(revised),assert_audit(reassessed)
            assert before['audit_id']!=after['audit_id']
            assert reassessed['model_planning_trace']==revised['model_planning_trace']
            assert role_counts(requests)=={'PLANNING':4,'LOGISTICS':9}
        for kind in ('LOGISTICS','SAFETY'):
            before=deepcopy(assessment(revised,kind)['result']); after=deepcopy(assessment(reassessed,kind)['result'])
            for value in (before,after):
                value.pop('version_context'); value.pop('depends_on_assessment_id',None)
            assert before==after


def test_boundary_missing_weather_is_coverage_not_missing_user_weather_field(tmp_path):
    with TestClient(app(tmp_path,today='2026-11-29')) as client:
        headers=sign_in(client)
        detail=wait_run(client,launch(client,headers,start='2026-11-30'),'SUCCEEDED')
        assert assessment(detail,'SAFETY')['result']['outcome']=='REVIEW'
        assert not detail['finalisation_available']
        questions=assessment(detail,'LOGISTICS')['result']['clarifications']
        assert any(value['field'].startswith('evidence.weather.') and 'source maintenance' in value['question'] for value in questions)


def test_new_normal_index_does_not_implicitly_load_old_missing_fixture(tmp_path):
    with TestClient(app(tmp_path,'missing_evidence')) as client:
        headers=sign_in(client)
        detail=wait_run(client,launch(client,headers,'missing_evidence'),'SUCCEEDED')
        assert detail['version']['content']['selected_campsite_ids']==['demo-river-flat']
        assert assessment(detail,'SAFETY')['result']['data_quality']['WEATHER']=='AVAILABLE'
        assert not any(item['record_id']=='safety-02' for item in assessment(detail,'SAFETY')['result']['source_refs'])


@pytest.mark.parametrize('model',[False,True])
def test_dated_road_closure_stays_blocked_in_automatic_mode(tmp_path,monkeypatch,model):
    if model:
        _,control=mock_roles(monkeypatch)
        control['site']='demo-moonlit-field'
    with TestClient(app(tmp_path,'road_closure',model=model)) as client:
        headers=sign_in(client)
        detail=wait_run(client,launch(client,headers,'road_closure'),'SUCCEEDED')
        result=assessment(detail,'SAFETY')['result']
        assert result['outcome']=='BLOCKED' and result['data_quality']['ROAD']=='AVAILABLE'
        assert any(value['code']=='ROAD_CLOSED' for value in result['mandatory_blockers'])
        assert not detail['finalisation_available']


def test_saved_model_logistics_is_reused_after_restart_and_lost_receipt(tmp_path,monkeypatch):
    requests,_=mock_roles(monkeypatch)
    used=[]
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port,'save_model_logistics_assessment',after=True)
        return port
    wrap_port(monkeypatch,once)
    with TestClient(app(tmp_path,model=True)) as client:
        headers=sign_in(client)
        failed=wait_run(client,launch(client,headers),'FAILED')
        assert failed['retry_available']
        saved_audit=failed['model_assessment_audits']['LOGISTICS']
        saved_version,saved_origin=failed['version']['content'],failed['model_planning_trace']
    with TestClient(app(tmp_path,model=True)) as client:
        headers=sign_in(client)
        assert retry(client,headers,failed).status_code==202
        recovered=wait_run(client,failed['run']['run_id'],'SUCCEEDED')
        assert recovered['model_assessment_audits']['LOGISTICS']==saved_audit
        assert recovered['version']['content']==saved_version and recovered['model_planning_trace']==saved_origin
        assert role_counts(requests)=={'PLANNING':2,'LOGISTICS':3}


def test_new_index_snapshot_does_not_rewrite_historical_saved_audit_or_final(tmp_path,monkeypatch):
    requests,_=mock_roles(monkeypatch)
    package=tmp_path/'package'; shutil.copytree(PACKAGE,package)
    with TestClient(app(tmp_path,model=True,package=package)) as client:
        headers=sign_in(client)
        detail=wait_run(client,launch(client,headers),'SUCCEEDED')
        path,snapshot=finalise(client,headers,detail)
        origin=detail['model_planning_trace']; audit=assert_audit(detail)
    # Independent test copy only, never the sealed production package.
    manifest=json.loads((package/'manifest.json').read_bytes())
    values=json.loads((package/'data/runtime_safety_evidence.json').read_bytes())
    target=next(value for value in values if value['active_kinds']==['WEATHER'])
    target['evidence_facts']['temperature_min_c']=11
    payload=(json.dumps(values,sort_keys=True)+'\n').encode()
    for name in ('runtime_safety_evidence.json','synthetic_safety_scenarios.json'):
        (package/'data'/name).write_bytes(payload)
        manifest['files_sha256']['data/'+name]=hashlib.sha256(payload).hexdigest()
    (package/'manifest.json').write_text(json.dumps(manifest))
    with TestClient(app(tmp_path,model=True,package=package)) as client:
        headers=sign_in(client)
        read=client.get('/api/v1/runs/'+detail['run']['run_id'])
        assert read.status_code==200,read.text
        assert json_with_internal_audits(client, read)['model_planning_trace']==origin
        assert json_with_internal_audits(client, read)['model_assessment_audits']['LOGISTICS']==audit
        assert json_with_internal_audits(client, read)['current_inputs_error'] is not None
        assert json_with_internal_audits(client, client.get(path))['final_record']==snapshot
        assert role_counts(requests)=={'PLANNING':2,'LOGISTICS':3}


def test_changed_index_cannot_resume_old_failed_run_or_regenerate_saved_model_products(tmp_path,monkeypatch):
    requests,_=mock_roles(monkeypatch)
    package=tmp_path/'package'; shutil.copytree(PACKAGE,package)
    used=[]
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port,'save_model_logistics_assessment',after=True)
        return port
    wrap_port(monkeypatch,once)
    with TestClient(app(tmp_path,model=True,package=package)) as client:
        headers=sign_in(client)
        failed=wait_run(client,launch(client,headers),'FAILED')
        audit=failed['model_assessment_audits']['LOGISTICS']
    manifest_path=package/'manifest.json'
    manifest=json.loads(manifest_path.read_bytes())
    manifest['revision_date']='2026-10-16'
    manifest_path.write_text(json.dumps(manifest))  # Only the independent test copy.
    with TestClient(app(tmp_path,model=True,package=package)) as client:
        headers=sign_in(client)
        read=client.get('/api/v1/runs/'+failed['run']['run_id'])
        assert read.status_code==200
        assert json_with_internal_audits(client, read)['model_assessment_audits']['LOGISTICS']==audit
        result=retry(client,headers,json_with_internal_audits(client, read))
        assert result.status_code==409 and json_with_internal_audits(client, result)['error']['code']=='STALE_CONTEXT'
        assert role_counts(requests)=={'PLANNING':2,'LOGISTICS':3}


def test_new_snapshot_identity_oracle_and_manifest_are_checked_before_binding(tmp_path):
    descriptor=inspect_dataset(Settings(_env_file=None,dataset_path=PACKAGE))
    dataset=SyntheticDatasetV2Adapter(PACKAGE).load(expected_context=descriptor.context)
    assert dataset.context.dataset_version=='2.1.0'
    package=tmp_path/'package'; shutil.copytree(PACKAGE,package)
    path=package/'data/runtime_safety_evidence.json'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ContractFailure) as error:
        SyntheticDatasetV2Adapter(package).load(expected_context=descriptor.context)
    assert error.value.error.code=='STALE_CONTEXT'
    with pytest.raises(ContractFailure): inspect_dataset(Settings(_env_file=None,dataset_path=package))
