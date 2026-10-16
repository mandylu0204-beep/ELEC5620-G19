"""User meal choices must precede confirmation, not appear as late gear failures."""
from copy import deepcopy

from fastapi.testclient import TestClient
from app.contracts.dto import ConfirmedRequirements, LogisticsInput
from rule_fixtures import call

from test_requests import sign_in
from test_trip_evidence_http import app, wait_run
from test_v2_http_demo import CASES, INPUTS


def test_missing_meal_is_clarified_then_explicit_choice_plans_without_stove(tmp_path):
    with TestClient(app(tmp_path)) as client:
        headers = sign_in(client)
        assert client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': 0, 'profile': INPUTS['profile']}).status_code == 200
        payload = deepcopy(CASES['normal']['request'])
        payload['raw_text'] = 'A quiet camping trip with showers.'
        payload['explicit_fields']['preferences'] = ['quiet']
        payload['explicit_fields']['mandatory_constraints'] = ['showers']
        response = client.post('/api/v1/requests', headers=headers, json=payload)
        path = '/api/v1/requests/' + response.json()['request_id']
        response = client.post(path+'/interpret', headers=headers,
            json={'expected_revision': response.json()['revision']})
        record = response.json()
        assert record['status'] == 'NEEDS_CLARIFICATION'
        assert [(item['field'], item['code']) for item in record['summary']['field_errors']] == [('preferences', 'MISSING')]
        assert client.post(path+'/confirm', headers=headers, json={
            'expected_revision': record['revision'], 'command_key': 'meal-unresolved-confirm',
            'acknowledged': True}).status_code == 409
        payload['explicit_fields']['preferences'] = ['quiet', 'ready-to-eat meals']
        response = client.patch(path, headers=headers,
            json={**payload, 'expected_revision': record['revision']})
        assert response.status_code == 200, response.text
        response = client.post(path+'/interpret', headers=headers,
            json={'expected_revision': response.json()['revision']})
        assert response.json()['status'] == 'AWAITING_CONFIRMATION', response.text
        response = client.post(path+'/confirm', headers=headers, json={
            'expected_revision': response.json()['revision'], 'command_key': 'meal-ready-confirm',
            'acknowledged': True})
        assert response.status_code == 200, response.text
        response = client.post(path+'/plan', headers=headers, json={
            'expected_request_revision': response.json()['revision'], 'command_key': 'meal-ready-plan-123456'})
        assert response.status_code == 202, response.text
        detail = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        logistics = next(a['result'] for a in detail['assessments'] if a['kind'] == 'LOGISTICS')
        assert logistics['transport_feasible'] is True
        assert logistics['total_cents'] is not None
        assert not logistics['clarifications']
        assert not any(item['item_key'] == 'camping_stove' for item in logistics['gear_checklist'])
        assert detail['finalisation_available']
        # A previously confirmed request can still lack a meal choice. Its
        # conditional stove need is unknown, never a confirmed shortage.
        context = detail['confirmed_context']
        unknown = ConfirmedRequirements.model_validate(context['requirements']).model_copy(update={'preferences': ['quiet']})
        result = call(client.app.state.runtime.resolve().agent.assess_gear_and_logistics(LogisticsInput(
            version_context=detail['version']['version_context'], saved_itinerary=detail['version']['content'],
            confirmed_requirements=unknown, profile_snapshot=context['profile_snapshot'],
            demo_context=context['demo_context'])))
        stove = next(item for item in result.gear_checklist if item.item_key == 'camping_stove')
        assert stove.required_quantity is None and stove.missing_quantity is None
        assert stove.arrangement_status == 'UNCONFIRMED'
        assert result.total_cents is None
        assert [item.field for item in result.clarifications] == ['meal_mode']
        assert not result.mandatory_blockers
