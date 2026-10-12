"""Independent campus-model transport fixtures; no live service or real key."""
import json
from datetime import date, timedelta
from pathlib import Path

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.contracts.dto import ConfirmedRequirements, DemoContext, ItineraryInput, ProfileSnapshot, RecommendCampsitesInput
from app.llm.config import CampusModelSettings
from app.llm.tools import recommend_for_model

ROOT = Path(__file__).resolve().parents[2]


def model_settings(**changes):
    values = dict(api_key='unit-only-school-secret', base_url='http://10.167.60.148:8000/v1',
        model='campus-qwen', timeout_seconds=5, max_completion_tokens=2048,
        max_attempts=1, max_turns=4)
    values.update(changes)
    return CampusModelSettings(_env_file=None, **values)


def model_input():
    data = json.loads((ROOT / 'docs/demo/v2_inputs.json').read_text(encoding='utf-8'))
    case = data['cases'][0]
    dataset = SyntheticDatasetV2Adapter(ROOT / 'data/synthetic_demo_v2').load()
    fields = dict(case['request']['explicit_fields'])
    fields['end_date'] = (date.fromisoformat(fields['start_date']) + timedelta(days=fields['duration_nights'])).isoformat()
    fields['duration_days'] = fields['duration_nights'] + 1
    requirements = ConfirmedRequirements.model_validate(fields)
    profile = ProfileSnapshot.model_validate(data['profile'])
    demo = DemoContext(mode='agent', demo_today='2026-11-05', dataset_version='2.0.0')
    recommendations = recommend_for_model(dataset, RecommendCampsitesInput(
        confirmed_requirements=requirements, profile_snapshot=profile, demo_context=demo))
    return dataset, ItineraryInput(confirmed_requirements=requirements,
        profile_snapshot=profile, recommendations=recommendations, demo_context=demo)


def tool_action():
    return {'action': 'tool', 'name': 'search_campsites', 'arguments': {}}


def final_action(**changes):
    proposal = {'campsite_id': 'demo-wattle-rest', 'nights': ['2026-11-06', '2026-11-07'],
        'decision_summary': 'Wattle Rest matches the confirmed quiet preference; other checks remain pending.'}
    proposal.update(changes)
    return {'action': 'final', 'proposal': proposal}


def completion(content, **changes):
    result = {'model': 'campus-qwen', 'choices': [{'message': {
        'role': 'assistant', 'content': content if isinstance(content, str) else json.dumps(content)},
        'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 60, 'total_tokens': 160}}
    result.update(changes)
    return result
