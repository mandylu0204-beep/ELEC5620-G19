"""Public revision/reassessment against real v1 rules and isolated facts.

These are integration tests, not final v2 scenarios or Canvas demo evidence.
"""
from dataclasses import replace
import json

from fastapi.testclient import TestClient
import pytest

from app.application.agent_runtime import DATASET_AGENT_FACTORIES
from app.auth import User
from app.contracts.errors import ContractFailure
from app.main import create_app
from rule_fixtures import call, full_profile
from test_agent_runtime import dataset, settings, confirmed, launch, KEY
from test_planning_entry import wait_run, retry
from test_requests import sign_in
from test_finalisation import command as final_command
from test_reviews import command as review_command
from test_rule_orchestration import FailOnce


def command(data, *, feedback=None, key='change-plan-command-123456'):
    return {'command_key': key, 'expected_current_version_id': data['plan']['current_version_id'],
        'expected_active_run_id': data['plan']['active_run_id'],
        'expected_version_revision': data['current_version_revision'],
        'expected_run_revision': data['run']['revision'],
        **({'feedback': feedback} if feedback is not None else {})}


def change(client, headers, data, operation='reassess', **kwargs):
    return client.post('/api/v1/plans/' + data['plan']['plan_id'] + '/' + operation,
        headers=headers, json=command(data, **kwargs))


def start_complete(client, headers):
    return wait_run(client, launch(client, headers, confirmed(client, headers))['run_id'], 'SUCCEEDED')


def change_fact(dataset, kind, **fields):
    path = dataset / 'data/scenarios/rule-integration.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    next(item for item in value['evidence'] if item['kind'] == kind).update(fields)
    path.write_text(json.dumps(value), encoding='utf-8')


def test_revision_receives_previous_version_and_saves_feedback_and_new_evidence(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        body = command(old, feedback='change campsite')
        response = change(client, headers, old, 'revise', feedback='change campsite')
        assert response.status_code == 202, response.text
        ids = response.json()
        current = wait_run(client, ids['run_id'], 'SUCCEEDED')
        assert current['version']['version_number'] == 2
        assert current['version']['content']['selected_campsite_ids'] != old['version']['content']['selected_campsite_ids']
        assert current['version']['content']['revision_reason'] == 'change campsite'
        assert current['confirmed_context']['dataset_context']['selection_config']['a_revision_feedback'] == 'change campsite'
        assert len(current['assessments']) == 2 and not current['reviews']
        assert current['version']['version_context']['input_fingerprint'] != old['version']['version_context']['input_fingerprint']
        # The alternate campsite has no fixture evidence; revision cannot imply safety clearance.
        assert not current['finalisation_available']
        history = client.get('/api/v1/runs/' + old['run']['run_id']).json()
        assert history['version']['content'] == old['version']['content']
        assert not history['revision_available'] and not history['reassessment_available']
        assert client.post('/api/v1/plans/' + ids['plan_id'] + '/revise', headers=headers, json=body).json() == ids
        conflict = client.post('/api/v1/plans/' + ids['plan_id'] + '/revise', headers=headers,
            json={**body, 'feedback': 'cheaper campsite'})
        assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 2


def test_reassessment_preserves_content_and_final_snapshot_with_new_run_and_assessments(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        final = client.post('/api/v1/plans/' + old['plan']['plan_id'] + '/finalise', headers=headers, json=final_command(old))
        assert final.status_code == 200
        snapshot_path = '/api/v1/plans/' + old['plan']['plan_id'] + '/finals/' + final.json()['final_id']
        snapshot = client.get(snapshot_path).json()['final_record']
        old = client.get('/api/v1/plans/' + old['plan']['plan_id']).json()
        response = change(client, headers, old)
        assert response.status_code == 202, response.text
        current = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert current['version']['content'] == old['version']['content']
        assert current['version']['version_context']['plan_version_id'] == old['plan']['current_version_id']
        assert current['run']['run_id'] != old['run']['run_id']
        assert {item['assessment_id'] for item in current['assessments']}.isdisjoint(item['assessment_id'] for item in old['assessments'])
        assert current['recommendations'] is None and current['finalisation_available']
        assert not current['last_final']['is_current']
        assert client.get(snapshot_path).json()['final_record'] == snapshot
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 1


def test_old_approval_cannot_transfer_to_reassessment(dataset, tmp_path):
    change_fact(dataset, 'WEATHER', summary='Strong wind in this synthetic scenario.')
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        assert old['version']['status'] == 'ESCALATED'
        plan_id = old['plan']['plan_id']
        founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        review = client.get('/api/v1/review/' + plan_id).json()
        body = review_command(review)
        assert client.post('/api/v1/review/' + plan_id, headers=founder, json=body).status_code == 200
        headers = sign_in(client)
        approved = client.get('/api/v1/plans/' + plan_id).json()
        assert approved['finalisation_available']
        response = change(client, headers, approved)
        current = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert current['version']['status'] == 'ESCALATED' and not current['reviews']
        assert current['eligibility']['valid_review_id'] is None and not current['finalisation_available']
        founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        assert client.post('/api/v1/review/' + plan_id, headers=founder, json=body).status_code == 409


def test_changed_evidence_blocks_old_finalisation_and_new_run_uses_closed_road(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        change_fact(dataset, 'ROAD', road_state='CLOSED', summary='closed in synthetic scenario')
        current = client.get('/api/v1/plans/' + old['plan']['plan_id']).json()
        assert current['current_inputs_error'] and not current['finalisation_available']
        blocked = client.post('/api/v1/plans/' + old['plan']['plan_id'] + '/finalise', headers=headers, json=final_command(old))
        assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'STALE_CONTEXT'
        response = change(client, headers, current)
        assert response.status_code == 202, response.text
        new = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert new['version']['status'] == 'BLOCKED' and not new['finalisation_available']
        assert new['version']['version_context']['input_fingerprint'] != old['version']['version_context']['input_fingerprint']


def test_changed_evidence_blocks_founder_review(dataset, tmp_path):
    change_fact(dataset, 'WEATHER', summary='Strong wind in this synthetic scenario.')
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        old = start_complete(client, sign_in(client))
        founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        path = '/api/v1/review/' + old['plan']['plan_id']
        body = review_command(client.get(path).json())
        change_fact(dataset, 'ROAD', road_state='CLOSED', summary='closed in synthetic scenario')
        assert not client.get(path).json()['review_available']
        response = client.post(path, headers=founder, json=body)
        assert response.status_code == 409 and response.json()['error']['code'] == 'STALE_CONTEXT'
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0


@pytest.mark.parametrize('field,value', [('expected_version_revision', 999), ('expected_run_revision', 999),
    ('expected_current_version_id', 'wrong-version'), ('expected_active_run_id', 'wrong-run')])
def test_new_operation_rejects_stale_pointers_and_revisions(dataset, tmp_path, field, value):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        response = client.post('/api/v1/plans/' + old['plan']['plan_id'] + '/reassess', headers=headers,
            json={**command(old), field: value})
        assert response.status_code == 409
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 1


def test_roles_csrf_validation_and_old_worker_fencing(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        path = '/api/v1/plans/' + old['plan']['plan_id']
        body = command(old, feedback='change campsite')
        assert client.post(path + '/revise', json=body).status_code == 403
        for change_body in ({'feedback': '   '}, {'expected_run_revision': True}, {'run_scope': {}}):
            assert client.post(path + '/revise', headers=headers, json={**body, **change_body}).status_code == 422
        other = sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.post(path + '/revise', headers=other, json=body).status_code == 404
        founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        assert client.post(path + '/revise', headers=founder, json=body).status_code == 403
        headers = sign_in(client)
        owner = User('camper-a', 'camper.a', 'Camper A', 'CAMPER')
        old_port = app.state.repository.bind_port(owner, old['run']['run_id'])
        response = change(client, headers, old)
        wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        with pytest.raises(ContractFailure) as error:
            call(old_port.load_confirmed_context())
        assert error.value.error.code == 'STALE_CONTEXT'


def test_revision_retry_recovers_bound_feedback_and_saved_version(dataset, tmp_path, monkeypatch):
    original = DATASET_AGENT_FACTORIES[KEY]
    control = {'failed': False}
    class FailRevision:
        def __init__(self, agent): self.agent = agent
        def __getattr__(self, name): return getattr(self.agent, name)
        async def orchestrate(self, input, port):
            if input.run_scope.operation == 'REVISE' and not control['failed']:
                control['failed'] = True
                port = FailOnce(port, 'append_plan_version', after=True)
            return await self.agent.orchestrate(input, port)
    def factory(config, descriptor):
        binding = original(config, descriptor)
        return replace(binding, agent=FailRevision(binding.agent))
    monkeypatch.setitem(DATASET_AGENT_FACTORIES, KEY, factory)
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        response = change(client, headers, old, 'revise', feedback='change campsite')
        failed = wait_run(client, response.json()['run_id'], 'FAILED')
        assert failed['retry_available']
        saved_id = failed['version']['version_context']['plan_version_id']
        assert retry(client, headers, failed).status_code == 202
        current = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        assert current['version']['version_context']['plan_version_id'] == saved_id
        assert current['version']['content']['revision_reason'] == 'change campsite'
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 2


def test_proposed_requirement_change_does_not_create_unconfirmed_version(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        response = change(client, headers, old, 'revise', feedback='remove campfire')
        failed = wait_run(client, response.json()['run_id'], 'FAILED')
        assert failed['run']['error']['code'] == 'REQUEST_NOT_CONFIRMED'
        assert failed['version'] is None and not failed['retry_available']
        assert failed['reassessment_available']
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 1


def test_reassessment_keeps_confirmed_profile_snapshot(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        response = client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': 1, 'profile': full_profile(group=3).model_dump(mode='json')})
        assert response.status_code == 200
        result = change(client, headers, old)
        current = wait_run(client, result.json()['run_id'], 'SUCCEEDED')
        assert current['confirmed_context']['profile_snapshot'] == old['confirmed_context']['profile_snapshot']
