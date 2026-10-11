"""Seal the registered UTF-8/LF release files, never local runtime artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILES = (
    '.gitattributes',
    'CHANGELOG.md', 'FINAL_VALIDATION_REPORT.md', 'README.md',
    'data/runtime_requests.json', 'data/runtime_safety_evidence.json',
    'data/synthetic_campsites.csv', 'data/synthetic_cost_reference.csv',
    'data/synthetic_gear_rules.csv', 'data/synthetic_profiles.json',
    'data/synthetic_requests.json', 'data/synthetic_safety_scenarios.json',
    'docs/integration_contract.md', 'docs/original_validation_report_v1.md',
    'docs/synthetic_data_dictionary.md', 'docs/synthetic_ui_content.md',
    'schemas/runtime_requests.json', 'schemas/runtime_safety_evidence.json',
    'schemas/synthetic_oracles.json', 'schemas/synthetic_profiles.json',
    'schemas/synthetic_requests.json', 'schemas/synthetic_safety_scenarios.json',
    'schemas/synthetic_test_fixtures.json',
    'scripts/repair_review_findings.py', 'scripts/runtime_inputs.py',
    'scripts/validate_dataset.py', 'scripts/release_files.py',
    'tests/static_validation_results.json', 'tests/synthetic_agent_test_cases.csv',
    'tests/synthetic_oracles.json', 'tests/synthetic_test_fixtures.json',
)


def seal_release(root=ROOT):
    """Explicit authoring operation: normalize distributed bytes, then hash them."""
    root = Path(root)
    payloads = {}
    for name in RELEASE_FILES:
        path = root / name
        if path.is_symlink():
            raise ValueError(f'Release source must be a regular file: {name}')
        payload = path.read_bytes()
        payload.decode('utf-8')
        payloads[name] = payload.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    # Read all required sources before writing anything; missing files are errors.
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    for name, payload in payloads.items():
        path = root / name
        if path.read_bytes() != payload:
            path.write_bytes(payload)
    manifest['release_format'] = 'UTF-8/LF; SHA-256 of distributed bytes; registered files only'
    manifest['files_sha256'] = {
        name: hashlib.sha256(payloads[name]).hexdigest() for name in sorted(payloads)
    }
    (root / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8', newline='\n',
    )
    return manifest


def verify_release(root=ROOT):
    """Read-only verification. Never reseal changed input to make a check pass."""
    root = Path(root)
    sealed = json.loads((root / 'manifest.json').read_text(encoding='utf-8')).get('files_sha256')
    if not isinstance(sealed, dict) or not sealed:
        return ['Missing or invalid release digest table']
    problems = [f'Unregistered manifest entry: {name}' for name in sorted(set(sealed) - set(RELEASE_FILES))]
    problems += [f'Missing manifest entry: {name}' for name in sorted(set(RELEASE_FILES) - set(sealed))]
    for name in RELEASE_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            problems.append(f'Missing or non-regular release file: {name}')
            continue
        payload = path.read_bytes()
        try:
            payload.decode('utf-8')
        except UnicodeDecodeError:
            problems.append(f'Non-UTF-8 release file: {name}')
        if b'\r' in payload:
            problems.append(f'Non-LF release file: {name}')
        if hashlib.sha256(payload).hexdigest() != sealed.get(name):
            problems.append(f'Digest mismatch: {name}')
    return problems


if __name__ == '__main__':
    manifest = seal_release()
    print(json.dumps({'sealed_files': len(manifest['files_sha256']),
                      'release_format': manifest['release_format']}))
