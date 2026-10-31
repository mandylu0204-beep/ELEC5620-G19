"""Read-only choices derived from the host's existing finite request vocabulary."""
from ..agents.rules.request_terms import canonical_term, _HARD_ALIASES, _SOFT_ALIASES

CHOICES_VERSION = 'structured-request-choices-1'
LABELS = {
    'preferences': {'quiet':'Quiet surroundings','toilets':'Toilets','showers':'Showers','potable water':'Drinking-water facilities',
        'public transport':'Public transport access','wheelchair accessible':'Wheelchair access','campfire':'Campfire','pets':'Pets allowed'},
    'mandatory_constraints': {'toilets':'Must have toilets','showers':'Must have showers','potable_water':'Drinking-water facilities required',
        'wheelchair_accessible':'Wheelchair access required','fire_allowed':'Fires must be allowed','no_fires':'No campfire',
        'pets_allowed':'Pets must be allowed','vehicle_access':'Vehicle access required',
        'public_transport_access':'Public-transport access required','walk_in_only':'Walk-in access only'},
    'accessibility_requirements': {'step-free path':'Need a step-free path','wheelchair access':'Need wheelchair access',
        'wheelchair-accessible toilet':'Need an accessible toilet'},
}
LEGACY_LABELS = {"preferences": {"quiet": "\u5b89\u9759\u7684\u73af\u5883", "toilets": "\u5395\u6240", "showers": "\u6dcb\u6d74", "potable water": "\u996e\u7528\u6c34\u8bbe\u65bd", "public transport": "\u516c\u5171\u4ea4\u901a\u53ef\u8fbe", "wheelchair accessible": "\u8f6e\u6905\u901a\u884c", "campfire": "\u8425\u706b", "pets": "\u5141\u8bb8\u643a\u5e26\u5ba0\u7269"}, "mandatory_constraints": {"toilets": "\u5fc5\u987b\u6709\u5395\u6240", "showers": "\u5fc5\u987b\u6709\u6dcb\u6d74", "potable_water": "\u5fc5\u987b\u6709\u996e\u7528\u6c34\u8bbe\u65bd", "wheelchair_accessible": "\u5fc5\u987b\u80fd\u8f6e\u6905\u901a\u884c", "fire_allowed": "\u5fc5\u987b\u5141\u8bb8\u751f\u706b", "no_fires": "\u4e0d\u4f7f\u7528\u8425\u706b", "pets_allowed": "\u5fc5\u987b\u5141\u8bb8\u643a\u5e26\u5ba0\u7269", "vehicle_access": "\u5fc5\u987b\u8f66\u8f86\u53ef\u8fbe", "public_transport_access": "\u5fc5\u987b\u516c\u5171\u4ea4\u901a\u53ef\u8fbe", "walk_in_only": "\u4ec5\u53ef\u6b65\u884c\u8fdb\u5165"}, "accessibility_requirements": {"step-free path": "\u9700\u8981\u65e0\u53f0\u9636\u901a\u9053", "wheelchair access": "\u9700\u8981\u8f6e\u6905\u901a\u884c", "wheelchair-accessible toilet": "\u9700\u8981\u65e0\u969c\u788d\u5395\u6240"}}
ACCESS_ALIASES = {'step-free path':['无台阶通道','需要无台阶通道'],
    'wheelchair access':['轮椅通行','需要轮椅通行'],
    'wheelchair-accessible toilet':['无障碍厕所','需要无障碍厕所']}


def choices():
    result = {}
    for field, labels in LABELS.items():
        aliases = _HARD_ALIASES if field == 'mandatory_constraints' else _SOFT_ALIASES if field == 'preferences' else ACCESS_ALIASES
        result[field] = []
        for key,label in labels.items():
            values=list(dict.fromkeys([key,label,LEGACY_LABELS[field][key],*aliases.get(key,())]))
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
        cleaned = text.strip().casefold().rstrip('\u3002.!\uff01')
        return next((key for key,label in LABELS[field].items()
            if cleaned in [key,label.casefold(),LEGACY_LABELS[field][key],*ACCESS_ALIASES[key]]), None)
    direct=next((key for key,label in LABELS[field].items() if text.strip().casefold().rstrip('\u3002.!\uff01')in [label.casefold(),LEGACY_LABELS[field][key]]),None)
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
