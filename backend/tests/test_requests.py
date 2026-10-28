"""Request integrity tests. Fixtures are separate from repaired B demo scenarios."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import shutil
from threading import Event

from fastapi.testclient import TestClient
import pytest

from app.agents.stub import StubAgent
from app.config import Settings
from app.main import BUSINESS_FILES, create_app
from app.storage.database import Database, MIGRATION_1, execute_migration

FIELDS = {'destination':'CampMate Demo Region', 'start_date':'2026-10-20', 'duration_nights':2, 'budget_cents':32000}


def sign_in(client, username='camper.a', password='CampMate-A-2026!'):
    response = client.post('/api/v1/auth/login', headers={'X-CampMate-Client':'1'}, json={'username':username, 'password':password})
    assert response.status_code == 200
    return {'X-CampMate-Client':'1', 'X-CSRF-Token':response.json()['csrf_token']}


@pytest.fixture
def web(tmp_path):
    source = Settings(_env_file=None).dataset_path
    dataset = tmp_path / 'dataset'
    (dataset / 'data').mkdir(parents=True)
    for filename in BUSINESS_FILES:
        shutil.copyfile(source / 'data' / filename, dataset / 'data' / filename)
    app = create_app(Settings(_env_file=None, dataset_path=dataset))
    with TestClient(app) as client:
        headers = sign_in(client)
        saved = client.put('/api/v1/profile', headers=headers, json={'expected_revision':0,'profile':{'group_size':2}})
        assert saved.status_code == 200
        yield app, client, headers


def draft(client, headers, fields=None):
    response = client.post('/api/v1/requests', headers=headers, json={'raw_text':'Independent request test; two nights', 'explicit_fields':fields if fields is not None else FIELDS})
    assert response.status_code == 201
    return response.json()


def analyse(client, headers, saved):
    response = client.post(f"/api/v1/requests/{saved['request_id']}/interpret", headers=headers, json={'expected_revision':saved['revision']})
    assert response.status_code == 200, response.text
    return response.json()


def confirm_body(record):
    return {'expected_revision':record['revision'], 'command_key':'confirmation-test-123456', 'acknowledged':True}


def test_confirmation_is_explicit_idempotent_immutable_and_never_plans(web):
    app, client, headers = web
    saved = draft(client, headers)
    endpoint = f"/api/v1/requests/{saved['request_id']}"
    assert client.post(endpoint+'/confirm', headers=headers, json=confirm_body(saved)).status_code == 409
    ready = analyse(client, headers, saved)
    assert ready['status'] == 'AWAITING_CONFIRMATION'
    requirements = ready['summary']['extracted_requirements']
    assert requirements['duration_nights'] == 2
    assert requirements['duration_days'] == 3
    assert requirements['end_date'] == '2026-10-22'
    assert ready['summary']['execution_mode'] == 'stub'
    for acknowledged in (False, 1):
        assert client.post(endpoint+'/confirm', headers=headers, json=confirm_body(ready)|{'acknowledged':acknowledged}).status_code == 422
    body = confirm_body(ready)
    confirmed = client.post(endpoint+'/confirm', headers=headers, json=body)
    assert confirmed.status_code == 200
    value = confirmed.json()
    assert value['status'] == 'CONFIRMED'
    assert value['planning_available'] is False
    assert value['confirmed_context']['profile_snapshot']['group_size'] == 2
    assert value['confirmed_context']['demo_context']['mode'] == 'stub'
    assert client.post(endpoint+'/confirm', headers=headers, json=body).json() == value
    assert client.post(endpoint+'/confirm', headers=headers, json=body|{'expected_revision':value['revision']}).status_code == 409
    assert client.patch(endpoint, headers=headers, json={'expected_revision':value['revision'],'raw_text':'Change confirmed input','explicit_fields':FIELDS}).status_code == 409
    assert client.put('/api/v1/profile', headers=headers, json={'expected_revision':1,'profile':{'group_size':8}}).status_code == 200
    assert client.get(endpoint).json()['confirmed_context']['profile_snapshot']['group_size'] == 2
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM request_confirmations').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM plans').fetchone()[0] == 0
    with TestClient(create_app(app.state.settings)) as restarted:
        sign_in(restarted)
        assert restarted.get(endpoint).json() == value


@pytest.mark.parametrize('fields,expected_field', [
    ({**FIELDS,'duration_nights':None,'duration_days':3},'duration_nights'),
    ({**FIELDS,'duration_days':2},'duration_days'),
    ({**FIELDS,'end_date':'2026-10-21'},'end_date'),
    ({**FIELDS,'destination':'   '},'destination'),
    ({**FIELDS,'duration_nights':10**18},'duration_nights'),
])
def test_ambiguous_conflicting_or_unrepresentable_dates_cannot_confirm(web, fields, expected_field):
    app, client, headers = web
    ready = analyse(client, headers, draft(client, headers, fields))
    assert ready['status'] == 'NEEDS_CLARIFICATION'
    assert expected_field in [item['field'] for item in ready['summary']['field_errors']]
    assert client.post(f"/api/v1/requests/{ready['request_id']}/confirm", headers=headers, json=confirm_body(ready)).status_code == 409
    if expected_field == 'duration_days':
        assert ready['summary']['extracted_requirements']['duration_days'] == 2  # Keep the explicit conflict.


def test_unsupported_region_and_missing_profile_remain_unconfirmed(web):
    app, client, headers = web
    unsupported = analyse(client, headers, draft(client, headers, FIELDS|{'destination':'Real Sydney'}))
    assert unsupported['status'] == 'UNSUPPORTED'
    assert client.post(f"/api/v1/requests/{unsupported['request_id']}/confirm", headers=headers, json=confirm_body(unsupported)).status_code == 409
    headers = sign_in(client,'camper.b','CampMate-B-2026!')
    missing = analyse(client, headers, draft(client, headers))
    assert missing['status'] == 'NEEDS_CLARIFICATION'
    assert 'profile.group_size' in [item['field'] for item in missing['summary']['field_errors']]


def test_profile_and_dataset_changes_invalidate_confirmation(web):
    app, client, headers = web
    ready = analyse(client, headers, draft(client, headers))
    endpoint = f"/api/v1/requests/{ready['request_id']}"
    assert client.put('/api/v1/profile', headers=headers, json={'expected_revision':1,'profile':{'group_size':3}}).status_code == 200
    assert client.post(endpoint+'/confirm', headers=headers, json=confirm_body(ready)).json()['error']['code'] == 'VERSION_CONFLICT'
    ready = analyse(client, headers, ready)
    source = app.state.settings.dataset_path / 'data/synthetic_cost_reference.csv'
    source.write_bytes(source.read_bytes()+b'\n')  # Modify this test's isolated copy only.
    assert client.post(endpoint+'/confirm', headers=headers, json=confirm_body(ready)).json()['error']['code'] == 'STALE_CONTEXT'
    ready = analyse(client, headers, ready)
    assert ready['profile_snapshot']['group_size'] == 3
    assert client.post(endpoint+'/confirm', headers=headers, json=confirm_body(ready)).status_code == 200


def test_old_summary_revision_and_foreign_requests_are_rejected(web):
    app, client, headers = web
    ready = analyse(client, headers, draft(client, headers))
    endpoint = f"/api/v1/requests/{ready['request_id']}"
    edited = client.patch(endpoint, headers=headers, json={'expected_revision':ready['revision'],'raw_text':'User changed budget','explicit_fields':FIELDS|{'budget_cents':40000}})
    assert edited.status_code == 200
    assert edited.json()['summary'] is None
    assert client.post(endpoint+'/confirm', headers=headers, json=confirm_body(ready)).json()['error']['code'] == 'VERSION_CONFLICT'
    b_headers = sign_in(client,'camper.b','CampMate-B-2026!')
    assert client.get('/api/v1/requests').json() == {'requests':[]}
    assert client.get(endpoint).status_code == 404
    assert client.patch(endpoint, headers=b_headers, json={'expected_revision':edited.json()['revision'],'raw_text':'Other user','explicit_fields':FIELDS}).status_code == 404
    assert client.post(endpoint+'/interpret', headers=b_headers, json={'expected_revision':edited.json()['revision']}).status_code == 404
    assert client.post(endpoint+'/confirm', headers=b_headers, json=confirm_body(ready)).status_code == 404
    founder_headers = sign_in(client,'founder','CampMate-Founder-2026!')
    assert client.get('/api/v1/requests').status_code == 403
    assert client.get(endpoint).status_code == 403
    assert client.post('/api/v1/requests', headers=founder_headers,json={'raw_text':'Spoof','explicit_fields':FIELDS}).status_code == 403


def test_invalid_interpreter_does_not_leave_a_confirmable_or_stuck_request(web):
    app, client, headers = web
    class Broken:
        async def interpret_request(self, input):
            return {'execution_mode':'stub','extracted_requirements':{'budget_cents':-1}}
    saved = draft(client, headers)
    app.state.agent = Broken()
    endpoint = f"/api/v1/requests/{saved['request_id']}"
    response = client.post(endpoint+'/interpret',headers=headers,json={'expected_revision':saved['revision']})
    assert response.status_code == 502
    latest = client.get(endpoint).json()
    assert latest['status'] == 'DRAFT'
    assert latest['summary'] is None
    assert latest['error']['code'] == 'CONTRACT_INVALID'
    app.state.agent = StubAgent()
    assert analyse(client,headers,latest)['status'] == 'AWAITING_CONFIRMATION'


def test_late_interpretation_cannot_replace_a_newer_input(web):
    app, client, headers = web
    entered, release = Event(), Event()
    class Delayed(StubAgent):
        async def interpret_request(self, input):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
            return await super().interpret_request(input)
    app.state.agent = Delayed()
    saved = draft(client,headers)
    endpoint = f"/api/v1/requests/{saved['request_id']}"
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.post,endpoint+'/interpret',headers=headers,json={'expected_revision':saved['revision']})
        try:
            assert entered.wait(timeout=5)
            analysing = client.get(endpoint).json()
            edited = client.patch(endpoint,headers=headers,json={'expected_revision':analysing['revision'],'raw_text':'New input while interpreter runs','explicit_fields':FIELDS|{'budget_cents':99900}})
            assert edited.status_code == 200
        finally:
            release.set()
        assert future.result(timeout=5).json()['error']['code'] == 'STALE_CONTEXT'
    current = client.get(endpoint).json()
    assert current['status'] == 'DRAFT'
    assert current['explicit_fields']['budget_cents'] == 99900
    assert current['summary'] is None


def test_migration_preserves_version_one_data(tmp_path):
    db = Database(tmp_path/'v1.sqlite3')
    with db.transaction() as connection:
        execute_migration(connection,MIGRATION_1)
        connection.execute("INSERT INTO schema_migrations VALUES(1,'test')")
        connection.execute("INSERT INTO users VALUES('legacy','legacy','Legacy Camper','CAMPER','test-hash')")
        connection.execute("INSERT INTO profiles VALUES('legacy','legacy-profile','{\"group_size\":2}',1,'test')")
    db.initialize()
    db.initialize()
    assert db.ready()
    with db.transaction(write=False) as connection:
        assert [row[0] for row in connection.execute('SELECT version FROM schema_migrations ORDER BY version')] == list(range(1,13))
        assert connection.execute('SELECT revision FROM profiles').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM request_confirmations').fetchone()[0] == 0
