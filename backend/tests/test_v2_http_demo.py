"""Four sealed v2 demos through real auth, confirmation, dispatcher and SQLite.

Only the retry test injects a persistence failure. No candidate or business
result is replaced; artifact IDs always come from the public application.
"""
from dataclasses import replace
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.agents.rule_agent import RuleAgent
from app.application.agent_runtime import DATASET_AGENT_FACTORIES
from app.config import Settings
from app.main import create_app
from test_finalisation import command as final_command
from test_plan_changes import change
from test_planning_entry import start, retry, wait_run
from test_requests import sign_in
from test_reviews import command as review_command
from test_rule_orchestration import FailOnce

ROOT = Path(__file__).resolve().parents[2]
INPUTS = json.loads((ROOT / 'docs/demo/v2_inputs.json').read_text(encoding='utf-8'))
CASES = {case['id']: case for case in INPUTS['cases']}
KEY = ('deterministic_demo', 'CampMate Synthetic Demo Dataset v2')


def application(case_id, tmp_path):
    values = dict(CASES[case_id]['settings'])
    values['dataset_path'] = ROOT / values['dataset_path']
    return create_app(Settings(_env_file=None, database_path=tmp_path / 'v2-http.sqlite3', **values))


def launch(client, headers, case_id):
    profile = client.put('/api/v1/profile', headers=headers,
        json={'expected_revision': 0, 'profile': INPUTS['profile']})
    assert profile.status_code == 200, profile.text
    saved = client.post('/api/v1/requests', headers=headers, json=CASES[case_id]['request'])
    assert saved.status_code == 201, saved.text
    record = saved.json()
    path = '/api/v1/requests/' + record['request_id']
    interpreted = client.post(path + '/interpret', headers=headers,
        json={'expected_revision': record['revision']})
    assert interpreted.status_code == 200, interpreted.text
    assert interpreted.json()['status'] == 'AWAITING_CONFIRMATION', interpreted.text
    confirmed = client.post(path + '/confirm', headers=headers, json={
        'expected_revision': interpreted.json()['revision'],
        'command_key': 'v2-http-confirm-123456', 'acknowledged': True})
    assert confirmed.status_code == 200, confirmed.text
    request = confirmed.json()
    response = start(client, headers, request_id=request['request_id'], revision=request['revision'])
    assert response.status_code == 202, response.text
    detail = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
    # A's registered input identity must survive B's factory and persisted run.
    context = detail['confirmed_context']['dataset_context']
    assert 'manifest.json' in context['file_digests']
    assert 'runtime_safety_evidence.json' in context['file_digests']
    assert context['selection_config']['a_runtime_bound'] == '1'
    assert context['selection_config']['demo_input'] == case_id
    assert 'a-runtime-bindings-v2' in context['rules_version']
    assert 'b02-v2-rules-1' in context['rules_version']
    assert len(detail['assessments']) == 2
    assert assessment(detail, 'SAFETY')['depends_on_assessment_id'] == assessment(detail, 'LOGISTICS')['assessment_id']
    return detail


def assessment(detail, kind):
    return next(item for item in detail['assessments'] if item['kind'] == kind)


def assert_site(detail, campsite_id, total_cents):
    assert detail['version']['content']['selected_campsite_ids'] == [campsite_id]
    assert assessment(detail, 'LOGISTICS')['result']['total_cents'] == total_cents


def finalise(client, headers, detail):
    response = client.post('/api/v1/plans/' + detail['plan']['plan_id'] + '/finalise',
        headers=headers, json=final_command(detail))
    assert response.status_code == 200, response.text
    path = '/api/v1/plans/' + detail['plan']['plan_id'] + '/finals/' + response.json()['final_id']
    record = client.get(path)
    assert record.status_code == 200, record.text
    assert record.json()['final_record']['content'] == detail['version']['content']
    return path, record.json()['final_record']


def revise(client, headers, old, *, status='SUCCEEDED'):
    response = change(client, headers, old, 'revise',
        feedback=CASES['budget_revision']['revision_feedback'])
    assert response.status_code == 202, response.text
    return wait_run(client, response.json()['run_id'], status)


def test_v2_normal_http_finalises_and_reads_saved_snapshot(tmp_path):
    app = application('normal', tmp_path)
    with TestClient(app) as client:
        headers = sign_in(client)
        detail = launch(client, headers, 'normal')
        assert_site(detail, 'demo-wattle-rest', 25100)
        assert assessment(detail, 'LOGISTICS')['result']['outcome'] == 'PASSED'
        assert assessment(detail, 'SAFETY')['result']['outcome'] == 'PASSED'
        assert detail['finalisation_available']
        finalise(client, headers, detail)
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM final_records').fetchone()[0] == 1


def test_v2_budget_http_revision_then_reassessment_preserves_snapshot_and_clears_feedback(tmp_path):
    app = application('budget_revision', tmp_path)
    with TestClient(app) as client:
        headers = sign_in(client)
        old = launch(client, headers, 'budget_revision')
        assert_site(old, 'demo-wattle-rest', 25100)
        assert assessment(old, 'LOGISTICS')['result']['outcome'] == 'REVISION'
        assert assessment(old, 'SAFETY')['result']['outcome'] == 'PASSED'
        assert not old['finalisation_available']
        blocked = client.post('/api/v1/plans/' + old['plan']['plan_id'] + '/finalise',
            headers=headers, json=final_command(old))
        assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'FINALISATION_BLOCKED'
        current = revise(client, headers, old)
        assert_site(current, 'demo-moonlit-field', 23100)
        assert current['version']['version_number'] == 2
        assert current['version']['content']['revision_reason'] == 'cheaper campsite'
        selection = current['confirmed_context']['dataset_context']['selection_config']
        assert selection['a_revision_feedback'] == selection['revision_feedback'] == 'cheaper campsite'
        assert current['finalisation_available'] and not current['reviews']
        assert assessment(current, 'SAFETY')['result']['outcome'] == 'PASSED'
        assert client.get('/api/v1/runs/' + old['run']['run_id']).json()['version']['content'] == old['version']['content']
        snapshot_path, snapshot = finalise(client, headers, current)
        saved = client.get('/api/v1/plans/' + current['plan']['plan_id']).json()
        response = change(client, headers, saved, key='v2-reassessment-123456')
        assert response.status_code == 202, response.text
        reassessed = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert reassessed['version']['content'] == current['version']['content']
        assert reassessed['version']['version_context']['plan_version_id'] == current['version']['version_context']['plan_version_id']
        assert reassessed['run']['run_id'] != current['run']['run_id']
        assert {a['assessment_id'] for a in reassessed['assessments']}.isdisjoint(a['assessment_id'] for a in current['assessments'])
        choices = reassessed['confirmed_context']['dataset_context']['selection_config']
        assert choices['revision_feedback'] == '' and 'a_revision_feedback' not in choices
        assert reassessed['finalisation_available'] and not reassessed['reviews']
        assert not reassessed['last_final']['is_current']
        assert client.get(snapshot_path).json()['final_record'] == snapshot
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 2


@pytest.mark.parametrize('case_id,site,total', [
    ('missing_evidence', 'demo-river-flat', 24100),
    ('road_closure', 'demo-moonlit-field', 23100),
])
def test_v2_http_missing_or_closed_evidence_cannot_be_approved_or_finalised(tmp_path, case_id, site, total):
    app = application(case_id, tmp_path)
    with TestClient(app) as client:
        headers = sign_in(client)
        detail = launch(client, headers, case_id)
        assert_site(detail, site, total)
        result = assessment(detail, 'SAFETY')['result']
        if case_id == 'missing_evidence':
            assert result['outcome'] == 'REVIEW'
            assert result['data_quality']['WEATHER'] == 'MISSING'
            assert result['data_quality']['FIRE'] == result['data_quality']['ROAD'] == 'AVAILABLE'
        else:
            assert assessment(detail, 'LOGISTICS')['result']['outcome'] == 'PASSED'
            assert result['outcome'] == 'BLOCKED'
            assert any(item['code'] == 'ROAD_CLOSED' for item in result['mandatory_blockers'])
        assert not detail['finalisation_available']
        plan_id = detail['plan']['plan_id']
        founder = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        review = client.get('/api/v1/review/' + plan_id)
        assert review.status_code == 200
        approval = client.post('/api/v1/review/' + plan_id, headers=founder,
            json=review_command(review.json()))
        assert approval.status_code == 409, approval.text
        headers = sign_in(client)
        detail = client.get('/api/v1/plans/' + plan_id).json()
        blocked = client.post('/api/v1/plans/' + plan_id + '/finalise',
            headers=headers, json=final_command(detail))
        assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'FINALISATION_BLOCKED'
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM final_records').fetchone()[0] == 0
            assert connection.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0


def test_v2_revision_http_retry_reuses_saved_bytes_without_regeneration(tmp_path, monkeypatch):
    original_factory = DATASET_AGENT_FACTORIES[KEY]
    original_generation = RuleAgent.generate_or_revise_itinerary
    generated = []
    control = {'failed': False}

    async def generation(agent, input):
        result = await original_generation(agent, input)
        generated.append(result.model_dump(mode='json'))
        return result

    class FailRevision:
        def __init__(self, agent):
            self.agent = agent

        def __getattr__(self, name):
            return getattr(self.agent, name)

        async def orchestrate(self, input, port):
            if input.run_scope.operation == 'REVISE' and not control['failed']:
                control['failed'] = True
                port = FailOnce(port, 'append_plan_version', after=True)
            return await self.agent.orchestrate(input, port)

    def factory(config, descriptor):
        binding = original_factory(config, descriptor)
        return replace(binding, agent=FailRevision(binding.agent))

    monkeypatch.setattr(RuleAgent, 'generate_or_revise_itinerary', generation)
    monkeypatch.setitem(DATASET_AGENT_FACTORIES, KEY, factory)
    app = application('budget_revision', tmp_path)
    with TestClient(app) as client:
        headers = sign_in(client)
        old = launch(client, headers, 'budget_revision')
        failed = revise(client, headers, old, status='FAILED')
        assert failed['retry_available']
        version = failed['version']
        assert len(generated) == 2
        response = retry(client, headers, failed)
        assert response.status_code == 202, response.text
        current = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        assert len(generated) == 2, 'Retry must not regenerate content under the original write key.'
        assert current['version']['version_context']['plan_version_id'] == version['version_context']['plan_version_id']
        assert current['version']['content'] == version['content']
        assert_site(current, 'demo-moonlit-field', 23100)
        choices = current['confirmed_context']['dataset_context']['selection_config']
        assert choices['a_revision_feedback'] == choices['revision_feedback'] == 'cheaper campsite'
        assert current['finalisation_available']
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 2
