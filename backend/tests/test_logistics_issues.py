from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.application.logistics_issues import project
from test_requests import sign_in
from test_trip_evidence_http import app, wait_run
from test_v2_http_demo import CASES, INPUTS


def saved():
    return {'plan': {'request_id': 'owned-request'}, 'confirmed_context': {
        'requirements': {'budget_cents': 100000}, 'profile_snapshot': {'group_size': 2,
            'has_children': False, 'children_count': 0,
            'transport': {'transport_type': 'CAR', 'vehicle_count': 1, 'estimated_km': '100'},
            'equipment': [{'item_key': 'tent', 'quantity': 1, 'capacity_persons': None, 'confirmed': True, 'unit': 'item'}]}},
        'assessments': [{'kind': 'LOGISTICS', 'result': {'outcome': 'REVISION', 'transport_feasible': True,
            'total_cents': None, 'budget_difference_cents': None, 'clarifications': [], 'cost_breakdown': [],
            'gear_checklist': []}}]}


def result(data):
    return data['assessments'][0]['result']


def question(field):
    return {'field': field, 'question': 'Explain input', 'reason': 'Unknown'}


def test_tent_capacity_has_observed_value_required_capacity_and_direct_target():
    data = saved()
    result(data)['clarifications'] = [question('equipment.tent')]
    issue, = project(data)
    assert issue['code'] == 'EQUIPMENT_DETAILS'
    assert issue['current']['records'][0]['quantity'] == 1
    assert issue['current']['records'][0]['capacity_persons'] is None
    assert issue['required']['capacity_persons'] == 2
    query = parse_qs(urlsplit(issue['action_url']).query)
    assert query == {'focus': ['equipment.tent.capacity'], 'request_id': ['owned-request']}


def test_distance_and_parking_costs_collapse_under_their_missing_inputs():
    data = saved()
    result(data)['clarifications'] = [question('transport.estimated_km'), question('transport.vehicle_count'), question('cost.cost-02')]
    result(data)['cost_breakdown'] = [dict(item_key=key, category='TRANSPORT', subtotal_cents=None, unit_price_cents=35) for key in ('cost-02', 'cost-15')]
    assert {i['code'] for i in project(data)} == {'DISTANCE', 'VEHICLE_COUNT'}


def test_missing_price_is_system_data_not_a_profile_edit():
    data = saved()
    result(data)['cost_breakdown'] = [dict(item_key='demo-lake-meadow', category='CAMPSITE', subtotal_cents=None, unit_price_cents=None)]
    issue, = project(data)
    assert issue['code'] == 'PRICE_DATA' and issue['category'] == 'DATA_GAP'
    assert issue['action_url'] is None and issue['target'] == 'OPERATOR'


def test_weather_and_tent_input_remain_independent():
    data = saved()
    result(data)['clarifications'] = [question('evidence.weather.temperature_min_c'), question('gear_rule_input.forecast_rain_mm'), question('equipment.tent')]
    assert {i['code'] for i in project(data)} == {'WEATHER_DATA', 'EQUIPMENT_DETAILS'}


def test_meal_root_deduplicates_old_questions_without_hiding_tent():
    data = saved()
    result(data)['clarifications'] = [question('meal_mode'), question('gear_rule_input.meal_mode'), question('equipment.camping_stove'), question('equipment.tent')]
    assert {i['code'] for i in project(data)} == {'MEAL_CHOICE', 'EQUIPMENT_DETAILS'}


@pytest.mark.parametrize('key', ['sleeping_bag', 'drinking_water', 'meal_supplies'])
def test_real_essential_gaps_need_actions_even_without_clarifications(key):
    data = saved()
    result(data)['gear_checklist'] = [dict(item_key=key, essential=True, required_quantity='2', available_quantity='1', missing_quantity='1', arrangement_status='MISSING', unit='item')]
    issue, = project(data)
    assert issue['code'] == 'EQUIPMENT_SHORTAGE' and issue['item_key'] == key
    assert issue['required']['missing_quantity'] == '1'


def test_unknown_fields_do_not_invent_user_fields_and_success_is_empty():
    data = saved()
    result(data)['clarifications'] = [question('gear_rule_input.new_external_fact')]
    assert project(data)[0]['target'] == 'OPERATOR'
    result(data).update(clarifications=[], outcome='PASSED', total_cents=24100)
    assert project(data) == []


def test_projection_does_not_mutate_saved_results():
    data = saved(); before = deepcopy(data)
    project(data)
    assert data == before


def test_dependent_groundsheet_need_collapses_to_tent_capacity_but_real_price_does_not():
    data = saved(); r = result(data)
    r['clarifications'] = [question('equipment.tent'), question('gear_rule_input.tent_count'),
        dict(field='equipment.groundsheet', question='Confirm stock', reason='Missing v2 rule inputs: tent_count.')]
    r['gear_checklist'] = [dict(item_key='groundsheet', essential=True, required_quantity=None,
        available_quantity='1', missing_quantity=None, arrangement_status='UNCONFIRMED', unit='item')]
    r['cost_breakdown'] = [dict(item_key='groundsheet', category='ADDITIONAL_GEAR', quantity=None, subtotal_cents=None, unit_price_cents=None)]
    issue, = project(data)
    assert issue['item_key'] == 'tent' and issue['affects'] == ['equipment.groundsheet']
    r['gear_checklist'][0].update(required_quantity='2', missing_quantity='1', arrangement_status='MISSING')
    r['cost_breakdown'][0]['quantity'] = '1'
    gear, = [i for i in project(data) if i['item_key'] == 'groundsheet']
    assert gear['code'] == 'EQUIPMENT_SHORTAGE'
    assert gear['cost_impacts'] == [{'code':'PRICE_DATA','item_key':'groundsheet','category':'ADDITIONAL_GEAR','unit_price_cents':None}]
    assert not any(i['code'] == 'PRICE_DATA' for i in project(data))


def test_self_catered_has_both_gear_and_meal_correction_paths():
    data = saved(); data['plan']['plan_id'] = 'owned-plan'; result(data)['clarifications'] = [question('cooking_method')]
    issue, = project(data)
    assert issue['code'] == 'COOKING_ARRANGEMENT'
    assert issue['action_url'] == '/plans/owned-plan/update?focus=request-meal'
    assert 'equipment.camping_stove' in issue['alternate_action_url']


def test_fuel_gap_and_missing_price_share_one_named_task_and_preserve_saved_cost():
    data = saved(); data['plan']['plan_id']='owned-plan'; r=result(data)
    r['gear_checklist']=[dict(item_key='fuel_canister',essential=True,required_quantity='3',available_quantity='0',missing_quantity='3',arrangement_status='MISSING',unit='item')]
    r['cost_breakdown']=[dict(item_key='fuel_canister',category='ADDITIONAL_GEAR',quantity='3',subtotal_cents=None,unit_price_cents=None)]
    before=deepcopy(data)
    issue,=project(data)
    assert issue['item_key']=='fuel_canister' and issue['code']=='EQUIPMENT_SHORTAGE'
    assert issue['cost_impacts'][0]['item_key']=='fuel_canister'
    assert issue['arrangement_action_url']=='/plans/owned-plan/update?focus=request-meal'
    assert 'plan_id=owned-plan' in issue['action_url']
    assert data==before
    # Only an actual new saved assessment can remove this gap, not a form edit.
    data['confirmed_context']['profile_snapshot']['equipment'].append(dict(item_key='fuel_canister',quantity=3,unit='item',confirmed=True,capacity_persons=None))
    assert project(data)[0]['required']['missing_quantity']=='3'
    r['gear_checklist'][0].update(available_quantity='3',missing_quantity='0',arrangement_status='OWNED')
    r.update(cost_breakdown=[],outcome='PASSED',total_cents=10000)
    assert project(data)==[]


def test_independent_price_problem_names_gear_without_a_fake_profile_price_editor():
    data=saved();r=result(data)
    r['gear_checklist']=[dict(item_key='fuel_canister',essential=False,required_quantity=None,available_quantity=None,missing_quantity=None,arrangement_status='UNCONFIRMED',unit='item')]
    r['cost_breakdown']=[dict(item_key='fuel_canister',category='ADDITIONAL_GEAR',subtotal_cents=None,unit_price_cents=None)]
    issue,=project(data)
    assert issue['item_key']=='fuel_canister' and issue['code']=='PRICE_DATA'
    assert issue['target']=='OPERATOR' and issue['action_url'] is None


def test_unknown_upstream_input_exposes_dependent_check_without_guessing_quantity():
    data=saved();r=result(data)
    r['clarifications']=[question('equipment.camping_stove'),question('gear_rule_input.stove_count'),
        dict(field='equipment.fuel_canister',question='Confirm stock',reason='Missing v2 rule inputs: stove_count.')]
    r['gear_checklist']=[dict(item_key='fuel_canister',essential=True,required_quantity=None,available_quantity='0',missing_quantity=None,arrangement_status='UNCONFIRMED',unit='item')]
    issue,=project(data)
    assert issue['item_key']=='camping_stove'
    assert issue['pending_checks']==[{'item_key':'fuel_canister','status':'WAITING_FOR_INPUT'}]


def test_budget_and_meal_actions_keep_explicit_plan_not_copy_from():
    data=saved();data['plan']['plan_id']='owned-plan';r=result(data)
    r.update(clarifications=[question('meal_mode')],total_cents=110000,budget_difference_cents=10000)
    issues=project(data)
    assert next(i for i in issues if i['code']=='MEAL_CHOICE')['action_url']=='/plans/owned-plan/update?focus=request-meal'
    assert next(i for i in issues if i['code']=='OVER_BUDGET')['action_url']=='/plans/owned-plan/update?focus=request-budget'
    assert 'copy_from' not in str(issues)


def test_unexplained_eligibility_issue_does_not_fall_back_to_edit_profile():
    data = saved(); result(data).update(outcome='PASSED', total_cents=24100)
    data['eligibility'] = {'blocking_reasons': [{'code': 'COSTS_INCOMPLETE'}]}
    issue, = project(data)
    assert issue['code'] == 'UNCLASSIFIED' and issue['target'] == 'OPERATOR'


def test_http_issues_are_owned_saved_facts_and_do_not_change_eligibility(tmp_path):
    with TestClient(app(tmp_path)) as client:
        headers = sign_in(client)
        profile = deepcopy(INPUTS['profile'])
        next(row for row in profile['equipment'] if row['item_key'] == 'tent')['capacity_persons'] = None
        profile['transport']['estimated_km'] = None
        assert client.put('/api/v1/profile', headers=headers, json={'expected_revision': 0, 'profile': profile}).status_code == 200
        record = client.post('/api/v1/requests', headers=headers, json=CASES['normal']['request']).json()
        path = '/api/v1/requests/'+record['request_id']
        record = client.post(path+'/interpret', headers=headers, json={'expected_revision': record['revision']}).json()
        record = client.post(path+'/confirm', headers=headers, json={'expected_revision': record['revision'], 'command_key': 'issues-confirm-123456', 'acknowledged': True}).json()
        response = client.post(path+'/plan', headers=headers, json={'expected_request_revision': record['revision'], 'command_key': 'issues-start-123456'})
        assert response.status_code == 202, response.text
        detail = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert {'DISTANCE', 'EQUIPMENT_DETAILS'} <= {i['code'] for i in detail['logistics_issues']}
        assert not detail['finalisation_available']
        before = detail['assessments']
        assert client.put('/api/v1/profile', headers=headers, json={'expected_revision': 1, 'profile': INPUTS['profile']}).status_code == 200
        reread = client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()
        assert reread['assessments'] == before
        assert reread['logistics_issues'] == detail['logistics_issues']
        sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get('/api/v1/plans/'+detail['plan']['plan_id']).status_code == 404
