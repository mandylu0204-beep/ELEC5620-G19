"""Approval is a task for complete current evidence, not a blocker override."""
REVIEW_POLICY_VERSION = 'current-evidence-risk-review-1'


def approval_required(assessments, eligibility):
    by_kind = {item['kind']: item['result'] for item in assessments}
    if set(by_kind) != {'LOGISTICS', 'SAFETY'}:
        return False
    triggered = any(item.get('outcome') == 'REVIEW' for item in by_kind.values()) or by_kind['SAFETY'].get('requires_human_review') is True
    return bool(triggered and eligibility and eligibility.get('review_required')
        and not any(reason['code'] != 'REVIEW_REQUIRED' for reason in eligibility['blocking_reasons']))
