import pytest
from fastapi.testclient import TestClient

from app.auth import User
from app.config import Settings
from app.main import create_app
from app.storage.database import Database
from app.storage.plan_queries import PlanQueries
from plan_fixtures import create
from test_accounts import login


@pytest.fixture
def deletion_client():
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        session = login(client)
        headers = {'X-CampMate-Client': '1', 'X-CSRF-Token': session['csrf_token']}
        yield client, app, User('camper-a', 'camper.a', 'Camper A', 'CAMPER'), headers


def test_deletion_persists_and_protects_other_plans_and_artifacts(deletion_client):
    client, app, user, headers = deletion_client
    scope, _ = create(app.state.repository, user, 'delete-complete', 'complete')
    other, _ = create(app.state.repository, user, 'keep-complete', 'complete')
    path = '/api/v1/plans/' + scope.plan_id
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get('/api/v1/runs/' + scope.run_id).status_code == 404
    assert client.delete(path, headers=headers).status_code == 404
    assert [row['plan_id'] for row in client.get('/api/v1/plans').json()['plans']] == [other.plan_id]
    restarted = Database(app.state.database.path)
    restarted.initialize()
    assert restarted.ready()
    assert [row['plan_id'] for row in PlanQueries(restarted).list(user)] == [other.plan_id]
    with restarted.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM assessments WHERE run_id=?', (scope.run_id,)).fetchone()[0] == 2
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_delete_requires_owner_and_csrf(deletion_client):
    client, app, user, headers = deletion_client
    scope, _ = create(app.state.repository, user, 'owner', 'complete')
    path = '/api/v1/plans/' + scope.plan_id
    assert client.delete(path).status_code == 403
    session = login(client, 'camper.b', 'CampMate-B-2026!')
    foreign = {**headers, 'X-CSRF-Token': session['csrf_token']}
    assert client.delete(path, headers=foreign).status_code == 404
    assert client.delete('/api/v1/plans/missing', headers=foreign).status_code == 404


def test_delete_rejects_active_work(deletion_client):
    client, app, user, headers = deletion_client
    scope, _ = create(app.state.repository, user, 'active')
    assert client.delete('/api/v1/plans/' + scope.plan_id, headers=headers).status_code == 409
    assert client.get('/api/v1/plans/' + scope.plan_id).status_code == 200


def test_delete_saved_final_removes_owner_access(deletion_client):
    from test_finalisation import command
    client, app, user, headers = deletion_client
    scope, _ = create(app.state.repository, user, 'delete-final', 'complete')
    path = '/api/v1/plans/' + scope.plan_id
    detail = client.get(path).json()
    saved = client.post(path + '/finalise', headers=headers, json=command(detail))
    assert saved.status_code == 200
    final_id = client.get(path).json()['last_final']['final_id']
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path + '/finals/' + final_id).status_code == 404
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM final_records WHERE plan_id=?', (scope.plan_id,)).fetchone()[0] == 1


def test_deleted_plan_leaves_review_queue(deletion_client):
    client, app, user, headers = deletion_client
    founder = User('founder', 'founder', 'Founder', 'FOUNDER')
    scope, _ = create(app.state.repository, user, 'delete-review', 'review')
    assert any(row['plan_id'] == scope.plan_id for row in app.state.reviews.queue(founder))
    assert client.delete('/api/v1/plans/' + scope.plan_id, headers=headers).status_code == 204
    assert not app.state.reviews.queue(founder)
