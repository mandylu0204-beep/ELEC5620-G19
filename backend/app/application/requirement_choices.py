"""Read-only choices derived from the host's existing finite request vocabulary."""
from ..agents.rules.request_terms import canonical_term, _HARD_ALIASES, _SOFT_ALIASES

CHOICES_VERSION = 'structured-request-choices-1'
LABELS = {
    'preferences': {'quiet':'安静的环境','toilets':'厕所','showers':'淋浴','potable water':'饮用水设施',
        'public transport':'公共交通可达','wheelchair accessible':'轮椅通行','campfire':'营火','pets':'允许携带宠物'},
    'mandatory_constraints': {'toilets':'必须有厕所','showers':'必须有淋浴','potable_water':'必须有饮用水设施',
        'wheelchair_accessible':'必须能轮椅通行','fire_allowed':'必须允许生火','no_fires':'不使用营火',
        'pets_allowed':'必须允许携带宠物','vehicle_access':'必须车辆可达',
        'public_transport_access':'必须公共交通可达','walk_in_only':'仅可步行进入'},
    'accessibility_requirements': {'step-free path':'需要无台阶通道','wheelchair access':'需要轮椅通行',
        'wheelchair-accessible toilet':'需要无障碍厕所'},
}
ACCESS_ALIASES = {'step-free path':['无台阶通道','需要无台阶通道'],
    'wheelchair access':['轮椅通行','需要轮椅通行'],
    'wheelchair-accessible toilet':['无障碍厕所','需要无障碍厕所']}


def choices():
    result = {}
    for field, labels in LABELS.items():
        aliases = _HARD_ALIASES if field == 'mandatory_constraints' else _SOFT_ALIASES if field == 'preferences' else ACCESS_ALIASES
        result[field] = []
        for key,label in labels.items():
            values=list(dict.fromkeys([key,label,*aliases.get(key,())]))
            if field!='accessibility_requirements':
                prefixes=('必须有','必须','需要有','需要','一定要有','一定要','must have ','requires ','require ','need ','needs ') if field=='mandatory_constraints' else ('希望有','希望','最好有','最好','prefer ','preferably ')
                base=list(values)
                values.extend(prefix+value for prefix in prefixes for value in base
                    if canonical_term(prefix+value,'constraint' if field=='mandatory_constraints' else 'preference')==key)
            if key=='fire_allowed':values.extend(['campfire','营火','篝火'])
            result[field].append({'value':key,'label':label,'aliases':list(dict.fromkeys(values))})
    return {'version':CHOICES_VERSION, 'fields':result}


def recognized(text, field):
    if field == 'accessibility_requirements':
        cleaned = text.strip().casefold().rstrip('。.!！')
        return next((key for key,label in LABELS[field].items()
            if cleaned in [key,label,*ACCESS_ALIASES[key]]), None)
    direct=next((key for key,label in LABELS[field].items() if text.strip().casefold().rstrip('。.!！')==label.casefold()),None)
    if direct:return direct
    kind = 'constraint' if field == 'mandatory_constraints' else 'preference'
    return canonical_term(text,kind)


def unknown_items(explicit, profile):
    result = []
    for field, items in [('preferences',explicit.preferences),('mandatory_constraints',explicit.mandatory_constraints),
                         ('accessibility_requirements',profile.accessibility_requirements)]:
        for index, text in enumerate(items):
            if text.strip() and recognized(text,field) is None:
                result.append({'field':field,'index':index,'text':text})
    return result
