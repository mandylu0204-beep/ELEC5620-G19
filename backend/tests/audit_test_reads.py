"""Explicit internal audit access for storage/orchestration integration tests.

HTTP no longer returns private traces to Camper. Assert that boundary first,
then read authorised internal services for the existing persistence assertions.
This helper is NOT used by the public projection/permission tests.
"""
from functools import wraps

from app.auth import User

CAMPER = User('camper-a', 'camper.a', 'Camper A', 'CAMPER')


class InternalAuditView(dict):
    """Mark an explicitly augmented test view, never an HTTP JSON response."""


def stored(data, client):
    if isinstance(data, InternalAuditView):
        return data
    if not isinstance(data, dict):
        return data
    if 'final_record' in data:
        record = data['final_record']
        if isinstance(record, InternalAuditView):
            return data
        assert 'model_planning_trace' not in record
        assert not record['can_view_model_diagnostics'] and 'model_diagnostics' not in record
        raw = client.app.state.finalisation.detail(CAMPER, record['version_context']['plan_id'], record['final_id'])
        return {**data, 'final_record': InternalAuditView(raw['final_record'])}
    if 'plan' in data and 'run' in data:
        assert 'model_planning_trace' not in data
        if data['can_view_model_diagnostics']:
            assert 'model_diagnostics' in data  # Authorised Founder review response.
            return data
        assert not data['can_view_model_diagnostics'] and 'model_diagnostics' not in data
        for audit in data.get('model_assessment_audits', {}).values():
            assert not {'trace', 'configuration_fingerprint', 'attempt_id'} & audit.keys()
        raw = client.app.state.plan_queries.detail(CAMPER, data['plan']['plan_id'],
            (data.get('run') or {}).get('run_id'))
        return InternalAuditView({**data, 'confirmed_context': raw['confirmed_context'],
            'model_planning_trace': raw.get('model_planning_trace'),
            'model_assessment_audits': raw.get('model_assessment_audits', {})})
    return data


def json_with_internal_audits(client, response):
    return stored(response.json(), client)


def internal_audit_reads(function):
    if getattr(function, '_reads_internal_audits', False):
        return function
    @wraps(function)
    def read(client, *args, **kwargs):
        value = function(client, *args, **kwargs)
        if isinstance(value, tuple):  # finalise() returns (path, saved snapshot).
            path, snapshot = value
            return path, stored({'final_record': snapshot}, client)['final_record']
        return stored(value, client)
    read._reads_internal_audits = True
    return read
