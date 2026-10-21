"""Detached Dataset views; no runtime cache, network or model execution."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

from app.adapters.synthetic_dataset import SyntheticDataset
from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.agents.rules import planning
from app.contracts.dto import DemoContext, RecommendCampsitesInput
from app.workflow import WorkflowConfiguration
from test_llm_logistics_agent import baseline, input_fixture

ROOT = Path(__file__).resolve().parents[2] / 'data'
VIEWS = ('v2_policy', 'runtime_requests', 'safety_facts', 'runtime_profiles')


@pytest.fixture(params=['synthetic_demo_v2', 'synthetic_demo_v2_1'])
def snapshot(request):
    return SyntheticDatasetV2Adapter(ROOT / request.param).load()


def mutate_nested(name, value):
    if name == 'v2_policy':
        row = value['gear'][next(iter(value['gear']))]
        row['quantity_json'] = {'add': [999, 999]}
    elif name == 'runtime_requests':
        row = value[next(iter(value))]
        row['natural_language_request'] = 'Offline mutation of an exported view.'
        row['profile_snapshot']['normalized_equipment'].clear()
    elif name == 'safety_facts':
        value[next(iter(value))]['temperature_min_c'] = -999
    else:
        value[next(iter(value))].equipment.clear()


@pytest.mark.parametrize('name', VIEWS)
def test_public_view_nested_changes_do_not_modify_snapshot(snapshot, name):
    original = deepcopy(getattr(snapshot, name))
    view = getattr(snapshot, name)
    mutate_nested(name, view)
    assert getattr(snapshot, name) == original
    view.clear()
    assert getattr(snapshot, name) == original


@pytest.mark.parametrize('name', VIEWS)
def test_public_source_views_cannot_be_rebound(snapshot, name):
    with pytest.raises(AttributeError):
        setattr(snapshot, name, {})


def test_constructor_detaches_source_dictionaries(snapshot):
    sources = {name: getattr(snapshot, name) for name in VIEWS}
    original = deepcopy(sources)
    loaded = SyntheticDataset(snapshot.context, snapshot._campsites,
        snapshot._gear_rules, snapshot._costs, snapshot._profiles,
        snapshot._requests, snapshot._safety, **sources)
    for name, value in sources.items():
        mutate_nested(name, value)
        value.clear()
    assert {name: getattr(loaded, name) for name in VIEWS} == original


def test_runtime_request_input_returns_detached_profile(snapshot):
    demo = DemoContext(mode='deterministic_demo', demo_today='2026-11-05',
        dataset_version=snapshot.context.dataset_version)
    key = next(iter(snapshot.runtime_requests))
    first = snapshot.request_input(key, demo)
    original = first.model_dump_json()
    first.profile_snapshot.equipment.clear()
    first.profile_snapshot.accessibility_requirements.append('Offline view mutation')
    assert snapshot.request_input(key, demo).model_dump_json() == original


def test_targeted_policy_and_fact_reads_return_detached_rows(snapshot):
    policy = deepcopy(snapshot.v2_policy)
    gear_key = next(iter(policy['gear']))
    cost_key = next(iter(policy['costs']))
    facts = deepcopy(snapshot.safety_facts)
    safety_key = next(iter(facts))
    snapshot.get_gear_policy(gear_key).clear()
    snapshot.get_cost_policy(cost_key).clear()
    snapshot.get_safety_facts(safety_key).clear()
    assert snapshot.get_gear_policy(gear_key) == policy['gear'][gear_key]
    assert snapshot.get_cost_policy(cost_key) == policy['costs'][cost_key]
    assert snapshot.get_safety_facts(safety_key) == facts[safety_key]
    assert snapshot.get_safety_facts('unknown-offline-case') == {}


def test_workflow_choices_and_exported_sources_stay_isolated(snapshot):
    automatic = getattr(snapshot, 'trip_evidence_selector', None) is not None
    first = WorkflowConfiguration(snapshot,
        safety_case_ids=() if automatic else ('safety-11',), feedback='first revision')
    second = WorkflowConfiguration(snapshot,
        safety_case_ids=() if automatic else ('safety-15',), feedback='second revision')
    original = second.context.model_dump_json()
    policy = deepcopy(snapshot.v2_policy)
    first.context.selection_config.clear()
    first.context.file_digests.clear()
    snapshot.v2_policy['gear'].clear()
    assert second.context.model_dump_json() == original
    assert snapshot.v2_policy == policy
    assert first.feedback == 'first revision' and second.feedback == 'second revision'
    assert first.context != second.context


def test_concurrent_export_mutations_do_not_change_snapshot(snapshot):
    original = {name: deepcopy(getattr(snapshot, name)) for name in VIEWS}
    def worker(index):
        name = VIEWS[index % len(VIEWS)]
        mutate_nested(name, getattr(snapshot, name))
        return getattr(snapshot, name) == original[name]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(worker, range(16)))
    assert {name: getattr(snapshot, name) for name in VIEWS} == original


def test_rule_hot_path_does_not_copy_entire_public_views(monkeypatch):
    dataset, input, config = input_fixture()
    expected = baseline(dataset, input, config).model_dump_json()
    recommend_input = RecommendCampsitesInput(confirmed_requirements=input.confirmed_requirements,
        profile_snapshot=input.profile_snapshot, demo_context=input.demo_context)
    expected_recommendations = planning.recommend(dataset, recommend_input).model_dump_json()
    key = next(iter(dataset.runtime_requests))
    expected_request = dataset.request_input(key, input.demo_context).model_dump_json()
    def forbidden(self):
        raise AssertionError('Rules must not request an entire source dictionary')
    for name in VIEWS:
        monkeypatch.setattr(SyntheticDataset, name, property(forbidden), raising=False)
    assert baseline(dataset, input, config).model_dump_json() == expected
    assert planning.recommend(dataset, recommend_input).model_dump_json() == expected_recommendations
    assert dataset.request_input(key, input.demo_context).model_dump_json() == expected_request
