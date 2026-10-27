"""Synthetic gear and budget rules. Estimates never confirm rentals or supplies."""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from functools import reduce

from ...contracts.dto import Blocker, Clarification, CostLine, GearItem, LogisticsResult
from ...contracts.enums import AssessmentOutcome, ExecutionMode
from .common import artifact, ensure_execution_mode, input_failure, meal_mode, rule_failure, validate_itinerary
from .planning import validate_constraints, violations, vehicle_arrival_supported

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


def _eval_expression(expression, values):
    """Evaluate the sealed v2 expression DSL; unknown variables never default to zero."""
    if not isinstance(expression, dict):
        return expression, set()
    if 'var' in expression:
        key = expression['var']
        return (values[key], set()) if values.get(key) is not None else (None, {key})
    if len(expression) != 1:
        raise rule_failure('Malformed v2 gear expression.', 'gear_rules')
    operator, args = next(iter(expression.items()))
    evaluated = [_eval_expression(arg, values) for arg in args]
    missing = set().union(*(item[1] for item in evaluated))
    if missing:
        return None, missing
    args = [item[0] for item in evaluated]
    if operator == 'mul': result = reduce(lambda left, right: left * right, args, 1)
    elif operator == 'add': result = sum(args)
    elif operator == 'sub': result = args[0] - args[1]
    elif operator == 'eq': result = args[0] == args[1]
    elif operator == 'lt': result = args[0] < args[1]
    elif operator == 'lte': result = args[0] <= args[1]
    elif operator == 'gt': result = args[0] > args[1]
    elif operator == 'gte': result = args[0] >= args[1]
    elif operator == 'and': result = all(args)
    elif operator == 'or': result = any(args)
    else: raise rule_failure(f'Unsupported v2 gear operator: {operator}.', 'gear_rules')
    return result, set()


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
    group, profile, campsites, requirements, mode = context[:5]
    dataset, policy_values = context[5:]
    if dataset.has_v2_policy:
        row = dataset.get_gear_policy(trigger.gear_rule_id)
        active, missing = _eval_expression(row['trigger_json'], policy_values)
        policy_values['_missing_inputs'].update(missing)
        # Unknown conditions are conservatively included; the resulting unknown
        # quantity is surfaced as a clarification below, never treated as zero.
        return True if active is None else bool(active)
    trigger = trigger.trigger_conditions
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
    group, profile, campsites, requirements, mode = context[:5]
    dataset, policy_values = context[5:]
    if dataset.has_v2_policy:
        row = dataset.get_gear_policy(rule.gear_rule_id)
        active, trigger_missing = _eval_expression(row['trigger_json'], policy_values)
        if active is None and 'meal_mode' in trigger_missing:
            # This is a conditional requirement awaiting a user choice, not a
            # confirmed equipment shortage. Preserve the unresolved item.
            return None
        quantity, missing = _eval_expression(row['quantity_json'], policy_values)
        policy_values['_missing_inputs'].update(missing)
        return None if quantity is None else Decimal(str(quantity))
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


def assess(dataset, input, *, expected_mode=ExecutionMode.DETERMINISTIC_DEMO, safety_case_ids=None, transport_policy=None) -> LogisticsResult:
    from .transport import checked_policy
    minimal_transport = checked_policy(transport_policy) is not None
    ensure_execution_mode(dataset, input.demo_context, expected_mode)
    requirements, profile = input.confirmed_requirements, input.profile_snapshot
    if profile.group_size is None:
        raise input_failure('Group size is required for gear and costs.', 'profile.group_size')
    validate_constraints(requirements)
    nights = validate_itinerary(dataset, input.saved_itinerary, requirements, expected_mode=expected_mode)
    campsites = [dataset.get_campsite(key) for key in nights]
    group, mode = Decimal(profile.group_size), meal_mode(requirements)
    policy_values = {}
    if dataset.has_v2_policy:
        tent_capacity = _available(profile, 'tent', 'person_space', group)
        tent_count = _tent_count(profile, group)
        sleeping_bags = _available(profile, 'sleeping_bag', 'item', group)
        stove_count = _available(profile, 'camping_stove', 'item')
        vehicle_count = profile.transport.vehicle_count
        if minimal_transport and profile.transport.transport_type == 'PUBLIC_TRANSPORT':
            # This is the count of private vehicles USED by this confirmed
            # mode, not missing inventory defaulted to zero. Do not mutate the
            # profile, infer ownership, or apply this to an unknown/other mode.
            vehicle_count = 0
        fire_prohibited = 'no_fires' in requirements.mandatory_constraints or any(camp.fire_allowed is not True for camp in campsites)
        selected_ids = set(getattr(dataset, 'selected_safety_case_ids', ()) if safety_case_ids is None else safety_case_ids)
        facts = []
        for case in dataset.safety_cases:
            if case.safety_case_id not in selected_ids or case.campsite_id not in {camp.campsite_id for camp in campsites}:
                continue
            weather = next((item for item in case.scenario_context.evidence if item.kind == 'WEATHER'), None)
            if (weather is None or weather.status.value != 'AVAILABLE' or weather.source_date is None
                    or weather.source_date > input.demo_context.demo_today
                    or weather.valid_from is None or weather.valid_from > requirements.start_date
                    or weather.valid_to is None or weather.valid_to < requirements.end_date
                    or not weather.summary):
                continue
            facts.append(dataset.get_safety_facts(case.safety_case_id))
        def known_fact(name):
            values = [fact.get(name) for fact in facts]
            return values[0] if values and all(value == values[0] for value in values) else None
        selector = getattr(dataset, 'trip_evidence_selector', None)
        evidence_selection = None
        if selector is not None:
            if selected_ids:
                raise input_failure('Automatic evidence cannot be overridden by startup scenario IDs.', 'safety_case_ids')
            evidence_selection = selector.resolve_trip_evidence(requirements,
                sorted({camp.campsite_id for camp in campsites}), input.demo_context)
            fire=[item for item in evidence_selection.scenario_context.evidence if item.kind=='FIRE']
            if not fire_prohibited:
                if any(item.status.value=='AVAILABLE' and item.summary=='Synthetic comprehensive no-fire restriction.' for item in fire):
                    fire_prohibited=True
                elif not fire or any(item.status.value!='AVAILABLE' for item in fire):
                    fire_prohibited=None
            facts = [value.model_dump() for value in evidence_selection.weather_facts_by_campsite.values()]
            def known_fact(name):
                values = [fact.get(name) for fact in facts]
                if not values or any(value is None for value in values):
                    return None
                # No inferred per-night mapping: every campsite must cover the
                # full trip. Use conservative extrema, not equality/default 0.
                return min(values) if name == 'temperature_min_c' else max(values)
        policy_values = {
            'duration_nights': requirements.duration_nights, 'duration_days': requirements.duration_days,
            'group_size': profile.group_size, 'tent_count': tent_count, 'tent_capacity_persons': tent_capacity,
            'sleeping_bag_count': sleeping_bags, 'stove_count': stove_count,
            'meal_mode': mode, 'fire_prohibited': fire_prohibited,
            'experience_level': profile.experience_level,
            'potable_water': all(camp.potable_water is True for camp in campsites) if all(camp.potable_water is not None for camp in campsites) else None,
            'toilets': all(camp.toilets is True for camp in campsites) if all(camp.toilets is not None for camp in campsites) else None,
            'remote': any('remote' in camp.risk_tags for camp in campsites),
            'transport_type': profile.transport.transport_type, 'vehicle_count': vehicle_count,
            'children_count': profile.children_count,
            'adult_count': None if profile.children_count is None else profile.group_size - profile.children_count,
            'temperature_min_c': known_fact('temperature_min_c'), 'temperature_max_c': known_fact('temperature_max_c'),
            'forecast_rain_mm': known_fact('forecast_rain_mm'), 'wind_kph': known_fact('wind_kph'),
            '_missing_inputs': set(),
        }
    context = (group, profile, campsites, requirements, mode, dataset, policy_values)
    clarifications, blockers, sources = [], [], [campsite.source_ref for campsite in campsites]
    if dataset.has_v2_policy and evidence_selection is not None:
        sources.extend(ref for evidence in evidence_selection.scenario_context.evidence for ref in evidence.source_refs)
    assumptions = [
        'Gear quantities are conservative synthetic planning rules, not real safety advice.',
        ('Conditional v2 weather gear uses only selected, current, trip-covering synthetic observations; unknown triggers are conservatively included.'
         if dataset.has_v2_policy else 'Conditional weather gear is provisionally included because LogisticsInput has no weather context.'),
        'Food/water use synthetic provision-value allowances, not a claim of actual purchases.',
        'Priced equipment gaps are estimates; they do not confirm a hire or purchase.',
    ]
    if dataset.has_v2_policy and evidence_selection is not None:
        assumptions.append('Trip evidence selection digest: ' + evidence_selection.selection_digest + '.')

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
    V2_UNITS = {'person_capacity': 'person_space', 'meal_portion': 'portion', 'snack_portion': 'portion',
        'item': 'item', 'litre': 'litre', 'plan': 'plan'}
    for rule in dataset.gear_rules:
        # Phone charge is a departure-time preparation task, not owned stock.
        # It must not require a profile inventory entry or prevent planning.
        if rule.item_name == 'Charged phone':
            continue
        if rule.item_name not in ITEMS:
            raise rule_failure(f'Unsupported gear item: {rule.item_name}.', 'gear_rules')
        if not _active(rule, context):
            continue
        sources.append(rule.source_ref)
        key, unit = ITEMS[rule.item_name]
        if dataset.has_v2_policy:
            source_rule = dataset.get_gear_policy(rule.gear_rule_id)
            if source_rule['item_key'] != key or source_rule['quantity_unit'] not in V2_UNITS:
                raise rule_failure(f'Unsupported v2 item/unit mapping for {rule.gear_rule_id}.', 'gear_rules')
            unit = V2_UNITS[source_rule['quantity_unit']]
        required = _required(rule, context)
        if key not in merged:
            merged[key] = {'required': required, 'unit': unit, 'essential': rule.essential, 'mandatory': rule.severity_if_missing == 'MANDATORY_BLOCKER', 'sources': [rule.source_ref]}
        else:
            existing = merged[key]
            if existing['unit'] != unit:
                raise rule_failure(f'Conflicting units for gear item {key}.', 'gear_rules')
            existing['required'] = None if existing['required'] is None or required is None else max(existing['required'], required)
            existing['essential'] |= rule.essential
            existing['mandatory'] |= rule.severity_if_missing == 'MANDATORY_BLOCKER'
            existing['sources'].append(rule.source_ref)
    checklist, meal_pending_keys = [], set()
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
            if required is None and mode is None and dataset.has_v2_policy:
                related = [dataset.get_gear_policy(rule.gear_rule_id) for rule in dataset.gear_rules
                           if rule.source_ref in details['sources']]
                if any('meal_mode' in _eval_expression(row['trigger_json'], policy_values)[1] for row in related):
                    meal_pending_keys.add(key)
                    continue  # Resolve the meal choice first; do not ask users to confirm an inferred need.
            reason = 'Essential stock or requirement is unknown/unconfirmed.'
            if dataset.has_v2_policy:
                row = dataset.get_gear_policy(next(item.gear_rule_id for item in dataset.gear_rules if item.source_ref in details['sources']))
                _, unknown = _eval_expression(row['quantity_json'], policy_values)
                if unknown:
                    reason = 'Missing v2 rule inputs: ' + ', '.join(sorted(unknown)) + '.'
            clarify(f'equipment.{key}', f'Confirm {key} quantity, units and capacity where relevant.', reason)
        if details['essential'] and missing is not None and missing > 0 and details['mandatory']:
            blockers.append(Blocker(code='ESSENTIAL_GEAR_MISSING', message=f'{key} has an unresolved gap of {missing} {details["unit"]}.', source_refs=details['sources']))
    if dataset.has_v2_policy:
        for name in sorted(policy_values['_missing_inputs']):
            if name == 'meal_mode':
                continue  # Already represented by the actionable meal_mode clarification.
            if evidence_selection is not None and name in {'temperature_min_c','temperature_max_c','forecast_rain_mm','wind_kph'}:
                clarify(f'evidence.weather.{name}', f'Registered trip evidence does not supply {name}; source maintenance is required.',
                    'This is a data coverage issue, not an omitted user weather field. Unknown weather was not replaced by zero.')
            else:
                clarify(f'gear_rule_input.{name}', f'Confirm the v2 rule input {name}.', 'The registered v2 expression references an unknown input; no default or zero was substituted.')

    transport = profile.transport
    transport_feasible = None
    if transport.transport_type == 'CAR':
        if any(not vehicle_arrival_supported(campsite) for campsite in campsites):
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
        if minimal_transport:
            assumptions.extend([
                'Public transport access is a registered campsite attribute, not live timetable verification.',
                'The traveller confirms outbound, return and last-mile arrangements; the system does not verify services or reservations.',
                'Public transport uses a synthetic return-fare allowance per person, not a live ticket quote.',
            ])
            if not any(item.strip() for item in transport.assumptions):
                if transport_feasible is not False:
                    transport_feasible = None
                clarify('transport.assumptions', 'Describe the outbound, return and last-mile arrangements you have checked.',
                    'User-confirmed connection details are required; the system cannot infer timetables from an access flag.')
            if any(camp.public_transport_access is None for camp in campsites) and not any(camp.public_transport_access is False for camp in campsites):
                transport_feasible = None
                clarify('transport.public_transport_access', 'Registered campsite public-transport access is unknown.',
                    'Source maintenance or another supported campsite is required; do not invent access evidence.')
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
        if dataset.has_v2_policy:
            row = dataset.get_cost_policy(cost_id)
            if row['rate_source'] != 'typical_aud':
                raise rule_failure(f'Unsupported v2 rate source for {cost_id}.', 'cost_reference')
            values = {
                'estimated_total_vehicle_km': transport.estimated_km,
                'vehicle_count': transport.vehicle_count,
                'group_size': profile.group_size,
                'duration_days': requirements.duration_days,
                'duration_nights': requirements.duration_nights,
                'meal_mode': mode,
                'water_equivalent_person_days': None,
                'hire_tent_count': Decimal(0), 'hire_sleeping_bag_count': Decimal(0),
                'hire_stove_count': Decimal(0), 'purchase_first_aid_count': Decimal(0),
                'purchase_torch_count': Decimal(0), 'purchase_rain_jacket_count': Decimal(0),
                'hire_sleeping_mat_count': Decimal(0), 'purchase_power_bank_count': Decimal(0),
                'purchase_map_count': Decimal(0),
            }
            by_key = {item.item_key: item for item in checklist}
            if 'drinking_water' in by_key and by_key['drinking_water'].required_quantity is not None:
                values['water_equivalent_person_days'] = by_key['drinking_water'].required_quantity / 2
            cost_item_variables = {
                'tent':'hire_tent_count', 'sleeping_bag':'hire_sleeping_bag_count',
                'camping_stove':'hire_stove_count', 'first_aid_kit':'purchase_first_aid_count',
                'torch':'purchase_torch_count', 'rain_jacket':'purchase_rain_jacket_count',
                'sleeping_mat':'hire_sleeping_mat_count', 'power_bank':'purchase_power_bank_count',
                'offline_map':'purchase_map_count',
            }
            for item_key, variable in cost_item_variables.items():
                item = by_key.get(item_key)
                if item is not None:
                    missing = item.missing_quantity
                    values[variable] = None if missing is None else _ceil(missing / 2) if item_key == 'tent' else missing
            quantity, unknown = _eval_expression(row['quantity_json'], values)
            policy_values['_missing_inputs'].update(unknown)
            quantity = None if unknown else Decimal(str(quantity))
            selection_group = row['selection_group']
            if selection_group not in {'', 'TRANSPORT_CHOICE', 'FOOD_CHOICE'}:
                raise rule_failure(f'Unsupported v2 cost selection group for {cost_id}.', 'cost_reference')
            if selection_group == 'TRANSPORT_CHOICE' and (
                    reference.unit in {'per_kilometre', 'per_vehicle'} and transport.transport_type != 'CAR'
                    or reference.unit == 'per_person' and transport.transport_type != 'PUBLIC_TRANSPORT'):
                return
            if selection_group == 'FOOD_CHOICE':
                if mode is None or (cost_id == 'cost-04' and mode != 'SELF_CATERED') or (cost_id == 'cost-14' and mode != 'READY_TO_EAT'):
                    return
        line(reference.category, cost_id, quantity, reference.typical_cents, reference.unit, reference.source_ref, assumption)
        if quantity is None or reference.typical_cents is None:
            if (quantity is None and reference.typical_cents is not None
                    and cost_id in {GEAR_COSTS.get(key) for key in meal_pending_keys}):
                return  # The unknown cost remains; the meal choice already explains its unknown quantity.
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
