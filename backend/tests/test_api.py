from fastapi.testclient import TestClient
import shutil

from app.config import Settings
from app.main import BUSINESS_FILES, create_app


def make_dataset(tmp_path):
    folder = tmp_path / 'data'
    folder.mkdir()
    for name in BUSINESS_FILES:
        shutil.copyfile(Settings(_env_file=None).dataset_path / 'data' / name, folder / name)
    return tmp_path


def test_liveness_is_separate_from_missing_dependency_readiness(tmp_path):
    app = create_app(Settings(_env_file=None, dataset_path=tmp_path, execution_mode='stub'))
    with TestClient(app) as client:
        assert client.get('/api/v1/health/live').status_code == 200
        response = client.get('/api/v1/health/ready')
        assert response.status_code == 503
        assert response.json()['checks']['dataset_readable'] is False


def test_foundation_ready_does_not_claim_business_workflows(tmp_path):
    app = create_app(Settings(_env_file=None, dataset_path=make_dataset(tmp_path), execution_mode='stub'))
    with TestClient(app) as client:
        ready = client.get('/api/v1/health/ready').json()
        assert ready['status'] == 'ready'
        assert ready['business_persistence_implemented'] is True
        assert ready['business_workflows_implemented'] is False
        assert ready['real_agents_implemented'] is False
        assert app.state.settings.database_path.exists()


def test_unimplemented_mode_never_falls_back_to_stub(tmp_path):
    app = create_app(Settings(_env_file=None, dataset_path=make_dataset(tmp_path), execution_mode='deterministic_demo'))
    with TestClient(app) as client:
        assert client.get('/api/v1/health/live').status_code == 200
        assert client.get('/api/v1/health/ready').status_code == 503
        response = client.post('/api/v1/dev/interpret', json={'raw_text': 'Trip', 'explicit_fields': {}})
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'AGENT_FAILURE'
        assert client.get('/api/v1/meta').json()['execution_mode'] == 'deterministic_demo'


def test_preview_echoes_explicit_fields_and_remains_unsaved(tmp_path):
    app = create_app(Settings(_env_file=None, dataset_path=make_dataset(tmp_path), execution_mode='stub'))
    with TestClient(app) as client:
        response = client.post('/api/v1/dev/interpret', json={'raw_text': 'An idea', 'explicit_fields': {'destination': 'Demo Region', 'budget_cents': 12345}})
        assert response.status_code == 200
        body = response.json()
        assert body['execution_mode'] == 'stub'
        assert body['extracted_requirements']['budget_cents'] == 12345
        assert body['extracted_requirements']['destination'] == 'Demo Region'
        assert 'request_id' not in body
        assert client.get('/api/v1/requests').status_code == 401
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == 0


def test_invalid_budget_and_spoofed_owner_return_uniform_errors(tmp_path):
    app = create_app(Settings(_env_file=None, dataset_path=make_dataset(tmp_path), execution_mode='stub'))
    with TestClient(app) as client:
        for fields in [{'budget_cents': True}, {'owner_user_id': 'other-camper'}, {'expected_request_status': 'CONFIRMED'}]:
            response = client.post('/api/v1/dev/interpret', json={'raw_text': 'Trip', 'explicit_fields': fields})
            assert response.status_code == 422
            body = response.json()
            assert body['error']['code'] == 'INPUT_INVALID'
            assert body['error']['field_errors']
            assert response.headers['x-trace-id'] == body['trace_id']


def test_malformed_agent_output_is_not_returned_as_a_success(tmp_path):
    class BrokenAgent:
        async def interpret_request(self, input):
            return {'execution_mode': 'stub', 'extracted_requirements': {'budget_cents': -1}}
    app = create_app(Settings(_env_file=None, dataset_path=make_dataset(tmp_path), execution_mode='stub'))
    app.state.agent = BrokenAgent()
    with TestClient(app) as client:
        response = client.post('/api/v1/dev/interpret', json={'raw_text': 'Trip', 'explicit_fields': {}})
        assert response.status_code == 502
        assert response.json()['error']['code'] == 'CONTRACT_INVALID'


def test_mode_mismatch_in_agent_output_is_rejected(tmp_path):
    class WrongMode:
        async def interpret_request(self, input):
            return {'execution_mode': 'agent', 'extracted_requirements': {}}
    app = create_app(Settings(_env_file=None, dataset_path=make_dataset(tmp_path), execution_mode='stub'))
    app.state.agent = WrongMode()
    with TestClient(app) as client:
        response = client.post('/api/v1/dev/interpret', json={'raw_text': 'Trip', 'explicit_fields': {}})
        assert response.status_code == 502
