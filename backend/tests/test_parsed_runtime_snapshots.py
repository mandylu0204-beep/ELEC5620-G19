"""Parsed-data reuse must not reuse client, mutable state or stale input identity."""
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
import shutil

import pytest

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.application.agent_runtime import DATASET_AGENT_FACTORIES, build_v2_binding
from app.application.parsed_snapshots import ParsedSnapshots
from app.config import Settings
from app.contracts.errors import ContractFailure
from app.contracts.enums import ExecutionMode
from app.main import create_app
from campus_http_fixtures import mock_campus
from llm_fixtures import model_settings

ROOT = Path(__file__).resolve().parents[2]


def config(tmp_path, **changes):
    return Settings(_env_file=None, dataset_path=ROOT/'data/synthetic_demo_v2_1',
        database_path=tmp_path/'cache.sqlite3', execution_mode='deterministic_demo',
        demo_today='2026-10-26', synthetic_evidence_mode='sealed', **changes)


@pytest.fixture
def parse_calls(monkeypatch):
    calls = []
    original = SyntheticDatasetV2Adapter._parse
    @wraps(original)
    def parse(self, *args):
        calls.append(1)
        return original(self, *args)
    monkeypatch.setattr(SyntheticDatasetV2Adapter, '_parse', parse)
    return calls


def test_warm_data_is_detached_and_identity_equals_cold(tmp_path, parse_calls):
    cfg = config(tmp_path)
    app = create_app(cfg)
    first = app.state.runtime.resolve()
    first.agent.dataset.v2_policy['gear'].clear()
    first.agent.dataset.runtime_requests.clear()
    second = app.state.runtime.resolve()
    assert len(parse_calls) == 1
    assert first.agent is not second.agent and first.agent.dataset is not second.agent.dataset
    assert second.agent.dataset.v2_policy['gear'] and second.agent.dataset.runtime_requests
    cold = build_v2_binding(cfg, second.descriptor)
    assert cold.context == second.dataset
    assert cold.agent.dataset.v2_policy == second.agent.dataset.v2_policy
    assert len(parse_calls) == 2


def test_app_instances_do_not_share_cache(tmp_path, parse_calls):
    first = create_app(config(tmp_path/'one'))
    second = create_app(config(tmp_path/'two'))
    assert first.state.runtime._parsed_snapshots is not second.state.runtime._parsed_snapshots
    assert len(parse_calls) == 2


@pytest.mark.parametrize('change', ['feedback', 'selection', 'factory', 'date'])
def test_context_and_factory_changes_do_not_reuse_wrong_snapshot(tmp_path, parse_calls, monkeypatch, change):
    cfg = config(tmp_path)
    app = create_app(cfg)
    first = app.state.runtime.resolve()
    kwargs = {}
    if change == 'feedback':
        kwargs['feedback'] = 'Choose a quieter campsite.'
    elif change == 'selection':
        cfg.dataset_selection = {'variant': 'another-input-selection'}
    elif change == 'date':
        cfg.demo_today = cfg.demo_today.replace(day=27)
    else:
        key = ('deterministic_demo', 'CampMate Synthetic Demo Dataset v2')
        original = DATASET_AGENT_FACTORIES[key]
        @wraps(original)
        def replacement(*args, **kwargs):
            return original(*args, **kwargs)
        monkeypatch.setitem(DATASET_AGENT_FACTORIES, key, replacement)
    current = app.state.runtime.resolve(**kwargs)
    assert len(parse_calls) == 2
    assert current.agent is not first.agent


@pytest.mark.parametrize('filename', ['manifest.json', 'data/runtime_requests.json', 'data/synthetic_campsites.csv'])
def test_warm_cache_does_not_hide_file_corruption(tmp_path, parse_calls, filename):
    package = tmp_path/'package'
    shutil.copytree(ROOT/'data/synthetic_demo_v2_1', package)
    cfg = config(tmp_path)
    cfg.dataset_path = package
    app = create_app(cfg)
    assert len(parse_calls) == 1
    target = package/filename
    target.write_bytes(b'not valid sealed input')
    with pytest.raises(ContractFailure):
        app.state.runtime.resolve()
    assert len(parse_calls) == 1


def test_warm_cache_checks_current_manifest_bytes(tmp_path, parse_calls):
    package = tmp_path/'package'
    shutil.copytree(ROOT/'data/synthetic_demo_v2_1', package)
    cfg = config(tmp_path)
    cfg.dataset_path = package
    app = create_app(cfg)
    before = app.state.runtime.resolve()
    manifest = package/'manifest.json'
    manifest.write_bytes(manifest.read_bytes()+b'\n')
    after = app.state.runtime.resolve()
    assert len(parse_calls) == 2
    assert before.dataset.file_digests['manifest.json'] != after.dataset.file_digests['manifest.json']


def test_warm_cache_does_not_skip_adapter_path_checks(tmp_path, monkeypatch, parse_calls):
    from app.adapters import synthetic_dataset_v2 as adapter
    app = create_app(config(tmp_path))
    original = adapter.data_file_path
    def rejected(*args, **kwargs):
        raise ValueError('Synthetic unsafe path')
    monkeypatch.setattr(adapter, 'data_file_path', rejected)
    with pytest.raises(ContractFailure):
        app.state.runtime.resolve()
    assert len(parse_calls) == 1
    monkeypatch.setattr(adapter, 'data_file_path', original)
    assert app.state.runtime.resolve().agent is not None
    assert len(parse_calls) == 1


def test_warm_cache_checks_adapter_bytes_against_fresh_descriptor(tmp_path, monkeypatch, parse_calls):
    from dataclasses import replace
    from app.application import agent_runtime
    app = create_app(config(tmp_path))
    original = agent_runtime.inspect_dataset
    def mismatched(settings):
        descriptor = original(settings)
        digests = {**descriptor.context.file_digests, 'runtime_requests.json': '0'*64}
        return replace(descriptor, context=descriptor.context.model_copy(update={'file_digests': digests}))
    monkeypatch.setattr(agent_runtime, 'inspect_dataset', mismatched)
    with pytest.raises(ContractFailure) as exc:
        app.state.runtime.resolve()
    assert exc.value.error.code == 'STALE_CONTEXT' and len(parse_calls) == 1


def test_warm_cache_does_not_skip_scenario_validation(tmp_path, monkeypatch):
    from app.application import agent_runtime
    app = create_app(config(tmp_path))
    original = agent_runtime.configured_scenarios
    calls = []
    def scenario_check(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(agent_runtime, 'configured_scenarios', scenario_check)
    app.state.runtime.resolve()
    app.state.runtime.resolve()
    assert len(calls) == 2
    app.state.settings.dataset_scenario_files = ['data/scenarios/missing.json']
    with pytest.raises(ContractFailure):
        app.state.runtime.resolve()


def test_registered_evidence_policy_change_cannot_replay_old_parse(tmp_path, monkeypatch, parse_calls):
    from app.agents.rules import trip_evidence
    app = create_app(config(tmp_path))
    monkeypatch.setattr(trip_evidence, 'POLICY_VERSION', 'unregistered-policy-for-test')
    with pytest.raises(ContractFailure):
        app.state.runtime.resolve()
    assert len(parse_calls) == 2


def test_failed_registration_does_not_publish_parsed_entry(tmp_path, parse_calls, monkeypatch):
    from app.application import agent_runtime
    cfg = config(tmp_path)
    original = agent_runtime.configured_scenarios
    def fail(*args):
        raise ValueError('Synthetic failure after parsing')
    monkeypatch.setattr(agent_runtime, 'configured_scenarios', fail)
    with pytest.raises(ValueError):
        create_app(cfg)
    monkeypatch.setattr(agent_runtime, 'configured_scenarios', original)
    cache = ParsedSnapshots(capacity=2)
    with pytest.raises(ValueError):
        with cache.transaction():
            cache.stage('failed', {'valid': []})
            raise ValueError('Synthetic registration failure')
    assert cache.get('failed') is None


def test_cache_capacity_and_copy_on_both_boundaries():
    cache = ParsedSnapshots(capacity=2)
    original = {'rows': []}
    with cache.transaction():
        cache.stage('one', original)
    original['rows'].append('mutated caller')
    returned = cache.get('one')
    returned['rows'].append('mutated result')
    assert cache.get('one') == {'rows': []}
    for key in ['two', 'three']:
        with cache.transaction():
            cache.stage(key, {})
    assert cache.get('one') is None and len(cache._entries) == 2


def test_nested_registration_only_publishes_after_outer_success():
    cache = ParsedSnapshots(capacity=2)
    with pytest.raises(ValueError):
        with cache.transaction():
            with cache.transaction():
                cache.stage('inner', {'rows': []})
            assert cache.get('inner') is None
            raise ValueError('Outer registration failed')
    assert cache.get('inner') is None
    with cache.transaction():
        with cache.transaction():
            cache.stage('inner', {'rows': []})
        assert cache.get('inner') is None
    assert cache.get('inner') == {'rows': []}


def test_failed_nested_registration_discards_only_its_candidates():
    cache = ParsedSnapshots(capacity=2)
    with cache.transaction():
        cache.stage('outer', {})
        with pytest.raises(ValueError):
            with cache.transaction():
                cache.stage('inner', {})
                raise ValueError('Inner registration failed')
    assert cache.get('outer') == {} and cache.get('inner') is None


def test_concurrent_resolutions_have_independent_public_dicts(tmp_path, parse_calls):
    app = create_app(config(tmp_path))
    with ThreadPoolExecutor(max_workers=3) as pool:
        snapshots = list(pool.map(lambda _: app.state.runtime.resolve(), range(3)))
    assert len(parse_calls) == 1
    assert len({id(s.agent.dataset) for s in snapshots}) == 3
    snapshots[0].agent.dataset.v2_policy['gear'].clear()
    assert snapshots[1].agent.dataset.v2_policy['gear'] and snapshots[2].agent.dataset.v2_policy['gear']


def test_model_key_rotation_revalidates_and_creates_new_client(tmp_path, monkeypatch, parse_calls):
    from app.llm import config as model_config
    calls, _ = mock_campus(monkeypatch)
    cfg = config(tmp_path)
    cfg.execution_mode = ExecutionMode.AGENT
    current = [model_settings()]
    monkeypatch.setattr(model_config, 'CampusModelSettings', lambda: current[0])
    app = create_app(cfg)
    first = app.state.runtime.resolve()
    current[0] = model_settings(api_key='unit-only-rotated-key')
    second = app.state.runtime.resolve()
    assert first.agent.coordinator.client is not second.agent.coordinator.client
    assert second.agent.coordinator.client.settings.api_key.get_secret_value() == 'unit-only-rotated-key'
    assert first.dataset == second.dataset and len(parse_calls) == 1
    current[0] = model_settings(api_key='')
    with pytest.raises(ContractFailure):
        app.state.runtime.resolve()
    assert calls == []


def test_public_model_config_and_role_switch_are_rebuilt(tmp_path, monkeypatch, parse_calls):
    from app.llm import config as model_config
    calls, _ = mock_campus(monkeypatch)
    cfg = config(tmp_path)
    cfg.execution_mode = ExecutionMode.AGENT
    current = [model_settings()]
    monkeypatch.setattr(model_config, 'CampusModelSettings', lambda: current[0])
    app = create_app(cfg)
    first = app.state.runtime.resolve()
    current[0] = model_settings(timeout_seconds=6)
    second = app.state.runtime.resolve()
    assert len(parse_calls) == 2 and second.dataset != first.dataset
    cfg.safety_execution = 'model'
    third = app.state.runtime.resolve()
    assert len(parse_calls) == 3 and third.dataset != second.dataset
    assert third.agent.safety_agent is not None and calls == []


def test_cross_day_recovery_remains_pinned_but_validation_uses_today(tmp_path, monkeypatch, parse_calls):
    from datetime import date
    from app import config as app_config
    day = [date(2026, 10, 26)]
    monkeypatch.setattr(app_config, 'sydney_today', lambda: day[0])
    cfg = config(tmp_path)
    cfg.clock_mode = 'current'
    cfg.synthetic_evidence_mode = 'rolling'
    cfg.snapshot_cache_path = tmp_path/'daily'
    app = create_app(cfg)
    old = app.state.runtime.resolve()
    scope = SimpleNamespace(dataset_context=old.dataset, demo_context=old.demo)
    day[0] = date(2026, 10, 27)
    current = app.state.runtime.resolve()
    pinned = app.state.runtime.for_scope(scope)
    assert pinned.dataset == old.dataset and pinned.demo == old.demo
    assert current.dataset != old.dataset and current.demo.demo_today == day[0]
    with pytest.raises(ContractFailure) as exc:
        app.state.runtime.validate_scope(scope)
    assert exc.value.error.code == 'STALE_CONTEXT'
