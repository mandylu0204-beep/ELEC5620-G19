"""Sealed v2 adapter identity tests; actual demo flows are tested over HTTP."""
from pathlib import Path
import shutil
from types import SimpleNamespace

from app.application.agent_runtime import build_v2_binding
from app.application.datasets import inspect_dataset
from app.contracts.dto import DemoContext
from app.contracts.errors import ContractFailure

ROOT = Path(__file__).resolve().parents[2] / 'data/synthetic_demo_v2'


def bound_agent(safety_ids=(), *, feedback=None):
    settings = SimpleNamespace(dataset_path=ROOT, dataset_scenario_files=[],
        dataset_selection={}, workflow_safety_case_ids=list(safety_ids))
    descriptor = inspect_dataset(settings)
    choices = dict(descriptor.context.selection_config) | {'a_runtime_bound': '1'}
    if feedback:
        choices['a_revision_feedback'] = feedback
    descriptor = SimpleNamespace(context=descriptor.context.model_copy(update={'selection_config': choices}),
        provenance=descriptor.provenance, regions=descriptor.regions)
    binding = build_v2_binding(settings, descriptor)
    return settings, binding


def test_v2_adapter_consumes_sealed_runtime_bytes_and_preserves_a13_context():
    settings, binding = bound_agent(['safety-11'], feedback='cheaper campsite')
    dataset = binding.agent.dataset
    assert (len(dataset.campsites), len(dataset.gear_rules), len(dataset.cost_references)) == (10, 30, 16)
    assert len(dataset.runtime_requests) == 13 and len(dataset.safety_cases) == 18
    assert dataset.context.file_digests == binding.context.file_digests
    assert all(name in binding.context.file_digests for name in (
        'manifest.json', 'runtime_requests.json', 'runtime_safety_evidence.json'))
    assert binding.context.selection_config['a_runtime_bound'] == '1'
    assert binding.context.selection_config['a_revision_feedback'] == 'cheaper campsite'
    assert binding.context.selection_config['revision_feedback'] == 'cheaper campsite'
    assert binding.context.rules_version.startswith('a-request-normalization-v1/a-runtime-bindings-v2/')
    input = dataset.request_input('request-13', DemoContext(mode='deterministic_demo', demo_today='2026-11-05', dataset_version='2.0.0'))
    assert '100 total vehicle kilometres' in input.raw_text


def test_v2_factory_rejects_bytes_changed_after_a_inspected_them(tmp_path):
    package = tmp_path / 'v2-copy'
    shutil.copytree(ROOT, package)
    settings = SimpleNamespace(dataset_path=package, dataset_scenario_files=[],
        dataset_selection={}, workflow_safety_case_ids=[])
    descriptor = inspect_dataset(settings)
    path = package / 'data/runtime_requests.json'
    path.write_bytes(path.read_bytes() + b'\n')
    try:
        build_v2_binding(settings, descriptor)
    except ContractFailure as failure:
        assert failure.error.code.value == 'STALE_CONTEXT'
    else:
        raise AssertionError('Factory accepted data bytes different from A inspection.')
