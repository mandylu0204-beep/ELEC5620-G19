"""Extra real v2 flows; independent approval fixture is labelled separately."""
import json

from fastapi.testclient import TestClient

from app.main import create_app
from test_agent_runtime import dataset as approval_dataset, settings, confirmed, launch as launch_fixture
from test_finalisation import command as final_command
from test_plan_changes import change
from test_planning_entry import start, wait_run
from test_requests import sign_in
from test_reviews import command as review_command
from test_v2_http_demo import application, launch, assessment, finalise, INPUTS, CASES


def confirm_saved(client, headers, record, key):
    path = '/api/v1/requests/' + record['request_id']
    analysed = client.post(path + '/interpret', headers=headers,
        json={'expected_revision': record['revision']})
    assert analysed.status_code == 200, analysed.text
    assert analysed.json()['status'] == 'AWAITING_CONFIRMATION', analysed.text
    response = client.post(path + '/confirm', headers=headers, json={
        'expected_revision': analysed.json()['revision'], 'command_key': key, 'acknowledged': True})
    assert response.status_code == 200, response.text
    return response.json()


def test_v2_conflict_after_actual_campsite_revision_cannot_be_approved_or_finalised(tmp_path):
    app = application('conflict_revision', tmp_path)
    with TestClient(app) as client:
        headers = sign_in(client)
        original = launch(client, headers, 'conflict_revision')
        assert original['version']['content']['selected_campsite_ids'] == ['demo-river-flat']
        assert original['finalisation_available']
        response = change(client, headers, original, 'revise', feedback='change campsite')
        assert response.status_code == 202, response.text
        current = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert current['version']['content']['selected_campsite_ids'] == ['demo-lake-meadow']
        assert current['version']['version_number'] == 2
        safety = assessment(current, 'SAFETY')['result']
        assert safety['outcome'] == 'REVIEW'
        assert safety['data_quality']['WEATHER'] == 'CONFLICTING'
        assert safety['data_quality']['FIRE'] == 'CONFLICTING'
        assert not current['finalisation_available']
        founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        path = '/api/v1/review/' + current['plan']['plan_id']
        approval = client.post(path, headers=founder, json=review_command(client.get(path).json()))
        assert approval.status_code == 409, approval.text
        headers = sign_in(client)
        current = client.get('/api/v1/plans/' + current['plan']['plan_id']).json()
        final = client.post('/api/v1/plans/' + current['plan']['plan_id'] + '/finalise',
            headers=headers, json=final_command(current))
        assert final.status_code == 409
        with app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 2
            assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM final_records').fetchone()[0] == 0


def test_v2_no_match_is_successful_search_without_itinerary_or_assessments(tmp_path):
    app = application('no_match', tmp_path)
    with TestClient(app) as client:
        headers = sign_in(client)
        assert client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': 0, 'profile': INPUTS['profile']}).status_code == 200
        saved = client.post('/api/v1/requests', headers=headers, json=CASES['no_match']['request'])
        assert saved.status_code == 201, saved.text
        request = confirm_saved(client, headers, saved.json(), 'no-match-confirm-123456')
        started = start(client, headers, request_id=request['request_id'], revision=request['revision'])
        assert started.status_code == 202, started.text
        detail = wait_run(client, started.json()['run_id'], 'SUCCEEDED')
        result = detail['recommendations']['result']
        assert result['search_outcome'] == 'NO_MATCH' and not result['candidates']
        assert len(result['excluded_candidates']) == 10
        assert detail['version'] is None and detail['assessments'] == []
        assert not detail['finalisation_available'] and not detail['retry_available']
        with app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM final_records').fetchone()[0] == 0


def test_v2_unsupported_revision_keeps_saved_content_and_reports_input_failure(tmp_path):
    with TestClient(application('normal', tmp_path)) as client:
        headers = sign_in(client)
        original = launch(client, headers, 'normal')
        response = change(client, headers, original, 'revise', feedback='unsupported activity request')
        assert response.status_code == 202, response.text
        failed = wait_run(client, response.json()['run_id'], 'FAILED')
        assert failed['run']['error']['code'] == 'INPUT_INVALID'
        assert not failed['finalisation_available']
        old = client.get('/api/v1/runs/' + original['run']['run_id']).json()
        assert old['version']['content'] == original['version']['content']


def test_new_request_reconfirmation_uses_current_profile_without_changing_old_snapshot(tmp_path):
    with TestClient(application('normal', tmp_path)) as client:
        headers = sign_in(client)
        original = launch(client, headers, 'normal')
        old_id = original['plan']['request_id']
        old = client.get('/api/v1/requests/' + old_id).json()
        stored = client.get('/api/v1/profile').json()
        profile = {**INPUTS['profile'], 'experience_level': 'EXPERIENCED'}
        assert client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': stored['revision'], 'profile': profile}).status_code == 200
        request = {**CASES['normal']['request'],
            'raw_text': CASES['normal']['request']['raw_text'].replace('AUD 320', 'AUD 400'),
            'explicit_fields': {**CASES['normal']['request']['explicit_fields'], 'budget_cents': 40000}}
        saved = client.post('/api/v1/requests', headers=headers, json=request)
        assert saved.status_code == 201, saved.text
        new = confirm_saved(client, headers, saved.json(), 'copy-confirm-123456')
        assert new['request_id'] != old_id
        assert new['confirmed_context']['requirements']['budget_cents'] == 40000
        assert new['confirmed_context']['profile_snapshot']['experience_level'] == 'EXPERIENCED'
        assert client.get('/api/v1/requests/' + old_id).json() == old
        other = sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get('/api/v1/requests/' + old_id).status_code == 404
        assert client.patch('/api/v1/requests/' + old_id, headers=other,
            json={**request, 'expected_revision': old['revision']}).status_code == 404


def test_real_rule_approval_finalisation_and_fresh_review_after_reassessment(approval_dataset, tmp_path):
    # Explicit isolated v1 test facts exercise A's review path. This is NOT a
    # sealed v2 scenario, UI demo, or a fabricated saved assessment/approval.
    path = approval_dataset / 'data/scenarios/rule-integration.json'
    facts = json.loads(path.read_text(encoding='utf-8'))
    next(row for row in facts['evidence'] if row['kind'] == 'WEATHER')['summary'] = 'Synthetic extreme heat expected.'
    path.write_text(json.dumps(facts), encoding='utf-8')
    with TestClient(create_app(settings(approval_dataset, tmp_path))) as client:
        headers = sign_in(client)
        request = confirmed(client, headers)
        current = wait_run(client, launch_fixture(client, headers, request)['run_id'], 'SUCCEEDED')
        assert current['version']['status'] == 'ESCALATED'
        assert assessment(current, 'SAFETY')['result']['risk_level'] == 'HIGH'
        assert assessment(current, 'SAFETY')['result']['outcome'] == 'REVIEW'
        assert {row['code'] for row in current['eligibility']['blocking_reasons']} == {'REVIEW_REQUIRED'}
        assert not current['finalisation_available']
        review_path = '/api/v1/review/' + current['plan']['plan_id']
        founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        body = review_command(client.get(review_path).json())
        approved = client.post(review_path, headers=founder, json=body)
        assert approved.status_code == 200, approved.text
        headers = sign_in(client)
        current = client.get('/api/v1/plans/' + current['plan']['plan_id']).json()
        assert current['finalisation_available']
        final_path, snapshot = finalise(client, headers, current)
        saved = client.get('/api/v1/plans/' + current['plan']['plan_id']).json()
        started = change(client, headers, saved)
        assert started.status_code == 202, started.text
        reassessed = wait_run(client, started.json()['run_id'], 'SUCCEEDED')
        assert reassessed['version']['content'] == current['version']['content']
        assert reassessed['run']['run_id'] != current['run']['run_id']
        assert reassessed['reviews'] == [] and not reassessed['finalisation_available']
        assert reassessed['version']['status'] == 'ESCALATED'
        assert client.get(final_path).json()['final_record'] == snapshot
        founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        assert client.post(review_path, headers=founder, json=body).status_code == 409
