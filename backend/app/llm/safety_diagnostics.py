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
    'PROPOSAL_SCHEMA': '安全模型方案结构校验未通过；未采纳该方案。',
    'FINDING_COVERAGE': '安全模型方案未完整覆盖本次安全事项；未采纳该方案。',
    'FACT_IDENTITY': '安全模型方案引用的数据身份不一致；未采纳该方案。',
    'ACTION_NOT_ALLOWED': '安全模型为某项安全问题选择了不适用的处理动作；未采纳该方案。',
    'FACT_BINDING': '安全事项的来源关联校验未通过，请联系开发负责人。',
    'PLAN_VALIDATION': '安全建议完整性校验未通过；未采纳该方案。',
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
