"""Dataset import boundary; never reads tests/oracles or creates workflow outcomes."""
import copy
import csv
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUEST_KEYS = ('request_id', 'profile_id', 'natural_language_request', 'user_supplements',
                'supplement_provenance', 'profile_snapshot', 'source_type', 'source_name',
                'source_date', 'demo_only')
SAFETY_KEYS = ('safety_case_id', 'campsite_id', 'scenario_date', 'weather', 'fire',
               'road_access', 'campsite_restrictions', 'risk_tags', 'mandatory_blockers',
               'evidence_facts', 'evidence_facts_provenance', 'valid_from', 'valid_until',
               'template_source_id', 'context_request_id', 'source_type', 'source_name',
               'source_date', 'demo_only')

def request_agent_input(record):
    return {k: copy.deepcopy(record[k]) for k in REQUEST_KEYS}

def safety_agent_input(record):
    return {k: copy.deepcopy(record[k]) for k in SAFETY_KEYS}

def load_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding='utf-8'))

def load_csv(relative_path, boolean_fields=(), integer_fields=(), number_fields=(), list_fields=(), json_fields=()):
    """Strict conversion: bool('false') would be incorrect; missing is not zero."""
    with (ROOT / relative_path).open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('Malformed CSV row')
        for field in boolean_fields:
            if row[field] not in ('true', 'false'):
                raise ValueError('Invalid boolean: ' + field)
            row[field] = row[field] == 'true'
        for field in integer_fields:
            row[field] = int(row[field]) if row[field] != '' else None
        for field in number_fields:
            try:
                row[field] = Decimal(row[field]) if row[field] != '' else None
            except InvalidOperation as exc:
                raise ValueError('Invalid decimal: ' + field) from exc
        for field in list_fields:
            row[field] = row[field].split(';') if row[field] else []
        for field in json_fields:
            row[field] = json.loads(row[field])
    return rows

def expression_variables(expr):
    if not isinstance(expr, dict):
        return set()
    if 'var' in expr:
        return {expr['var']}
    return set().union(*(expression_variables(x) for args in expr.values() for x in args))

def evaluate(expr, context):
    """Small declarative DSL. Returns (value, missing_fields); no eval or defaults."""
    if not isinstance(expr, dict):
        return expr, set()
    if 'var' in expr:
        key = expr['var']
        return (context[key], set()) if context.get(key) is not None else (None, {key})
    if len(expr) != 1:
        raise ValueError('Expression must have one operator')
    operator, args = next(iter(expr.items()))
    evaluated = [evaluate(a, context) for a in args]
    missing = set().union(*(m for _, m in evaluated))
    if missing:
        return None, missing
    values = [v for v, _ in evaluated]
    if operator == 'mul':
        result = 1
        for value in values:
            result *= value
    elif operator == 'add': result = sum(values)
    elif operator == 'sub': result = values[0] - values[1]
    elif operator == 'eq': result = values[0] == values[1]
    elif operator == 'lt': result = values[0] < values[1]
    elif operator == 'lte': result = values[0] <= values[1]
    elif operator == 'gt': result = values[0] > values[1]
    elif operator == 'gte': result = values[0] >= values[1]
    elif operator == 'and': result = all(values)
    elif operator == 'or': result = any(values)
    else: raise ValueError('Unsupported operator: ' + operator)
    return result, set()

def required_gear(rules, context):
    """Returns quantities and missing inputs; actual Agent assessment is separate."""
    requirements, missing = {}, set()
    for rule in rules:
        triggered, unknown = evaluate(rule['trigger_json'], context)
        missing.update(unknown)
        if not triggered:
            continue
        qty, unknown = evaluate(rule['quantity_json'], context)
        missing.update(unknown)
        if qty is not None:
            key = (rule['item_key'], rule['quantity_unit'])
            requirements[key] = max(requirements.get(key, 0), qty)
    return requirements, sorted(missing)

def estimate_cost(costs, campsite, context):
    """Reference arithmetic in integer cents; missing inputs never produce a full total."""
    lines, missing = [], set()
    for cost in costs:
        cid = cost['cost_id']
        if cid == 'cost-01':
            rate = campsite['nightly_fee_aud']
        else:
            rate = cost['typical_aud']
        if cid in ('cost-02', 'cost-15') and context.get('transport_type') == 'PUBLIC_TRANSPORT':
            continue
        if cid == 'cost-03' and context.get('transport_type') == 'CAR':
            continue
        if cid == 'cost-04' and context.get('meal_mode') == 'READY_TO_EAT':
            continue
        if cid == 'cost-14' and context.get('meal_mode') == 'SELF_CATERED':
            continue
        if cid in ('cost-02','cost-03','cost-15') and context.get('transport_type') not in ('CAR','PUBLIC_TRANSPORT'):
            missing.add('transport_type'); continue
        if cid in ('cost-04','cost-14') and context.get('meal_mode') not in ('SELF_CATERED','READY_TO_EAT'):
            missing.add('meal_mode'); continue
        quantity, unknown = evaluate(cost['quantity_json'], context)
        missing.update(unknown)
        if quantity is not None:
            amount_cents = (Decimal(str(quantity)) * Decimal(str(rate)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            rate_cents = (Decimal(str(rate)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            lines.append(dict(cost_id=cid, quantity=quantity, rate_aud=str(rate),
                              rate_cents=int(rate_cents), amount_cents=int(amount_cents),
                              amount_aud=int(amount_cents) / 100))
    subtotal_cents = sum(x['amount_cents'] for x in lines)
    subtotal = subtotal_cents / 100
    return dict(lines=lines, partial_subtotal_cents=subtotal_cents, partial_subtotal_aud=subtotal,
                total_cents=None if missing else subtotal_cents,
                total_aud=None if missing else subtotal,
                missing_inputs=sorted(missing), assumption='Typical synthetic rates; no live quotes.')

if __name__ == '__main__':
    requests = [request_agent_input(r) for r in load_json('data/synthetic_requests.json')]
    evidence = [safety_agent_input(s) for s in load_json('data/synthetic_safety_scenarios.json')]
    print(json.dumps({'runtime_request_count': len(requests), 'runtime_evidence_count': len(evidence),
                      'oracles_loaded': False}))
