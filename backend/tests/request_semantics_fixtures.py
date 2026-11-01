"""Declared offline response grammar for legacy HTTP fixtures, not a parser oracle.

Only phrases actually present in these test fixtures are assigned meanings. This
module never imports the production interpreter, aliases or schema generator.
"""

_TERMS = {
    'quiet': 'quiet', 'ready-to-eat meals': 'ready-to-eat meals',
    'self-catered meals': 'self-catered meals', 'toilets': 'toilets',
    'showers': 'showers', 'potable_water': 'potable_water',
    'fire_allowed': 'fire_allowed', 'campfire': 'campfire',
    'pets_allowed': 'pets_allowed', 'wheelchair_accessible': 'wheelchair_accessible',
    'vehicle_access': 'vehicle_access', 'public_transport_access': 'public_transport_access',
    'no_fires': 'no_fires', 'walk_in_only': 'walk_in_only',
    '\u5373\u98df\u9910\u98df': 'ready-to-eat meals', '\u81ea\u884c\u70f9\u996a': 'self-catered meals',
    '\u5b89\u9759': 'quiet', '\u9700\u8981\u6d17\u6fa1': 'showers', '\u5fc5\u987b\u6709\u6dcb\u6d74': 'showers',
}
_RAW_PHRASES = (
    ('quiet', 'quiet', 'soft'),
    ('ready-to-eat meals', 'ready-to-eat meals', 'soft'),
    ('self-catered meals', 'self-catered meals', 'soft'),
    ('Must have showers', 'showers', 'hard'),
)


def _mention(quote, canonical, strength):
    return {'quote': quote, 'canonical': canonical, 'polarity': 'positive',
        'strength': strength, 'ambiguous': False}


def interpretation_proposal(payload):
    """Return quoted clauses for the explicitly declared test-input phrases."""
    assert payload['operation'] == 'INTERPRET_REQUEST'
    clauses = []
    for source in payload['sources']:
        text, kind = source['text'], source['source']
        if kind == 'raw_text':
            mentions = [_mention(phrase, canonical, strength)
                for phrase, canonical, strength in _RAW_PHRASES if phrase in text]
        else:
            mentions = [_mention(text, _TERMS.get(text),
                'hard' if kind == 'mandatory_constraints' else 'soft')]
        clauses.append({'source': kind, 'index': source['index'], 'quote': text,
            'mentions': mentions, 'unresolved': False})
    return {'clauses': clauses}


def model_operation(body):
    """Planning tool turns keep their original user payload at message 1."""
    import json
    return json.loads(body['messages'][1]['content']).get('operation')


def role_requests(requests, role):
    return [row for row in requests if row['role'] == role]
