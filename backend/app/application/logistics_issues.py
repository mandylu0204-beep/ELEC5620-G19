"""Read-only, authorised issue projection. Never changes assessments or eligibility."""
from decimal import Decimal
import re
from urllib.parse import urlencode


def project(data):
    confirmed = data.get('confirmed_context') or {}
    profile = confirmed.get('profile_snapshot') or {}
    transport = profile.get('transport') or {}
    equipment = profile.get('equipment') or []
    logistics = next((a['result'] for a in data.get('assessments', []) if a['kind'] == 'LOGISTICS'), None)
    if logistics is None:
        return []
    request_id = data['plan']['request_id']
    origin = {'request_id': request_id, **({'plan_id': data['plan']['plan_id']} if data['plan'].get('plan_id') else {})}
    issues = {}

    def add(key, code, category, field, *, item=None, current=None, required=None, diagnostic=None):
        if key in issues:
            return
        target = 'REQUEST' if field in {'meal_mode', 'budget_cents'} else 'PROFILE' if category in {'USER_INPUT', 'EQUIPMENT_GAP'} else 'SAFETY' if field.startswith('evidence.') else 'OPERATOR'
        focus = field
        if target == 'PROFILE':
            url = '/profile?' + urlencode({'focus': focus, **origin})
        elif target == 'REQUEST':
            url = '/request?' + urlencode({'copy_from': request_id, 'focus': 'request-meal' if field == 'meal_mode' else 'request-budget'})
        else:
            url = None
        issues[key] = dict(issue_id=key, code=code, category=category, field=field,
            item_key=item, current=current, required=required, target=target,
            action_url=url, diagnostic=diagnostic)

    def gear(key, shortage=False):
        rows = [row for row in equipment if row['item_key'] == key]
        fact = next((row for row in logistics['gear_checklist'] if row['item_key'] == key), {})
        shortage = shortage or (fact.get('missing_quantity') is not None and Decimal(fact['missing_quantity']) > 0)
        if key == 'vehicle':
            field, code = 'equipment.vehicle.capacity', 'VEHICLE_DETAILS'
        else:
            suffix = 'capacity' if key == 'tent' and any(row.get('quantity') and row.get('capacity_persons') is None for row in rows) else 'quantity'
            field, code = f'equipment.{key}.{suffix}', 'EQUIPMENT_SHORTAGE' if shortage else 'EQUIPMENT_DETAILS'
        add('equipment.'+key, code, 'EQUIPMENT_GAP' if shortage else 'USER_INPUT', field, item=key,
            current={'records': rows, 'available_quantity': fact.get('available_quantity'), 'unit': fact.get('unit')},
            required={'quantity': fact.get('required_quantity'), 'missing_quantity': fact.get('missing_quantity'),
                'capacity_persons': profile.get('group_size') if key in {'tent', 'vehicle'} else None})
        if key == 'tent':
            from .presentation import tent_capacity
            issues['equipment.'+key]['tent_capacity'] = tent_capacity(profile, logistics)

    questions = logistics.get('clarifications', [])
    fields = {row['field'] for row in questions}
    meal_unknown = bool(fields & {'meal_mode', 'gear_rule_input.meal_mode'})
    weather_unknown = any(field.startswith(('evidence.weather.', 'gear_rule_input.temperature_', 'gear_rule_input.forecast_', 'gear_rule_input.wind_')) for field in fields)
    aliases = {'gear_rule_input.children_count': 'profile.children_count', 'gear_rule_input.adult_count': 'profile.children_count',
        'gear_rule_input.vehicle_count': 'transport.vehicle_count', 'gear_rule_input.transport_type': 'transport.transport_type',
        'gear_rule_input.tent_count': 'equipment.tent', 'gear_rule_input.tent_capacity_persons': 'equipment.tent',
        'gear_rule_input.sleeping_bag_count': 'equipment.sleeping_bag', 'gear_rule_input.stove_count': 'equipment.camping_stove',
        'gear_rule_input.experience_level': 'profile.experience_level'}
    dependencies = {}
    for question in questions:
        match = re.fullmatch(r'Missing v2 rule inputs: ([a-z_, ]+)\.', question['reason'])
        if match and question['field'].startswith('equipment.'):
            roots = [aliases.get('gear_rule_input.'+name.strip()) for name in match[1].split(',')]
            fact = next((row for row in logistics['gear_checklist'] if 'equipment.'+row['item_key'] == question['field']), {})
            if roots and all(root in {aliases.get(field, field) for field in fields} for root in roots) and fact.get('required_quantity') is None and fact.get('available_quantity') is not None:
                dependencies[question['field'].split('.')[1]] = roots
    for question in questions:
        field = aliases.get(question['field'], question['field'])
        if field in {'meal_mode', 'gear_rule_input.meal_mode', 'cooking_method'}:
            add('meal_mode', 'MEAL_CHOICE' if meal_unknown else 'COOKING_ARRANGEMENT', 'USER_INPUT', 'meal_mode')
            if field == 'cooking_method' and not meal_unknown:
                issues['meal_mode']['alternate_action_url'] = '/profile?' + urlencode({'focus': 'equipment.camping_stove', **origin})
        elif field.startswith('equipment.'):
            key = field.split('.')[1]
            if key in dependencies:
                continue
            # Old conservatively included cooking requirements stem from one
            # unresolved meal decision. Keep genuinely independent stock gaps.
            if meal_unknown and key in {'camping_stove', 'fuel_canister', 'cooking_pot', 'fire_free_meal_plan'}:
                continue
            gear(key)
        elif field.startswith('transport.'):
            name = field.split('.')[1]
            add(field, {'estimated_km': 'DISTANCE', 'vehicle_count': 'VEHICLE_COUNT', 'transport_type': 'TRANSPORT_MODE'}.get(name, 'PROFILE_FIELD'),
                'USER_INPUT', field, current=transport.get(name), required={'registered_vehicle_count': sum(row.get('quantity') or 0 for row in equipment if row['item_key'] == 'vehicle' and row.get('confirmed'))} if name == 'vehicle_count' else None)
        elif field in {'profile.children_count', 'profile.experience_level'}:
            if field == 'profile.children_count' and profile.get('has_children') is None:
                field = 'profile.has_children'
            add(field, 'EXPERIENCE' if field.endswith('experience_level') else 'CHILDREN', 'USER_INPUT', field,
                current={key: profile.get(key) for key in ('has_children', 'children_count', 'experience_level')})
        elif field.startswith('evidence.') or field.startswith(('gear_rule_input.temperature_', 'gear_rule_input.forecast_', 'gear_rule_input.wind_')):
            add('evidence.weather', 'WEATHER_DATA', 'DATA_GAP', 'evidence.weather')
        elif field.startswith('cost.'):
            continue  # Derived cost roots are resolved below using actual cost facts.
        else:
            add(field, 'SOURCE_DATA', 'DATA_GAP', field, diagnostic=question)

    for fact in logistics['gear_checklist']:
        if not fact['essential']:
            continue
        key = fact['item_key']
        if key in dependencies:
            continue
        if meal_unknown and key in {'camping_stove', 'fuel_canister', 'cooking_pot', 'fire_free_meal_plan'}:
            continue
        if fact['required_quantity'] is None and weather_unknown:
            continue
        if fact['missing_quantity'] is None or fact['arrangement_status'] not in {'OWNED', 'CONFIRMED_RENTAL'}:
            gear(key, shortage=fact['missing_quantity'] is not None and Decimal(fact['missing_quantity']) > 0)
        elif Decimal(fact['missing_quantity']) > 0:
            gear(key, shortage=True)

    cost_gear = {'cost-06': 'tent', 'cost-07': 'sleeping_bag', 'cost-08': 'camping_stove',
        'cost-09': 'first_aid_kit', 'cost-10': 'torch', 'cost-11': 'rain_jacket',
        'cost-12': 'sleeping_mat', 'cost-13': 'power_bank', 'cost-16': 'offline_map'}
    for cost in logistics['cost_breakdown']:
        if cost['subtotal_cents'] is not None:
            continue
        key = cost['item_key']
        if cost.get('quantity') is None and key in dependencies:
            continue
        if meal_unknown and (cost['category'] == 'FOOD' or key == 'cost-08'):
            continue
        if key == 'unknown_transport' and 'transport.transport_type' in issues:
            continue
        if cost['unit_price_cents'] is None:
            add('price.'+key, 'PRICE_DATA', 'DATA_GAP', 'cost.'+key, item=cost_gear.get(key),
                current={'category': cost['category'], 'unit_price_cents': None})
        elif key == 'cost-02' and 'transport.estimated_km' in issues:
            continue
        elif key == 'cost-15' and 'transport.vehicle_count' in issues:
            continue
        elif 'equipment.'+cost_gear.get(key, key) in issues:
            continue
        elif weather_unknown and any(fact['item_key'] == cost_gear.get(key) and fact['required_quantity'] is None for fact in logistics['gear_checklist']):
            continue
        else:
            add('cost.'+key, 'COST_QUANTITY', 'DATA_GAP', 'cost.'+key, item=key, diagnostic=cost)

    if logistics['transport_feasible'] is False:
        vehicles = [row for row in equipment if row['item_key'] == 'vehicle']
        complete = vehicles and all(row.get('confirmed') and row.get('quantity') is not None and row.get('capacity_persons') is not None and row.get('unit') == 'vehicle' for row in vehicles)
        capacity = sum(row['quantity'] * row['capacity_persons'] for row in vehicles) if complete else None
        if transport.get('transport_type') == 'CAR' and capacity is not None and capacity < (profile.get('group_size') or 0):
            add('transport.capacity', 'TRANSPORT_CAPACITY', 'EQUIPMENT_GAP', 'equipment.vehicle.capacity', item='vehicle',
                current=capacity, required=profile.get('group_size'))
        else:
            add('transport.access', 'TRANSPORT_ACCESS', 'EQUIPMENT_GAP', 'transport.transport_type')
    if logistics.get('budget_difference_cents') is not None and logistics['budget_difference_cents'] > 0:
        add('budget', 'OVER_BUDGET', 'USER_INPUT', 'budget_cents', current=logistics['total_cents'],
            required=confirmed.get('requirements', {}).get('budget_cents'))
    blocking_codes = {row['code'] for row in (data.get('eligibility') or {}).get('blocking_reasons', [])}
    if not issues and (logistics['outcome'] != 'PASSED' or logistics['transport_feasible'] is not True or logistics['total_cents'] is None
            or blocking_codes & {'LOGISTICS_INCOMPLETE', 'COSTS_INCOMPLETE', 'ESSENTIAL_GEAR_MISSING', 'TRANSPORT_UNAVAILABLE'}):
        add('logistics.unclassified', 'UNCLASSIFIED', 'DATA_GAP', 'logistics',
            diagnostic={'clarifications': questions, 'outcome': logistics['outcome']})
    for key, roots in dependencies.items():
        for root in roots:
            if root in issues:
                issues[root].setdefault('affects', []).append('equipment.'+key)
    return list(issues.values())
