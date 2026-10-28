"""Versioned, once-only action correction within the existing turn budget."""
from ..contracts.enums import ErrorCode
from .client import model_failure

POLICY_KEY = 'b_safety_action_feedback'
POLICY_VERSION = 'safety-allowed-action-feedback-1'


def checked_policy(value):
    if value not in {None, POLICY_VERSION}:
        raise model_failure('安全动作反馈策略身份不受支持。', code=ErrorCode.STALE_CONTEXT)
    return value


def correction_result(error, tools, *, compact, policy, turn, max_turns, already_used):
    # Reserve one response for correction and another for an exact final.
    # No repair of syntax, sources, missing findings or host-owned facts.
    if (checked_policy(policy) is None or already_used or turn + 2 > max_turns
            or error.context.get('failure_stage') != 'ACTION_NOT_ALLOWED'):
        return None
    aliases = {value: key for key, value in getattr(tools, '_full_keys', {}).items()}
    constraints = [{('id' if compact else 'finding_key'): aliases[item.finding_key] if compact else item.finding_key,
        'allowed_actions': list(item.allowed_actions)} for item in tools._definitions]
    return {'tool': 'evaluate_safety_plan', 'read_only': True, 'valid': False,
        'error_code': 'ACTION_NOT_ALLOWED', 'action_constraints': constraints,
        'official_checks_unchanged': True, 'advice_is_not_approval': True,
        'instruction': 'The proposal was rejected. Resubmit the COMPLETE proposal using only each finding\'s allowed_actions. '
            'Keep registered facts, all findings and complete priority. Do not finalise this rejected proposal.'}
