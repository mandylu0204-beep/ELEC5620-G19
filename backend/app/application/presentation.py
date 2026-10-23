"""Role-scoped HTTP views only. Never used by storage, replay or eligibility."""
from copy import deepcopy

# Public location-display identity only. This is not a model/runtime capability
# and never exposes the registered configuration or its file-digest mapping.
SYDNEY_CATALOGUE_ID = 'sydney-surrounds-2.2-2026-10-23'
SYDNEY_CATALOGUE_DIGEST = '6eea5205281d41e308e5a0cc8f2c0225b6a3b685ad990579ab6f20c7ae04b8fe'


def tent_capacity(profile, logistics):
    """Display the saved records alongside the authoritative person-space gap."""
    rows = []
    for item in (profile or {}).get('equipment', []):
        if item['item_key'] != 'tent':
            continue
        count, capacity = item.get('quantity'), item.get('capacity_persons')
        rows.append({'quantity': count, 'capacity_per_tent': capacity,
            'total_capacity': count * capacity if count is not None and capacity is not None and item.get('unit') == 'item' else None,
            'confirmed': item.get('confirmed', False), 'unit': item.get('unit')})
    fact = next((v for v in (logistics or {}).get('gear_checklist', []) if v['item_key'] == 'tent'), None)
    return {'records': rows, 'group_size': (profile or {}).get('group_size'),
        'registered_tent_count': sum(r['quantity'] for r in rows) if rows and all(r['quantity'] is not None and r['unit'] == 'item' for r in rows) else None,
        'registered_capacity': sum(r['total_capacity'] for r in rows) if rows and all(r['total_capacity'] is not None for r in rows) else None,
        # These come from the saved assessment, not a recalculation of its rules.
        'assessed_capacity': fact.get('available_quantity') if fact and fact.get('unit') == 'person_space' else None,
        'required_person_spaces': fact.get('required_quantity') if fact and fact.get('unit') == 'person_space' else None,
        'missing_person_spaces': fact.get('missing_quantity') if fact and fact.get('unit') == 'person_space' else None}


def display_status(run_status, version_status, logistics=None, safety=None, issues=()):
    """A label only; it cannot grant/revoke any operation."""
    if run_status in {'PENDING', 'RUNNING', 'FAILED', 'CANCELLED'}:
        return run_status
    if version_status == 'FINALISED':
        return 'FINALISED'
    physical = {'ROAD_CLOSED', 'CAMPSITE_CLOSED', 'FIRE_PROHIBITED', 'HARD_CONSTRAINT'}
    road_closed = safety and any(v.get('kind') == 'ROAD' and v.get('road_state') == 'CLOSED'
        for v in safety.get('evidence', []))
    if road_closed or any(v['code'] in physical for result in (logistics, safety) if result for v in result.get('mandatory_blockers', [])):
        return 'CANNOT_RELEASE'
    if any(v['category'] == 'USER_INPUT' and v['code'] != 'OVER_BUDGET' for v in issues):
        return 'NEEDS_USER_INPUT'
    if any(v['category'] == 'DATA_GAP' for v in issues) or safety and any(v != 'AVAILABLE' for v in safety.get('data_quality', {}).values()):
        return 'NEEDS_EVIDENCE'
    if issues or logistics and logistics.get('outcome') != 'PASSED' or version_status in {'REVISION_REQUIRED', 'REJECTED'}:
        return 'NEEDS_REVISION'
    if safety and safety.get('requires_human_review') and version_status != 'ELIGIBLE_FOR_FINALISATION':
        return 'AWAITING_REVIEW'
    return version_status


_PUBLIC_AUDIT = {'audit_contract_version', 'audit_id', 'kind', 'run_id', 'plan_id', 'plan_version_id',
    'assessment_id', 'gear_checklist_id', 'depends_on_assessment_id', 'input_fingerprint', 'plan'}
_PUBLIC_ERROR_CONTEXT = {'plan_id', 'plan_version_id', 'run_id', 'stage', 'operation'}


def request_response(value):
    """Confirmed-request reads must not become a runtime-configuration side door."""
    data = deepcopy(value)
    from .cooking_preparation import outline
    requirements = ((data.get('confirmed_context') or {}).get('requirements')
        or (data.get('summary') or {}).get('extracted_requirements') or data.get('explicit_fields') or {})
    data['cooking_preparation'] = outline(requirements, (data.get('confirmed_context') or {}).get('profile_snapshot') or data.get('profile_snapshot') or {})
    confirmed = data.get('confirmed_context')
    if confirmed and 'dataset_context' in confirmed:
        confirmed['dataset_context'] = {key: val for key, val in confirmed['dataset_context'].items()
            if key == 'dataset_version'}
    return data


def _view(value, diagnostics_allowed):
    data = deepcopy(value)
    from .cooking_preparation import outline
    confirmed = data.get('confirmed_context') or {}
    source = confirmed.get('dataset_context') or {}
    if (source.get('dataset_version') == '2.2.0' and
            source.get('file_digests', {}).get('source_catalogue.json') == SYDNEY_CATALOGUE_DIGEST):
        data['campsite_catalogue_id'] = SYDNEY_CATALOGUE_ID
    else:
        data.pop('campsite_catalogue_id', None)
    data['cooking_preparation'] = outline(confirmed.get('requirements') or {}, confirmed.get('profile_snapshot') or {})
    planning = data.pop('model_planning_trace', None)
    audits = data.get('model_assessment_audits') or {}
    diagnostics = {'planning': planning,
        'assessments': {key: {k: v for k, v in audit.items() if k != 'plan'} for key, audit in audits.items()}}
    data['model_assessment_audits'] = {key: {k: v for k, v in audit.items() if k in _PUBLIC_AUDIT} for key, audit in audits.items()}
    data['planning_explanation'] = None if not planning else {
        'source_run_id': planning['run_id'],
        'selected_campsite_id': planning['trace']['selected_campsite_id'],
        'decision_summary_unverified': planning['trace']['decision_summary']}
    confirmed = data.get('confirmed_context')
    if confirmed and 'dataset_context' in confirmed:
        diagnostics['dataset_context'] = confirmed['dataset_context']
        confirmed['dataset_context'] = {key: val for key, val in confirmed['dataset_context'].items()
            if key == 'dataset_version'}
    logistics = next((v['result'] for v in data.get('assessments', []) if v['kind'] == 'LOGISTICS'), None)
    data['tent_capacity'] = tent_capacity((confirmed or {}).get('profile_snapshot'), logistics)
    safety = next((v['result'] for v in data.get('assessments', []) if v['kind'] == 'SAFETY'), None)
    data['display_status'] = display_status((data.get('run') or {}).get('status'),
        (data.get('version') or {}).get('status', data.get('status')), logistics, safety,
        data.get('logistics_issues', []))
    if not diagnostics_allowed:
        for item in [data.get('run'), *data.get('events', [])]:
            if item and item.get('error') and 'context' in item['error']:
                item['error']['context'] = {key: val for key, val in item['error']['context'].items() if key in _PUBLIC_ERROR_CONTEXT}
    data['can_view_model_diagnostics'] = diagnostics_allowed
    if diagnostics_allowed:
        data['model_diagnostics'] = diagnostics
    return data


def plan_response(data, user):
    # No caller/query/header flag can grant this permission. Current application
    # has no developer role; Founder is the existing authorised review role.
    allowed = user.role == 'FOUNDER'
    if 'final_record' in data:
        result = deepcopy(data)
        result['final_record'] = _view(data['final_record'], allowed)
        # Historical issues are computed from that immutable saved snapshot only.
        from .logistics_issues import project
        record = result['final_record']
        record['logistics_issues'] = project({**record, 'plan': {
            'plan_id': record['version_context']['plan_id'],
            'request_id': record['confirmed_context']['request_id']}})
        return result
    return _view(data, allowed)
