"""Actual RuleAgent through A's authenticated HTTP/supervisor, with isolated input.

These scenarios are explicitly authored test inputs, not defaults or v2 demos.
"""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json
import shutil

from fastapi.testclient import TestClient
import pytest

from app.application.agent_runtime import DATASET_AGENT_FACTORIES, build_v1_rule_binding
from app.application.datasets import BUSINESS_FILES, inspect_dataset
from app.config import APP_ROOT, Settings
from app.contracts.errors import ContractFailure
from app.main import create_app
from rule_fixtures import complete_scenario, full_profile, requirements
from test_planning_entry import start, retry, wait_run
from test_requests import sign_in
from test_rule_orchestration import FailOnce
from test_finalisation import command as final_command
from test_reviews import command as review_command


KEY = ('deterministic_demo', 'CampMate Synthetic Demo Dataset v1')


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / 'dataset'
    (root / 'data/scenarios').mkdir(parents=True)
    for name in BUSINESS_FILES:
        shutil.copyfile(Settings(_env_file=None).dataset_path / 'data' / name, root / 'data' / name)
    scenario = complete_scenario(requirements(), ['demo-moonlit-field'])
    scenario = scenario.model_copy(update={'evidence': [
        evidence.model_copy(update={'source_refs': [
            ref.model_copy(update={'dataset_file': 'data/scenarios/rule-integration.json'}) for ref in evidence.source_refs
        ]}) for evidence in scenario.evidence
    ]})
    (root / 'data/scenarios/rule-integration.json').write_text(scenario.model_dump_json(), encoding='utf-8')
    return root


def settings(dataset, tmp_path, **changes):
    return Settings(_env_file=None, dataset_path=dataset, database_path=tmp_path / 'integration.sqlite3',
        execution_mode='deterministic_demo', planning_enabled=True,
        dataset_scenario_files=changes.pop('dataset_scenario_files', ['data/scenarios/rule-integration.json']), **changes)


def confirmed(client, headers):
    profile = client.put('/api/v1/profile', headers=headers,
        json={'expected_revision': 0, 'profile': full_profile().model_dump(mode='json')})
    assert profile.status_code == 200, profile.text
    saved = client.post('/api/v1/requests', headers=headers, json={
        'raw_text': 'Two people in CampMate Demo Region from 2026-10-20 for two nights, AUD 500. We want ready-to-eat meals and toilets.'}).json()
    analysed = client.post(f"/api/v1/requests/{saved['request_id']}/interpret", headers=headers,
        json={'expected_revision': saved['revision']})
    assert analysed.status_code == 200, analysed.text
    assert analysed.json()['status'] == 'AWAITING_CONFIRMATION', analysed.text
    result = client.post(f"/api/v1/requests/{saved['request_id']}/confirm", headers=headers,
        json={'expected_revision': analysed.json()['revision'], 'command_key': 'confirm-runtime-123456', 'acknowledged': True})
    assert result.status_code == 200, result.text
    return result.json()


def launch(client, headers, request):
    result = start(client, headers, request_id=request['request_id'], revision=request['revision'])
    assert result.status_code == 202, result.text
    return result.json()


def test_real_rule_http_flow_preserves_full_context_and_finalisation(dataset, tmp_path):
    # A manifest is an additional consumed input, not one of B's six source files.
    source = {'source_type':'SYNTHETIC','source_name':'CampMate Synthetic Demo Dataset v1','source_date':'2026-10-07','demo_only':True}
    manifest = {'dataset_version':'v1','provenance':source}
    (dataset / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        request = confirmed(client, headers)
        context = request['confirmed_context']['dataset_context']
        assert 'manifest.json' in context['file_digests']
        assert 'data/scenarios/rule-integration.json' in context['fixture_digests']
        assert 'b03-explicit-scenarios.canonical.json' in context['fixture_digests']
        assert 'b02-v1-rules-2' in context['rules_version']
        ids = launch(client, headers, request)
        result = wait_run(client, ids['run_id'], 'SUCCEEDED')
        assert result['finalisation_available'], result
        assert len(result['assessments']) == 2
        version = result['version']['version_context']
        logistics = next(item for item in result['assessments'] if item['kind']=='LOGISTICS')
        safety = next(item for item in result['assessments'] if item['kind']=='SAFETY')
        assert safety['depends_on_assessment_id'] == logistics['assessment_id']
        assert not result['eligibility']['blocking_reasons']
        assert client.get('/api/v1/meta').json()['features']['planning']
        assert client.get('/api/v1/health/ready').json()['rule_agents_available']
        assert version['run_id'] == ids['run_id']
        saved = client.post('/api/v1/plans/' + ids['plan_id'] + '/finalise', headers=headers, json=final_command(result))
        assert saved.status_code == 200, saved.text
        snapshot = client.get('/api/v1/plans/' + ids['plan_id'] + '/finals/' + saved.json()['final_id'])
        assert snapshot.status_code == 200
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM final_records').fetchone()[0] == 1


def test_real_rule_without_evidence_finishes_but_remains_blocked(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path, dataset_scenario_files=[]))
    with TestClient(app) as client:
        headers = sign_in(client)
        request = confirmed(client, headers)
        result = wait_run(client, launch(client, headers, request)['run_id'], 'SUCCEEDED')
        assert result['version']['status'] == 'BLOCKED'
        assert not result['finalisation_available']
        assert any(item['code'] == 'EVIDENCE_UNAVAILABLE' for item in result['eligibility']['blocking_reasons'])


def test_real_rule_closed_road_is_a_hard_blocker(dataset, tmp_path):
    path = dataset / 'data/scenarios/rule-integration.json'
    scenario = json.loads(path.read_text(encoding='utf-8'))
    road = next(item for item in scenario['evidence'] if item['kind']=='ROAD')
    road.update(road_state='CLOSED', summary='closed in synthetic scenario')
    path.write_text(json.dumps(scenario), encoding='utf-8')
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        result = wait_run(client, launch(client, headers, confirmed(client, headers))['run_id'], 'SUCCEEDED')
        assert result['version']['status'] == 'BLOCKED'
        assert not result['finalisation_available']
        assert any(item['code'] in {'ROAD_CLOSED','ROAD_UNAVAILABLE'} for item in result['eligibility']['blocking_reasons'])
        plan_id = result['version']['version_context']['plan_id']
        founder_headers = sign_in(client, 'founder', 'CampMate-Founder-2026!')
        detail = client.get('/api/v1/review/' + plan_id).json()
        approved = client.post('/api/v1/review/' + plan_id, headers=founder_headers,
            json=review_command(detail))
        assert approved.status_code == 409 and approved.json()['error']['code'] == 'INVALID_STATE'
        camper_headers = sign_in(client)
        detail = client.get('/api/v1/plans/' + plan_id).json()
        assert not detail['finalisation_available']
        blocked = client.post('/api/v1/plans/' + plan_id + '/finalise', headers=camper_headers, json=final_command(detail))
        assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'FINALISATION_BLOCKED'


def failed_run(dataset, tmp_path, monkeypatch):
    original = DATASET_AGENT_FACTORIES[KEY]
    control = {'remaining': 1}
    class FailAfterVersion:
        def __init__(self, agent): self.agent = agent
        def __getattr__(self, name): return getattr(self.agent, name)
        async def orchestrate(self, input, port):
            if control['remaining']:
                control['remaining'] -= 1
                port = FailOnce(port, 'append_plan_version', after=True)
            return await self.agent.orchestrate(input, port)
    def factory(config, descriptor):
        binding = original(config, descriptor)
        return replace(binding, agent=FailAfterVersion(binding.agent))
    monkeypatch.setitem(DATASET_AGENT_FACTORIES, KEY, factory)
    return create_app(settings(dataset, tmp_path))


def test_real_rule_retry_reuses_saved_version_after_lost_receipt(dataset, tmp_path, monkeypatch):
    app = failed_run(dataset, tmp_path, monkeypatch)
    with TestClient(app) as client:
        headers = sign_in(client)
        ids = launch(client, headers, confirmed(client, headers))
        failed = wait_run(client, ids['run_id'], 'FAILED')
        old_id = failed['version']['version_context']['plan_version_id']
        assert failed['retry_available']
        response = retry(client, headers, failed)
        assert response.status_code == 202, response.text
        result = wait_run(client, ids['run_id'], 'SUCCEEDED')
        assert result['version']['version_context']['plan_version_id'] == old_id
        assert result['finalisation_available']
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 1


def test_actual_file_change_disables_retry_of_old_run(dataset, tmp_path, monkeypatch):
    app = failed_run(dataset, tmp_path, monkeypatch)
    with TestClient(app) as client:
        headers = sign_in(client)
        ids = launch(client, headers, confirmed(client, headers))
        failed = wait_run(client, ids['run_id'], 'FAILED')
        path = dataset / 'data/scenarios/rule-integration.json'
        path.write_bytes(path.read_bytes() + b'\n')
        reread = client.get('/api/v1/runs/' + ids['run_id']).json()
        assert not reread['retry_available']
        response = retry(client, headers, failed)
        assert response.status_code == 409 and response.json()['error']['code'] == 'STALE_CONTEXT'


def test_factory_detects_dataset_changed_between_inspection_and_consumption(dataset, tmp_path):
    config = settings(dataset, tmp_path)
    descriptor = inspect_dataset(config)
    path = dataset / 'data/synthetic_campsites.csv'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ContractFailure) as failure:
        build_v1_rule_binding(config, descriptor)
    assert failure.value.error.code == 'STALE_CONTEXT'


def test_v2_data_identity_resolves_the_registered_business_adapter(tmp_path):
    app = create_app(settings(APP_ROOT / 'data/synthetic_demo_v2', tmp_path, dataset_scenario_files=[]))
    with TestClient(app) as client:
        meta = client.get('/api/v1/meta').json()
        assert meta['dataset_version'] == '2.0.0'
        assert meta['features']['planning']
        assert meta['agent_configuration_error'] is None
        assert client.get('/api/v1/health/live').status_code == 200
        response = client.get('/api/v1/health/ready')
        assert response.status_code == 200
        assert response.json()['checks']['dataset_context_valid']
        assert response.json()['checks']['configured_agent_available']
        assert app.state.agent is not None


def test_legacy_case_selection_and_rules_enter_registered_context(dataset, tmp_path):
    config = settings(dataset, tmp_path, workflow_safety_case_ids=['safety-01'])
    app = create_app(config)
    snapshot = app.state.runtime.resolve()
    assert snapshot.dataset.selection_config['safety_case_ids'] == '["safety-01"]'
    config.workflow_safety_case_ids = ['safety-02']
    assert app.state.runtime.resolve().dataset != snapshot.dataset


def test_registered_factory_cannot_omit_a_scenario_digest(dataset, tmp_path, monkeypatch):
    original = DATASET_AGENT_FACTORIES[KEY]
    def bad_factory(config, descriptor):
        binding = original(config, descriptor)
        context = binding.context.model_copy(update={'fixture_digests': {}})
        return replace(binding, context=context)
    monkeypatch.setitem(DATASET_AGENT_FACTORIES, KEY, bad_factory)
    app = create_app(settings(dataset, tmp_path))
    with TestClient(app) as client:
        response = client.get('/api/v1/health/ready')
        assert response.status_code == 503
        assert response.json()['agent_configuration_error']['code'] == 'STALE_CONTEXT'
        assert not client.get('/api/v1/meta').json()['features']['planning']


def test_parallel_application_reads_keep_the_same_registered_context(dataset, tmp_path):
    app = create_app(settings(dataset, tmp_path))
    expected = app.state.runtime.resolve().dataset
    with ThreadPoolExecutor(max_workers=4) as pool:
        contexts = list(pool.map(lambda _: app.state.runtime.resolve().dataset, range(16)))
    assert all(context == expected for context in contexts)
