import csv
from decimal import Decimal
import shutil

import pytest

from app.adapters import SyntheticDatasetAdapter
from app.adapters.synthetic_dataset import BUSINESS_FILES
from app.agents.rule_agent import RuleAgent
from app.config import Settings
from app.contracts.dto import ItineraryEntry, LogisticsInput, Transport
from app.contracts.enums import ErrorCode
from app.contracts.errors import ContractFailure
from rule_fixtures import (
    DEMO, VERSION, call, draft, equipment, full_profile, logistics_input, make_agent, requirements,
)


@pytest.fixture
def agent():
    return make_agent()


def replace_stock(profile, key, item=None):
    stock = [value for value in profile.equipment if value.item_key != key]
    if item is not None:
        stock.append(item)
    return profile.model_copy(update={'equipment': stock})


def assess(agent, profile=None, req=None, campsite_id='demo-pine-camp'):
    return call(agent.assess_gear_and_logistics(logistics_input(agent, req, profile, campsite_id)))


def gear(result, key):
    return next(item for item in result.gear_checklist if item.item_key == key)


def test_confirmed_stock_and_inputs_produce_consistent_five_category_estimate(agent):
    result = assess(agent)
    assert result.outcome == 'PASSED'
    assert result.transport_feasible is True
    assert not result.clarifications and not result.mandatory_blockers
    assert result.total_cents == result.known_subtotal_cents == 22723
    assert result.budget_difference_cents == 22723 - 50000
    assert {item.category for item in result.cost_breakdown} == {'CAMPSITE', 'TRANSPORT', 'FOOD', 'WATER', 'ADDITIONAL_GEAR'}
    assert next(item for item in result.cost_breakdown if item.item_key == 'cost-02').subtotal_cents == 123
    assert sum(item.subtotal_cents for item in result.cost_breakdown) == result.total_cents
    assert result.version_context == VERSION


def test_unmodified_git_profile_does_not_fake_success(agent):
    profile = agent.dataset.get_profile('profile-a').snapshot
    result = assess(agent, profile)
    assert result.outcome == 'REVISION'
    assert result.total_cents is None
    assert result.transport_feasible is None
    assert gear(result, 'tent').available_quantity is None
    assert gear(result, 'sleeping_bag').available_quantity is None
    assert all(item.arrangement_status != 'CONFIRMED_RENTAL' for item in result.gear_checklist)
    assert {'transport.vehicle_count', 'transport.estimated_km', 'equipment.vehicle'}.issubset({item.field for item in result.clarifications})


def test_group_total_kilometres_are_not_multiplied_by_vehicles(agent):
    profile = full_profile(kilometres='100', vehicles=2)
    result = assess(agent, profile)
    assert next(item for item in result.cost_breakdown if item.item_key == 'cost-02').subtotal_cents == 3500
    assert next(item for item in result.cost_breakdown if item.item_key == 'cost-15').subtotal_cents == 2400
    assert result.total_cents == 27300


@pytest.mark.parametrize('transport', [
    Transport(transport_type='CAR', vehicle_count=1),
    Transport(transport_type='CAR', estimated_km='100'),
    Transport(),
])
def test_missing_transport_input_keeps_amount_and_feasibility_unknown(agent, transport):
    result = assess(agent, full_profile().model_copy(update={'transport': transport}))
    assert result.total_cents is None and result.transport_feasible is None
    assert result.outcome == 'REVISION' and result.clarifications


def test_confirmed_vehicle_capacity_cannot_be_invented(agent):
    profile = replace_stock(full_profile(), 'vehicle', equipment('vehicle', 1, 'vehicle'))
    result = assess(agent, profile)
    assert result.transport_feasible is None
    assert any(item.field == 'equipment.vehicle' for item in result.clarifications)
    short = replace_stock(full_profile(), 'vehicle', equipment('vehicle', 1, 'vehicle', capacity=1))
    result = assess(agent, short)
    assert result.transport_feasible is False
    assert any(item.code == 'TRANSPORT_UNAVAILABLE' for item in result.mandatory_blockers)


def test_vehicle_count_disagreement_requires_clarification(agent):
    result = assess(agent, full_profile().model_copy(update={'transport': Transport(transport_type='CAR', vehicle_count=2, estimated_km='100')}))
    assert result.transport_feasible is None
    assert any(item.field == 'transport.vehicle_count' for item in result.clarifications)


def test_public_transport_requires_confirmed_connection_plan(agent):
    profile = full_profile(mode='PUBLIC_TRANSPORT')
    result = assess(agent, profile, campsite_id='demo-river-flat')
    assert result.outcome == 'PASSED' and result.total_cents == 22600
    assert next(item for item in result.cost_breakdown if item.item_key == 'cost-03').quantity == Decimal(2)
    result = assess(agent, replace_stock(profile, 'transport_itinerary'), campsite_id='demo-river-flat')
    assert result.transport_feasible is None and result.outcome == 'REVISION'


def test_fire_free_ready_meals_do_not_require_a_stove_and_water_units_do_not_mix(agent):
    result = assess(agent, full_profile(water=16), campsite_id='demo-ridge-lookout')
    assert result.outcome == 'PASSED'
    assert 'camping_stove' not in {item.item_key for item in result.gear_checklist}
    assert gear(result, 'fire_free_meal_plan').missing_quantity == 0
    assert gear(result, 'drinking_water').required_quantity == Decimal(16)
    water = next(item for item in result.cost_breakdown if item.item_key == 'cost-05')
    assert water.quantity == Decimal(8) and water.unit == 'per_person_per_day'
    assert water.subtotal_cents == 4800
    assert result.total_cents == 25923


def test_self_catered_no_fire_trip_requires_stove_fuel_and_confirmed_plan(agent):
    req = requirements(preferences=['self-catered meals'])
    profile = full_profile(water=16)
    profile = profile.model_copy(update={'equipment': [*profile.equipment, equipment('camping_stove', 1), equipment('fuel_canister', 2), equipment('fire_free_meal_plan', 1, 'plan')]})
    result = assess(agent, profile, req, 'demo-ridge-lookout')
    assert result.outcome == 'PASSED' and result.total_cents == 27123
    assert gear(result, 'camping_stove').required_quantity == 1
    assert gear(result, 'fuel_canister').required_quantity == 2
    assert next(item for item in result.cost_breakdown if item.item_key == 'cost-04').subtotal_cents == 12000


@pytest.mark.parametrize('preferences', [[], ['ready-to-eat meals', 'self-catered meals'], ['SIMPLE']])
def test_unknown_or_ambiguous_meal_mode_is_not_defaulted(agent, preferences):
    result = assess(agent, req=requirements(preferences=preferences))
    assert result.total_cents is None
    assert any(item.field == 'meal_mode' for item in result.clarifications)
    assert next(item for item in result.cost_breakdown if item.category == 'FOOD').unit_price_cents is None


def test_tent_capacity_and_sleeping_bag_duplicate_rules_merge_gaps_once(agent):
    profile = replace_stock(full_profile(), 'tent', equipment('tent', 1, capacity=1))
    profile = replace_stock(profile, 'sleeping_bag', equipment('sleeping_bag', 1))
    result = assess(agent, profile)
    assert len([item for item in result.gear_checklist if item.item_key == 'tent']) == 1
    assert len([item for item in result.gear_checklist if item.item_key == 'sleeping_bag']) == 1
    assert gear(result, 'tent').required_quantity == 2 and gear(result, 'tent').missing_quantity == 1
    assert gear(result, 'sleeping_bag').missing_quantity == 1
    tents = [item for item in result.cost_breakdown if item.item_key == 'cost-06']
    bags = [item for item in result.cost_breakdown if item.item_key == 'cost-07']
    assert len(tents) == len(bags) == 1
    assert tents[0].quantity == 1 and tents[0].subtotal_cents == 4500
    assert bags[0].quantity == 1 and bags[0].subtotal_cents == 2200
    assert any(item.code == 'ESSENTIAL_GEAR_MISSING' for item in result.mandatory_blockers)


def test_three_people_two_differently_named_tents_use_actual_combined_capacity(agent):
    profile=full_profile().model_copy(update={'group_size':3})
    stock=[item for item in profile.equipment if item.item_key!='tent']
    stock.extend([equipment('tent',1,capacity=1).model_copy(update={'label':'大帐篷（名称不是容量）'}),
        equipment('tent',1,capacity=2).model_copy(update={'label':'备用小帐'})])
    result=assess(agent,profile.model_copy(update={'equipment':stock}))
    item=gear(result,'tent')
    assert item.required_quantity==3 and item.available_quantity==3 and item.missing_quantity==0
    assert len([row for row in result.gear_checklist if row.item_key=='tent'])==1


@pytest.mark.parametrize('patch',[{'quantity':None},{'confirmed':False},{'capacity_persons':None}])
def test_partial_mixed_capacity_does_not_infer_unknown_values_from_custom_names(agent,patch):
    profile=full_profile().model_copy(update={'group_size':3})
    stock=[item for item in profile.equipment if item.item_key!='tent']
    stock.extend([equipment('tent',1,capacity=1),equipment('tent',1,capacity=2).model_copy(update={**patch,'label':'十人帐（仅名称）'})])
    item=gear(assess(agent,profile.model_copy(update={'equipment':stock})),'tent')
    assert item.available_quantity is None and item.missing_quantity is None


@pytest.mark.parametrize('item', [equipment('tent', 1), equipment('tent', 1, capacity=2, confirmed=False), equipment('tent', 1, 'litre', capacity=2)])
def test_unknown_unconfirmed_or_wrong_unit_tent_capacity_never_passes(agent, item):
    result = assess(agent, replace_stock(full_profile(), 'tent', item))
    assert gear(result, 'tent').available_quantity is None
    assert gear(result, 'tent').missing_quantity is None
    assert result.total_cents is None and result.outcome == 'REVISION'


def test_unknown_price_is_null_and_optional_recommendations_are_not_charged(agent):
    result = assess(agent, replace_stock(full_profile(), 'warm_layers'))
    line = next(item for item in result.cost_breakdown if item.item_key == 'warm_layers')
    assert line.unit_price_cents is None and line.subtotal_cents is None
    assert result.total_cents is None
    assert result.known_subtotal_cents == 22723
    complete = assess(agent)
    assert gear(complete, 'warm_liner').missing_quantity == 2
    assert gear(complete, 'warm_liner').essential is False
    assert 'warm_liner' not in {item.item_key for item in complete.cost_breakdown}


def test_children_count_is_not_read_from_notes_or_defaulted(agent):
    profile = full_profile(group=3).model_copy(update={'has_children': True})
    result = assess(agent, profile)
    assert 'charged_phone' not in {item.item_key for item in result.gear_checklist}
    assert any(item.field == 'profile.children_count' for item in result.clarifications)
    assert result.outcome == 'REVISION'
    fixed = assess(agent, profile.model_copy(update={'children_count': 1}))
    assert 'charged_phone' not in {item.item_key for item in fixed.gear_checklist}
    assert gear(fixed, 'child_snacks').required_quantity == 6


def test_phone_charge_is_not_inventory_or_a_planning_requirement(agent):
    result = assess(agent, replace_stock(full_profile(), 'charged_phone'))
    assert result.outcome == 'PASSED'
    assert 'charged_phone' not in {item.item_key for item in result.gear_checklist}
    assert not any('charged_phone' in item.field for item in result.clarifications)
    assert result.total_cents == assess(agent).total_cents


def test_known_over_budget_is_revision_even_when_other_costs_are_unknown(agent):
    req = requirements(budget_cents=10000)
    known = assess(agent, req=req)
    assert known.total_cents == 22723 and known.budget_difference_cents == 12723
    assert known.outcome == 'REVISION'
    unknown = assess(agent, replace_stock(full_profile(), 'warm_layers'), req)
    assert unknown.total_cents is None and unknown.budget_difference_cents is None
    assert unknown.known_subtotal_cents > req.budget_cents
    assert any('already exceeds' in text for text in unknown.uncertainties)


def test_legitimate_zero_additional_gear_is_not_used_for_missing_gear(agent):
    complete = assess(agent)
    assert [item.subtotal_cents for item in complete.cost_breakdown if item.category == 'ADDITIONAL_GEAR'] == [0]
    incomplete = assess(agent, replace_stock(full_profile(), 'first_aid_kit', equipment('first_aid_kit', None)))
    assert gear(incomplete, 'first_aid_kit').available_quantity is None
    assert next(item for item in incomplete.cost_breakdown if item.item_key == 'cost-09').subtotal_cents is None
    assert incomplete.total_cents is None


def test_provisional_weather_gear_is_not_skipped_or_claimed_as_forecast(agent):
    result = assess(agent, replace_stock(full_profile(), 'rain_jacket'))
    assert gear(result, 'rain_jacket').required_quantity == 2
    assert gear(result, 'rain_jacket').missing_quantity == 2
    assert result.outcome == 'REVISION'
    assert any('no weather context' in text for text in result.assumptions)


@pytest.mark.parametrize('mutation', ['overlap', 'missing_night', 'unselected_camp'])
def test_invalid_saved_itinerary_is_rejected_before_assessment(agent, mutation):
    input = logistics_input(agent)
    entries = list(input.saved_itinerary.itinerary_entries)
    if mutation == 'overlap':
        entries[1] = ItineraryEntry.model_validate(entries[1].model_dump() | {'start_at': entries[0].start_at})
    elif mutation == 'missing_night':
        entries = entries[:1]
    else:
        entries[0] = ItineraryEntry.model_validate(entries[0].model_dump() | {'campsite_id': 'demo-river-flat'})
    input = input.model_copy(update={'saved_itinerary': input.saved_itinerary.model_copy(update={'itinerary_entries': entries})})
    with pytest.raises(ContractFailure) as failure:
        call(agent.assess_gear_and_logistics(input))
    assert failure.value.error.code == ErrorCode.INPUT_INVALID


@pytest.mark.parametrize('filename,field,value', [
    ('synthetic_gear_rules.csv', 'trigger_conditions', 'run arbitrary code'),
    ('synthetic_gear_rules.csv', 'quantity_rule', 'invent a quantity'),
    ('synthetic_gear_rules.csv', 'item_name', 'Imaginary mandatory item'),
    ('synthetic_cost_reference.csv', 'unit', 'per_person'),
])
def test_unsupported_source_rule_semantics_fail_instead_of_silent_reinterpretation(tmp_path, filename, field, value):
    source = Settings(_env_file=None).dataset_path
    target = tmp_path / 'dataset'
    (target / 'data').mkdir(parents=True)
    for name in BUSINESS_FILES:
        shutil.copyfile(source / 'data' / name, target / 'data' / name)
    path = target / 'data' / filename
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    rows[1 if filename.startswith('synthetic_cost') else 0][field] = value
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    changed = RuleAgent(SyntheticDatasetAdapter(target).load())
    with pytest.raises(ContractFailure) as failure:
        assess(changed)
    assert failure.value.error.code == ErrorCode.ADAPTER_FAILURE
