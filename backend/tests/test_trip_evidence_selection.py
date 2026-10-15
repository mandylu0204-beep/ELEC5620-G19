"""Independent selector edge fixtures, never mixed into normal runtime data."""
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path

import pytest

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter, _safety
from app.agents.rules.trip_evidence import TripEvidenceSelector
from app.contracts.dto import DemoContext
from app.contracts.errors import ContractFailure
from app.workflow import WorkflowConfiguration
from rule_fixtures import requirements

ROOT = Path(__file__).resolve().parents[2]
SITE = 'demo-wattle-rest'


@pytest.fixture(scope='module')
def snapshot():
    return SyntheticDatasetV2Adapter(ROOT/'data/synthetic_demo_v2_1').load()


def query(dataset, *, sites=(SITE,), start='2026-11-06', nights=2, today='2026-11-05'):
    req = requirements(start_date=date.fromisoformat(start),duration_nights=nights)
    demo = DemoContext(mode='deterministic_demo',demo_today=today,dataset_version='2.1.0')
    return dataset.trip_evidence_selector.resolve_trip_evidence(req,sites,demo)


def narrow_rows(snapshot, campsite=SITE):
    selection=query(snapshot,sites=(campsite,))
    return [deepcopy(snapshot.v2_policy['safety'][key]) for key in selection.selected_case_ids]


def fixture(snapshot, rows):
    """Explicit detached test world; no production files or stored runs changed."""
    dataset=deepcopy(snapshot)
    dataset._safety={row['safety_case_id']:_safety(row,'runtime_safety_evidence.json') for row in rows}
    dataset._context=dataset.context.model_copy(update={'file_digests':{
        **dataset.context.file_digests,'runtime_safety_evidence.json':hashlib.sha256(json.dumps(sorted(rows,key=lambda row:row['safety_case_id']),sort_keys=True).encode()).hexdigest()}})
    dataset.trip_evidence_selector=TripEvidenceSelector(dataset,rows)
    return dataset


def weather(rows):
    return next(value for value in rows if value['active_kinds']==['WEATHER'])


def test_all_ten_campsites_can_be_queried_without_startup_scenario_changes(snapshot):
    for campsite in snapshot.campsites:
        selection=query(snapshot,sites=(campsite.campsite_id,))
        assert not selection.coverage_issues
        assert len(selection.selected_case_ids)==4
        assert {item.kind for item in selection.scenario_context.evidence}=={'WEATHER','FIRE','ROAD','RESTRICTION'}
        assert all(item.status=='AVAILABLE' for item in selection.scenario_context.evidence)
        assert selection.weather_facts_by_campsite[campsite.campsite_id].temperature_min_c==12


def test_irrelevant_dates_and_other_campsites_do_not_create_global_intersection_or_conflicts(snapshot):
    selection=query(snapshot,sites=('demo-river-flat',))
    assert not selection.coverage_issues
    assert all('demo-river-flat' in key for key in selection.selected_case_ids)
    assert all('2027-' not in key for key in selection.selected_case_ids)
    assert selection.scenario_context.valid_from==date(2026,11,6)
    assert selection.scenario_context.valid_to==date(2026,11,8)


def test_stable_order_and_snapshot_detachment(snapshot):
    rows=narrow_rows(snapshot)
    a,b=fixture(snapshot,rows),fixture(snapshot,list(reversed(rows)))
    assert query(a)==query(b)
    before=query(a)
    for value in a._safety.values():
        value.scenario_context.evidence.clear()
    rows.clear()
    assert query(a)==before
    before.scenario_context.evidence.clear()
    assert query(a).scenario_context.evidence


@pytest.mark.parametrize('field', ['published_at','observed_at'])
def test_future_publication_and_future_observation_are_not_consumed(snapshot,field):
    rows=narrow_rows(snapshot)
    target=weather(rows)
    if field=='published_at': target[field]='2026-11-07T00:00:00+11:00'
    else: target['weather'][field]='2026-11-07T00:00:00+11:00'
    selection=query(fixture(snapshot,rows))
    assert any(issue.code=='NOT_YET_OBSERVED' and issue.kind=='WEATHER' for issue in selection.coverage_issues)
    assert target['safety_case_id'] not in selection.selected_case_ids
    assert selection.weather_facts_by_campsite[SITE].temperature_min_c is None
    assert next(item for item in selection.scenario_context.evidence if item.kind=='WEATHER').status=='MISSING'


def test_future_extra_forecast_does_not_hide_a_current_complete_forecast(snapshot):
    rows=narrow_rows(snapshot)
    extra=deepcopy(weather(rows)); extra['safety_case_id']+='-future'
    extra['published_at']='2026-11-07T00:00:00+11:00'
    extra['evidence_facts']['temperature_min_c']=-10
    selection=query(fixture(snapshot,[*rows,extra]))
    assert not selection.coverage_issues and extra['safety_case_id'] not in selection.selected_case_ids
    assert selection.weather_facts_by_campsite[SITE].temperature_min_c==12


def test_stale_observation_does_not_supply_gear_weather(snapshot):
    rows=narrow_rows(snapshot)
    weather(rows)['weather']['observed_at']='2026-10-01T00:00:00+10:00'
    selection=query(fixture(snapshot,rows))
    assert any(issue.code=='STALE' for issue in selection.coverage_issues)
    assert selection.weather_facts_by_campsite[SITE].wind_kph is None


@pytest.mark.parametrize('change', ['summary','numeric'])
def test_overlapping_available_sources_must_not_silently_choose_favourable_facts(snapshot,change):
    rows=narrow_rows(snapshot)
    extra=deepcopy(weather(rows)); extra['safety_case_id']+='-other'
    if change=='summary': extra['weather']['summary']='Heavy rain in synthetic conditions.'
    else: extra['evidence_facts']['forecast_rain_mm']=50
    selection=query(fixture(snapshot,[*rows,extra]))
    assert any(issue.code=='CONFLICTING' and issue.kind=='WEATHER' for issue in selection.coverage_issues)
    assert selection.weather_facts_by_campsite[SITE].forecast_rain_mm is None
    assert all(item.status=='CONFLICTING' for item in selection.scenario_context.evidence if item.kind=='WEATHER')


def test_disjoint_weather_intervals_are_partial_not_a_false_conflict_or_merged_coverage(snapshot):
    rows=narrow_rows(snapshot)
    first=weather(rows)
    first['weather'].update(valid_from='2026-11-06',valid_until='2026-11-07')
    second=deepcopy(first); second['safety_case_id']+='-next'
    second['weather'].update(valid_from='2026-11-08',valid_until='2026-11-09',summary='Dry synthetic conditions.')
    selection=query(fixture(snapshot,[*rows,second]),nights=3)
    issue=next(value for value in selection.coverage_issues if value.kind=='WEATHER')
    assert issue.code=='OUTSIDE_VALIDITY' and not issue.uncovered_ranges
    assert 'not spliced' in issue.reason
    assert all(item.status=='MISSING' for item in selection.scenario_context.evidence if item.kind=='WEATHER')
    assert not any(value.code=='CONFLICTING' for value in selection.coverage_issues)


def test_real_boundary_gap_is_reported_without_extending_weather_validity(snapshot):
    selection=query(snapshot,start='2026-11-30',today='2026-11-29')
    issue=next(value for value in selection.coverage_issues if value.kind=='WEATHER')
    assert issue.code=='OUTSIDE_VALIDITY'
    assert issue.uncovered_ranges[0].start==date(2026,12,1)
    assert issue.uncovered_ranges[-1].end==date(2026,12,2)


def test_all_selected_campsites_need_full_trip_coverage_without_inferred_night_mapping(snapshot):
    selection=query(snapshot,sites=(SITE,'demo-river-flat'))
    assert set(selection.weather_facts_by_campsite)=={SITE,'demo-river-flat'}
    assert not selection.coverage_issues and len(selection.selected_case_ids)==8
    rows=[*narrow_rows(snapshot),*narrow_rows(snapshot,'demo-river-flat')]
    rows=[row for row in rows if not(row['campsite_id']=='demo-river-flat' and row['active_kinds']==['WEATHER'])]
    incomplete=query(fixture(snapshot,rows),sites=(SITE,'demo-river-flat'))
    assert any(value.campsite_id=='demo-river-flat' and value.code=='MISSING' for value in incomplete.coverage_issues)
    assert incomplete.weather_facts_by_campsite['demo-river-flat'].temperature_min_c is None


def test_unknown_road_is_not_open(snapshot):
    rows=narrow_rows(snapshot)
    road=next(row for row in rows if row['active_kinds']==['ROAD'])
    road['road_access']['status']='UNKNOWN'
    selection=query(fixture(snapshot,rows))
    assert any(value.code=='ROAD_STATE_UNKNOWN' for value in selection.coverage_issues)


def test_explicit_closure_is_business_restriction_not_missing_evidence(snapshot):
    selection=query(snapshot,sites=('demo-moonlit-field',),start='2027-04-10',today='2027-04-09')
    assert not selection.coverage_issues
    road=next(item for item in selection.scenario_context.evidence if item.kind=='ROAD')
    assert road.road_state=='CLOSED' and road.status=='AVAILABLE'


def test_closure_boundary_is_not_false_conflict_and_still_retains_real_closed_interval(snapshot):
    selection=query(snapshot,sites=('demo-moonlit-field',),start='2027-04-09',today='2027-04-09')
    assert not any(value.code=='CONFLICTING' for value in selection.coverage_issues)
    assert any(item.road_state=='CLOSED' for item in selection.scenario_context.evidence if item.kind=='ROAD')


def test_selection_requires_scope_inputs_and_rejects_mixed_test_worlds(snapshot):
    config=WorkflowConfiguration(snapshot)
    assert config.context.selection_config['b_evidence_index_sha256']==snapshot.trip_evidence_selector.index_digest
    with pytest.raises(ContractFailure): config.scenario_for([SITE])
    with pytest.raises(ContractFailure): WorkflowConfiguration(snapshot,safety_case_ids=[snapshot.safety_cases[0].safety_case_id])
    for ids in [[],[SITE,SITE],['not-a-campsite']]:
        with pytest.raises(ContractFailure): query(snapshot,sites=ids)


def test_utc_observation_is_compared_in_the_fixed_sydney_calendar(snapshot):
    rows=narrow_rows(snapshot)
    target=weather(rows)
    target['published_at']='2026-11-04T00:00:00+11:00'
    target['weather']['observed_at']='2026-11-04T14:30:00+00:00'  # Nov 5 in Sydney.
    selection=query(fixture(snapshot,rows),today='2026-11-04')
    assert any(value.code=='NOT_YET_OBSERVED' and value.kind=='WEATHER' for value in selection.coverage_issues)


def test_production_index_rejects_oracle_metadata(snapshot):
    rows=narrow_rows(snapshot)
    weather(rows)['expected_risk']='LOW'
    with pytest.raises(ValueError,match='oracle'): fixture(snapshot,rows)


def test_gear_and_safety_share_the_exact_selection_and_reject_substituted_scenario(snapshot):
    from app.agents.rules import logistics,safety
    from app.contracts.dto import SafetyInput
    from test_llm_logistics_agent import input_fixture
    from rule_fixtures import stored_logistics
    _,input,_=input_fixture()
    input=input.model_copy(update={'demo_context':input.demo_context.model_copy(update={'dataset_version':'2.1.0'})})
    result=logistics.assess(snapshot,input,expected_mode='agent')
    selection=snapshot.trip_evidence_selector.resolve_trip_evidence(input.confirmed_requirements,
        input.saved_itinerary.selected_campsite_ids,input.demo_context)
    safety_input=SafetyInput(version_context=input.version_context,saved_itinerary=input.saved_itinerary,
        confirmed_requirements=input.confirmed_requirements,saved_logistics_assessment=stored_logistics(result),
        scenario_context=selection.scenario_context,demo_context=input.demo_context)
    reviewed=safety.assess(snapshot,safety_input,expected_mode='agent')
    marker='Trip evidence selection digest: '+selection.selection_digest+'.'
    assert marker in reviewed.assumptions and marker in result.assumptions
    corrupted=selection.scenario_context.model_copy(update={'evidence':[]})
    with pytest.raises(ContractFailure):
        safety.assess(snapshot,safety_input.model_copy(update={'scenario_context':corrupted}),expected_mode='agent')
