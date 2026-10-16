from test_plan_deletion import deletion_client
from plan_fixtures import create
from test_accounts import login


def test_delete_request_preserves_existing_plan(deletion_client):
    client, app, user, headers = deletion_client
    scope, _ = create(app.state.repository, user, 'request-delete', 'complete')
    path = '/api/v1/requests/' + scope.request_id
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get('/api/v1/requests').json() == {'requests': []}
    assert client.get(path).status_code == 404
    assert client.delete(path, headers=headers).status_code == 404
    assert client.get('/api/v1/plans/' + scope.plan_id).status_code == 200
    assert client.get('/api/v1/runs/' + scope.run_id).status_code == 200
    app.state.database.initialize()
    assert app.state.database.ready()
    assert app.state.requests.list(user) == []


def test_delete_draft_requires_csrf_and_owner(deletion_client):
    client, app, user, headers = deletion_client
    response = client.post('/api/v1/requests', headers=headers, json={'raw_text': 'An unwanted draft'})
    assert response.status_code == 201
    path = '/api/v1/requests/' + response.json()['request_id']
    assert client.delete(path).status_code == 403
    other = login(client, 'camper.b', 'CampMate-B-2026!')
    assert client.delete(path, headers={**headers, 'X-CSRF-Token': other['csrf_token']}).status_code == 404
    owner = login(client)
    assert client.delete(path, headers={**headers, 'X-CSRF-Token': owner['csrf_token']}).status_code == 204


def test_delete_during_interpretation_is_rejected(deletion_client):
    client, app, user, headers = deletion_client
    record = client.post('/api/v1/requests', headers=headers, json={'raw_text': 'Draft'}).json()
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE requests SET status='ANALYSING' WHERE id=?", (record['request_id'],))
    assert client.delete('/api/v1/requests/' + record['request_id'], headers=headers).status_code == 409
    assert client.get('/api/v1/requests/' + record['request_id']).status_code == 200
