"""Canonical request terms and confirmation checks, independent of any model.

These aliases are a convenience for structured/legacy input, not a prose
interpreter. Free text is understood by the opt-in Planning request interpreter.
Unknown hard conditions must be clarified before a request can be confirmed.
"""
import re

from ...contracts.dto import Clarification
from ...contracts.enums import FieldErrorCode
from ...contracts.errors import FieldError

REQUEST_TERMS_VERSION = 'request-terms-1'

HARD_TERMS = frozenset({
    'toilets', 'potable_water', 'showers', 'fire_allowed', 'campfire',
    'pets_allowed', 'wheelchair_accessible', 'vehicle_access',
    'public_transport_access', 'no_fires', 'walk_in_only',
})
SOFT_TERMS = frozenset({
    'quiet', 'toilets', 'showers', 'potable water', 'public transport',
    'wheelchair accessible', 'campfire', 'pets', 'ready-to-eat meals',
    'self-catered meals',
})




# English labels plus unchanged legacy input aliases.
_SOFT_ALIASES = {'quiet': ('\u5b89\u9759', '\u5b89\u9759\u7684\u73af\u5883', '\u5b89\u9759\u7684\u5730\u65b9', '\u6e05\u9759', 'quiet', 'quiet surroundings', 'quiet place'), 'toilets': ('\u5395\u6240', '\u536b\u751f\u95f4', 'toilet', 'toilets'), 'showers': ('\u6dcb\u6d74', '\u6d17\u6fa1', '\u53ef\u4ee5\u6d17\u6fa1', 'shower', 'showers', 'showers available'), 'potable water': ('\u996e\u7528\u6c34\u8bbe\u65bd', '\u996e\u7528\u6c34', 'potable_water', 'drinking-water facilities', 'drinking water'), 'public transport': ('\u516c\u5171\u4ea4\u901a', 'public_transport_access', 'public transport'), 'wheelchair accessible': ('\u8f6e\u6905\u901a\u884c', 'wheelchair_accessible', 'wheelchair access'), 'campfire': ('\u8425\u706b', '\u7bdd\u706b', 'fire_allowed', 'campfire'), 'pets': ('\u643a\u5e26\u5ba0\u7269', '\u5ba0\u7269', 'pets_allowed', 'bring pets', 'pets'), 'ready-to-eat meals': ('\u5373\u98df\u9910\u98df', '\u5373\u98df\u98df\u54c1', '\u65e0\u9700\u70f9\u996a\u7684\u9910\u98df', 'ready_to_eat', 'ready-to-eat', 'ready-to-eat meals', 'ready-to-eat food', 'meals requiring no cooking'), 'self-catered meals': ('\u81ea\u884c\u70f9\u996a', '\u81ea\u5df1\u505a\u996d', 'self_catered', 'self-catered', 'self-catered meals', 'cook own meals')}
_HARD_ALIASES = {'toilets': ('\u5395\u6240', '\u536b\u751f\u95f4', 'toilet', 'toilets'), 'showers': ('\u6dcb\u6d74', '\u6d17\u6fa1', '\u53ef\u4ee5\u6d17\u6fa1', 'shower', 'showers', 'showers available'), 'potable_water': ('\u996e\u7528\u6c34\u8bbe\u65bd', '\u996e\u7528\u6c34', 'potable water', 'drinking-water facilities', 'drinking water'), 'wheelchair_accessible': ('\u8f6e\u6905\u901a\u884c', 'wheelchair access', 'wheelchair accessible'), 'fire_allowed': ('\u5141\u8bb8\u8425\u706b', '\u5141\u8bb8\u751f\u706b', 'campfires allowed', 'fires allowed'), 'campfire': ('\u8425\u706b', '\u7bdd\u706b', 'campfire'), 'no_fires': ('\u4e0d\u751f\u706b', '\u4e0d\u4f7f\u7528\u8425\u706b', '\u7981\u6b62\u8425\u706b', '\u4e0d\u8981\u751f\u706b', 'no campfires', 'no campfire', 'no fires', 'campfires prohibited'), 'pets_allowed': ('\u5141\u8bb8\u643a\u5e26\u5ba0\u7269', '\u643a\u5e26\u5ba0\u7269', 'pets allowed', 'bring pets'), 'vehicle_access': ('\u8f66\u8f86\u53ef\u8fbe', 'vehicle access'), 'public_transport_access': ('\u516c\u5171\u4ea4\u901a\u53ef\u8fbe', '\u516c\u5171\u4ea4\u901a', 'public transport access', 'public transport'), 'walk_in_only': ('\u4ec5\u53ef\u6b65\u884c\u8fdb\u5165', 'walk-in only', 'walk-in access only')}

def _clean(value):
    return re.sub(r'\s+', ' ', value.strip().casefold()).rstrip('。.!！')


def canonical_term(text, kind):
    """Recognise complete, unambiguous structured labels only.

    Never reduce modifiers such as hot/private showers, negation, a conjunction
    or an unknown facility to a less restrictive condition.
    """
    value = _clean(text)
    aliases = _HARD_ALIASES if kind == 'constraint' else _SOFT_ALIASES
    for canonical, labels in aliases.items():
        if value == canonical or value in labels:
            return canonical
    prefixes = (('必须有', '必须', '需要有', '需要', '一定要有', '一定要',
                 'must have ', 'requires ', 'require ', 'need ', 'needs ')
                if kind == 'constraint' else ('希望有', '希望', '最好有', '最好', 'prefer ', 'preferably '))
    for prefix in prefixes:
        if value.startswith(prefix):
            suffix = value[len(prefix):].strip()
            suffix = re.sub(r'^an?\s+', '', suffix)
            for canonical, labels in aliases.items():
                if suffix == canonical or suffix in labels:
                    return canonical
    return None


def _unique(values, kind):
    result = []
    for value in values:
        if not value.strip():
            continue
        item = canonical_term(value, kind) or value.strip()
        if item not in result:
            result.append(item)
    return result


def merge_explicit_terms(preferences, constraints, explicit):
    """Merge semantic items; an empty text box never erases prose requirements.

    Keep unknown phrases, so the hard-condition validator can explain them and
    unverified soft preferences remain visible for user confirmation.
    """
    return (
        _unique([*preferences, *explicit.preferences], 'preference'),
        _unique([*constraints, *explicit.mandatory_constraints], 'constraint'),
    )


def term_issues(preferences, constraints, *, require_meal=True):
    errors, questions = [], []

    def issue(field, code, question, reason):
        errors.append(FieldError(field=field, code=code, message=question))
        questions.append(Clarification(field=field, question=question, reason=reason))

    for value in constraints:
        if value not in HARD_TERMS:
            issue('mandatory_constraints', FieldErrorCode.UNSUPPORTED,
                  f'Cannot verify required condition: {value}. Specify the facilities needed, or move this to preferences and regenerate the summary.',
                  'The condition meaning or source sufficiency is unconfirmed. It cannot directly be treated as met.')
    if 'no_fires' in constraints and {'campfire', 'fire_allowed'} & set(constraints):
        issue('mandatory_constraints', FieldErrorCode.CONFLICTING,
              'Fires must be allowed conflicts with No fires. Choose the actual arrangement for this trip.',
              'Conflicting required conditions cannot be resolved automatically for you.')
    meals = set(preferences)
    ready = bool(meals & {'ready-to-eat meals', 'ready_to_eat'})
    cooked = bool(meals & {'self-catered meals', 'self_catered'})
    if ready and cooked:
        issue('preferences', FieldErrorCode.CONFLICTING,
              'Both ready-to-eat and self-catered meals were selected. Choose one arrangement for this trip.',
              'Food costs and cooking equipment must use the same confirmed meal arrangement.')
    elif require_meal and not (ready or cooked):
        issue('preferences', FieldErrorCode.MISSING,
              'Choose a meal arrangement: ready-to-eat or self-catered meals.',
              'Specify how food costs and cooking equipment should be calculated before confirming requirements.')
    return errors, questions
