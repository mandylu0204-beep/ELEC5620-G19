"""Exercise the actual v2 authoring/validation commands, without Agent or DB input."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / 'data/synthetic_demo_v2'


@pytest.fixture
def release(tmp_path):
    target = tmp_path / 'release'
    shutil.copytree(PACKAGE, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return target


def run(root, script, *args):
    # Explicit file encoding must work without Python's UTF-8 default mode.
    return subprocess.run([sys.executable, '-B', f'scripts/{script}', *args], cwd=root,
        env={**os.environ, 'PYTHONUTF8': '0', 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, encoding='utf-8', timeout=20)


def validate(root):
    result = run(root, 'validate_dataset.py')
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout.splitlines()[0])
    assert summary['passed'] == 68 and summary['failed'] == 0
    assert summary['acceptance_specs'] == 58 and not summary['application_tests_executed']


def test_git_delivered_package_validates_without_extra_environment(release):
    before = (release / 'manifest.json').read_bytes()
    validate(release)
    assert (release / 'manifest.json').read_bytes() == before


def test_runtime_caches_and_unregistered_local_outputs_do_not_enter_seal(release):
    cache = release / 'scripts/__pycache__'
    cache.mkdir()
    (cache / 'runtime_inputs.cpython-999.pyc').write_bytes(b'Local interpreter artifact')
    (release / 'tests/local-run-results.json').write_text('{}', encoding='utf-8')
    before = (release / 'manifest.json').read_bytes()
    result = run(release, 'release_files.py')
    assert result.returncode == 0, result.stderr
    assert (release / 'manifest.json').read_bytes() == before
    validate(release)


def test_explicit_seal_repairs_crlf_and_removes_stale_cache_registration(release):
    path = release / 'tests/synthetic_agent_test_cases.csv'
    original = path.read_bytes()
    path.write_bytes(original.replace(b'\n', b'\r\n'))
    manifest = json.loads((release / 'manifest.json').read_text(encoding='utf-8'))
    manifest['files_sha256']['scripts/__pycache__/missing.pyc'] = '0' * 64
    (release / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert run(release, 'validate_dataset.py').returncode == 1
    result = run(release, 'release_files.py')
    assert result.returncode == 0, result.stderr
    assert path.read_bytes() == original
    validate(release)


def test_report_regeneration_preserves_the_release_and_is_repeatable(release):
    for _ in range(2):
        result = run(release, 'validate_dataset.py', '--write-report')
        assert result.returncode == 0, result.stdout + result.stderr
        validate(release)
    manifest = json.loads((release / 'manifest.json').read_text(encoding='utf-8'))
    for name in ('FINAL_VALIDATION_REPORT.md', 'tests/static_validation_results.json'):
        assert hashlib.sha256((release / name).read_bytes()).hexdigest() == manifest['files_sha256'][name]


def test_failed_validation_does_not_auto_accept_changed_release_input(release):
    manifest_before = (release / 'manifest.json').read_bytes()
    with (release / 'README.md').open('a', encoding='utf-8', newline='\n') as stream:
        stream.write('\nUnsealed change\n')
    result = run(release, 'validate_dataset.py', '--write-report')
    assert result.returncode == 1
    assert 'Digest mismatch: README.md' in result.stdout
    assert (release / 'manifest.json').read_bytes() == manifest_before


def test_fixture_repair_is_repeatable_without_crlf_or_cache_sealing(release):
    expected_business = {path.name: path.read_bytes() for path in (release / 'data').iterdir()}
    for _ in range(2):
        result = run(release, 'repair_review_findings.py')
        assert result.returncode == 0, result.stdout + result.stderr
        validate(release)
    assert {path.name: path.read_bytes() for path in (release / 'data').iterdir()} == expected_business
    assert b'\r' not in (release / 'tests/synthetic_agent_test_cases.csv').read_bytes()


def test_git_subtree_export_with_windows_autocrlf_preserves_release(release, tmp_path):
    git = shutil.which('git')
    if git is None:
        pytest.skip('Git is required to exercise Git subtree export; package validation itself needs only Python.')
    repository = tmp_path / 'git-export'
    package = repository / 'data/synthetic_demo_v2'
    shutil.copytree(release, package)

    def command(*args):
        result = subprocess.run([git, '-C', str(repository), *args], capture_output=True,
                                text=True, encoding='utf-8', timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()

    command('init', '-q')
    command('config', 'core.autocrlf', 'true')
    command('add', '--', 'data/synthetic_demo_v2')
    tree = command('write-tree')
    archive = tmp_path / 'subtree.zip'
    command('archive', '--format=zip', f'--output={archive}', f'{tree}:data/synthetic_demo_v2')
    extracted = tmp_path / 'extracted'
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    validate(extracted)
    for source in release.rglob('*'):
        if source.is_file():
            assert (extracted / source.relative_to(release)).read_bytes() == source.read_bytes()
