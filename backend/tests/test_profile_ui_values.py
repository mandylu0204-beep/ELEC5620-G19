"""Browser vocabulary must reach real rules without changing saved snapshots."""
from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from test_requests import sign_in
from test_v2_http_demo import application, launch, INPUTS, assessment


@pytest.mark.parametrize('level,mode', [('beginner', 'car'), ('BEGINNER', 'CAR')])
def test_profile_values_are_canonical_in_actual_v2_rules_and_old_snapshots_stay_fixed(tmp_path, monkeypatch, level, mode):
    profile = {**INPUTS['profile'], 'experience_level': level,
        'transport': {**INPUTS['profile']['transport'], 'transport_type': mode}}
    monkeypatch.setitem(INPUTS, 'profile', profile)
    with TestClient(application('normal', tmp_path)) as client:
        headers = sign_in(client)
        detail = launch(client, headers, 'normal')
        stored = client.get('/api/v1/profile').json()
        assert stored['profile']['experience_level'] == 'BEGINNER'
        assert stored['profile']['transport']['transport_type'] == 'CAR'
        logistics = assessment(detail, 'LOGISTICS')['result']
        assert any(item['item_key'] == 'emergency_contact_card' for item in logistics['gear_checklist'])
        assert logistics['transport_feasible'] and logistics['outcome'] == 'PASSED'
        old = detail['confirmed_context']['profile_snapshot']
        newer = {**profile, 'experience_level': 'intermediate'}
        assert client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': stored['revision'], 'profile': newer}).status_code == 200
        current = client.get('/api/v1/plans/' + detail['plan']['plan_id']).json()
        assert current['confirmed_context']['profile_snapshot'] == old


def test_unknown_profile_vocabulary_is_preserved_for_clarification(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, database_path=tmp_path/'profile.sqlite3'))) as client:
        headers = sign_in(client)
        response = client.put('/api/v1/profile', headers=headers, json={'expected_revision': 0,
            'profile': {'group_size': 2, 'experience_level': 'custom training',
                'transport': {'transport_type': 'unconfirmed connection'}}})
        assert response.status_code == 200
        assert response.json()['profile']['experience_level'] == 'custom training'
        assert response.json()['profile']['transport']['transport_type'] == 'unconfirmed connection'
