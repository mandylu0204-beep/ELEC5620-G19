"""Compact factory, persistence, replay and recovery. MockTransport only."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.application.agent_runtime import build_v2_hybrid_binding
from app.application.datasets import inspect_dataset
from app.application.safety_audit import registered_identity
from app.config import Settings
from app.contracts.dto import RunScope
from app.contracts.errors import ContractFailure
from app.llm.safety_support import matches_live_protocol
from app.main import create_app
from audit_test_reads import CAMPER, json_with_internal_audits
from safety_runtime_fixtures import mock_safety_runtime, role_counts
from test_finalisation import command as final_command
from test_model_logistics_wiring import wrap_port
from test_plan_changes import change
from test_planning_entry import retry
from test_requests import sign_in
from test_rule_orchestration import FailOnce
from test_sydney_model_safety import settings, begin, wait_run

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    def forbidden(*a, **k):
        pytest.fail('Real HTTP forbidden in compact runtime tests')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def compact_settings(tmp_path, **changes):
    return settings(tmp_path, **{'safety_protocol':'compact', **changes})


def assert_compact(data):
    audit = data['model_assessment_audits']['SAFETY']
    assert audit['trace']['tool_version'] == 'safety-read-only-tools-4'
    assert audit['trace']['turns'] == 3
    assert audit['trace']['tool_calls'] == ['read_safety_facts', 'evaluate_safety_plan']
    assert audit['configuration_fingerprint'] == audit['trace']['configuration_fingerprint']
    assert all(row['action_unverified'] == row['interpretation_unverified'] for row in audit['plan']['findings'])
    safe = next(x for x in data['assessments'] if x['kind'] == 'SAFETY')
    log = next(x for x in data['assessments'] if x['kind'] == 'LOGISTICS')
    assert audit['assessment_id'] == safe['assessment_id']
    assert audit['depends_on_assessment_id'] == safe['depends_on_assessment_id'] == log['assessment_id']
    return audit


def test_defaults_and_closed_configuration_values():
    cfg = Settings(_env_file=None)
    assert cfg.safety_execution == 'rules' and cfg.safety_protocol == 'standard'
    with pytest.raises(ValidationError):
        Settings(_env_file=None, safety_protocol='auto')


@pytest.mark.parametrize('args,expected', [([], 'standard'),
    (['--mode','agent','--safety','model','--safety-protocol','compact'], 'compact')])
def test_launcher_passes_only_explicit_protocol(monkeypatch, args, expected):
    spec = importlib.util.spec_from_file_location('sydney_compact_launcher', ROOT/'scripts/sydney.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = []
    monkeypatch.setattr(module.sys, 'argv', ['sydney.py', *args])
    monkeypatch.setattr(module.subprocess, 'call', lambda command, *, cwd, env:
        captured.append(env['CAMPMATE_SAFETY_PROTOCOL']) or 0)
    assert module.main() == 0 and captured == [expected]


@pytest.mark.parametrize('args', [['--safety-protocol','compact'],
    ['--mode','agent','--safety-protocol','compact']])
def test_launcher_rejects_compact_without_model_safety(monkeypatch, args):
    spec = importlib.util.spec_from_file_location('sydney_compact_invalid', ROOT/'scripts/sydney.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, 'argv', ['sydney.py', *args])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2


@pytest.mark.parametrize('changes', [
    {'safety_execution':'rules'}, {'execution_mode':'deterministic_demo'},
    {'dataset_path':'data/synthetic_demo_v2_1'},
])
def test_compact_requires_explicit_compatible_model_runtime(tmp_path, monkeypatch, changes):
    requests, _ = mock_safety_runtime(monkeypatch)
    app = create_app(compact_settings(tmp_path, **changes))
    with pytest.raises(ContractFailure):
        app.state.runtime.resolve()
    assert not requests


@pytest.mark.parametrize('logistics_mode', ['rules', 'model'])
def test_factory_complete_final_identity_and_strict_codec(tmp_path, monkeypatch, logistics_mode):
    requests, _ = mock_safety_runtime(monkeypatch)
    cfg = compact_settings(tmp_path, logistics_execution=logistics_mode)
    binding = build_v2_hybrid_binding(cfg, inspect_dataset(cfg))
    choices = binding.context.selection_config
    seed = json.loads(choices['a_safety_identity_seed'])
    assert seed['codec_version'] == 'safety-lossless-facts-1'
    assert matches_live_protocol('2.2.0', seed, protocol='compact')
    assert not matches_live_protocol('2.2.0', seed, protocol='standard')
    scope = SimpleNamespace(dataset_context=binding.context,
        demo_context=SimpleNamespace(mode='agent'))
    identity = registered_identity(scope, new_write=True)
    assert identity == binding.agent.safety_agent.identity
    assert identity['workflow_context'] == binding.context.model_dump(mode='json')
    assert binding.agent.coordinator.identity['configuration_fingerprint'] == choices['hybrid_planning_fingerprint']
    for value in ('unknown-codec', None):
        bad = deepcopy(seed)
        if value is None:
            bad.pop('codec_version')
        else:
            bad['codec_version'] = value
        context = binding.context.model_copy(deep=True)
        context.selection_config['a_safety_identity_seed'] = json.dumps(bad)
        with pytest.raises(ValueError):
            registered_identity(SimpleNamespace(dataset_context=context, demo_context=scope.demo_context), new_write=True)
    assert not requests


@pytest.mark.parametrize('logistics_mode', ['rules', 'model'])
def test_http_save_revision_reassessment_final_restart_and_permissions(tmp_path, monkeypatch, logistics_mode):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    cfg = compact_settings(tmp_path, daily=True, logistics_execution=logistics_mode)
    with TestClient(create_app(cfg)) as client:
        headers = sign_in(client)
        first = wait_run(client, begin(client, headers), 'SUCCEEDED')
        first_audit = assert_compact(first)
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3 if logistics_mode=='model' else 0,'SAFETY':3}
        public = client.get('/api/v1/plans/'+first['plan']['plan_id']).json()
        audit = public['model_assessment_audits']['SAFETY']
        assert audit['advice_format'] == 'single-advice-v1'
        assert not {'trace','configuration_fingerprint','attempt_id'} & audit.keys()
        control['site'] = 'euroka'
        revised = change(client, headers, first, 'revise', feedback='change campsite', key='compact-revise-test')
        assert revised.status_code == 202, revised.text
        current = wait_run(client, revised.json()['run_id'], 'SUCCEEDED')
        assert_compact(current)
        reassessed = change(client, headers, current, key='compact-reassess-test')
        assert reassessed.status_code == 202, reassessed.text
        updated = wait_run(client, reassessed.json()['run_id'], 'SUCCEEDED')
        assert_compact(updated)
        assert updated['version']['version_context']['plan_version_id'] == current['version']['version_context']['plan_version_id']
        assert updated['model_planning_trace'] == current['model_planning_trace']
        assert updated['model_assessment_audits']['SAFETY']['audit_id'] != first_audit['audit_id']
        assert updated['finalisation_available']
        saved = client.post('/api/v1/plans/'+updated['plan']['plan_id']+'/finalise',
            headers=headers, json=final_command(updated))
        assert saved.status_code == 200, saved.text
        path = '/api/v1/plans/'+updated['plan']['plan_id']+'/finals/'+saved.json()['final_id']
        snapshot = client.get(path).json()
        assert snapshot['final_record']['model_assessment_audits']['SAFETY']['advice_format'] == 'single-advice-v1'
        preparation = snapshot['final_record']['preparation_summary']
        assert preparation['system_preparation'] is True
        assert preparation['origin_label'] == '悉尼市区（固定模拟出发地）'
        assert preparation['estimated_total_vehicle_km'] == '140'  # Saved Euroka reference, one confirmed car.
        assert preparation['source_refs'][0]['record_id'] == 'euroka'
        assert 'b_transport_reference_sha256' not in str(snapshot)
        assert role_counts(requests) == {'PLANNING':4,'LOGISTICS':9 if logistics_mode=='model' else 0,'SAFETY':9}
    count = len(requests)
    with TestClient(create_app(cfg)) as client:
        sign_in(client)
        assert client.get(path).json() == snapshot
        assert len(requests) == count
        sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get(path).status_code == 404
        assert client.get('/api/v1/plans/'+updated['plan']['plan_id']).status_code == 404
        client.post('/api/v1/auth/logout', headers=sign_in(client))
        assert client.get(path).status_code == 401


@pytest.mark.parametrize('after,expected', [(False,6),(True,3)])
def test_safety_receipt_recovery_reuses_planning_logistics_and_saved_advice(tmp_path, monkeypatch, after, expected):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    used = []
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port, 'save_model_safety_assessment', after=after)
        return port
    wrap_port(monkeypatch, once)
    cfg = compact_settings(tmp_path, daily=True)
    with TestClient(create_app(cfg)) as client:
        headers = sign_in(client)
        failed = wait_run(client, begin(client, headers), 'FAILED')
        old_log = deepcopy(failed['model_assessment_audits']['LOGISTICS'])
        old_trace, old_version = deepcopy(failed['model_planning_trace']), deepcopy(failed['version']['content'])
        old_safe = deepcopy(failed['model_assessment_audits'].get('SAFETY'))
    with TestClient(create_app(cfg)) as client:
        headers = sign_in(client)
        assert retry(client, headers, failed).status_code == 202
        restored = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        assert_compact(restored)
        assert restored['model_assessment_audits']['LOGISTICS'] == old_log
        assert restored['model_planning_trace'] == old_trace and restored['version']['content'] == old_version
        if old_safe:
            assert restored['model_assessment_audits']['SAFETY'] == old_safe
        assert role_counts(requests) == {'PLANNING':2,'LOGISTICS':3,'SAFETY':expected}


def test_standard_scope_rebuilds_its_original_protocol_but_current_guard_stays_strict(tmp_path, monkeypatch):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    cfg = settings(tmp_path, daily=True)
    app = create_app(cfg)
    with TestClient(app) as client:
        sign_in(client)
        detail = wait_run(client, begin(client, sign_in(client)), 'SUCCEEDED')
        with app.state.database.transaction(write=False) as db:
            row = db.execute('SELECT scope FROM runs WHERE id=?', (detail['run']['run_id'],)).fetchone()
        scope = RunScope.model_validate_json(row['scope'])
        assert detail['model_assessment_audits']['SAFETY']['trace']['tool_version'] == 'safety-read-only-tools-3'
    count = len(requests)
    cfg.safety_protocol = 'compact'
    newer = create_app(cfg)
    with TestClient(newer) as client:
        sign_in(client)
        snapshot = newer.state.runtime.for_scope(scope)
        assert snapshot.dataset == scope.dataset_context
        assert snapshot.agent.safety_agent.tool_version == 'safety-read-only-tools-3'
        with pytest.raises(ContractFailure) as caught:
            newer.state.runtime.validate_scope(scope)
        assert caught.value.error.code == 'STALE_CONTEXT'
        public = client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()
        assert public['model_assessment_audits']['SAFETY']['advice_format'] == 'separate-advice-v1'
        assert public['current_inputs_error'] and not public['finalisation_available']
        assert len(requests) == count


def test_corrupt_compact_audit_is_terminal_and_never_regenerated(tmp_path, monkeypatch):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    with TestClient(create_app(compact_settings(tmp_path))) as client:
        headers = sign_in(client)
        detail = wait_run(client, begin(client, headers), 'SUCCEEDED')
        before = len(requests)
        with client.app.state.database.transaction() as db:
            # Simulate external corruption only in this isolated test database.
            db.execute('DROP TRIGGER no_delete_safety_audit')
            db.execute('DELETE FROM model_safety_audits WHERE run_id=?', (detail['run']['run_id'],))
        response = client.get('/api/v1/plans/'+detail['plan']['plan_id'])
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'PERSISTENCE_FAILURE'
        assert not response.json()['error']['recoverable']
        assert len(requests) == before


def test_compact_recovery_pins_snapshot_but_finalisation_checks_current_date(tmp_path, monkeypatch):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    cfg = compact_settings(tmp_path, daily=True)
    with TestClient(create_app(cfg)) as client:
        headers = sign_in(client)
        detail = wait_run(client, begin(client, headers), 'SUCCEEDED')
        old = assert_compact(detail)
        with client.app.state.database.transaction(write=False) as db:
            row = db.execute('SELECT scope FROM runs WHERE id=?', (detail['run']['run_id'],)).fetchone()
        scope = RunScope.model_validate_json(row['scope'])
    count = len(requests)
    cfg.demo_today = cfg.demo_today.replace(day=28)
    app = create_app(cfg)
    with TestClient(app) as client:
        headers = sign_in(client)
        assert app.state.runtime.for_scope(scope).dataset == scope.dataset_context
        with pytest.raises(ContractFailure) as caught:
            app.state.runtime.validate_scope(scope)
        assert caught.value.error.code == 'STALE_CONTEXT'
        current = json_with_internal_audits(client, client.get('/api/v1/plans/'+detail['plan']['plan_id']))
        assert current['model_assessment_audits']['SAFETY'] == old
        assert current['current_inputs_error'] and not current['finalisation_available']
        response = client.post('/api/v1/plans/'+detail['plan']['plan_id']+'/finalise',
            headers=headers, json=final_command(detail))
        assert response.status_code == 409
        assert len(requests) == count
