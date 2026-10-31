"""Bounded host-owned finding/action metadata; never advice, facts or prompts."""
import json
import re
from typing import get_args

from ..contracts.enums import ErrorCode
from .client import model_failure
from .safety_schema import ActionCode

VERSION = 'safety-structural-diagnostics-1'
_ACTIONS = frozenset(get_args(ActionCode))
_MESSAGES = {
    'PROPOSAL_SCHEMA': 'Safety model proposal failed structural validation. It was not adopted.',
    'FINDING_COVERAGE': 'Safety model proposal does not cover all safety issues. It was not adopted.',
    'FACT_IDENTITY': 'Safety model proposal references a different data identity. It was not adopted.',
    'ACTION_NOT_ALLOWED': 'Safety model selected an unsupported action for a safety issue. It was not adopted.',
    'FACT_BINDING': 'Safety issue source links failed validation. Contact the developer.',
    'PLAN_VALIDATION': 'Safety suggestion completeness validation failed. The proposal was not adopted.',
}


def proposal_failure(stage, *, expected=(), provided=(), finding=None, actual=None, allowed=(), aliases=None, run_id=None):
    """Emit only registered identifiers; unrecognised model values are redacted."""
    def safe_id(value):
        return value if isinstance(value, str) and re.fullmatch(r'finding-[0-9a-f]{64}', value) else '<redacted_id>'
    detail = {'reason': stage}
    if stage == 'FINDING_COVERAGE':
        registered, received = set(expected), set(provided)
        missing = sorted(registered - received)
        detail.update(expected_count=len(expected), provided_count=len(provided),
            missing_count=len(missing), missing_ids=[safe_id(key) for key in missing[:16]],
            unexpected_count=len(received - registered), duplicate_count=len(provided) - len(received),
            details_truncated=len(missing) > 16)
    if finding is not None:
        detail['finding_id'] = safe_id(finding)
        alias = next((key for key, value in (aliases or {}).items() if value == finding), None)
        if isinstance(alias, str) and re.fullmatch(r'f(?:[0-9]|[1-5][0-9]|6[0-3])', alias):
            detail['compact_id'] = alias
    if stage == 'ACTION_NOT_ALLOWED':
        detail.update(actual_action=actual if actual in _ACTIONS else '<redacted_action>',
            allowed_actions=[item for item in allowed if item in _ACTIONS][:8])
    failure = model_failure(_MESSAGES[stage], code=ErrorCode.CONTRACT_INVALID)
    context = {**failure.error.context, 'diagnostic_version': VERSION, 'failure_stage': stage,
        'safety_validation_diagnostics': json.dumps(detail, ensure_ascii=True, separators=(',', ':'))}
    if isinstance(run_id, str) and re.fullmatch(r'[0-9a-f]{32}', run_id):
        context['run_id'] = run_id
    return type(failure)(failure.error.model_copy(update={'context': context}))
