"""A input identity tests; independent fixtures, no B rules or demo claims."""
import hashlib
import json
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from app.application.datasets import BUSINESS_FILES, RUNTIME_FILES, inspect_dataset
from app.application.request_rules import data_context
from app.config import Settings
from app.contracts.dto import DemoContext, Provenance
from app.contracts.errors import ContractFailure
from app.main import create_app
from test_requests import sign_in, draft, analyse, confirm_body
from test_storage import call
from test_workflows import workflow, failure, itinerary, revision


def write_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def package(tmp_path):
    root = tmp_path / 'dataset'
    (root / 'data').mkdir(parents=True)
    for name in BUSINESS_FILES:
        shutil.copyfile(Settings(_env_file=None).dataset_path / 'data' / name, root / 'data' / name)
    return root


def to_v2(root, sealed=False):
    for name in BUSINESS_FILES:
        path = root / 'data' / name
        path.write_text(path.read_text(encoding='utf-8').replace('CampMate Synthetic Demo Dataset v1', 'CampMate Synthetic Demo Dataset v2'), encoding='utf-8')
    source = Provenance(source_name='CampMate Synthetic Demo Dataset v2').model_dump(mode='json')
    # Only identity fields are relevant here; these are not business fixtures.
    for name in RUNTIME_FILES:
        write_json(root / 'data' / name, [{'input_id': 'a-digest-test', **source}])
    manifest = {'dataset_version': '2.0.0', 'provenance': source, 'default_demo_clock': '2026-10-09T10:00:00+11:00'}
    if sealed:
        manifest['files_sha256'] = {f'data/{name}': hashlib.sha256((root / 'data' / name).read_bytes()).hexdigest() for name in BUSINESS_FILES + RUNTIME_FILES}
    write_json(root / 'manifest.json', manifest)
    return Settings(_env_file=None, dataset_path=root)


def test_legacy_identity_and_context_remain_compatible(package):
    settings = Settings(_env_file=None, dataset_path=package)
    descriptor = inspect_dataset(settings)
    context, regions = data_context(settings)
    assert descriptor.context == context
    assert context.dataset_version == 'v1'
    assert context.file_digests == {name: hashlib.sha256((package / 'data' / name).read_bytes()).hexdigest() for name in BUSINESS_FILES}
    assert regions == ['CampMate Demo Region']
    assert descriptor.provenance == Provenance()


def test_v2_identity_metadata_and_demo_snapshot_follow_selected_package(package):
    settings = to_v2(package, sealed=True)
    settings.clock_mode = 'fixed'  # This test explicitly compares a fixed date.
    with TestClient(create_app(settings)) as client:
        meta = client.get('/api/v1/meta').json()
        assert meta['dataset_version'] == '2.0.0'
        assert meta['provenance']['source_name'].endswith('v2')
        assert meta['demo_today'] == '2026-10-08'  # No adoption of the manifest clock.
        assert meta['features']['planning'] is False
        assert client.get('/api/v1/health/ready').json()['checks']['dataset_context_valid'] is True
        headers = sign_in(client)
        assert client.put('/api/v1/profile', headers=headers, json={'expected_revision': 0, 'profile': {'group_size': 2}}).status_code == 200
        ready = analyse(client, headers, draft(client, headers))
        response = client.post('/api/v1/requests/'+ready['request_id']+'/confirm', headers=headers, json=confirm_body(ready))
        assert response.status_code == 200
        confirmed = response.json()['confirmed_context']
        assert confirmed['demo_context']['dataset_version'] == confirmed['dataset_context']['dataset_version'] == '2.0.0'
        assert set(RUNTIME_FILES).issubset(confirmed['dataset_context']['file_digests'])


@pytest.mark.parametrize('changed', ['runtime_requests.json', 'runtime_safety_evidence.json', 'scenario', 'selection'])
def test_effective_runtime_changes_invalidate_old_confirmation(package, changed):
    settings = to_v2(package)
    (package / 'data/scenarios').mkdir()
    scene = package / 'data/scenarios/independent.json'
    write_json(scene, {'scenario_id': 'a-only', 'request_id': 'input-a'})
    settings.dataset_scenario_files = ['data/scenarios/independent.json']
    settings.dataset_selection = {'scenario_id': 'a-only'}
    with TestClient(create_app(settings)) as client:
        headers = sign_in(client)
        client.put('/api/v1/profile', headers=headers, json={'expected_revision': 0, 'profile': {'group_size': 2}})
        ready = analyse(client, headers, draft(client, headers))
        if changed == 'selection':
            settings.dataset_selection = {'scenario_id': 'a-new'}
        else:
            target = scene if changed == 'scenario' else package / 'data' / changed
            target.write_bytes(target.read_bytes()+b'\n')
        endpoint = '/api/v1/requests/'+ready['request_id']+'/confirm'
        response = client.post(endpoint, headers=headers, json=confirm_body(ready))
        assert response.status_code == 409 and response.json()['error']['code'] == 'STALE_CONTEXT'
        refreshed = analyse(client, headers, ready)
        assert client.post(endpoint, headers=headers, json=confirm_body(refreshed)).status_code == 200


@pytest.mark.parametrize('problem', ['manifest', 'version', 'mixed_source', 'runtime_pair', 'sealed_mismatch', 'oracle'])
def test_invalid_packages_fail_explicitly_without_v1_fallback(package, problem):
    settings = to_v2(package, sealed=problem == 'sealed_mismatch')
    if problem == 'manifest':
        # A JSON null manifest is invalid; it must not act like an absent legacy manifest.
        (package / 'manifest.json').write_text('null', encoding='utf-8')
    elif problem == 'version':
        manifest = json.loads((package / 'manifest.json').read_text())
        manifest['dataset_version'] = 'v1'
        write_json(package / 'manifest.json', manifest)
    elif problem == 'mixed_source':
        path = package / 'data/synthetic_profiles.json'
        path.write_text(path.read_text().replace('Dataset v2', 'Dataset v1'), encoding='utf-8')
    elif problem == 'runtime_pair':
        (package / 'data/runtime_requests.json').rename(package / 'runtime-disabled.json')
    elif problem == 'sealed_mismatch':
        path = package / 'data/runtime_requests.json'
        path.write_bytes(path.read_bytes()+b'\n')
    else:
        path = package / 'data/runtime_requests.json'
        rows = json.loads(path.read_text())
        rows[0]['profile_snapshot'] = {'expected_outcome': 'PASSED'}
        write_json(path, rows)
    with pytest.raises(ContractFailure) as error:
        inspect_dataset(settings)
    assert error.value.error.code == 'ADAPTER_FAILURE'
    with TestClient(create_app(settings)) as client:
        ready = client.get('/api/v1/health/ready')
        assert ready.status_code == 503 and ready.json()['checks']['dataset_context_valid'] is False
        assert client.get('/api/v1/meta').json()['provenance'] is None
        assert client.post('/api/v1/dev/interpret', json={'raw_text': 'Trip', 'explicit_fields': {}}).json()['error']['code'] == 'ADAPTER_FAILURE'


@pytest.mark.parametrize('name', ['tests/synthetic_oracles.json', '../outside.json', 'data/scenarios/../oracle.json', 'data\\scenarios\\a.json', 'data/scenarios/a.csv'])
def test_scenario_inputs_cannot_load_oracles_or_escape_package(package, name):
    settings = Settings(_env_file=None, dataset_path=package, dataset_scenario_files=[name])
    with pytest.raises(ContractFailure):
        inspect_dataset(settings)


def test_scenario_test_setup_is_not_runtime_input(package):
    (package / 'data/scenarios').mkdir()
    write_json(package / 'data/scenarios/wrong.json', {'setup': {'plans': []}, 'assertions': {'result': 'FINALIZED'}})
    with pytest.raises(ContractFailure):
        inspect_dataset(Settings(_env_file=None, dataset_path=package, dataset_scenario_files=['data/scenarios/wrong.json']))


def test_dataset_detection_never_loads_test_oracle_files(package):
    settings = to_v2(package)
    before = inspect_dataset(settings).context
    (package / 'tests').mkdir()
    (package / 'tests/synthetic_oracles.json').write_text('invalid JSON must never be read', encoding='utf-8')
    assert inspect_dataset(settings).context == before


def test_runtime_evidence_change_rejects_old_retry_and_changes_version_fingerprint(package, workflow):
    settings = to_v2(package)
    old = inspect_dataset(settings).context
    service, user, _, _, _ = workflow
    demo = DemoContext(mode='deterministic_demo', demo_today='2026-10-08', dataset_version=old.dataset_version)
    scope = service.start(user, 'request-a09', demo, old, command_key='dataset-start')
    attempt = service.claim(user, scope.run_id, demo, old)
    port = service.port(user, attempt)
    version = call(port.append_plan_version(None, itinerary(), scope.request_id, 'Initial independent dataset test', scope.write_keys['version']))
    confirmed = service.checkpoint(user, attempt)['confirmed_context']
    failure(port)
    path = package / 'data/runtime_safety_evidence.json'
    path.write_bytes(path.read_bytes()+b'\n')
    changed = inspect_dataset(settings).context
    with pytest.raises(ContractFailure) as error:
        service.retry(user, scope.run_id, demo, changed, command_key='dataset-retry', expected_run_revision=revision(service, scope))
    assert error.value.error.code == 'STALE_CONTEXT'
    content = version.content.model_dump(mode='json')
    fingerprint = service.repository.input_fingerprint
    assert fingerprint(scope, confirmed, content) != fingerprint(scope.model_copy(update={'dataset_context': changed}), confirmed, content)
