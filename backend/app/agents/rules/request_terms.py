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

_SOFT_ALIASES = {
    'quiet': ('安静', '安静的环境', '安静的地方', '清静'),
    'toilets': ('厕所', '卫生间', 'toilet'),
    'showers': ('淋浴', '洗澡', '可以洗澡', 'shower'),
    'potable water': ('饮用水设施', '饮用水', 'potable_water'),
    'public transport': ('公共交通', 'public_transport_access'),
    'wheelchair accessible': ('轮椅通行', 'wheelchair_accessible'),
    'campfire': ('营火', '篝火', 'fire_allowed'),
    'pets': ('携带宠物', '宠物', 'pets_allowed'),
    'ready-to-eat meals': ('即食餐食', '即食食品', '无需烹饪的餐食', 'ready_to_eat', 'ready-to-eat'),
    'self-catered meals': ('自行烹饪', '自己做饭', 'self_catered', 'self-catered'),
}
_HARD_ALIASES = {
    'toilets': ('厕所', '卫生间', 'toilet'),
    'showers': ('淋浴', '洗澡', '可以洗澡', 'shower'),
    'potable_water': ('饮用水设施', '饮用水', 'potable water'),
    'wheelchair_accessible': ('轮椅通行', 'wheelchair access', 'wheelchair accessible'),
    'fire_allowed': ('允许营火', '允许生火'),
    'campfire': ('营火', '篝火'),
    'no_fires': ('不生火', '不使用营火', '禁止营火', '不要生火', 'no campfires', 'no campfire', 'no fires'),
    'pets_allowed': ('允许携带宠物', '携带宠物', 'pets allowed'),
    'vehicle_access': ('车辆可达', 'vehicle access'),
    'public_transport_access': ('公共交通可达', '公共交通', 'public transport access', 'public transport'),
    'walk_in_only': ('仅可步行进入', 'walk-in only'),
}


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
                  f'无法核实必须条件“{value}”。请说明具体需要的设施，或将它调整为偏好后重新生成摘要。',
                  '尚未确认这项条件的含义或营地资料是否足以验证，不能直接作为已满足条件。')
    if 'no_fires' in constraints and {'campfire', 'fire_allowed'} & set(constraints):
        issue('mandatory_constraints', FieldErrorCode.CONFLICTING,
              '“必须能生火”和“不生火”存在冲突，请选择本次行程实际需要的安排。',
              '相互冲突的必须条件不能自动替你取舍。')
    meals = set(preferences)
    ready = bool(meals & {'ready-to-eat meals', 'ready_to_eat'})
    cooked = bool(meals & {'self-catered meals', 'self_catered'})
    if ready and cooked:
        issue('preferences', FieldErrorCode.CONFLICTING,
              '用餐方式同时包含即食餐食和自行烹饪，请明确本次采用哪一种。',
              '餐食费用和烹饪装备需要按同一种已确认安排检查。')
    elif require_meal and not (ready or cooked):
        issue('preferences', FieldErrorCode.MISSING,
              '请选择用餐方式：即食餐食或自行烹饪。',
              '确认需求前，需要明确餐食费用和烹饪装备的计算方式。')
    return errors, questions
