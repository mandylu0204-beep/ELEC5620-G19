"""R-01: A and B reject redirected inputs before reading their target bytes."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.adapters.synthetic_dataset_v2 import BUSINESS_FILES, RUNTIME_FILES, SyntheticDatasetV2Adapter
from app.application.agent_runtime import configured_scenarios
from app.application.datasets import inspect_dataset
from app.contracts.errors import ContractFailure

SOURCE = Path(__file__).resolve().parents[2] / 'data/synthetic_demo_v2'


@pytest.fixture
def package(tmp_path):
    root = tmp_path / 'package'
    shutil.copytree(SOURCE, root)
    settings = SimpleNamespace(dataset_path=root, dataset_scenario_files=[], dataset_selection={})
    descriptor = inspect_dataset(settings)
    return root, settings, descriptor


def link(path, target, *, directory=False):
    if directory and os.name == 'nt':
        # Directory junctions do not need the privilege required for file symlinks.
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(path), str(target)],
            check=True, capture_output=True, text=True)
        return
    try:
        path.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        if os.name == 'nt' and getattr(exc, 'winerror', None) in {5, 1314}:
            pytest.skip(f'Windows file symlink creation is unavailable: {exc}')
        raise


def reject_before_read(package, reader, forbidden, monkeypatch):
    root, settings, descriptor = package
    original = Path.read_bytes
    forbidden = forbidden.resolve()
    accessed = []

    def guarded(path):
        actual = path.resolve()
        assert actual != forbidden and not actual.is_relative_to(forbidden), (
            f'Forbidden input was opened before path rejection: {actual}')
        accessed.append(actual)
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', guarded)
    with pytest.raises(ContractFailure) as error:
        if reader == 'A':
            inspect_dataset(settings)
        else:
            SyntheticDatasetV2Adapter(root).load(expected_context=descriptor.context)
    assert error.value.error.code == 'ADAPTER_FAILURE'
    assert 'source' in str(error.value.__cause__).casefold()
    return accessed


@pytest.mark.parametrize('reader', ['A', 'B'])
@pytest.mark.parametrize('name', [*BUSINESS_FILES, *RUNTIME_FILES, 'manifest.json'])
@pytest.mark.parametrize('destination', ['tests', 'external'])
def test_each_source_link_is_rejected_even_when_sealed_bytes_match(
        package, tmp_path, monkeypatch, reader, name, destination):
    root, _, descriptor = package
    source = root / name if name == 'manifest.json' else root / 'data' / name
    target_dir = root / 'tests/source-lookalike' if destination == 'tests' else tmp_path / 'outside'
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    shutil.copyfile(source, target)
    source.unlink()
    link(source, target)
    # The original inspected identity remains valid for the unchanged bytes.
    assert hashlib.sha256(target.read_bytes()).hexdigest() == descriptor.context.file_digests[name]
    reject_before_read(package, reader, target_dir, monkeypatch)


@pytest.mark.parametrize('reader', ['A', 'B'])
@pytest.mark.parametrize('destination', ['tests', 'external'])
def test_parent_data_junction_or_symlink_is_not_a_new_allowlisted_directory(
        package, tmp_path, monkeypatch, reader, destination):
    root, _, _ = package
    target = root / 'tests/source-lookalike' if destination == 'tests' else tmp_path / 'outside-data'
    (root / 'data').rename(target)
    link(root / 'data', target, directory=True)
    reject_before_read(package, reader, target, monkeypatch)


@pytest.mark.parametrize('reader', ['A', 'B'])
def test_manifest_alias_inside_package_is_rejected(package, monkeypatch, reader):
    root, _, _ = package
    target = root / 'manifest-alias.json'
    (root / 'manifest.json').rename(target)
    link(root / 'manifest.json', target)
    reject_before_read(package, reader, target, monkeypatch)


@pytest.mark.parametrize('reader', ['A', 'B'])
def test_broken_manifest_link_does_not_act_like_an_absent_legacy_manifest(
        package, monkeypatch, reader):
    root, _, _ = package
    source = root / 'manifest.json'
    source.unlink()
    link(source, root / 'missing-manifest.json')
    with pytest.raises(ContractFailure) as error:
        if reader == 'A':
            inspect_dataset(package[1])
        else:
            SyntheticDatasetV2Adapter(root).load(expected_context=package[2].context)
    assert error.value.error.code == 'ADAPTER_FAILURE'


@pytest.mark.parametrize('reader', ['inspect', 'binding'])
@pytest.mark.parametrize('redirect_parent', [False, True])
def test_registered_scenario_cannot_redirect_to_tests_before_either_a_read(
        package, monkeypatch, reader, redirect_parent):
    root, settings, descriptor = package
    scenarios = root / 'data/scenarios'
    scenarios.mkdir()
    scene = scenarios / 'safe.json'
    scene.write_text('{}', encoding='utf-8')
    settings.dataset_scenario_files = ['data/scenarios/safe.json']
    target = root / 'tests/scenario-lookalike'
    if redirect_parent:
        scenarios.rename(target)
        link(scenarios, target, directory=True)
    else:
        target.mkdir()
        scene.rename(target / 'safe.json')
        link(scene, target / 'safe.json')
    original = Path.read_bytes

    def guarded(path):
        assert not path.resolve().is_relative_to(target)
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', guarded)
    with pytest.raises(ContractFailure) as error:
        if reader == 'inspect':
            inspect_dataset(settings)
        else:
            configured_scenarios(settings, descriptor)
    assert error.value.error.code == ('ADAPTER_FAILURE' if reader == 'inspect' else 'STALE_CONTEXT')


def test_regular_package_still_has_identical_a_b_source_digests(package):
    root, settings, descriptor = package
    dataset = SyntheticDatasetV2Adapter(root).load(expected_context=descriptor.context)
    assert inspect_dataset(settings).context == descriptor.context
    assert dataset.context.file_digests == descriptor.context.file_digests
