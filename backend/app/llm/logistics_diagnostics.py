"""Bounded structural diagnostics only: never model text or profile values."""
import json
from collections import Counter
import re

from .client import model_failure
from ..contracts.enums import ErrorCode

VERSION = 'logistics-structural-diagnostics-1'
_FIELDS = frozenset({'action', 'name', 'arguments', 'proposal', 'gear_choices',
    'cost_priority', 'decision_summary', 'item_key', 'method', 'reason'})
_BRANCHES = frozenset({'ReadFactsAction', 'EvaluateAction', 'FinalLogisticsAction'})
_TYPES = frozenset({'missing', 'extra_forbidden', 'literal_error', 'list_type',
    'string_type', 'string_too_long', 'string_too_short', 'too_long', 'too_short',
    'model_type', 'dict_type', 'json_invalid', 'duplicate_key', 'nonfinite_json',
    'invalid_json_value', 'recursion_limit', 'blank_explanation'})


def safe_path(location):
    parts = []
    for part in location[:10]:
        if isinstance(part, str) and part in _BRANCHES:
            continue
        if type(part) is int:
            parts.append(f'[{part}]' if 0 <= part <= 1024 else '[*]')
        else:
            parts.append('.'+(part if part in _FIELDS else '<extra_field>'))
    return '$'+''.join(parts)


def protocol_failure(stage, errors, *, line=None, column=None):
    issues = [{'path': safe_path(error.get('loc', ())),
        'type': error['type'] if error.get('type') in _TYPES else 'schema_error'} for error in errors[:8]]
    failure = model_failure('The model equipment proposal does not match the controlled  JSON  protocol. No proposal was adopted.', code=ErrorCode.CONTRACT_INVALID)
    context = {**failure.error.context, 'diagnostic_version': VERSION,
        'failure_stage': stage, 'validation_errors': json.dumps(issues, ensure_ascii=True, separators=(',', ':'))}
    if type(line) is int and type(column) is int:
        context.update(json_line=str(min(max(line, 1), 262144)), json_column=str(min(max(column, 1), 262144)))
    return type(failure)(failure.error.model_copy(update={'context': context}))


def schema_errors(exc, value):
    # Union validation includes failures for unrelated envelopes. Report only
    # the selected, known envelope when possible, not those distracting errors.
    branch = None
    if isinstance(value, dict):
        if value.get('action') == 'final':
            branch = 'FinalLogisticsAction'
        elif value.get('action') == 'tool':
            branch = {'read_logistics_facts': 'ReadFactsAction',
                'evaluate_logistics_plan': 'EvaluateAction'}.get(value.get('name')) if isinstance(value.get('name'), str) else None
    errors = exc.errors(include_input=False, include_context=False, include_url=False)
    if branch:
        selected = [error for error in errors if error['loc'] and error['loc'][0] == branch]
        if selected:
            errors = selected
    return errors


def cost_priority_failure(expected, provided):
    """Report host-owned IDs only; never echo an invented model/user value."""
    from ..agents.rules.logistics import ITEMS
    known_items = {item[0] for item in ITEMS.values()}
    def safe_id(value):
        if re.fullmatch(r'line-(?:0|[1-9][0-9]{0,2})', value) and int(value[5:]) < 128:
            return value
        if value.startswith('unpriced-') and value[9:] in known_items:
            return value
        return '<redacted_id>'
    counts = Counter(provided)
    expected_set = set(expected)
    missing = [key for key in expected if key not in counts]
    duplicate = [key for key in expected if counts[key] > 1]
    unexpected = [index for index,key in enumerate(provided) if key not in expected_set]
    detail = {'expected_count':len(expected),'provided_count':len(provided),
        'missing_count':len(missing),'missing_ids':[safe_id(key) for key in missing[:16]],
        'duplicate_count':sum(count-1 for count in counts.values() if count > 1),
        'duplicated_expected_ids':[safe_id(key) for key in duplicate[:16]],
        'unexpected_count':len(unexpected),'unexpected_positions':unexpected[:16],
        'details_truncated':len(missing)>16 or len(duplicate)>16 or len(unexpected)>16}
    failure = model_failure('Model cost priorities must include every original cost row and cannot remove required costs.',code=ErrorCode.CONTRACT_INVALID)
    return type(failure)(failure.error.model_copy(update={'context':{
        **failure.error.context,'diagnostic_version':VERSION,'failure_stage':'COST_PRIORITY_COVERAGE',
        'cost_priority_diagnostics':json.dumps(detail,ensure_ascii=True,separators=(',',':'))}}))
