from datetime import date, timedelta
import re

from ...adapters.dataset_mapping import aud_to_cents
from ...contracts.dto import Clarification, InterpretRequestResult, TripRequirements
from ...contracts.enums import FieldErrorCode
from ...contracts.errors import FieldError
from .common import artifact
from .request_terms import canonical_term, merge_explicit_terms, term_issues

NUMBERS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
NUMBER = r'(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|[+-]?(?:\d+(?:\.\d+)?|\.\d+))'
NUMBER_BOUNDARY = r'(?<![\w.])'
NO_FIRE_PATTERN = r"\b(?:no fires|no campfires?|without campfires?|avoid campfires?|(?:do not|don't|must not)\s+(?:use|light|have|build|start)\s+(?:a\s+)?campfires?)\b"


def _negated_before(text, start):
    prefix = re.split(r'[,，.;。；!?！？]', text[:start])[-1]
    return bool(re.search(r"(?:\b(?:no|not|without|avoid|do not want|don't want|do not|don't)\s+(?:need\s+|require\s+|want\s+|an?\s+|any\s+)?|不需要|不想要|不想|无需|不用|不要|不)\s*$", prefix))


def _positive_integer_tokens(tokens: list[str]) -> tuple[list[int], bool]:
    """Parse complete numeric tokens; never take a positive suffix of -2 or 1.5."""
    values, invalid = [], False
    for token in tokens:
        if token in NUMBERS:
            value = NUMBERS[token]
        else:
            try:
                value = int(token)
            except ValueError:
                invalid = True
                continue
        if value <= 0:
            invalid = True
        else:
            values.append(value)
    return values, invalid


def interpret(dataset, input) -> InterpretRequestResult:
    text, lowered = input.raw_text, input.raw_text.casefold()
    values, errors, clarifications = {}, [], []
    explicit = {key: value for key, value in input.explicit_fields.model_dump(exclude_unset=True).items() if value is not None}

    def error(field, code, message):
        if not any(item.field == field and item.code == code for item in errors):
            errors.append(FieldError(field=field, code=code, message=message))

    def scalar(field, candidates):
        if field in explicit or not candidates:
            return
        if len(set(candidates)) != 1:
            error(field, FieldErrorCode.CONFLICTING, f'Multiple different {field} values were stated.')
        else:
            values[field] = candidates[0]

    regions = [region for region in dataset.regions if region.casefold() in lowered]
    scalar('destination', regions)
    if not regions and 'destination' not in explicit:
        destination = re.search(r'\b(?:in|to|at)\s+([A-Z][A-Za-z ]+?)(?=\s+(?:from|for|on)\b|[,.;]|$)', text)
        if destination:
            values['destination'] = destination.group(1).strip()

    dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', text)
    if dates and 'start_date' not in explicit:
        try:
            values['start_date'] = date.fromisoformat(dates[0])
        except ValueError:
            error('start_date', FieldErrorCode.INVALID, 'The stated start date is invalid.')
    if len(dates) > 1 and 'end_date' not in explicit:
        try:
            values['end_date'] = date.fromisoformat(dates[1])
        except ValueError:
            error('end_date', FieldErrorCode.INVALID, 'The stated end date is invalid.')
        if len(dates) > 2:
            error('start_date', FieldErrorCode.AMBIGUOUS, 'More than two dates need clarification.')

    for field, suffix in (('duration_nights', 'nights?'), ('duration_days', 'days?')):
        tokens = re.findall(rf'{NUMBER_BOUNDARY}({NUMBER})(?:\s+|-){suffix}\b', lowered)
        if field not in explicit:
            counts, invalid = _positive_integer_tokens(tokens)
            if invalid:
                error(field, FieldErrorCode.INVALID, 'Duration must be a positive whole number.')
            else:
                scalar(field, counts)

    budgets = re.findall(r'\bAUD\s*([+-]?\d+(?:\.\d+)?)|\$\s*([+-]?\d+(?:\.\d+)?)', text, flags=re.IGNORECASE)
    if budgets and 'budget_cents' not in explicit:
        try:
            amounts = [aud_to_cents(left or right) for left, right in budgets]
            if any(amount <= 0 for amount in amounts):
                raise ValueError('Nonpositive budget')
            scalar('budget_cents', amounts)
        except (ValueError, ArithmeticError):
            error('budget_cents', FieldErrorCode.INVALID, 'Group budget must be a positive AUD amount.')

    preferences = []
    phrases = (
        ('quiet', r'\bquiet\b|安静|清静'), ('toilets', r'\btoilets?\b|厕所|卫生间'),
        ('showers', r'\bshowers?\b|淋浴|洗澡'),
        ('public transport', r'\bpublic transport\b|公共交通'),
        ('wheelchair accessible', r'\b(?:accessible|wheelchair)\b|轮椅通行'),
        ('ready-to-eat meals', r'\bready[- ]to[- ]eat\b|即食餐食|即食食品'),
        ('self-catered meals', r'\bself[- ]catered\b|自行烹饪|自己做饭'),
    )
    for preference, pattern in phrases:
        matches = list(re.finditer(pattern, lowered))
        if any(not _negated_before(lowered, match.start()) for match in matches):
            preferences.append(preference)
    no_fire = bool(re.search(NO_FIRE_PATTERN, lowered))
    if re.search(r'\bcampfire\b', lowered) and not no_fire and not re.search(r'\bremove\s+campfires?\b', lowered):
        preferences.append('campfire')
    values['preferences'] = preferences
    constraints = []
    hard_phrases = {
        'toilets': r'\b(?:must have|require|requires|need)\s+(?:a\s+)?toilets?\b',
        'showers': r'\b(?:must have|require|requires|need)\s+(?:a\s+)?showers?\b',
        'potable_water': r'\b(?:must have|require|requires|need)\s+potable water\b',
        'wheelchair_accessible': r'\b(?:must have|require|requires|need)\s+(?:an?\s+)?(?:wheelchair access|accessible)\b',
        'public_transport_access': r'\b(?:must have|require|requires|need|using|use)\s+public transport\b',
        'campfire': r'\b(?:must have|require|requires)\s+(?:a\s+)?campfire\b',
    }
    for constraint, pattern in hard_phrases.items():
        if any(not _negated_before(lowered, match.start()) for match in re.finditer(pattern, lowered)):
            constraints.append(constraint)
    if no_fire:
        constraints.append('no_fires')
    chinese_clauses = [match.group(0).strip() for match in re.finditer(r'(?:必须|需要|一定要)[^，,。；;.!！?？]*', text)
                       if not _negated_before(text, match.start())]
    for clause in chinese_clauses:
        canonical = canonical_term(clause, 'constraint')
        if canonical:
            constraints.append(canonical)
    if re.search(r'不生火|不使用营火|禁止营火|不要生火', text):
        constraints.append('no_fires')
    # An empty structured box does not waive an unknown mandatory prose clause.
    clauses = [match.group(0).split(',')[0].strip() for match in re.finditer(r'\b(?:must|requires?|need)\b[^.;]*', lowered)
               if not _negated_before(lowered, match.start())]
    if (any(not any(re.fullmatch(pattern, clause) for pattern in (*hard_phrases.values(), NO_FIRE_PATTERN)) for clause in clauses)
            or any(canonical_term(clause, 'constraint') is None for clause in chinese_clauses)):
        error('mandatory_constraints', FieldErrorCode.UNSUPPORTED,
              '部分必须条件的含义尚未明确，请拆分并说明具体需要的设施，再重新生成摘要。')
    values.update({field: value for field, value in explicit.items() if field not in {'preferences', 'mandatory_constraints'}})
    values['preferences'], values['mandatory_constraints'] = merge_explicit_terms(preferences, constraints, input.explicit_fields)
    term_errors, term_questions = term_issues(values['preferences'], values['mandatory_constraints'])
    errors.extend(item for item in term_errors if item not in errors)
    clarifications.extend(term_questions)

    start, nights = values.get('start_date'), values.get('duration_nights')
    if start and nights:
        try:
            derived_end = start + timedelta(days=nights)
            if 'end_date' not in values:
                values['end_date'] = derived_end
            elif values['end_date'] != derived_end:
                error('end_date', FieldErrorCode.CONFLICTING, 'End date conflicts with the stated nights.')
            if 'duration_days' not in values:
                values['duration_days'] = nights + 1
            elif values['duration_days'] != nights + 1:
                error('duration_days', FieldErrorCode.CONFLICTING, 'Days must equal nights plus one.')
        except OverflowError:
            values.pop('duration_nights', None)
            error('duration_nights', FieldErrorCode.INVALID, 'Trip duration exceeds the supported date range.')
    if values.get('start_date') and values['start_date'] < input.demo_context.demo_today:
        error('start_date', FieldErrorCode.INVALID, f'Start date must be on or after the checking date ({input.demo_context.demo_today.isoformat()}, Australia/Sydney).')
    if values.get('destination') and values['destination'] not in dataset.regions:
        error('destination', FieldErrorCode.UNSUPPORTED, 'Only registered synthetic regions are supported.')

    required = {'destination': 'Which synthetic region?', 'start_date': 'What start date?', 'duration_nights': 'How many nights?', 'budget_cents': 'What total AUD group budget?'}
    for field, question in required.items():
        if values.get(field) is None and not any(item.field == field for item in errors):
            error(field, FieldErrorCode.MISSING, 'Required request information is missing.')
            clarifications.append(Clarification(field=field, question=question, reason='Do not infer a missing value from fixtures or Profile notes.'))
    profile = input.profile_snapshot
    stated_transport = None
    if re.search(r'\b(?:using public transport|use public transport|without (?:a )?car|without a vehicle)\b', lowered):
        stated_transport = 'PUBLIC_TRANSPORT'
    elif re.search(r'\bwith (?:a )?car\b', lowered):
        stated_transport = 'CAR'
    if stated_transport and profile and profile.transport.transport_type is not None and profile.transport.transport_type != stated_transport:
        error('profile.transport.transport_type', FieldErrorCode.CONFLICTING, 'Original request transport differs from the saved Profile.')
    stated_group = re.findall(rf'{NUMBER_BOUNDARY}({NUMBER})\s+(?:campers|beginners|people)\b', lowered)
    stated_group += re.findall(rf'\bwe are\s+({NUMBER})\b', lowered)
    groups_list, invalid_groups = _positive_integer_tokens(stated_group)
    groups = set(groups_list)
    if invalid_groups:
        error('profile.group_size', FieldErrorCode.INVALID, 'The original request states an invalid or nonpositive group size.')
    elif len(groups) > 1 or groups and profile and profile.group_size is not None and groups != {profile.group_size}:
        error('profile.group_size', FieldErrorCode.CONFLICTING, 'Request group size differs from the Profile snapshot.')
    if profile is None or profile.group_size is None:
        error('profile.group_size', FieldErrorCode.MISSING, 'Save and confirm the group size in the Profile.')
    for item in errors:
        if not any(question.field == item.field for question in clarifications):
            clarifications.append(Clarification(field=item.field, question=f'Please clarify {item.field}.', reason=item.message))
    return InterpretRequestResult(
        extracted_requirements=TripRequirements.model_validate(values),
        field_errors=errors, clarifications=clarifications,
        **artifact(input.demo_context, assumptions=['Limited deterministic parser; scalar controls take precedence and text conditions are merged.'], uncertainties=['This output is not a confirmation event.']),
    )
