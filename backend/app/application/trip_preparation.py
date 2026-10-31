"""Public preparation facts projected from saved artifacts only; never a guard."""
from ..agents.rules.transport import POLICY_KEY, POLICY_VERSION


def summary(confirmed, logistics):
    context = confirmed.get('dataset_context') or {}
    if context.get('selection_config', {}).get(POLICY_KEY) != POLICY_VERSION:
        return None
    profile = confirmed.get('profile_snapshot') or {}
    mode = (profile.get('transport') or {}).get('transport_type')
    lines = [row for row in (logistics or {}).get('cost_breakdown', []) if row['category'] == 'TRANSPORT']
    distance = next((row for row in lines if row['item_key'] == 'cost-02'), None)
    from types import SimpleNamespace
    from ..agents.rules.common import meal_mode
    cooking_mode = meal_mode(SimpleNamespace(preferences=(confirmed.get('requirements') or {}).get('preferences', [])))
    return {'system_preparation': True, 'transport_type': mode,
        'origin_label': 'Central Sydney (fixed demonstration origin)',
        'access_and_capacity': (logistics or {}).get('transport_feasible'),
        'estimated_total_vehicle_km': distance.get('quantity') if distance else None,
        'vehicle_count': (profile.get('transport') or {}).get('vehicle_count') if mode == 'CAR' else None,
        'estimated_transport_cents': sum(row['subtotal_cents'] for row in lines)
            if lines and all(row.get('subtotal_cents') is not None for row in lines) else None,
        'meal_mode': cooking_mode,
        'source_refs': [ref for ref in (logistics or {}).get('source_refs', [])
            if ref.get('dataset_file') == 'transport/sydney_city_v1.json'],
    }
