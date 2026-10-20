"""Explicit standalone proxy probe/planning check, not an HTTP workflow."""
import argparse
import asyncio
from datetime import date, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from ..adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from ..application.datasets import inspect_dataset
from ..config import APP_ROOT
from ..contracts.dto import DemoContext, ItineraryInput, ProfileSnapshot, ConfirmedRequirements, RecommendCampsitesInput
from ..contracts.errors import ContractFailure
from .client import CampusModelClient
from .config import CampusModelSettings, LOCAL_ENV
from .coordinator import PlanningCoordinator
from .tools import recommend_for_model


async def execute(args):
    settings = CampusModelSettings(_env_file=args.env_file)
    if args.probe:
        client = CampusModelClient(settings.model_copy(update={'max_completion_tokens': 128}))
        result = await client.complete([{'role': 'user', 'content': 'Explain Ohm’s law in one short sentence.'}])
        return {'status': 'PROXY_RESPONSE_RECEIVED', 'requested_model': result.model,
            'served_model': result.served_model, 'attempts': result.attempts,
            'usage': result.usage, 'reply_received': bool(result.content.strip())}
    source = json.loads((APP_ROOT / 'docs/demo/v2_inputs.json').read_text(encoding='utf-8'))
    case = next(value for value in source['cases'] if value['id'] == args.plan)
    dataset_settings = SimpleNamespace(dataset_path=APP_ROOT / case['settings']['dataset_path'],
        dataset_scenario_files=[], dataset_selection=case['settings']['dataset_selection'])
    descriptor = inspect_dataset(dataset_settings)
    dataset = SyntheticDatasetV2Adapter(dataset_settings.dataset_path).load(expected_context=descriptor.context)
    demo = DemoContext(mode='agent', demo_today=case['settings']['demo_today'],
        dataset_version=dataset.context.dataset_version)
    fields = dict(case['request']['explicit_fields'])
    fields['end_date'] = (date.fromisoformat(fields['start_date']) + timedelta(days=fields['duration_nights'])).isoformat()
    fields['duration_days'] = fields['duration_nights'] + 1
    requirements = ConfirmedRequirements.model_validate(fields)
    profile = ProfileSnapshot.model_validate(source['profile'])
    recommendations = recommend_for_model(dataset, RecommendCampsitesInput(
        confirmed_requirements=requirements, profile_snapshot=profile, demo_context=demo))
    outcome = await PlanningCoordinator(dataset, CampusModelClient(settings)).plan(ItineraryInput(
        confirmed_requirements=requirements, profile_snapshot=profile,
        recommendations=recommendations, demo_context=demo))
    return {'status': 'PLANNING_COMPONENT_VALIDATED', 'execution_mode': 'agent',
        'application_registered': False, 'assessments_run': False, 'finalisation_performed': False,
        'itinerary': outcome.itinerary.model_dump(mode='json'), 'trace': outcome.trace.model_dump(mode='json')}


def _print_json(value, *, indent=None):
    # Escapes preserve decoded Unicode while remaining safe on restrictive
    # Windows stdout/pipes. Do not change the caller's stream encoding.
    print(json.dumps(value, ensure_ascii=True, indent=indent))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--probe', action='store_true')
    group.add_argument('--plan', choices=['normal', 'budget_revision', 'missing_evidence', 'road_closure'])
    parser.add_argument('--env-file', type=Path, default=LOCAL_ENV)
    args = parser.parse_args()
    try:
        result = asyncio.run(execute(args))
    except ContractFailure as exc:
        _print_json({'status': 'FAILED', 'error': exc.error.model_dump(mode='json')})
        return 1
    except (ValueError, OSError, KeyError, ValidationError):
        # Do not echo local config values or malformed response/input payloads.
        _print_json({'status': 'FAILED', 'message': '本地模型配置或演示输入无效。'})
        return 1
    _print_json(result, indent=2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
