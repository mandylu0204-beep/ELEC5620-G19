"""B-01 boundary tests. Mutations only affect pytest's isolated source copies."""
import csv
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from app.adapters import SyntheticDatasetAdapter
from app.adapters.dataset_mapping import aud_to_cents, normalize_equipment
from app.adapters.synthetic_dataset import BUSINESS_FILES
from app.application.request_rules import data_context
from app.config import APP_ROOT, Settings
from app.contracts.dto import CostLine, DemoContext
from app.contracts.enums import DataQuality, ErrorCode, RoadState
from app.contracts.errors import ContractFailure

SOURCE = APP_ROOT / 'data/synthetic_demo'
DEMO = DemoContext(mode='deterministic_demo', demo_today=date(2026, 10, 8))
CSV_FILES = BUSINESS_FILES[:3]
JSON_FILES = BUSINESS_FILES[3:]


@pytest.fixture
def dataset(tmp_path):
    target = tmp_path / 'dataset'
    (target / 'data').mkdir(parents=True)
    for filename in BUSINESS_FILES:
        shutil.copyfile(SOURCE / 'data' / filename, target / 'data' / filename)
    return target


def read_json(dataset, filename):
    return json.loads((dataset / 'data' / filename).read_text(encoding='utf-8'))


def write_json(dataset, filename, rows):
    (dataset / 'data' / filename).write_text(json.dumps(rows), encoding='utf-8')


def change_csv(dataset, filename, edit):
    path = dataset / 'data' / filename
    with path.open(encoding='utf-8', newline='') as source:
        reader = csv.DictReader(source)
        fields, rows = reader.fieldnames, list(reader)
    edit(rows)
    with path.open('w', encoding='utf-8', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_failure(dataset, code=ErrorCode.ADAPTER_FAILURE):
    with pytest.raises(ContractFailure) as failure:
        SyntheticDatasetAdapter(dataset).load()
    assert failure.value.error.code == code
    return failure.value.error


def test_git_dataset_loads_without_writes_and_matches_a_context(dataset):
    before = {name: (dataset / 'data' / name).read_bytes() for name in BUSINESS_FILES}
    snapshot = SyntheticDatasetAdapter(dataset).load()
    assert [len(getattr(snapshot, key)) for key in ('campsites', 'gear_rules', 'cost_references', 'profiles', 'requests', 'safety_cases')] == [10, 30, 16, 5, 12, 10]
    assert snapshot.context.dataset_version == 'v1'
    assert snapshot.regions == ('CampMate Demo Region',)
    a_context, regions = data_context(Settings(_env_file=None, dataset_path=dataset))
    assert snapshot.context == a_context
    assert list(snapshot.regions) == regions
    assert snapshot.context.file_digests == {name: hashlib.sha256(content).hexdigest() for name, content in before.items()}
    assert before == {name: (dataset / 'data' / name).read_bytes() for name in BUSINESS_FILES}
    assert SyntheticDatasetAdapter(dataset).load(expected_context=a_context).context == a_context


def test_original_git_sources_still_match_a_manifest():
    manifest = json.loads((APP_ROOT / 'docs/dataset_manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        assert hashlib.sha256((APP_ROOT / entry['path']).read_bytes()).hexdigest() == entry['sha256']


def test_campsite_and_rule_fields_preserve_units_and_sources(dataset):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    campsite = snapshot.get_campsite('demo-pine-camp')
    assert campsite.nightly_fee_cents == 3500
    assert campsite.latitude == Decimal('-33.1011')
    assert campsite.booking_required is True
    assert campsite.public_transport_access is False
    assert campsite.supported_seasons == ['spring', 'summer', 'autumn']
    assert campsite.source_ref.dataset_file == 'synthetic_campsites.csv'
    assert campsite.source_ref.record_id == 'demo-pine-camp'
    assert campsite.source_ref.provenance.demo_only is True
    rule = snapshot.get_gear_rule('gear-14')
    assert rule.essential is True
    assert rule.severity_if_missing == 'MANDATORY_BLOCKER'
    assert rule.quantity_rule == 'two litres per camper per day plus one emergency day'


@pytest.mark.parametrize('value,expected', [
    ('0', 0), ('0.35', 35), ('1.225', 123), (320, 32000),
    (Decimal('1.005'), 101), ('unknown', None), ('', None), (None, None),
])
def test_money_conversion_uses_decimal_half_up(value, expected):
    assert aud_to_cents(value) == expected


@pytest.mark.parametrize('value', [True, False, 0.35, '-1', 'NaN', 'Infinity', 'invalid'])
def test_money_conversion_rejects_bool_float_negative_and_nonfinite(value):
    with pytest.raises((ValueError, ArithmeticError)):
        aud_to_cents(value)


def test_price_mapping_supports_shared_cost_line_rounding(dataset):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    reference = snapshot.get_cost_reference('cost-02')
    assert reference.category == 'TRANSPORT'
    assert (reference.low_cents, reference.typical_cents, reference.high_cents) == (20, 35, 55)
    line = CostLine(
        category=reference.category, item_key=reference.cost_id, quantity='3.5',
        unit=reference.unit, unit_price_cents=reference.typical_cents,
        subtotal_cents=123, source_ref=reference.source_ref,
    )
    assert line.subtotal_cents == 123
    assert snapshot.get_cost_reference('cost-06').category == 'ADDITIONAL_GEAR'


def test_unknown_is_not_zero_and_explicit_zero_is_kept(dataset):
    change_csv(dataset, 'synthetic_campsites.csv', lambda rows: rows[0].update(nightly_fee_aud='unknown', toilets='unknown'))
    change_csv(dataset, 'synthetic_cost_reference.csv', lambda rows: rows[0].update(typical_aud='unknown'))
    snapshot = SyntheticDatasetAdapter(dataset).load()
    assert snapshot.get_campsite('demo-pine-camp').nightly_fee_cents is None
    assert snapshot.get_campsite('demo-pine-camp').toilets is None
    assert snapshot.get_cost_reference('cost-01').typical_cents is None
    assert snapshot.get_cost_reference('cost-15').low_cents == 0


def test_profiles_do_not_invent_gear_children_or_transport_inputs(dataset):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    profile = snapshot.get_profile('profile-a').snapshot
    equipment = {item.item_key: item for item in profile.equipment}
    assert equipment['tent'].quantity == 1
    assert equipment['tent'].capacity_persons == 2
    assert equipment['sleeping_bag'].quantity == 2
    assert equipment['torch'].quantity is None
    assert equipment['first_aid_kit'].quantity is None
    assert all(item.confirmed is False for item in profile.equipment)
    assert profile.transport.vehicle_count is None
    assert profile.transport.estimated_km is None
    family = snapshot.get_profile('profile-d')
    assert family.snapshot.children_count is None
    assert next(item for item in family.snapshot.equipment if item.item_key == 'tent').capacity_persons is None
    assert any('Children count' in note for note in family.uncertainties)


def test_unknown_equipment_keeps_label_and_does_not_match_known_rules():
    item = normalize_equipment('Mystery camping gadget')
    assert item.item_key == 'unmapped_mystery_camping_gadget'
    assert item.label == 'Mystery camping gadget'
    assert item.quantity is None and item.confirmed is False


def test_request_input_uses_original_text_not_metadata_or_confirmation(dataset):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    request = snapshot.request_input('request-01', DEMO)
    assert request.raw_text == read_json(dataset, 'synthetic_requests.json')[0]['natural_language_request']
    assert request.profile_snapshot.profile_id == 'profile-a'
    assert request.explicit_fields.duration_nights is None
    assert request.explicit_fields.duration_days is None
    assert request.explicit_fields.budget_cents is None
    assert snapshot.request_input('request-03', DEMO).explicit_fields.duration_days is None
    assert 'AUD -50' in snapshot.request_input('request-05', DEMO).raw_text
    encoded = request.model_dump_json()
    assert 'expected_request_status' not in encoded and 'missing_fields' not in encoded
    assert 'CONFIRMED' not in encoded


def test_request_metadata_and_oracle_poisoning_cannot_change_runtime_input(dataset):
    before = SyntheticDatasetAdapter(dataset).load().request_input('request-01', DEMO)
    rows = read_json(dataset, 'synthetic_requests.json')
    rows[0].update(
        expected_request_status='POISON', missing_fields=['POISON'], notes='POISON',
        destination='POISON', duration_days=99, budget_aud=-999, preferences=['POISON'],
        expected_nested={'instruction': 'POISON'},
    )
    write_json(dataset, 'synthetic_requests.json', rows)
    assert SyntheticDatasetAdapter(dataset).load().request_input('request-01', DEMO) == before


def test_safety_oracle_and_precomputed_blockers_are_not_consumed(dataset):
    before = SyntheticDatasetAdapter(dataset).load().get_safety('safety-01')
    rows = read_json(dataset, 'synthetic_safety_scenarios.json')
    rows[0].update(
        severity='POISON', confidence='POISON', expected_outcome='POISON',
        expected_actions=['POISON'], mandatory_blockers=['POISON'], title='POISON', notes='POISON',
    )
    write_json(dataset, 'synthetic_safety_scenarios.json', rows)
    after = SyntheticDatasetAdapter(dataset).load().get_safety('safety-01')
    assert after == before
    assert 'POISON' not in after.model_dump_json()


def test_safety_does_not_invent_coverage_or_relabel_evidence(dataset):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    record = snapshot.get_safety('safety-01', campsite_id='demo-pine-camp')
    assert record.scenario_date == date(2026, 10, 20)
    assert record.scenario_context.valid_from is None and record.scenario_context.valid_to is None
    assert {item.kind for item in record.scenario_context.evidence} == {'WEATHER', 'FIRE', 'ROAD', 'RESTRICTION'}
    for evidence in record.scenario_context.evidence:
        assert evidence.valid_from is None and evidence.valid_to is None
        assert evidence.source_refs[0].record_id == 'demo-pine-camp'
    missing = snapshot.get_safety('safety-02').scenario_context.evidence[0]
    assert missing.status == DataQuality.MISSING and missing.source_date is None
    assert snapshot.get_safety('safety-03').scenario_context.evidence[0].status == DataQuality.STALE
    assert snapshot.get_safety('safety-08').scenario_context.evidence[0].status == DataQuality.CONFLICTING
    road = next(item for item in snapshot.get_safety('safety-06').scenario_context.evidence if item.kind == 'ROAD')
    assert road.road_state == RoadState.CLOSED
    assert 'synthetic campsite closure' in snapshot.get_safety('safety-07').campsite_restrictions


def test_restricted_road_is_preserved_and_never_treated_as_open(dataset):
    record = SyntheticDatasetAdapter(dataset).load().get_safety('safety-09')
    road = next(item for item in record.scenario_context.evidence if item.kind == 'ROAD')
    assert record.raw_road_status == 'RESTRICTED'
    assert road.road_state == RoadState.UNKNOWN
    assert road.status == DataQuality.MISSING
    assert any('RESTRICTED' in note for note in record.uncertainties)


def test_available_evidence_with_unknown_date_is_not_complete(dataset):
    rows = read_json(dataset, 'synthetic_safety_scenarios.json')
    rows[0]['weather']['source_date'] = 'unknown'
    write_json(dataset, 'synthetic_safety_scenarios.json', rows)
    record = SyntheticDatasetAdapter(dataset).load().get_safety('safety-01')
    assert record.scenario_context.evidence[0].status == DataQuality.MISSING


def test_safety_cannot_be_applied_to_another_campsite(dataset):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    with pytest.raises(ContractFailure) as failure:
        snapshot.get_safety('safety-01', campsite_id='demo-river-flat')
    assert failure.value.error.code == ErrorCode.ADAPTER_FAILURE


@pytest.mark.parametrize('method', ['get_campsite', 'get_gear_rule', 'get_cost_reference', 'get_profile', 'get_request', 'get_safety'])
def test_unknown_record_is_failure_not_empty_success(dataset, method):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    with pytest.raises(ContractFailure) as failure:
        getattr(snapshot, method)('does-not-exist')
    assert failure.value.error.code == ErrorCode.ADAPTER_FAILURE


@pytest.mark.parametrize('filename', BUSINESS_FILES)
def test_missing_business_file_is_failure(dataset, filename):
    (dataset / 'data' / filename).unlink()
    assert load_failure(dataset).context['dataset_file'] == filename


@pytest.mark.parametrize('filename', BUSINESS_FILES)
def test_empty_record_collection_is_failure(dataset, filename):
    path = dataset / 'data' / filename
    if filename.endswith('.csv'):
        path.write_text(path.read_text(encoding='utf-8').splitlines()[0] + '\n', encoding='utf-8')
    else:
        path.write_text('[]', encoding='utf-8')
    load_failure(dataset)


@pytest.mark.parametrize('filename', BUSINESS_FILES)
def test_duplicate_record_id_is_failure(dataset, filename):
    if filename.endswith('.csv'):
        change_csv(dataset, filename, lambda rows: rows.append(rows[0].copy()))
    else:
        rows = read_json(dataset, filename)
        rows.append(rows[0].copy())
        write_json(dataset, filename, rows)
    load_failure(dataset)


@pytest.mark.parametrize('filename,field,value', [
    ('synthetic_campsites.csv', 'demo_only', 'false'),
    ('synthetic_gear_rules.csv', 'source_type', 'REAL'),
    ('synthetic_cost_reference.csv', 'source_name', 'CampMate Synthetic Demo Dataset v2'),
    ('synthetic_profiles.json', 'demo_only', 'true'),
    ('synthetic_requests.json', 'source_date', '2026-10-08'),
    ('synthetic_safety_scenarios.json', 'source_name', 'Real provider'),
])
def test_source_identity_is_validated_in_every_business_file(dataset, filename, field, value):
    if filename.endswith('.csv'):
        change_csv(dataset, filename, lambda rows: rows[0].update({field: value}))
    else:
        rows = read_json(dataset, filename)
        rows[0][field] = value
        write_json(dataset, filename, rows)
    load_failure(dataset)


@pytest.mark.parametrize('filename,field,value', [
    ('synthetic_campsites.csv', 'vehicle_access', 'maybe'),
    ('synthetic_campsites.csv', 'latitude', 'NaN'),
    ('synthetic_campsites.csv', 'latitude', '91'),
    ('synthetic_campsites.csv', 'max_group_size', '0'),
    ('synthetic_campsites.csv', 'fee_unit', 'per_person'),
    ('synthetic_cost_reference.csv', 'typical_aud', '-1'),
    ('synthetic_cost_reference.csv', 'low_aud', '99'),
    ('synthetic_cost_reference.csv', 'category', 'UNKNOWN'),
    ('synthetic_cost_reference.csv', 'unit', 'per_litre'),
    ('synthetic_gear_rules.csv', 'essential', 'unknown'),
    ('synthetic_gear_rules.csv', 'severity_if_missing', 'CRITICAL'),
])
def test_invalid_csv_fields_are_rejected(dataset, filename, field, value):
    change_csv(dataset, filename, lambda rows: rows[0].update({field: value}))
    load_failure(dataset)


@pytest.mark.parametrize('filename,field,value', [
    ('synthetic_profiles.json', 'group_size', True),
    ('synthetic_profiles.json', 'has_children', 'false'),
    ('synthetic_profiles.json', 'available_equipment', ['tent', 1]),
    ('synthetic_profiles.json', 'transport_type', 'FLY'),
    ('synthetic_requests.json', 'natural_language_request', '   '),
    ('synthetic_safety_scenarios.json', 'scenario_date', '2026-02-30'),
    ('synthetic_safety_scenarios.json', 'weather', 'AVAILABLE'),
])
def test_invalid_json_business_fields_are_rejected(dataset, filename, field, value):
    rows = read_json(dataset, filename)
    rows[0][field] = value
    write_json(dataset, filename, rows)
    load_failure(dataset)


@pytest.mark.parametrize('filename,field', [('synthetic_requests.json', 'profile_id'), ('synthetic_safety_scenarios.json', 'campsite_id')])
def test_unknown_cross_file_references_are_rejected(dataset, filename, field):
    rows = read_json(dataset, filename)
    rows[0][field] = 'missing-record'
    write_json(dataset, filename, rows)
    load_failure(dataset)


@pytest.mark.parametrize('payload', ['{}', '[1]', '[{"profile_id":"a","profile_id":"b"}]', '[{"group_size":NaN}]', 'not json'])
def test_malformed_json_is_rejected(dataset, payload):
    (dataset / 'data/synthetic_profiles.json').write_text(payload, encoding='utf-8')
    load_failure(dataset)


@pytest.mark.parametrize('payload', ['name,name\na,b\n', 'name\na,b\n', 'name,region\na\n'])
def test_malformed_csv_is_rejected(dataset, payload):
    (dataset / 'data/synthetic_campsites.csv').write_text(payload, encoding='utf-8')
    load_failure(dataset)


@pytest.mark.parametrize('filename', BUSINESS_FILES)
def test_utf8_bom_is_supported(dataset, filename):
    path = dataset / 'data' / filename
    path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
    assert SyntheticDatasetAdapter(dataset).load().context.dataset_version == 'v1'


@pytest.mark.parametrize('changes', [
    {'dataset_version': 'v2'}, {'file_digests': {}}, {'fixture_digests': {'fixture': '0' * 64}},
    {'selection_config': {'scenario_id': 'other'}}, {'rules_version': 'changed'},
])
def test_unregistered_or_changed_context_cannot_be_reused(dataset, changes):
    adapter = SyntheticDatasetAdapter(dataset)
    context = adapter.load().context.model_copy(update=changes)
    with pytest.raises(ContractFailure) as failure:
        adapter.load(expected_context=context)
    assert failure.value.error.code == ErrorCode.STALE_CONTEXT


def test_source_changes_invalidate_context_but_old_snapshot_stays_stable(dataset):
    adapter = SyntheticDatasetAdapter(dataset)
    saved = adapter.load()
    change_csv(dataset, 'synthetic_campsites.csv', lambda rows: rows[0].update(nightly_fee_aud='36'))
    with pytest.raises(ContractFailure) as failure:
        adapter.load(expected_context=saved.context)
    assert failure.value.error.code == ErrorCode.STALE_CONTEXT
    assert saved.get_campsite('demo-pine-camp').nightly_fee_cents == 3500
    assert adapter.load().get_campsite('demo-pine-camp').nightly_fee_cents == 3600


def test_public_models_do_not_mutate_the_loaded_snapshot(dataset):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    snapshot.context.file_digests.clear()
    snapshot.get_profile('profile-a').snapshot.equipment.clear()
    snapshot.campsites[0].facilities.append('POISON')
    snapshot.get_safety('safety-01').scenario_context.evidence.clear()
    assert len(snapshot.context.file_digests) == 6
    assert snapshot.get_profile('profile-a').snapshot.equipment
    assert 'POISON' not in snapshot.campsites[0].facilities
    assert len(snapshot.get_safety('safety-01').scenario_context.evidence) == 4


def test_demo_dataset_version_must_match_source(dataset):
    snapshot = SyntheticDatasetAdapter(dataset).load()
    with pytest.raises(ContractFailure) as failure:
        snapshot.request_input('request-01', DEMO.model_copy(update={'dataset_version': 'v2'}))
    assert failure.value.error.code == ErrorCode.STALE_CONTEXT


def test_oracle_docs_and_package_scripts_are_never_opened(dataset, monkeypatch):
    original = Path.read_bytes
    accessed = []
    def guarded_read(path):
        accessed.append(path)
        assert path.parent == dataset / 'data'
        assert path.name in BUSINESS_FILES
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    SyntheticDatasetAdapter(dataset).load()
    assert len(accessed) == 6


def test_symlink_cannot_escape_dataset_root(dataset, tmp_path):
    path = dataset / 'data/synthetic_campsites.csv'
    outside = tmp_path / 'outside.csv'
    shutil.copyfile(path, outside)
    path.unlink()
    path.symlink_to(outside)
    load_failure(dataset)


def test_symlink_cannot_redirect_to_oracle_inside_dataset(dataset):
    path = dataset / 'data/synthetic_campsites.csv'
    oracle = dataset / 'tests/oracle.csv'
    oracle.parent.mkdir()
    shutil.copyfile(path, oracle)
    path.unlink()
    path.symlink_to(oracle)
    # Even structurally valid source-looking content in tests must not be opened.
    load_failure(dataset)


def test_missing_dataset_directory_is_contract_failure(tmp_path):
    load_failure(tmp_path / 'does-not-exist')
