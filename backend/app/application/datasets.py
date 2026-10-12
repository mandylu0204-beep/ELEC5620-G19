"""A-owned dataset identity and input digests; no business evaluation or oracle loading."""
import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path, PurePosixPath

from ..contracts.dto import DatasetContext, Provenance
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from ..dataset_paths import data_file_path, manifest_file_path

BUSINESS_FILES = (
    'synthetic_campsites.csv', 'synthetic_gear_rules.csv', 'synthetic_cost_reference.csv',
    'synthetic_profiles.json', 'synthetic_requests.json', 'synthetic_safety_scenarios.json',
)
RUNTIME_FILES = ('runtime_requests.json', 'runtime_safety_evidence.json')


@dataclass(frozen=True)
class DatasetDescriptor:
    context: DatasetContext
    provenance: Provenance
    regions: list[str]


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def records(name, payload):
    text = payload.decode('utf-8-sig')
    rows = list(csv.DictReader(io.StringIO(text))) if name.endswith('.csv') else json.loads(text)
    if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Expected nonempty record list')
    if any(None in row or any(value is None for value in row.values()) for row in rows) and name.endswith('.csv'):
        raise ValueError('Malformed CSV')
    return rows


def provenance_for(row, csv_record=False):
    return Provenance.model_validate({
        'source_type': row['source_type'], 'source_name': row['source_name'],
        'source_date': row['source_date'],
        'demo_only': row['demo_only'] == 'true' if csv_record else row['demo_only'],
    })


def contains_oracle(value):
    if isinstance(value, dict):
        return any(key.startswith('expected_') or key in {'missing_fields', 'invalid_fields', 'severity', 'confidence',
                   'setup', 'actions', 'assertions', 'test_id', 'execution_status', 'finalization_eligible'}
                   or contains_oracle(item) for key, item in value.items())
    return isinstance(value, list) and any(contains_oracle(item) for item in value)


def scenario_path(root, name):
    path = PurePosixPath(name)
    if (not isinstance(name, str) or '\\' in name or ':' in name or path.as_posix() != name
            or path.is_absolute() or '..' in path.parts or path.suffix != '.json'
            or len(path.parts) < 3 or path.parts[:2] != ('data', 'scenarios')):
        raise ValueError('Scenarios must be JSON under data/scenarios')
    return data_file_path(root, path.relative_to('data').as_posix(), scenarios=True)


def inspect_dataset(settings):
    """Read identity afresh; changes never hide behind a process-lifetime cache.

    Manifest checks only files consumed here. tests/docs/scripts are never loaded
    as business input, even if the package manifest lists them.
    """
    try:
        root = settings.dataset_path.resolve(strict=True)
        payloads = {f'data/{name}': data_file_path(root, name).read_bytes() for name in BUSINESS_FILES}
        rows = {name: records(name, payloads[f'data/{name}']) for name in BUSINESS_FILES}
        camps = rows['synthetic_campsites.csv']
        source = provenance_for(camps[0], True)
        if any(provenance_for(row, name.endswith('.csv')) != source for name, group in rows.items() for row in group):
            raise ValueError('Mixed dataset provenance')
        regions = sorted({row['region'].strip() for row in camps})
        if not regions or not all(regions):
            raise ValueError('Missing region')
        manifest_path = root / 'manifest.json'
        manifest_payload = manifest_file_path(root).read_bytes() if manifest_path.exists() or manifest_path.is_symlink() else None
        manifest = json.loads(manifest_payload.decode('utf-8-sig')) if manifest_payload is not None else None
        if manifest_payload is not None and not isinstance(manifest, dict):
            raise ValueError('Manifest must be an object')
        version = 'v1'
        if manifest is not None:
            version = manifest['dataset_version']
            if not isinstance(version, str) or not version.strip():
                raise ValueError('Missing dataset version')
            if provenance_for(manifest['provenance']) != source:
                raise ValueError('Manifest provenance differs')
        elif source.source_name != 'CampMate Synthetic Demo Dataset v1':
            raise ValueError('Versioned datasets need a manifest')
        source_v2 = source.source_name == 'CampMate Synthetic Demo Dataset v2'
        if not (version.startswith('2.') if source_v2 else version == 'v1' or version.startswith('1.')):
            raise ValueError('Version and source name differ')

        runtime_present = [(root / 'data' / name).exists() for name in RUNTIME_FILES]
        if (source_v2 or any(runtime_present)) and not all(runtime_present):
            raise ValueError('Incomplete runtime input pair')
        for name in RUNTIME_FILES if all(runtime_present) else ():
            payload = data_file_path(root, name).read_bytes()
            runtime_rows = records(name, payload)
            if contains_oracle(runtime_rows) or any(provenance_for(row) != source for row in runtime_rows):
                raise ValueError('Runtime input contains oracle or mixed provenance')
            payloads[f'data/{name}'] = payload

        scenarios = {}
        if contains_oracle(settings.dataset_selection):
            raise ValueError('Selection cannot contain test expectations')
        if len(settings.dataset_scenario_files) != len(set(settings.dataset_scenario_files)):
            raise ValueError('Duplicate scenario paths')
        for name in settings.dataset_scenario_files:
            payload = scenario_path(root, name).read_bytes()
            value = json.loads(payload.decode('utf-8-sig'))
            if not isinstance(value, (dict, list)) or contains_oracle(value):
                raise ValueError('Scenario input must be separate from test setup/oracle')
            scenarios[name] = payload

        sealed = manifest.get('files_sha256', {}) if manifest is not None else {}
        if manifest is not None and not isinstance(sealed, dict):
            raise ValueError('Invalid manifest digest table')
        # New development manifests can omit the table; a sealed release cannot
        # omit or disagree on any consumed file, including configured scenarios.
        if sealed and any(sealed.get(name) != digest(payload) for name, payload in (payloads | scenarios).items()):
            raise ValueError('Consumed file differs from sealed manifest')
        digests = {Path(name).name: digest(payload) for name, payload in payloads.items()}
        if manifest_payload is not None:
            digests['manifest.json'] = digest(manifest_payload)
        context = DatasetContext(
            dataset_version=version, file_digests=digests,
            fixture_digests={name: digest(payload) for name, payload in scenarios.items()},
            selection_config=dict(settings.dataset_selection), rules_version='a-request-normalization-v1',
        )
        return DatasetDescriptor(context, source, regions)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, csv.Error) as exc:
        raise ContractFailure(ContractError(
            code=ErrorCode.ADAPTER_FAILURE,
            message='演示数据包版本、来源或运行输入无法验证，请检查数据包与场景配置。',
        )) from exc
