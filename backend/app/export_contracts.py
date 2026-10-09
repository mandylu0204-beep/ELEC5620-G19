"""Export input/serialization schemas for B and frontend consumers."""
import argparse
import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

from .config import APP_ROOT
from .contracts import dto
from .contracts.base import ContractModel, SCHEMA_VERSION
from .contracts.errors import ErrorEnvelope


def schema_bundle() -> str:
    models = [model for model in vars(dto).values() if isinstance(model, type) and issubclass(model, ContractModel) and model.__module__ == dto.__name__]
    models.append(ErrorEnvelope)
    _, validation = models_json_schema([(model, 'validation') for model in models])
    _, serialization = models_json_schema([(model, 'serialization') for model in models])
    return json.dumps({'schema_version': SCHEMA_VERSION, 'validation': validation, 'serialization': serialization}, indent=2, ensure_ascii=False, sort_keys=True) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = APP_ROOT / 'docs/contracts.schema.json'
    expected = schema_bundle()
    if args.check:
        if not path.is_file() or path.read_text(encoding='utf-8') != expected:
            print('Schema differs. Run: python -m app.export_contracts')
            return 1
        print('Shared JSON schemas are up to date.')
    else:
        path.parent.mkdir(exist_ok=True)
        path.write_text(expected, encoding='utf-8')
        print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
