"""Select one checked-in v2 scenario without changing personal configuration."""
import argparse
import json
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    inputs = json.loads((ROOT / 'docs/demo/v2_inputs.json').read_text(encoding='utf-8'))
    cases = {value['id']: value for value in inputs['cases']}
    parser = argparse.ArgumentParser(description='Start one synthetic v2 scenario with its fixed clock.')
    parser.add_argument('--case', choices=cases, default='normal')
    parser.add_argument('--database', type=Path, help='Optional isolated database; existing records are preserved.')
    parser.add_argument('--backend-port', type=int, default=8000)
    parser.add_argument('--frontend-port', type=int, default=5173)
    parser.add_argument('--stop-file', type=Path)
    args = parser.parse_args()
    database = args.database or Path('var') / ('demo-' + args.case + '.sqlite3')
    database = database.resolve() if database.is_absolute() else (ROOT / database).resolve()
    if database == (ROOT / 'var/campmate.sqlite3').resolve():
        parser.error('Use an isolated demo database, not the personal application database.')
    env = os.environ.copy()
    for key, value in cases[args.case]['settings'].items():
        env['CAMPMATE_' + key.upper()] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, bool)) else str(value)
    env['CAMPMATE_DATABASE_PATH'] = str(database)
    env['CAMPMATE_SEED_DEMO_ACCOUNTS'] = 'true'
    env['CAMPMATE_SECURE_COOKIES'] = 'false'
    command = [sys.executable, str(ROOT / 'scripts/dev.py'), '--backend-port', str(args.backend_port),
        '--frontend-port', str(args.frontend_port)]
    if args.stop_file:
        command.extend(['--stop-file', str(args.stop_file.resolve())])
    print(f'Synthetic case: {args.case}; database: {database}; clock: {cases[args.case]["settings"]["demo_today"]}', flush=True)
    print('Personal .env is unchanged. Log in, load the demo profile, review and save it, then confirm your request.', flush=True)
    try:
        return subprocess.call(command, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
