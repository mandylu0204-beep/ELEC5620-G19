"""Sydney source identity and daily snapshots; local files only, no model calls."""
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.application.daily_snapshot import effective_settings
from app.application.datasets import inspect_dataset
from app.application.parsed_snapshots import ParsedSnapshots
from app.config import Settings
from app.contracts.dto import DemoContext
from app.contracts.errors import ContractFailure
from rule_fixtures import requirements
from rule_fixtures import full_profile
from app.agents.rules.planning import violations


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'data/sydney_surrounds_v2_2'
CATALOGUE = 'source_catalogue.json'
REGION = 'Sydney & Surrounds'
NAMES = {
    'The Basin campground', 'Bonnie Vale campground', 'Bents Basin campground',
    'Cattai campground', 'Euroka campground', 'Lane Cove caravan park',
    'Putty Beach campground', 'Little Beach campground', 'Tallow Beach campground',
    'Cockatoo Island waterfront campground',
}
LEGACY_MANIFESTS = {
    'synthetic_demo_v2': '502ce1a3cc84a27c39b26abcf0c757d2861152928da343ea316f50a42c9806be',
    'synthetic_demo_v2_1': '638d0b887defd50afc95c73295ec86c11a4336deb44c55df329f9c46e2fed731',
}


def settings(tmp_path, *, package=PACKAGE, **changes):
    return Settings(_env_file=None, **{
        'dataset_path': package, 'execution_mode': 'deterministic_demo',
        'planning_enabled': True, 'clock_mode': 'fixed', 'demo_today': '2026-10-26',
        'synthetic_evidence_mode': 'sealed', 'database_path': tmp_path / 'sydney.sqlite3',
        'snapshot_cache_path': tmp_path / 'snapshots', **changes,
    })


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def test_real_campsite_names_are_bound_to_a_distinct_version_and_region(tmp_path):
    config = settings(tmp_path)
    descriptor = inspect_dataset(config)
    dataset = SyntheticDatasetV2Adapter(PACKAGE).load(expected_context=descriptor.context)
    assert descriptor.context.dataset_version == dataset.context.dataset_version == '2.2.0'
    assert descriptor.regions == [REGION] and dataset.regions == (REGION,)
    assert len(dataset.campsites) == 10
    assert {camp.name for camp in dataset.campsites} == NAMES
    assert len({camp.campsite_id for camp in dataset.campsites}) == 10
    for camp in dataset.campsites:
        assert 'demo' not in ' '.join((camp.campsite_id, camp.name, camp.region, camp.subregion)).casefold()
        assert camp.fee_unit == 'per_night'  # Group/site estimates, never raw per-person tariffs.
    # The source family remains explicit internally; collected places are not a live API.
    assert descriptor.provenance.source_type == 'SYNTHETIC'
    assert descriptor.provenance.demo_only is True
    assert dataset.trip_evidence_selector is not None


def test_catalogue_bytes_are_part_of_both_registered_and_adapter_identities(tmp_path):
    descriptor = inspect_dataset(settings(tmp_path))
    dataset = SyntheticDatasetV2Adapter(PACKAGE).load(expected_context=descriptor.context)
    manifest = json.loads((PACKAGE / 'manifest.json').read_bytes())
    digest = sha((PACKAGE / 'data' / CATALOGUE).read_bytes())
    assert manifest['files_sha256']['data/' + CATALOGUE] == digest
    assert descriptor.context.file_digests[CATALOGUE] == digest
    assert dataset.context.file_digests[CATALOGUE] == digest


@pytest.mark.parametrize('name', list(LEGACY_MANIFESTS))
def test_original_sealed_packages_and_their_names_remain_readable(name):
    package = ROOT / 'data' / name
    payload = (package / 'manifest.json').read_bytes()
    assert sha(payload) == LEGACY_MANIFESTS[name]
    manifest = json.loads(payload)
    for relative, digest in manifest['files_sha256'].items():
        assert sha((package / relative).read_bytes()) == digest
    dataset = SyntheticDatasetV2Adapter(package).load()
    assert len(dataset.campsites) == 10
    assert dataset.regions == ('CampMate Demo Region',)
    assert all(camp.campsite_id.startswith('demo-') for camp in dataset.campsites)
    assert {camp.name for camp in dataset.campsites}.isdisjoint(NAMES)


@pytest.mark.parametrize('mutation', ['replace', 'remove', 'trailing-newline'])
def test_catalogue_tampering_is_rejected_by_inspection_and_adapter(tmp_path, mutation):
    package = tmp_path / 'package'
    shutil.copytree(PACKAGE, package)
    config = settings(tmp_path, package=package)
    registered = inspect_dataset(config).context
    target = package / 'data' / CATALOGUE
    if mutation == 'remove':
        target.unlink()
    elif mutation == 'replace':
        target.write_bytes(b'{"campsites":[]}\n')
    else:
        target.write_bytes(target.read_bytes() + b'\n')
    with pytest.raises(ContractFailure):
        inspect_dataset(config)
    with pytest.raises(ContractFailure):
        SyntheticDatasetV2Adapter(package).load(expected_context=registered)
    with pytest.raises(ContractFailure):
        SyntheticDatasetV2Adapter(package).load()


def test_warm_parsed_snapshot_cannot_hide_resealed_catalogue_changes(tmp_path):
    package = tmp_path / 'package'
    shutil.copytree(PACKAGE, package)
    config = settings(tmp_path, package=package)
    registered = inspect_dataset(config).context
    adapter = SyntheticDatasetV2Adapter(package)
    snapshots = ParsedSnapshots()
    with snapshots.transaction():
        original = adapter.load(expected_context=registered, parsed_snapshots=snapshots)
    with snapshots.transaction():
        warm = adapter.load(expected_context=registered, parsed_snapshots=snapshots)
    assert original.context == warm.context
    target = package / 'data' / CATALOGUE
    target.write_bytes(target.read_bytes() + b'\n')
    manifest_path = package / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest['files_sha256']['data/' + CATALOGUE] = sha(target.read_bytes())
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    current = inspect_dataset(config).context
    assert current.file_digests[CATALOGUE] != registered.file_digests[CATALOGUE]
    with snapshots.transaction(), pytest.raises(ContractFailure) as failure:
        adapter.load(expected_context=registered, parsed_snapshots=snapshots)
    assert failure.value.error.code == 'STALE_CONTEXT'
    with snapshots.transaction():
        updated = adapter.load(expected_context=current, parsed_snapshots=snapshots)
    assert updated.context.file_digests[CATALOGUE] == current.file_digests[CATALOGUE]
    assert updated.context != warm.context


def test_daily_snapshot_preserves_catalogue_bytes_version_and_real_campsites(tmp_path):
    config = settings(tmp_path, clock_mode='current', synthetic_evidence_mode='auto')
    before = inspect_dataset(config)
    original = (PACKAGE / 'data' / CATALOGUE).read_bytes()
    day = date(2026, 10, 26)
    effective = effective_settings(config, day)
    assert effective.dataset_path != PACKAGE
    assert (effective.dataset_path / 'data' / CATALOGUE).read_bytes() == original
    descriptor = inspect_dataset(effective)
    dataset = SyntheticDatasetV2Adapter(effective.dataset_path).load(expected_context=descriptor.context)
    assert dataset.context.dataset_version == '2.2.0'
    assert descriptor.context.file_digests[CATALOGUE] == before.context.file_digests[CATALOGUE]
    assert {camp.name for camp in dataset.campsites} == NAMES
    assert inspect_dataset(config) == before
    assert effective_settings(config, day).dataset_path == effective.dataset_path
    tomorrow = effective_settings(config, date(2026, 10, 27))
    assert tomorrow.dataset_path != effective.dataset_path
    assert (tomorrow.dataset_path / 'data' / CATALOGUE).read_bytes() == original
    assert inspect_dataset(tomorrow).context.dataset_version == '2.2.0'
    assert inspect_dataset(tomorrow).context != descriptor.context


def test_new_daily_evidence_does_not_inherit_fictitious_old_site_closures(tmp_path):
    config = settings(tmp_path, clock_mode='current', synthetic_evidence_mode='auto')
    effective = effective_settings(config, date(2026, 10, 26))
    dataset = SyntheticDatasetV2Adapter(effective.dataset_path).load()
    rows = json.loads((effective.dataset_path / 'data/runtime_safety_evidence.json').read_bytes())
    ids = {camp.campsite_id for camp in dataset.campsites}
    assert {row['campsite_id'] for row in rows} == ids
    assert all(not row['campsite_id'].startswith('demo-') for row in rows)
    assert all(not any('demo-' in origin for origin in row.get('origin_case_ids', [])) for row in rows)
    assert not any('Synthetic campsite closure.' in row['campsite_restrictions'] for row in rows)
    demo = DemoContext(mode='deterministic_demo', demo_today='2026-10-26', dataset_version='2.2.0')
    req = requirements(destination=REGION, start_date=date(2026, 10, 27))
    for camp in dataset.campsites:
        selection = dataset.trip_evidence_selector.resolve_trip_evidence(req, [camp.campsite_id], demo)
        assert not selection.coverage_issues
        assert {item.kind for item in selection.scenario_context.evidence} == {'WEATHER', 'FIRE', 'ROAD', 'RESTRICTION'}
        assert all(item.status == 'AVAILABLE' for item in selection.scenario_context.evidence)


@pytest.mark.parametrize('key', ['the-basin', 'euroka', 'putty-beach', 'little-beach', 'tallow-beach'])
def test_documented_carpark_walk_is_arrival_not_vehicle_camping(key):
    dataset = SyntheticDatasetV2Adapter(PACKAGE).load()
    camp = dataset.get_campsite(key)
    assert camp.vehicle_access is False and camp.walk_in_only is True
    req = requirements(destination=REGION)
    assert 'Vehicle access is unavailable or unknown.' not in violations(camp, req, full_profile())
    direct = req.model_copy(update={'mandatory_constraints': ['vehicle_access']})
    assert any('Mandatory feature vehicle_access' in reason for reason in violations(camp, direct, full_profile()))
    undocumented = camp.model_copy(update={'facilities': ['carpark']})
    assert 'Vehicle access is unavailable or unknown.' in violations(undocumented, req, full_profile())


def test_wood_fire_ban_remains_a_hard_constraint_without_inventing_a_total_ban(tmp_path):
    effective = effective_settings(settings(tmp_path, clock_mode='current', synthetic_evidence_mode='auto'), date(2026,10,26))
    dataset = SyntheticDatasetV2Adapter(effective.dataset_path).load()
    camp = dataset.get_campsite('bonnie-vale')
    assert camp.fire_allowed is False
    req = requirements(destination=REGION, mandatory_constraints=['campfire'])
    assert any('Mandatory feature campfire' in reason for reason in violations(camp, req, full_profile()))
    rows = json.loads((effective.dataset_path / 'data/runtime_safety_evidence.json').read_bytes())
    assert not any(row['fire']['summary'] == 'Synthetic comprehensive no-fire restriction.' for row in rows)
    assert 'gas/electric barbecues' in camp.facilities


def test_new_catalogue_does_not_silently_enable_incomplete_model_safety(tmp_path, monkeypatch):
    from app.application.agent_runtime import build_v2_hybrid_binding
    def no_client(*args, **kwargs):
        pytest.fail('Unsupported model safety must be rejected before creating a model client')
    monkeypatch.setattr('app.llm.client.CampusModelClient', no_client)
    monkeypatch.setattr('app.workflow.orchestration.Orchestrator.safety_audit_contract', None)
    config = settings(tmp_path, execution_mode='agent', safety_execution='model')
    with pytest.raises(ContractFailure) as error:
        build_v2_hybrid_binding(config, inspect_dataset(config))
    assert error.value.error.code == 'AGENT_FAILURE'
