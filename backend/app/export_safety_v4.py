"""Generate/check only the unregistered compact candidate schema."""
import argparse
import json
from .config import APP_ROOT
from .llm.safety_v4 import safety_contract_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    path = APP_ROOT/'docs/contracts/safety_advisory_v4.schema.json'
    expected = json.dumps(safety_contract_document(),ensure_ascii=False,indent=2,sort_keys=True)+'\n'
    if args.check:
        if not path.is_file() or path.read_text(encoding='utf-8') != expected:
            print('Compact candidate schema differs.')
            return 1
        print('Compact candidate schema current; production unchanged.')
    else:
        path.write_text(expected,encoding='utf-8')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
