"""Portable checks, including Windows terminals which block PowerShell scripts."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if npm is None:
        print('npm is required for frontend checks.', file=sys.stderr)
        return 1
    steps = [
        ([sys.executable, '-m', 'pytest', '--basetemp', str(ROOT / 'var/pytest-temp')], ROOT / 'backend'),
        ([sys.executable, '-m', 'app.export_contracts', '--check'], ROOT / 'backend'),
        ([npm, 'test'], ROOT / 'frontend'),
        ([npm, 'run', 'build'], ROOT / 'frontend'),
    ]
    for command, folder in steps:
        result = subprocess.run(command, cwd=folder)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
