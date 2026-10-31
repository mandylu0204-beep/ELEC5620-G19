"""One narrowly scoped envelope correction; never repair or adopt model values."""
from pydantic import ValidationError

from .client import strict_json
from .logistics_schema import LogisticsProposal


READ_ENVELOPE = {'action': 'tool', 'name': 'read_logistics_facts', 'arguments': {}}
EVALUATE_ENVELOPE = {'action': 'tool', 'name': 'evaluate_logistics_plan', 'arguments': {
    'gear_choices': '<choices for every supplied gear item>',
    'cost_priority': '<every required cost-line ID exactly once>',
    'decision_summary': '<brief summary>',
}}
FINAL_ENVELOPE = {'action': 'final', 'proposal': '<copy evaluated_proposal exactly>'}


def misplaced_evaluation_name(text):
    """Recognize only the known nesting mistake, not arbitrary malformed JSON.

    The parsed proposal is used solely to recognize the envelope. It is never
    returned, moved into a different object, evaluated or accepted here.
    """
    try:
        # Match the parser's existing whitespace/fenced-JSON handling exactly.
        stripped = text.strip()
        if stripped.startswith('```json\n') and stripped.endswith('\n```'):
            stripped = stripped[8:-4]
        value = strict_json(stripped)
        if (not isinstance(value, dict) or set(value) != {'action', 'arguments'}
                or value['action'] != 'tool' or not isinstance(value['arguments'], dict)
                or set(value['arguments']) != {'name', 'gear_choices', 'cost_priority', 'decision_summary'}
                or value['arguments']['name'] != 'evaluate_logistics_plan'):
            return False
        LogisticsProposal.model_validate({key: item for key, item in value['arguments'].items() if key != 'name'})
        return True
    except (ValueError, TypeError, RecursionError, ValidationError):
        return False


def correction_instruction():
    # Fixed host text only. Never echo the rejected reply or unknown field names.
    return {
        'kind': 'LOGISTICS_FORMAT_CORRECTION',
        'errors': [{'path': '$.name', 'type': 'missing'},
                   {'path': '$.arguments.name', 'type': 'extra_forbidden'}],
        'instruction': 'Return a fresh complete evaluation action. Put name beside action, '
            'outside arguments. arguments contains only gear_choices, cost_priority and '
            'decision_summary. Use the previously supplied facts and allowed choices. '
            'Do not skip evaluation or change confirmed inputs. Replace template placeholders '
            'with actual values. This is the only format correction; all original checks apply.',
        'next_action': EVALUATE_ENVELOPE,
    }
