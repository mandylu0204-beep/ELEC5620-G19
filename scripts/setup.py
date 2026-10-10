"""Install locked dependencies from a checkout or extracted source package."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info < (3, 11):
        print('Python 3.11+ is required; Python 3.12 is the tested version.', file=sys.stderr)
        return 1
    node = shutil.which('node')
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not node or not npm:
        print('Install Node.js 22.12+ (including npm), then restart your terminal.', file=sys.stderr)
        return 1
    version = subprocess.check_output([node, '--version'], text=True).strip()
    parts = tuple(int(part) for part in version.lstrip('v').split('.'))
    if parts < (22, 12, 0):
        print('Node.js 22.12+ is required.', file=sys.stderr)
        return 1
    python = ROOT / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
    for command, folder in (
        ([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'requirements.lock'], ROOT / 'backend'),
        ([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-deps', '-e', '.'], ROOT / 'backend'),
        ([npm, 'ci'], ROOT / 'frontend'),
    ):
        subprocess.run(command, cwd=folder, check=True)
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
    print('Setup complete. Run .venv/Scripts/python.exe scripts/dev.py on Windows, or .venv/bin/python scripts/dev.py on Linux/macOS.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print(f'Setup failed: {error}. Correct the cause and run setup again.', file=sys.stderr)
        raise SystemExit(1)
