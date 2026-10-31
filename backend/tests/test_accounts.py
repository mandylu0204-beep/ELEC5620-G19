from fastapi.testclient import TestClient

from app.auth import COOKIE_NAME, digest, verify_password
from app.config import Settings
from app.main import create_app


CLIENT_HEADER = {'X-CampMate-Client': '1'}


def login(client, username='camper.a', password='CampMate-A-2026!'):
    response = client.post('/api/v1/auth/login', headers=CLIENT_HEADER, json={'username': username, 'password': password})
    assert response.status_code == 200
    return response.json()


def test_login_cookie_csrf_logout_expiry_and_no_client_role(tmp_path):
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        assert client.get('/api/v1/plans').status_code == 401
        assert client.post('/api/v1/auth/login', json={'username': 'camper.a', 'password': 'CampMate-A-2026!'}).status_code == 403
        for username in ('unknown', 'camper.a'):
            bad = client.post('/api/v1/auth/login', headers=CLIENT_HEADER, json={'username': username, 'password': 'wrong'})
            assert bad.status_code == 401
            assert bad.json()['error']['message'] == 'Incorrect username or password.'
        spoofed = client.post('/api/v1/auth/login', headers=CLIENT_HEADER, json={'username': 'camper.a', 'password': 'CampMate-A-2026!', 'role': 'FOUNDER'})
        assert spoofed.status_code == 422
        session = login(client)
        cookie = client.cookies.get(COOKIE_NAME)
        assert client.get('/api/v1/auth/me').json() == session
        assert client.get('/api/v1/review-queue').status_code == 403
        assert client.post('/api/v1/auth/logout', headers=CLIENT_HEADER).status_code == 403
        assert client.post('/api/v1/auth/logout', headers={**CLIENT_HEADER, 'X-CSRF-Token': session['csrf_token']}).status_code == 204
        assert client.get('/api/v1/auth/me').status_code == 401
        client.cookies.set(COOKIE_NAME, cookie, path='/api/v1')
        assert client.get('/api/v1/auth/me').status_code == 401
        login(client)
        with app.state.database.transaction() as connection:
            connection.execute('UPDATE sessions SET expires_at=0')
        assert client.get('/api/v1/auth/me').status_code == 401


def test_profile_isolation_revision_conflict_and_restart(tmp_path):
    settings = Settings(_env_file=None)
    app = create_app(settings)
    with TestClient(app) as client:
        session = login(client)
        headers = {**CLIENT_HEADER, 'X-CSRF-Token': session['csrf_token']}
        assert client.get('/api/v1/profile').json() == {'profile': None, 'revision': 0}
        payload = {'profile': {'group_size': 2}, 'expected_revision': 0}
        assert client.put('/api/v1/profile', headers=CLIENT_HEADER, json=payload).status_code == 403
        stored = client.put('/api/v1/profile', headers=headers, json=payload)
        assert stored.status_code == 200
        assert stored.json()['revision'] == 1
        assert stored.json()['profile']['profile_id']
        assert client.put('/api/v1/profile', headers=headers, json=payload).status_code == 409
        assert client.put('/api/v1/profile', headers=headers, json={**payload, 'owner_user_id': 'camper-b'}).status_code == 422
        assert client.put('/api/v1/profile', headers=headers, json={'expected_revision': 1, 'profile': {'profile_id': 'other'}}).status_code == 422
        login(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get('/api/v1/profile').json()['profile'] is None
        assert client.get('/api/v1/plans').json() == {'plans': []}
        session = login(client, 'founder', 'CampMate-Founder-2026!')
        assert client.get('/api/v1/profile').status_code == 403
        assert client.get('/api/v1/plans').status_code == 403
        assert client.get('/api/v1/review-queue').json() == {'reviews': []}
        response = client.get('/api/v1/auth/me')
        assert response.headers['cache-control'] == 'no-store'
    # New application and connection against the same on-disk database.
    with TestClient(create_app(settings)) as client:
        login(client)
        assert client.get('/api/v1/profile').json() == stored.json()
        with app.state.database.transaction(write=False) as connection:
            users = connection.execute('SELECT * FROM users').fetchall()
            assert len(users) == 3
            assert all(user['password_hash'].startswith('pbkdf2_sha256$600000$') for user in users)
            assert verify_password('CampMate-A-2026!', users[0]['password_hash'])
            tokens = connection.execute('SELECT token_hash FROM sessions').fetchall()
            assert all(len(row[0]) == 64 for row in tokens)


def test_seed_can_be_disabled_and_session_token_is_not_returned(tmp_path):
    app = create_app(Settings(_env_file=None, seed_demo_accounts=False))
    with TestClient(app) as client:
        response = client.post('/api/v1/auth/login', headers=CLIENT_HEADER, json={'username': 'camper.a', 'password': 'CampMate-A-2026!'})
        assert response.status_code == 401
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.post('/api/v1/auth/login', headers=CLIENT_HEADER, json={'username': 'camper.a', 'password': 'CampMate-A-2026!'})
        assert response.status_code == 200
        token = client.cookies.get(COOKIE_NAME)
        assert token not in response.text
        assert 'HttpOnly' in response.headers['set-cookie']
        assert 'SameSite=lax' in response.headers['set-cookie']
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT token_hash FROM sessions').fetchone()[0] == digest(token)
