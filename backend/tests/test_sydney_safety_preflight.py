"""Frozen-v2 and incomplete-v3 registration boundaries, with no model calls.

No private env, HTTP service, database, real client or model invocation. These
characterise fail-closed boundaries, not live acceptance of the v3 role.
"""
from datetime import date
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.application.agent_runtime import build_v2_binding, build_v2_hybrid_binding
from app.application.daily_snapshot import effective_settings
from app.application.datasets import inspect_dataset
from app.config import Settings
from app.contracts.errors import ContractFailure
from app.llm.safety_agent import SafetyAgent
from app.llm.safety_identity import compose_safety_identity, safety_identity_seed
from app.workflow import WorkflowConfiguration


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'data/sydney_surrounds_v2_2'


@pytest.fixture(autouse=True)
def prohibit_network_and_model_configuration(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Preflight must not read model configuration, construct a client or send HTTP')

    monkeypatch.setattr('app.llm.config.CampusModelSettings', forbidden)
    monkeypatch.setattr('app.llm.client.CampusModelClient', forbidden)
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    monkeypatch.setattr(httpx.AsyncClient, 'send', forbidden)


@pytest.fixture(params=['sealed', 'daily'])
def sydney_settings(request, tmp_path):
    config = Settings(_env_file=None, dataset_path=PACKAGE, execution_mode='agent',
        planning_enabled=True, logistics_execution='rules', safety_execution='model',
        clock_mode='fixed', demo_today='2026-10-26', synthetic_evidence_mode='sealed',
        workflow_safety_case_ids=[], dataset_scenario_files=[], dataset_selection={},
        database_path=tmp_path / 'unused.sqlite3', snapshot_cache_path=tmp_path / 'snapshots')
    if request.param == 'daily':
        config = effective_settings(config.model_copy(update={
            'clock_mode': 'current', 'synthetic_evidence_mode': 'auto'}), date(2026, 10, 26))
        assert config.dataset_selection['a_daily_snapshot'] == 'synthetic-daily-v1'
    assert inspect_dataset(config).context.dataset_version == '2.2.0'
    assert not config.database_path.exists()
    return config


@pytest.mark.parametrize('logistics_mode', ['rules', 'model'])
def test_v22_incomplete_audit_factory_stops_before_client_creation(sydney_settings, logistics_mode, monkeypatch):
    monkeypatch.setattr('app.workflow.orchestration.Orchestrator.safety_audit_contract', None)
    config = sydney_settings.model_copy(update={'logistics_execution': logistics_mode})
    with pytest.raises(ContractFailure) as failure:
        build_v2_hybrid_binding(config, inspect_dataset(config))
    assert failure.value.error.code == 'AGENT_FAILURE'
    assert not config.database_path.exists()


def test_standalone_component_also_rejects_real_v22_snapshot(sydney_settings):
    descriptor = inspect_dataset(sydney_settings)
    dataset = SyntheticDatasetV2Adapter(sydney_settings.dataset_path).load(expected_context=descriptor.context)
    configuration = WorkflowConfiguration(dataset, registered_context=descriptor.context)
    with pytest.raises(ContractFailure) as failure:
        SafetyAgent(dataset, SimpleNamespace(), workflow_configuration=configuration)
    assert failure.value.error.code == 'STALE_CONTEXT'


def test_rule_binding_keeps_catalogue_and_snapshot_identity_without_model_markers(sydney_settings):
    config = sydney_settings.model_copy(update={
        'execution_mode': 'deterministic_demo', 'safety_execution': 'rules'})
    descriptor = inspect_dataset(config)
    binding = build_v2_binding(config, descriptor)
    assert binding.context.dataset_version == '2.2.0'
    assert binding.context.file_digests == descriptor.context.file_digests
    assert 'source_catalogue.json' in binding.context.file_digests
    for key, value in descriptor.context.selection_config.items():
        assert binding.context.selection_config[key] == value
    assert not any(key.startswith('a_safety_') for key in binding.context.selection_config)
    assert not config.database_path.exists()


def test_v2_seed_schema_alone_is_not_v22_runtime_authorisation(sydney_settings):
    descriptor = inspect_dataset(sydney_settings)
    dataset = SyntheticDatasetV2Adapter(sydney_settings.dataset_path).load(expected_context=descriptor.context)
    configuration = WorkflowConfiguration(dataset, registered_context=descriptor.context)
    public = {'client_version': 'b04-campus-client-1', 'base_url': 'http://127.0.0.1:9/v1',
        'model': 'campus-qwen', 'timeout_seconds': 45, 'max_completion_tokens': 4096,
        'max_attempts': 2, 'max_turns': 4, 'reasoning_effort': 'low'}
    # Rules identities match 2.1, so the current seed/compose functions accept
    # this context. That is not permission: component/factory guards above deny it.
    seed = safety_identity_seed(dataset, public)
    identity = compose_safety_identity(seed, configuration.context)
    assert seed['validation_version'] == 'safety-advisory-validation-2'
    assert identity['workflow_context']['dataset_version'] == '2.2.0'
    assert identity['workflow_context']['file_digests']['source_catalogue.json'] == (
        descriptor.context.file_digests['source_catalogue.json'])
    changed = configuration.context.model_dump(mode='json')
    changed['file_digests']['source_catalogue.json'] = '0' * 64
    assert compose_safety_identity(seed, changed)['configuration_fingerprint'] != identity['configuration_fingerprint']


def test_sydney_launcher_still_forces_rules_even_with_inherited_model_safety(monkeypatch):
    spec = importlib.util.spec_from_file_location('sydney_preflight_launcher', ROOT / 'scripts/sydney.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def capture(command, *, cwd, env):
        calls.append({key: value for key, value in env.items() if key.startswith('CAMPMATE_')})
        return 0

    monkeypatch.setenv('CAMPMATE_SAFETY_EXECUTION', 'model')
    monkeypatch.setattr(module.sys, 'argv', ['sydney.py'])
    monkeypatch.setattr(module.subprocess, 'call', capture)
    assert module.main() == 0
    assert len(calls) == 1
    assert calls[0]['CAMPMATE_SAFETY_EXECUTION'] == 'rules'
    assert calls[0]['CAMPMATE_EXECUTION_MODE'] == 'deterministic_demo'
