"""Non-authoritative cooking preparation; never persists or changes eligibility."""
from decimal import Decimal
from types import SimpleNamespace

from ..agents.rules.common import meal_mode
from ..agents.rules.logistics import GEAR_COSTS, ITEMS, _eval_expression

PREPARATION_VERSION = 'cooking-preparation-1'
COOKING_ITEMS = ('camping_stove', 'fuel_canister')


def inventory(equipment, key):
    rows = [item for item in equipment if item['item_key'] == key]
    valid = bool(rows) and all(item.get('quantity') is not None and item.get('unit') == 'item' for item in rows)
    entered = sum(item['quantity'] for item in rows) if valid else None
    confirmed = entered if valid and all(item.get('confirmed') for item in rows) else None
    return {'item_key': key, 'recorded': bool(rows), 'entered_quantity': entered,
        'confirmed_quantity': confirmed, 'unit_valid': all(item.get('unit') == 'item' for item in rows)}


def outline(requirements, profile):
    if meal_mode(SimpleNamespace(preferences=requirements.get('preferences', []))) != 'SELF_CATERED':
        return None
    return {'scope': 'PREPARATION_ONLY', 'policy_version': PREPARATION_VERSION,
        'official_assessment': False,
        'items': [inventory(profile.get('equipment', []), key) for key in COOKING_ITEMS],
        'fuel_price_status': 'MISSING_REFERENCE' if 'fuel_canister' not in GEAR_COSTS else 'CHECK_REFERENCE',
        'conditional_items': ['fuel_canister']}


def preview(dataset, requirements, equipment):
    value = outline(requirements, {'equipment': equipment})
    if value is None:
        return {'scope': 'PREPARATION_ONLY', 'policy_version': PREPARATION_VERSION,
            'official_assessment': False, 'applicable': False, 'items': [], 'fuel_price_status': 'NOT_APPLICABLE'}
    value.update(applicable=True, dataset_version=dataset.context.dataset_version,
        required_fuel_quantity=None, fuel_gap=None, example=None, calculation_status='UNAVAILABLE')
    if not getattr(dataset, 'has_v2_policy', False):
        return value
    rules = [row for row in dataset.gear_rules if ITEMS.get(row.item_name, (None,))[0] == 'fuel_canister']
    # Do not invent a policy for unsupported/overlapping rules. Formal assess
    # remains authoritative. The deployed package exposes exactly one rule.
    if len(rules) != 1:
        return value
    policy = dataset.get_gear_policy(rules[0].gear_rule_id)
    if policy.get('quantity_unit') != 'item':
        return value

    def required(stoves):
        values = {'stove_count': stoves, 'meal_mode': 'SELF_CATERED'}
        active, missing = _eval_expression(policy['trigger_json'], values)
        if missing or active is not True:
            return None
        quantity, missing = _eval_expression(policy['quantity_json'], values)
        return None if missing or quantity is None else str(Decimal(str(quantity)))

    stove, fuel = value['items']
    example = required(1)
    value['example'] = {'stove_quantity': 1, 'fuel_quantity': example} if example is not None else None
    quantity = required(stove['entered_quantity']) if stove['entered_quantity'] is not None else None
    value['required_fuel_quantity'] = quantity
    value['calculation_status'] = 'DRAFT_ESTIMATE' if quantity is not None else 'WAITING_FOR_STOVE'
    if quantity is not None and fuel['confirmed_quantity'] is not None:
        value['fuel_gap'] = str(max(Decimal(quantity) - Decimal(fuel['confirmed_quantity']), Decimal(0)))
    cost_id = GEAR_COSTS.get('fuel_canister')
    if cost_id:
        reference = dataset.get_cost_reference(cost_id)
        value['fuel_price_status'] = 'REFERENCE_AVAILABLE' if reference.typical_cents is not None else 'MISSING_REFERENCE'
    return value
