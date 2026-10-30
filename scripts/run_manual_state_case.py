"""Start a named, isolated rules-only manual UI scenario. Never edits local env files."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / 'docs' / 'manual_state_flow_inputs.json'


def main():
    cases = {item['id']: item for item in json.loads(INPUTS.read_text(encoding='utf-8'))['cases']}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', nargs='?', choices=sorted(cases), default='normal')
    parser.add_argument('--show-input', action='store_true', help='Print the test profile/request/settings and exit.')
    parser.add_argument('--backend-port', type=int, default=8870)
    parser.add_argument('--frontend-port', type=int, default=5370)
    args = parser.parse_args()
    case = cases[args.case]
    if args.show_input:
        print(json.dumps(case, ensure_ascii=False, indent=2))
        return 0
    if any(case['settings'].get(key) != value for key, value in {
        'execution_mode': 'deterministic_demo', 'logistics_execution': 'rules', 'safety_execution': 'rules'
    }.items()):
        parser.error('This launcher accepts only rules-only manual scenarios.')
    env = os.environ.copy()
    for key, value in case['settings'].items():
        env['CAMPMATE_' + key.upper()] = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict, bool)) else str(value)
    env.update(CAMPMATE_SEED_DEMO_ACCOUNTS='true', CAMPMATE_SECURE_COOKIES='false')
    print(f"Manual case: {args.case} | rules only | database: {case['settings']['database_path']}", flush=True)
    print('Profile and request: ' + str(INPUTS) + ' | existing test records are preserved.', flush=True)
    try:
        return subprocess.call([sys.executable, str(ROOT / 'scripts' / 'dev.py'),
            '--backend-port', str(args.backend_port), '--frontend-port', str(args.frontend_port)], cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
