"""Advisory-only cooking checks: no model calls, persistence or eligibility."""
from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from app.application.cooking_preparation import outline, preview
from app.application.logistics_issues import project
from test_logistics_issues import saved, result, question
from test_requests import sign_in
from test_trip_evidence_http import app, launch, wait_run
from test_v2_http_demo import CASES, INPUTS
from test_model_logistics_wiring import mock_roles


SELF = {'preferences': ['self-catered meals']}


def gear(key, quantity, **patch):
    return dict(item_key=key, label='Custom name', quantity=quantity, unit='item',
        capacity_persons=None, confirmed=True) | patch


def test_first_cooking_question_includes_inactive_fuel_without_inventing_official_gap():
    data = saved()
    data['confirmed_context']['requirements'].update(SELF)
    result(data)['clarifications'] = [question('cooking_method')]
    original = deepcopy(data)
    issue, = project(data)
    assert issue['code'] == 'COOKING_ARRANGEMENT'
    assert issue['related_equipment'] == ['camping_stove', 'fuel_canister']
    preparation = issue['cooking_preparation']
    assert preparation['official_assessment'] is False
    assert preparation['fuel_price_status'] == 'MISSING_REFERENCE'
    assert len(preparation['items']) == 2
    assert all(item['confirmed_quantity'] is None for item in preparation['items'])
    assert 'required_fuel_quantity' not in preparation
    assert data == original and result(data)['gear_checklist'] == []


@pytest.fixture
def web(tmp_path):
    application = app(tmp_path)
    with TestClient(application) as client:
        headers = sign_in(client)
        yield application, client, headers


def test_preview_uses_registered_quantity_rule_and_keeps_unknowns_and_confirmation(web):
    application, _, _ = web
    dataset = application.state.runtime.resolve().agent.dataset
    for quantity in (None, 0):
        value = preview(dataset, SELF, [gear('camping_stove', quantity)])
        assert value['required_fuel_quantity'] is None
        assert value['example'] == {'stove_quantity': 1, 'fuel_quantity': '2'}
        assert value['calculation_status'] == 'WAITING_FOR_STOVE'
    value = preview(dataset, SELF, [gear('camping_stove', 1, confirmed=False), gear('fuel_canister', None)])
    assert value['required_fuel_quantity'] == '2' and value['fuel_gap'] is None
    assert value['items'][0]['confirmed_quantity'] is None
    assert value['official_assessment'] is False
    value = preview(dataset, SELF, [gear('camping_stove', 1), gear('fuel_canister', 2)])
    assert value['fuel_gap'] == '0' and value['fuel_price_status'] == 'MISSING_REFERENCE'
    assert not {'eligibility', 'finalisation_available', 'outcome'} & value.keys()
    wrong = preview(dataset, SELF, [gear('camping_stove', 1, unit='set')])
    assert wrong['required_fuel_quantity'] is None and not wrong['items'][0]['unit_valid']
    duplicate = preview(dataset, SELF, [gear('camping_stove', 1), gear('camping_stove', 1, confirmed=False)])
    assert duplicate['required_fuel_quantity'] == '3' and duplicate['items'][0]['confirmed_quantity'] is None
    assert outline({'preferences': ['ready-to-eat meals']}, {}) is None


def make_request(client, headers):
    payload = deepcopy(CASES['normal']['request'])
    payload['explicit_fields'].update(SELF)
    response = client.post('/api/v1/requests', headers=headers, json=payload)
    assert response.status_code == 201, response.text
    request_id = response.json()['request_id']
    assert client.get('/api/v1/requests/'+request_id).json()['cooking_preparation']['conditional_items'] == ['fuel_canister']
    return request_id


def business_snapshot(application):
    tables = ('profiles', 'requests', 'request_summaries', 'plans', 'runs', 'versions',
        'assessments', 'final_records', 'write_receipts', 'trip_series')
    with application.state.database.transaction(write=False) as connection:
        return {table: [tuple(row) for row in connection.execute('SELECT * FROM '+table)] for table in tables}


def test_http_is_explicit_candidate_only_no_agent_dispatch_no_business_write(web, monkeypatch):
    application, client, headers = web
    request_id = make_request(client, headers)
    agent = application.state.runtime.resolve().agent
    def forbidden(*args, **kwargs):
        pytest.fail('Preparation must not invoke an agent role')
    for name in ('interpret_request', 'generate_itinerary', 'assess_logistics', 'assess_safety'):
        if hasattr(type(agent), name):
            monkeypatch.setattr(type(agent), name, forbidden)
    before = business_snapshot(application)
    body = {'request_id': request_id, 'equipment': [gear('camping_stove', 1), gear('fuel_canister', 2)]}
    for _ in range(2):
        response = client.post('/api/v1/preparation/cooking', headers=headers, json=body)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['required_fuel_quantity'] == '2' and value['fuel_gap'] == '0'
        assert value['scope'] == 'PREPARATION_ONLY' and value['official_assessment'] is False
        assert not any(word in response.text for word in ('trace', 'token_usage', 'config_digest', 'api_key'))
    assert business_snapshot(application) == before
    assert client.post('/api/v1/preparation/cooking', json=body).status_code == 403
    for patch in ({'plan_id': 'extra-source'}, {'equipment': [gear('fuel_canister', -1)]}):
        assert client.post('/api/v1/preparation/cooking', headers=headers, json=body | patch).status_code == 422
    assert client.post('/api/v1/preparation/cooking', headers=headers, json={'equipment': []}).status_code == 422
    other = sign_in(client, 'camper.b', 'CampMate-B-2026!')
    assert client.post('/api/v1/preparation/cooking', headers=other, json=body).status_code == 404
    founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
    assert client.post('/api/v1/preparation/cooking', headers=founder, json=body).status_code == 403


def test_owned_plan_precheck_uses_saved_meal_not_candidate_preferences(web):
    application, client, headers = web
    run = wait_run(client, launch(client, headers), 'SUCCEEDED')
    before = business_snapshot(application)
    response = client.post('/api/v1/preparation/cooking', headers=headers,
        json={'plan_id': run['plan']['plan_id'], 'equipment': [gear('camping_stove', 1)]})
    assert response.status_code == 200, response.text
    assert response.json()['applicable'] is False  # saved normal request is ready-to-eat
    assert business_snapshot(application) == before


def test_first_self_catered_http_read_exposes_both_preparations_even_when_fuel_rule_is_inactive(web, monkeypatch):
    application, client, headers = web
    payload = deepcopy(CASES['normal']['request'])
    payload['explicit_fields'].update(SELF)
    profile = deepcopy(INPUTS['profile'])
    profile['equipment'] = [row for row in profile['equipment'] if row['item_key'] not in ('camping_stove', 'fuel_canister')]
    monkeypatch.setitem(CASES['normal'], 'request', payload)
    monkeypatch.setitem(INPUTS, 'profile', profile)
    run = wait_run(client, launch(client, headers), 'SUCCEEDED')
    path = '/api/v1/plans/'+run['plan']['plan_id']
    response = client.get(path)
    assert response.status_code == 200, response.text
    value = response.json()
    preparation = value['cooking_preparation']
    assert {row['item_key'] for row in preparation['items']} == {'camping_stove', 'fuel_canister'}
    assert preparation['official_assessment'] is False
    assert preparation['fuel_price_status'] == 'MISSING_REFERENCE'
    logistics = next(row['result'] for row in value['assessments'] if row['kind'] == 'LOGISTICS')
    assert not any(row['item_key'] == 'fuel_canister' for row in logistics['gear_checklist'])
    before = business_snapshot(application)
    response = client.post('/api/v1/preparation/cooking', headers=headers, json={
        'plan_id': run['plan']['plan_id'], 'equipment': [gear('camping_stove', 1), gear('fuel_canister', None)]})
    assert response.status_code == 200, response.text
    assert response.json()['required_fuel_quantity'] == '2'
    assert response.json()['fuel_gap'] is None
    assert business_snapshot(application) == before
    assert client.get(path).json() == value


def test_deleted_request_is_not_a_preview_source(web):
    _, client, headers = web
    request_id = make_request(client, headers)
    assert client.delete('/api/v1/requests/'+request_id, headers=headers).status_code == 204
    assert client.post('/api/v1/preparation/cooking', headers=headers,
        json={'request_id': request_id, 'equipment': []}).status_code == 404


def test_agent_mode_preparation_does_not_call_any_model(tmp_path, monkeypatch):
    calls, _ = mock_roles(monkeypatch)
    with TestClient(app(tmp_path, model=True)) as client:
        headers = sign_in(client)
        request_id = make_request(client, headers)
        response = client.post('/api/v1/preparation/cooking', headers=headers,
            json={'request_id': request_id, 'equipment': [gear('camping_stove', 1)]})
        assert response.status_code == 200, response.text
        assert response.json()['required_fuel_quantity'] == '2'
        assert calls == []
