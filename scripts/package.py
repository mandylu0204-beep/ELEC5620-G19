"""Archive committed source with a checksum manifest; never include local files."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'campmate_app/'
MANIFEST = PREFIX + 'PACKAGE_MANIFEST.json'
DENIED = {'.git', '.venv', '__pycache__', 'node_modules', 'dist', 'var', '.pytest_cache'}


def safe_path(name):
    path = PurePosixPath(name)
    if not name.startswith(PREFIX) or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or name.rstrip('/') != path.as_posix():
        raise ValueError(f'Unsafe package path: {name}')
    if any(part in DENIED for part in path.parts):
        raise ValueError(f'Runtime/private directory in source package: {name}')
    lowered = path.name.lower()
    if (any(part.startswith('.env') and part != '.env.example' for part in path.parts)
            or path.suffix.lower() in {'.db', '.sqlite3', '.sqlite', '.log', '.pyc', '.pyo'}
            or any(lowered.endswith(ext+suffix) for ext in ('.db','.sqlite3','.sqlite')
                   for suffix in ('-wal','-shm','-journal'))):
        raise ValueError(f'Runtime/private file in source package: {name}')


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP entries')
        for entry in archive.infolist():
            safe_path(entry.filename)
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError(f'Symlink in package: {entry.filename}')
        manifest = json.loads(archive.read(MANIFEST))
        expected = {PREFIX + name: digest for name, digest in manifest['files'].items()}
        actual = {name for name in names if not name.endswith('/') and name != MANIFEST}
        if actual != set(expected):
            raise ValueError('Manifest file list differs from ZIP payload')
        for name, digest in expected.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f'Checksum mismatch: {name}')
    return {'commit': manifest['commit'], 'files': len(expected), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def create(output):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT)
    if Path(git('rev-parse', '--show-toplevel').decode().strip()).resolve() != ROOT:
        raise ValueError('Run packaging from the project repository root')
    # Untracked local diagnostics are not a reason to publish or delete them.
    # git archive reads HEAD only. Tracked changes still block packaging so the
    # deliverable cannot silently omit work a developer has just reviewed.
    if git('status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('Commit tracked source changes first; archive uses committed HEAD only')
    commit = git('rev-parse', 'HEAD').decode().strip()
    output = output or ROOT / 'var/releases' / f'campmate-stage2-{commit[:12]}.zip'
    output = output.resolve()
    checksum_path = output.with_suffix(output.suffix + '.sha256')
    if output.exists() or checksum_path.exists():
        raise ValueError('Output already exists; choose a new --output path')
    payload = git('archive', '--format=zip', '--prefix='+PREFIX, commit)
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        files = {}
        for entry in source.infolist():
            safe_path(entry.filename)
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError(f'Symlink in source: {entry.filename}')
            if not entry.is_dir():
                files[entry.filename[len(PREFIX):]] = hashlib.sha256(source.read(entry)).hexdigest()
    committed_at = datetime.fromtimestamp(int(git('show', '-s', '--format=%ct', commit)), timezone.utc).isoformat()
    manifest = {'format_version': 1, 'commit': commit, 'committed_at': committed_at,
        'scope': 'CampMate Stage 2 source: web frontend, API, SQLite migrations, Sydney 2.2 data, '
                 'planning/logistics/safety roles, review and final snapshots. Acceptance status '
                 'is separate; see docs/canvas_submission.md.',
        'default_execution_mode': 'stub',
        'recommended_launcher': 'scripts/sydney.py',
        'archive_source': 'committed HEAD only; untracked and ignored files excluded',
        'files': dict(sorted(files.items()))}
    result = io.BytesIO(payload)
    with zipfile.ZipFile(result, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo(MANIFEST), json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as target:
        target.write(result.getvalue())
    report = verify(output)
    with checksum_path.open('x', encoding='utf-8') as target:
        target.write(report['sha256'] + '  ' + output.name + '\n')
    print(json.dumps({'package': str(output), **report}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify), ensure_ascii=False))
    else:
        create(args.output)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f'Package check failed: {error}', file=sys.stderr)
        raise SystemExit(1)
