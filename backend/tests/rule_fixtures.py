"""Independent B-02 unit inputs. These are NOT production/demo data or DB runs."""
import asyncio
from datetime import date, timedelta

from app.adapters import SyntheticDatasetAdapter
from app.agents.rule_agent import RuleAgent
from app.config import Settings
from app.contracts.dto import (
    ConfirmedRequirements, DemoContext, EquipmentItem, Evidence, ItineraryInput,
    LogisticsInput, ProfileSnapshot, RecommendCampsitesResult, ScenarioContext,
    StoredAssessment, StoredVersion, Transport, VersionContext,
)

DEMO = DemoContext(mode='deterministic_demo', demo_today='2026-10-08')
VERSION = VersionContext(plan_id='b02-unit-plan', plan_version_id='b02-unit-version', run_id='b02-unit-run', input_fingerprint='b' * 64)


def call(coroutine):
    return asyncio.run(coroutine)


def make_agent():
    return RuleAgent(SyntheticDatasetAdapter(Settings(_env_file=None).dataset_path).load())


def requirements(**changes):
    fields = dict(destination='CampMate Demo Region', start_date=date(2026, 10, 20), duration_nights=2, budget_cents=50000, preferences=['ready-to-eat meals'])
    fields.update(changes)
    fields.setdefault('end_date', fields['start_date'] + timedelta(days=fields['duration_nights']))
    fields.setdefault('duration_days', fields['duration_nights'] + 1)
    return ConfirmedRequirements(**fields)


def equipment(key, quantity, unit='item', *, capacity=None, confirmed=True):
    return EquipmentItem(item_key=key, label=f'Independent unit fixture: {key}', quantity=quantity, unit=unit, capacity_persons=capacity, confirmed=confirmed)


def full_profile(*, group=2, mode='CAR', water=None, kilometres='3.5', vehicles=1):
    # Counts are explicit test input, not values added to Git profiles by an Agent.
    items = [
        equipment('tent', 1, capacity=max(2, group)), equipment('groundsheet', 1),
        *[equipment(key, group) for key in ('sleeping_bag', 'sleeping_mat', 'rain_jacket', 'windproof_outer_layer', 'first_aid_kit', 'torch', 'charged_phone')],
        equipment('warm_layers', group, 'set'),
        equipment('drinking_water', water if water is not None else group * 3 * 2, 'litre'),
        equipment('meal_supplies', group * 3 * 3, 'portion'),
    ]
    if mode == 'CAR':
        items.append(equipment('vehicle', vehicles, 'vehicle', capacity=max(2, group)))
    else:
        items.extend([equipment('offline_map', 1), equipment('transport_itinerary', 1, 'plan')])
    return ProfileSnapshot(
        group_size=group, experience_level='INTERMEDIATE', has_children=False,
        equipment=items,
        transport=Transport(transport_type=mode, vehicle_count=vehicles if mode == 'CAR' else None, estimated_km=kilometres if mode == 'CAR' else None),
    )


def draft(agent, req=None, profile=None, campsite_id='demo-pine-camp'):
    req, profile = req or requirements(), profile or full_profile()
    candidates = RecommendCampsitesResult(execution_mode='deterministic_demo', search_outcome='MATCHES', candidates=[{'campsite_id': campsite_id, 'rank': 1, 'reasons': ['Explicit unit-test selection.']}])
    return call(agent.generate_or_revise_itinerary(ItineraryInput(confirmed_requirements=req, profile_snapshot=profile, recommendations=candidates, demo_context=DEMO)))


def logistics_input(agent, req=None, profile=None, campsite_id='demo-pine-camp'):
    req, profile = req or requirements(), profile or full_profile()
    return LogisticsInput(version_context=VERSION, saved_itinerary=draft(agent, req, profile, campsite_id), confirmed_requirements=req, profile_snapshot=profile, demo_context=DEMO)


def stored_logistics(result):
    return StoredAssessment(assessment_id='b02-unit-saved-logistics', version_context=result.version_context, kind='LOGISTICS', result=result, gear_checklist_id='b02-unit-checklist', depends_on_assessment_id=None)


def previous_version(content):
    return StoredVersion(version_context=VERSION, version_number=1, content=content, status='REVISION_REQUIRED', revision=0)


def complete_scenario(req=None, campsite_ids=None):
    req, campsite_ids = req or requirements(), campsite_ids or ['demo-pine-camp']
    evidence = []
    summaries = {'WEATHER': 'Mild synthetic conditions.', 'FIRE': 'No synthetic fire restriction.', 'ROAD': 'open in synthetic scenario', 'RESTRICTION': 'No campsite restrictions.'}
    for campsite_id in campsite_ids:
        for kind, summary in summaries.items():
            evidence.append(Evidence(
                kind=kind, summary=summary, source_date='2026-10-07', status='AVAILABLE',
                valid_from=req.start_date, valid_to=req.end_date,
                road_state='OPEN' if kind == 'ROAD' else None,
                source_refs=[{'dataset_file': 'independent-b02-unit-facts.json', 'record_id': campsite_id}],
            ))
    return ScenarioContext(scenario_id='independent-b02-unit-scenario', campsite_ids=campsite_ids, valid_from=req.start_date, valid_to=req.end_date, evidence=evidence)
