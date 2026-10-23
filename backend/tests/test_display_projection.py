"""Public HTTP projection and immutable audit boundaries; no paid requests."""
from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from app.auth import User
from app.application.presentation import display_status, plan_response, tent_capacity
from safety_runtime_fixtures import application, launch, mock_safety_runtime, wait_run
from test_requests import sign_in
from test_plan_changes import change
from test_finalisation import command as final_command

CAMPER = User('camper-a', 'camper.a', 'Camper A', 'CAMPER')
FOUNDER = User('founder', 'founder', 'Founder', 'FOUNDER')


def finalise(client, headers, detail):
    # Deliberately raw HTTP: never use the internal-audit fixture for permissions.
    base = '/api/v1/plans/'+detail['plan']['plan_id']
    response = client.post(base+'/finalise', headers=headers, json=final_command(detail))
    assert response.status_code == 200, response.text
    path = base+'/finals/'+response.json()['final_id']
    result = client.get(path)
    assert result.status_code == 200, result.text
    return path, result.json()['final_record']


def assert_public(value):
    assert value['can_view_model_diagnostics'] is False
    assert 'model_diagnostics' not in value and 'model_planning_trace' not in value
    for audit in value['model_assessment_audits'].values():
        assert 'plan' in audit
        assert not {'trace', 'attempt_id', 'configuration_fingerprint', 'prompt_sha256'} & audit.keys()
    context = value['confirmed_context']['dataset_context']
    assert set(context) == {'dataset_version'}
    text = json.dumps(value)
    for field in ('requested_model', 'served_models', 'http_attempts', 'elapsed_ms',
                  'prompt_tokens', 'completion_tokens', 'configuration_fingerprint', 'selection_config'):
        assert '"'+field+'"' not in text


def test_capacity_rows_are_counts_but_gap_is_authoritative_person_spaces():
    profile = {'group_size': 3, 'equipment': [
        {'item_key':'tent', 'quantity':2, 'capacity_persons':1, 'unit':'item', 'confirmed':True}]}
    log = {'gear_checklist':[{'item_key':'tent', 'unit':'person_space',
        'available_quantity':'2', 'required_quantity':'3', 'missing_quantity':'1'}]}
    facts = tent_capacity(profile, log)
    assert facts['registered_tent_count'] == 2 and facts['registered_capacity'] == 2
    assert facts['missing_person_spaces'] == '1' and facts['group_size'] == 3
    profile['equipment'].append({'item_key':'tent','quantity':1,'capacity_persons':3,'unit':'item','confirmed':False})
    facts = tent_capacity(profile, log)
    assert [r['total_capacity'] for r in facts['records']] == [2,3]
    assert facts['registered_capacity'] == 5 and facts['assessed_capacity'] == '2'
    assert facts['missing_person_spaces'] == '1'  # Not recalculated by this view.
    profile['equipment'][0]['quantity'] = None
    assert tent_capacity(profile, log)['registered_capacity'] is None


@pytest.mark.parametrize('run,version,issues,safety,expected',[
    ('RUNNING','FINALISED',[],None,'RUNNING'),
    ('PENDING','ELIGIBLE_FOR_FINALISATION',[],None,'PENDING'),
    ('SUCCEEDED','BLOCKED',[{'category':'USER_INPUT','code':'EQUIPMENT_DETAILS'}],None,'NEEDS_USER_INPUT'),
    ('SUCCEEDED','REVISION_REQUIRED',[{'category':'EQUIPMENT_GAP','code':'EQUIPMENT_SHORTAGE'}],None,'NEEDS_REVISION'),
    ('SUCCEEDED','ESCALATED',[],{'requires_human_review':True},'AWAITING_REVIEW'),
    ('SUCCEEDED','BLOCKED',[],{'mandatory_blockers':[{'code':'ROAD_CLOSED'}]},'CANNOT_RELEASE'),
])
def test_display_status_is_separate_from_route(run, version, issues, safety, expected):
    assert display_status(run, version, safety=safety, issues=issues) == expected


def test_read_projection_does_not_mutate_saved_artifacts_or_allow_error_context_side_channel():
    raw = {'confirmed_context':{'profile_snapshot':{'equipment':[]},'dataset_context':{
        'dataset_version':'demo','rules_version':'1','selection_config':{'model':'private'}}},
        'run':{'status':'FAILED','error':{'context':{'run_id':'r','requested_model':'private','elapsed_ms':12}}},
        'events':[], 'assessments':[], 'model_assessment_audits':{}}
    before = deepcopy(raw)
    view = plan_response(raw, CAMPER)
    assert view['run']['error']['context'] == {'run_id':'r'}
    assert raw == before
    privileged = plan_response(raw, FOUNDER)
    assert privileged['model_diagnostics']['dataset_context']['selection_config']['model'] == 'private'
    assert raw == before


def test_camper_current_historical_final_and_request_reads_hide_diagnostics(tmp_path, monkeypatch):
    requests,_ = mock_safety_runtime(monkeypatch)
    app = application(tmp_path)
    with TestClient(app) as client:
        headers = sign_in(client)
        detail = launch(client, headers, 'normal')
        assert_public(detail)
        private = app.state.plan_queries.detail(CAMPER,detail['plan']['plan_id'])
        config_hash = private['model_planning_trace']['trace']['configuration_fingerprint']
        assert config_hash not in json.dumps(detail)
        for suffix in ('?include_diagnostics=true','?role=FOUNDER'):
            assert_public(client.get('/api/v1/plans/'+detail['plan']['plan_id']+suffix,headers={'X-Role':'FOUNDER'}).json())
        assert detail['planning_explanation']['source_run_id'] == detail['run']['run_id']
        assert detail['tent_capacity']['missing_person_spaces'] == '0'
        with app.state.database.transaction(write=False) as db:
            audit_before = [tuple(row) for row in db.execute('SELECT * FROM model_planning_traces')]
        path, final = finalise(client, headers, detail)
        assert_public(final)
        assert config_hash not in json.dumps(final)
        with app.state.database.transaction(write=False) as db:
            frozen_before = db.execute('SELECT payload FROM final_records').fetchone()[0]
            assert json.loads(frozen_before)['model_planning_trace']['trace']['usage']
            assert json.loads(frozen_before)['model_assessment_audits']['SAFETY']['trace']['usage']
        confirmed_path = '/api/v1/requests/'+detail['plan']['request_id']
        assert 'selection_config' not in json.dumps(client.get(confirmed_path).json())
        current = client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()
        response = change(client, headers, current, key='display-reassess-only-123456')
        assert response.status_code == 202, response.text
        assessed = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert_public(assessed)
        assert assessed['planning_explanation'] == detail['planning_explanation']
        history = client.get('/api/v1/plans/'+detail['plan']['plan_id']+'?run_id='+detail['run']['run_id']).json()
        assert_public(history)
        assert client.get(path).json()['final_record'] == final
        with app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT payload FROM final_records').fetchone()[0] == frozen_before
            assert [tuple(row) for row in db.execute('SELECT * FROM model_planning_traces')] == audit_before
        call_count = len(requests)
        sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get(path).status_code == 404
        assert client.get('/api/v1/plans/'+detail['plan']['plan_id']).status_code == 404
        assert client.get('/api/v1/runs/'+detail['run']['run_id']).status_code == 404
        assert client.get('/api/v1/review/'+detail['plan']['plan_id']).status_code == 403
        sign_in(client, 'founder', 'CampMate-Founder-2026!')
        assert client.get(path).status_code == 403  # No new cross-owner final privilege.
        assert len(requests) == call_count  # Reads never request a model.


def test_founder_review_sees_separate_diagnostics_and_cannot_bypass_final_ownership(tmp_path, monkeypatch):
    requests,_ = mock_safety_runtime(monkeypatch)
    with TestClient(application(tmp_path, 'budget_revision')) as client:
        headers = sign_in(client)
        detail = launch(client, headers, 'budget_revision')
        assert_public(detail)
        calls = len(requests)
        sign_in(client, 'founder', 'CampMate-Founder-2026!')
        response = client.get('/api/v1/review/'+detail['plan']['plan_id'])
        assert response.status_code == 200, response.text
        review = response.json()
        assert review['can_view_model_diagnostics'] is True
        assert review['model_diagnostics']['planning']['trace']['usage']
        assert review['model_diagnostics']['assessments']['LOGISTICS']['trace']['usage']
        assert review['model_diagnostics']['assessments']['SAFETY']['trace']['usage']
        assert 'trace' not in review['model_assessment_audits']['LOGISTICS']
        assert review['model_assessment_audits']['LOGISTICS']['plan'] == detail['model_assessment_audits']['LOGISTICS']['plan']
        assert client.get('/api/v1/plans/'+detail['plan']['plan_id']).status_code == 403
        assert len(requests) == calls


@pytest.mark.parametrize('state,expected', [('CLOSED','CANNOT_RELEASE'),('OPEN','AWAITING_REVIEW'),('UNKNOWN','AWAITING_REVIEW')])
def test_explicit_road_fact_wins_over_review_route_without_mutating_assessment(state,expected):
    safety={'requires_human_review':True,'mandatory_blockers':[],
        'evidence':[{'kind':'ROAD','road_state':state}]}
    before=deepcopy(safety)
    assert display_status('SUCCEEDED','ESCALATED',safety=safety)==expected
    assert safety==before
    assert display_status('RUNNING','ESCALATED',safety=safety)=='RUNNING'
    assert display_status('SUCCEEDED','FINALISED',safety=safety)=='FINALISED'
