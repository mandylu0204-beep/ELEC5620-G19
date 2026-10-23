"""Run Sydney & Surrounds using local rules by default and an independent DB.

Does not edit environment files, install dependencies or
contact external services in default rules mode.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-port', type=int, default=8000)
    parser.add_argument('--frontend-port', type=int, default=5173)
    parser.add_argument('--mode', choices=('rules', 'agent'), default='rules',
                        help='agent explicitly opts into the campus planning model')
    parser.add_argument('--logistics', choices=('rules', 'model'), default='rules')
    parser.add_argument('--safety', choices=('rules', 'model'), default='rules',
                        help='model explicitly opts into the 2.2/v3 safety adviser')
    args = parser.parse_args()
    if (args.logistics == 'model' or args.safety == 'model') and args.mode != 'agent':
        parser.error('Model assessment roles require --mode agent')
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('CAMPMATE_')}
    env.update(CAMPMATE_DATASET_PATH=str(ROOT / 'data/sydney_surrounds_v2_2'),
               CAMPMATE_EXECUTION_MODE='agent' if args.mode == 'agent' else 'deterministic_demo',
               CAMPMATE_PLANNING_ENABLED='true', CAMPMATE_LOGISTICS_EXECUTION=args.logistics,
               CAMPMATE_SAFETY_EXECUTION=args.safety, CAMPMATE_CLOCK_MODE='current',
               CAMPMATE_SYNTHETIC_EVIDENCE_MODE='auto',
               CAMPMATE_DATASET_SCENARIO_FILES='[]', CAMPMATE_DATASET_SELECTION='{}',
               CAMPMATE_WORKFLOW_SAFETY_CASE_IDS='[]',
               CAMPMATE_DATABASE_PATH=str(ROOT / 'var/sydney/campmate.sqlite3'),
               CAMPMATE_SNAPSHOT_CACHE_PATH=str(ROOT / 'var/sydney/daily-snapshots'))
    return subprocess.call([sys.executable, str(ROOT / 'scripts/dev.py'),
                            '--backend-port', str(args.backend_port),
                            '--frontend-port', str(args.frontend_port)], cwd=ROOT, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
