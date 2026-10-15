"""Authenticated, persisted feedback for completed and interrupted rechecks."""
from fastapi.testclient import TestClient
import pytest

from app.auth import User
from app.contracts.errors import ContractError, ContractFailure
from app.main import create_app
from app.storage.check_feedback import reassessment_feedback
from test_agent_runtime import dataset, settings
from test_plan_changes import change, change_fact, command, start_complete
from test_planning_entry import wait_run
from test_requests import sign_in


def test_same_results_have_new_records_and_persistent_completion_feedback(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        assert old['check_feedback'] is None
        response = change(client, headers, old)
        current = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        feedback = current['check_feedback']
        assert feedback['status'] == 'COMPLETED'
        assert feedback['comparison'] == 'UNCHANGED'
        assert feedback['compared_run_id'] == old['run']['run_id']
        assert feedback['changed_sections'] == []
        assert feedback['completed_at'] == next(event['created_at'] for event in reversed(current['events'])
            if event['status'] == 'SUCCEEDED' and event['stage'] == 'COMPLETED')
        assert {item['assessment_id'] for item in current['assessments']}.isdisjoint(
            item['assessment_id'] for item in old['assessments'])
        with app.state.database.transaction(write=False) as connection:
            before = connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
        path = '/api/v1/plans/' + current['plan']['plan_id']
        assert client.get(path).json()['check_feedback'] == feedback
        assert client.get('/api/v1/runs/' + old['run']['run_id']).json()['check_feedback'] is None
        sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get(path).status_code == 404
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == before
    # Reload through a fresh application instance, without client-side memory.
    with TestClient(create_app(settings(dataset, tmp_path))) as client:
        sign_in(client)
        assert client.get(path).json()['check_feedback'] == feedback


def test_changed_safety_is_reported_without_treating_completion_as_approval(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        change_fact(dataset, 'ROAD', road_state='CLOSED', summary='closed in synthetic scenario')
        stale = client.get('/api/v1/plans/' + old['plan']['plan_id']).json()
        assert stale['current_inputs_state'] == 'CHANGED'
        response = change(client, headers, stale)
        current = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert current['check_feedback']['comparison'] == 'CHANGED'
        assert current['check_feedback']['changed_sections'] == ['SAFETY']
        assert current['version']['status'] == 'BLOCKED'
        assert not current['finalisation_available']


def test_rechecking_missing_information_can_finish_with_same_unresolved_result(dataset, tmp_path):
    change_fact(dataset, 'WEATHER', status='MISSING', summary=None)
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        response = change(client, headers, old)
        current = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert current['check_feedback']['status'] == 'COMPLETED'
        assert current['check_feedback']['comparison'] == 'UNCHANGED'
        assert not current['finalisation_available']
        assert next(item for item in current['assessments'] if item['kind'] == 'SAFETY')['result']['data_quality']['WEATHER'] == 'MISSING'


def test_pending_failed_and_incomplete_history_never_claim_unchanged(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        old = start_complete(client, headers)
        owner = User('camper-a', 'camper.a', 'Camper A', 'CAMPER')
        snapshot = app.state.runtime.resolve()
        scope = app.state.workflows.start(owner, old['plan']['request_id'], snapshot.demo, snapshot.dataset,
            plan_id=old['plan']['plan_id'], operation='REASSESS', **command(old))
        pending = client.get('/api/v1/runs/' + scope.run_id).json()
        assert pending['check_feedback']['status'] == 'IN_PROGRESS'
        assert pending['check_feedback']['completed_at'] is None
        app.state.workflows.fail_dispatch(owner, scope.run_id,
            ContractError(code='AGENT_FAILURE', message='Independent offline service interruption.'))
        failed = client.get('/api/v1/runs/' + scope.run_id).json()
        assert failed['check_feedback']['status'] == 'FAILED'
        assert failed['check_feedback']['comparison'] == 'NOT_COMPARABLE'
        assert not failed['finalisation_available']
        # Even an inconsistent success status must not claim completed checks.
        with app.state.database.transaction(write=False) as connection:
            row = dict(connection.execute('SELECT * FROM runs WHERE id=?', (scope.run_id,)).fetchone())
            row.update(status='SUCCEEDED', stage='COMPLETED')
            feedback = reassessment_feedback(connection, scope.plan_id, row, scope,
                old['plan']['current_version_id'])
        assert feedback['status'] == 'INCOMPLETE'
        assert feedback['comparison'] == 'NOT_COMPARABLE'


@pytest.mark.parametrize('code', ['AGENT_FAILURE', 'ADAPTER_FAILURE'])
def test_unavailable_service_is_distinct_from_updated_data(dataset, tmp_path, monkeypatch, code):
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        old = start_complete(client, sign_in(client))
        def unavailable(scope):
            # Deliberately contains "变化": classification must use the code.
            raise ContractFailure(ContractError(code=code, message='服务变化导致暂时不可用。'))
        monkeypatch.setattr(app.state.runtime, 'validate_scope', unavailable)
        current = client.get('/api/v1/plans/' + old['plan']['plan_id']).json()
        assert current['current_inputs_state'] == 'UNAVAILABLE'
        assert not current['reassessment_available'] and not current['revision_available']
        assert not current['finalisation_available']
