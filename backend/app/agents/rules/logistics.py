"""Synthetic gear and budget rules. Estimates never confirm rentals or supplies."""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from ...contracts.dto import Blocker, Clarification, CostLine, GearItem, LogisticsResult
from ...contracts.enums import AssessmentOutcome
from .common import artifact, input_failure, meal_mode, rule_failure, validate_itinerary
from .planning import validate_constraints, violations

ITEMS = {
    'Tent': ('tent', 'person_space'), 'Groundsheet': ('groundsheet', 'item'),
    'Tent repair kit': ('tent_repair_kit', 'item'), 'Sleeping bag': ('sleeping_bag', 'item'),
    'Sleeping mat': ('sleeping_mat', 'item'), 'Warm liner': ('warm_liner', 'item'),
    'Rain jacket': ('rain_jacket', 'item'), 'Warm layers': ('warm_layers', 'set'),
    'Sun hat': ('sun_hat', 'item'), 'Windproof outer layer': ('windproof_outer_layer', 'item'),
    'Camping stove': ('camping_stove', 'item'), 'Fuel canister': ('fuel_canister', 'item'),
    'Cooking pot': ('cooking_pot', 'item'), 'Drinking water': ('drinking_water', 'litre'),
    'Meal supplies': ('meal_supplies', 'portion'), 'Child snacks': ('child_snacks', 'portion'),
    'Offline map': ('offline_map', 'item'), 'Charged phone': ('charged_phone', 'item'),
    'Power bank': ('power_bank', 'item'), 'First aid kit': ('first_aid_kit', 'item'),
    'Torch': ('torch', 'item'), 'Whistle': ('whistle', 'item'),
    'Emergency contact card': ('emergency_contact_card', 'item'),
    'Hand sanitiser': ('hand_sanitiser', 'item'), 'Toilet kit': ('toilet_kit', 'item'),
    'Extra tent capacity': ('tent', 'person_space'), 'Extra sleeping bag': ('sleeping_bag', 'item'),
    'Transport itinerary': ('transport_itinerary', 'plan'), 'Fire-free meal plan': ('fire_free_meal_plan', 'plan'),
}
GEAR_COSTS = {
    'tent': 'cost-06', 'sleeping_bag': 'cost-07', 'camping_stove': 'cost-08',
    'first_aid_kit': 'cost-09', 'torch': 'cost-10', 'rain_jacket': 'cost-11',
    'sleeping_mat': 'cost-12', 'power_bank': 'cost-13', 'offline_map': 'cost-16',
}
EXPECTED_COST_UNITS = {
    'cost-02': ('TRANSPORT', 'per_kilometre'), 'cost-03': ('TRANSPORT', 'per_person'),
    'cost-04': ('FOOD', 'per_person_per_day'), 'cost-05': ('WATER', 'per_person_per_day'),
    **{f'cost-{number:02}': ('ADDITIONAL_GEAR', 'per_item') for number in range(6, 14)},
    'cost-14': ('FOOD', 'per_person_per_day'), 'cost-15': ('TRANSPORT', 'per_vehicle'),
    'cost-16': ('ADDITIONAL_GEAR', 'one_time'),
}
WEATHER_TRIGGERS = {
    'low temperature forecast', 'strong rain or heavy rain forecast',
    'cold forecast', 'high heat forecast', 'strong wind forecast',
}


def _ceil(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_CEILING)


def _available(profile, item_key, unit, required=None):
    entries = [item for item in profile.equipment if item.item_key == item_key]
    if not entries:
        return Decimal(0)
    known, unknown = Decimal(0), False
    for item in entries:
        expected_unit = 'item' if item_key == 'tent' else unit
        if not item.confirmed or item.quantity is None or item.unit != expected_unit:
            unknown = True
        elif item_key == 'tent':
            if item.quantity == 0:
                continue
            if item.capacity_persons is None:
                unknown = True
            else:
                known += Decimal(item.quantity * item.capacity_persons)
        else:
            known += Decimal(item.quantity)
    return None if unknown and (required is None or known < required) else known


def _tent_count(profile, group):
    capacity = _available(profile, 'tent', 'person_space', group)
    tents = [item for item in profile.equipment if item.item_key == 'tent']
    if capacity is None or any(not item.confirmed or item.quantity is None or item.unit != 'item' for item in tents):
        return None
    count = sum(item.quantity for item in tents)
    return Decimal(count) + _ceil(max(group - capacity, Decimal(0)) / 2)


def _active(trigger, context):
    group, profile, campsites, requirements, mode = context
    remote = any('remote' in campsite.risk_tags for campsite in campsites)
    no_vehicle = profile.transport.transport_type != 'CAR'
    fire_prohibited = 'no_fires' in requirements.mandatory_constraints or any(campsite.fire_allowed is not True for campsite in campsites)
    tent_capacity = _available(profile, 'tent', 'person_space', group)
    bags = _available(profile, 'sleeping_bag', 'item', group)
    stove_count = _available(profile, 'camping_stove', 'item')
    conditions = {
        'all overnight trips': True, 'all tent stays': True, 'all trips': True,
        'trips of two or more days': requirements.duration_days >= 2,
        'trips with self-catered meals and fires prohibited': mode != 'READY_TO_EAT' and fire_prohibited,
        'camping stove used': mode != 'READY_TO_EAT' and (fire_prohibited or stove_count is None or stove_count > 0),
        'self-catered meals': mode != 'READY_TO_EAT',
        'campsite without potable water': any(campsite.potable_water is not True for campsite in campsites),
        'campsite with potable water': all(campsite.potable_water is True for campsite in campsites),
        'group includes children': profile.has_children is not False,
        'remote campsite or no vehicle': remote or no_vehicle, 'remote campsite': remote,
        'new campers': profile.experience_level in {None, 'BEGINNER'},
        'campsite without toilets': any(campsite.toilets is not True for campsite in campsites),
        'group size exceeds existing tent capacity': tent_capacity is None or tent_capacity < group,
        'user lacks sleeping bags': bags is None or bags < group,
        'public transport trip': profile.transport.transport_type == 'PUBLIC_TRANSPORT',
        'fire prohibited campsite': fire_prohibited,
    }
    if trigger in WEATHER_TRIGGERS:
        # LogisticsInput has no frozen weather facts. Cover the conservative
        # superset instead of guessing that a conditional essential item is unneeded.
        return True
    if trigger not in conditions:
        raise rule_failure(f'Unsupported gear trigger: {trigger}.', 'gear_rules')
    return conditions[trigger]


def _required(rule, context):
    group, profile, campsites, requirements, mode = context
    if rule.quantity_rule in {'one tent space per two campers', 'one tent space per uncovered camper'}:
        return group
    if rule.quantity_rule in {'one per camper', 'one set per camper', 'one per uncovered camper'}:
        return group
    if rule.quantity_rule == 'one per group':
        return Decimal(1)
    if rule.quantity_rule == 'one per tent':
        return _tent_count(profile, group)
    if rule.quantity_rule == 'one per stove plus reserve':
        count = _available(profile, 'camping_stove', 'item')
        return None if count is None else max(count, Decimal(1)) + 1
    if rule.quantity_rule == 'two litres per camper per day plus one emergency day':
        return group * (requirements.duration_days + 1) * 2
    if rule.quantity_rule == 'two litres per camper per day':
        return group * requirements.duration_days * 2
    if rule.quantity_rule == 'three simple meals per camper per day':
        return group * requirements.duration_days * 3
    if rule.quantity_rule == 'two snack portions per child per day':
        return None if profile.children_count is None else Decimal(profile.children_count * requirements.duration_days * 2)
    if rule.quantity_rule == 'one per adult camper':
        if profile.has_children is False:
            return group
        return None if profile.children_count is None else group - profile.children_count
    raise rule_failure(f'Unsupported gear quantity rule: {rule.quantity_rule}.', 'gear_rules')


def assess(dataset, input) -> LogisticsResult:
    requirements, profile = input.confirmed_requirements, input.profile_snapshot
    if profile.group_size is None:
        raise input_failure('Group size is required for gear and costs.', 'profile.group_size')
    validate_constraints(requirements)
    nights = validate_itinerary(dataset, input.saved_itinerary, requirements)
    campsites = [dataset.get_campsite(key) for key in nights]
    group, mode = Decimal(profile.group_size), meal_mode(requirements)
    context = (group, profile, campsites, requirements, mode)
    clarifications, blockers, sources = [], [], [campsite.source_ref for campsite in campsites]
    assumptions = [
        'Gear quantities are conservative synthetic planning rules, not real safety advice.',
        'Conditional weather gear is provisionally included because LogisticsInput has no weather context.',
        'Food/water use synthetic provision-value allowances, not a claim of actual purchases.',
        'Priced equipment gaps are estimates; they do not confirm a hire or purchase.',
    ]

    def clarify(field, question, reason):
        if not any(item.field == field for item in clarifications):
            clarifications.append(Clarification(field=field, question=question, reason=reason))

    for campsite in campsites:
        problems = violations(campsite, requirements, profile, include_budget=False)
        if problems:
            blockers.append(Blocker(code='HARD_CONSTRAINT', message=' '.join(problems), source_refs=[campsite.source_ref]))
        if campsite.potable_water is None:
            clarify(f'campsite.{campsite.campsite_id}.potable_water', 'Confirm potable-water availability.', 'Unknown availability cannot be treated as a free supply.')
    if mode is None:
        clarify('meal_mode', 'Confirm ready-to-eat meals or self-catered meals in request preferences.', 'Meal and stove rules need one unambiguous, confirmed meal mode.')
    if profile.has_children is None or profile.has_children and profile.children_count is None:
        clarify('profile.children_count', 'Confirm whether children are present and how many.', 'Do not derive child/adult counts from notes.')
    if mode == 'SELF_CATERED' and all(campsite.fire_allowed is True for campsite in campsites) and _available(profile, 'camping_stove', 'item') == 0:
        clarify('cooking_method', 'Confirm a fire-free cooking arrangement.', 'A campsite fire_allowed flag is not current fire permission or a cooking arrangement.')

    merged = {}
    for rule in dataset.gear_rules:
        if rule.item_name not in ITEMS:
            raise rule_failure(f'Unsupported gear item: {rule.item_name}.', 'gear_rules')
        if not _active(rule.trigger_conditions, context):
            continue
        sources.append(rule.source_ref)
        key, unit = ITEMS[rule.item_name]
        required = _required(rule, context)
        if key not in merged:
            merged[key] = {'required': required, 'unit': unit, 'essential': rule.essential, 'mandatory': rule.severity_if_missing == 'MANDATORY_BLOCKER', 'sources': [rule.source_ref]}
        else:
            existing = merged[key]
            existing['required'] = None if existing['required'] is None or required is None else max(existing['required'], required)
            existing['essential'] |= rule.essential
            existing['mandatory'] |= rule.severity_if_missing == 'MANDATORY_BLOCKER'
            existing['sources'].append(rule.source_ref)
    checklist = []
    for key, details in merged.items():
        required = details['required']
        available = Decimal(1) if key == 'fire_free_meal_plan' and mode == 'READY_TO_EAT' else _available(profile, key, details['unit'], required)
        missing = None if required is None or available is None else max(required - available, Decimal(0))
        arrangement = 'UNCONFIRMED' if missing is None else 'OWNED' if missing == 0 else 'MISSING'
        checklist.append(GearItem(
            item_key=key, required_quantity=required, available_quantity=available, missing_quantity=missing,
            unit=details['unit'], capacity_requirement=profile.group_size if key == 'tent' else None,
            arrangement_status=arrangement, essential=details['essential'],
        ))
        if details['essential'] and missing is None:
            clarify(f'equipment.{key}', f'Confirm {key} quantity, units and capacity where relevant.', 'Essential stock or requirement is unknown/unconfirmed.')
        if details['essential'] and missing is not None and missing > 0 and details['mandatory']:
            blockers.append(Blocker(code='ESSENTIAL_GEAR_MISSING', message=f'{key} has an unresolved gap of {missing} {details["unit"]}.', source_refs=details['sources']))

    transport = profile.transport
    transport_feasible = None
    if transport.transport_type == 'CAR':
        if any(campsite.vehicle_access is not True for campsite in campsites):
            transport_feasible = False
        else:
            vehicles = [item for item in profile.equipment if item.item_key == 'vehicle']
            capacity = sum(item.quantity * item.capacity_persons for item in vehicles if item.confirmed and item.unit == 'vehicle' and item.quantity is not None and item.capacity_persons is not None)
            unknown = any(not item.confirmed or item.unit != 'vehicle' or item.quantity is None or item.capacity_persons is None for item in vehicles)
            vehicle_count = sum(item.quantity for item in vehicles if item.confirmed and item.unit == 'vehicle' and item.quantity is not None)
            if transport.vehicle_count is None:
                clarify('transport.vehicle_count', 'Confirm vehicle count.', 'Parking uses a per-vehicle rate.')
            if transport.estimated_km is None:
                clarify('transport.estimated_km', 'Confirm total vehicle kilometres for the trip.', 'Do not invent distance or multiply a group-total distance by vehicle count again.')
            if not vehicles or unknown:
                clarify('equipment.vehicle', 'Confirm available vehicle count and passenger capacity.', 'Vehicle access does not establish group transport capacity.')
            elif transport.vehicle_count is not None and vehicle_count != transport.vehicle_count:
                clarify('transport.vehicle_count', 'Reconcile vehicle stock and vehicle count.', 'Confirmed vehicle records and parking input disagree.')
            elif capacity < profile.group_size:
                transport_feasible = False
            elif transport.vehicle_count is not None and transport.estimated_km is not None:
                transport_feasible = True
    elif transport.transport_type == 'PUBLIC_TRANSPORT':
        transport_feasible = all(campsite.public_transport_access is True for campsite in campsites)
        if transport_feasible and _available(profile, 'transport_itinerary', 'plan', Decimal(1)) in {None, Decimal(0)}:
            transport_feasible = None
            clarify('equipment.transport_itinerary', 'Confirm an actual public-transport connection plan.', 'An access flag alone does not verify connections.')
    else:
        clarify('transport.transport_type', 'Confirm car or public transport.', 'Unsupported or missing mode cannot be assumed.')
    if transport_feasible is False:
        blockers.append(Blocker(code='TRANSPORT_UNAVAILABLE', message='Mode access or confirmed passenger capacity cannot support the selected itinerary.'))

    lines = []
    def line(category, key, quantity, price, unit, source=None, assumption=None):
        subtotal = None if quantity is None or price is None else int((quantity * price).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        lines.append(CostLine(category=category, item_key=key, quantity=quantity, unit=unit, unit_price_cents=price, subtotal_cents=subtotal, source_ref=source, assumption=assumption))
        if source:
            sources.append(source)

    def reference_line(cost_id, quantity, assumption):
        reference = dataset.get_cost_reference(cost_id)
        if (reference.category, reference.unit) != EXPECTED_COST_UNITS[cost_id]:
            raise rule_failure(f'Cost reference {cost_id} has unsupported category/unit semantics.', 'cost_reference')
        line(reference.category, cost_id, quantity, reference.typical_cents, reference.unit, reference.source_ref, assumption)
        if quantity is None or reference.typical_cents is None:
            clarify(f'cost.{cost_id}', f'Complete quantity/rate for {reference.item_name}.', 'Unknown quantity or price means unknown line amount.')

    for campsite in campsites:
        line('CAMPSITE', campsite.campsite_id, Decimal(nights[campsite.campsite_id]), campsite.nightly_fee_cents, campsite.fee_unit, campsite.source_ref, 'Nightly synthetic campsite rate is a group/site allowance, not a per-person rate.')
        if campsite.nightly_fee_cents is None:
            clarify(f'cost.{campsite.campsite_id}', 'Supply a registered campsite fee.', 'Missing fee cannot be zero.')
    if transport.transport_type == 'CAR':
        reference_line('cost-02', transport.estimated_km, 'Total vehicle kilometres already includes all vehicles.')
        reference_line('cost-15', None if transport.vehicle_count is None else Decimal(transport.vehicle_count), 'One parking allowance per confirmed vehicle.')
    elif transport.transport_type == 'PUBLIC_TRANSPORT':
        reference_line('cost-03', group, 'Synthetic return fare per traveller; connection feasibility is separate.')
    else:
        line('TRANSPORT', 'unknown_transport', None, None, 'unconfirmed', assumption='No verified transport mode.')
    if mode is None:
        line('FOOD', 'unconfirmed_meal_mode', group * requirements.duration_days, None, 'per_person_per_day', assumption='Choose and confirm one meal mode before pricing.')
    else:
        reference_line('cost-14' if mode == 'READY_TO_EAT' else 'cost-04', group * requirements.duration_days, 'Synthetic provision-value allowance; possession does not imply a free trip.')
    water_days = requirements.duration_days + int(any(campsite.potable_water is not True for campsite in campsites))
    reference_line('cost-05', group * water_days, 'Packaged-water value allowance; add one emergency day when potable supply is absent/unknown. Rule litre quantities are not multiplied by a person-day price.')
    priced_gaps = 0
    for item in checklist:
        if not item.essential or item.item_key in {'drinking_water', 'meal_supplies', 'transport_itinerary', 'fire_free_meal_plan'} or item.missing_quantity == 0:
            continue
        quantity = None if item.missing_quantity is None else _ceil(item.missing_quantity / 2) if item.item_key == 'tent' else item.missing_quantity
        cost_id = GEAR_COSTS.get(item.item_key)
        if cost_id:
            reference_line(cost_id, quantity, f'Estimated {item.item_key} gap only; not confirmed rental. Tent hire units have two-person capacity.')
        else:
            line('ADDITIONAL_GEAR', item.item_key, quantity, None, item.unit, assumption='No matching registered rate; do not invent a price.')
            clarify(f'cost.equipment.{item.item_key}', f'Supply a registered price or confirmed stock for {item.item_key}.', 'Essential equipment price is missing.')
        priced_gaps += 1
    if not priced_gaps:
        line('ADDITIONAL_GEAR', 'no_priced_equipment_gaps', Decimal(1), 0, 'one_time', assumption='No priced essential-equipment gaps; supply/plan confirmation is still checked separately.')
    known = sum(item.subtotal_cents or 0 for item in lines)
    total = None if any(item.subtotal_cents is None for item in lines) else known
    unresolved_gear = any(item.essential and (item.missing_quantity is None or item.missing_quantity > 0) for item in checklist)
    if blockers or clarifications or unresolved_gear or total is None or transport_feasible is not True or known > requirements.budget_cents:
        outcome = AssessmentOutcome.REVISION
    else:
        outcome = AssessmentOutcome.PASSED
    return LogisticsResult(
        version_context=input.version_context, gear_checklist=checklist, transport_feasible=transport_feasible,
        cost_breakdown=lines, total_cents=total, known_subtotal_cents=known,
        budget_difference_cents=None if total is None else total - requirements.budget_cents,
        outcome=outcome, mandatory_blockers=blockers, clarifications=clarifications,
        **artifact(input.demo_context, sources, assumptions=assumptions,
                   uncertainties=['Weather-specific equipment is a conservative superset, not a forecast assessment.', *(['Known subtotal already exceeds budget; missing amounts cannot restore affordability.'] if known > requirements.budget_cents else [])]),
    )
