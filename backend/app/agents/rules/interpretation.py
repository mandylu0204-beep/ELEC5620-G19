from datetime import date, timedelta
import re

from ...adapters.dataset_mapping import aud_to_cents
from ...contracts.dto import Clarification, InterpretRequestResult, TripRequirements
from ...contracts.enums import FieldErrorCode
from ...contracts.errors import FieldError
from .common import artifact

NUMBERS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
NUMBER = r'(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|[+-]?(?:\d+(?:\.\d+)?|\.\d+))'
NUMBER_BOUNDARY = r'(?<![\w.])'
NO_FIRE_PATTERN = r"\b(?:no fires|no campfires?|without campfires?|avoid campfires?|(?:do not|don't|must not)\s+(?:use|light|have|build|start)\s+(?:a\s+)?campfires?)\b"


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
        ('quiet', r'\bquiet\b'), ('toilets', r'\btoilets?\b'),
        ('public transport', r'\bpublic transport\b'),
        ('wheelchair accessible', r'\b(?:accessible|wheelchair)\b'),
        ('ready-to-eat meals', r'\bready[- ]to[- ]eat\b'),
        ('self-catered meals', r'\bself[- ]catered\b'),
    )
    for preference, pattern in phrases:
        matches = list(re.finditer(pattern, lowered))
        if any(not re.search(r"\b(?:no|not|without|avoid|do not want|don't want)\s+(?:a\s+|any\s+)?$", lowered[:match.start()]) for match in matches):
            preferences.append(preference)
    no_fire = bool(re.search(NO_FIRE_PATTERN, lowered))
    if re.search(r'\bcampfire\b', lowered) and not no_fire and not re.search(r'\bremove\s+campfires?\b', lowered):
        preferences.append('campfire')
    values['preferences'] = preferences
    constraints = []
    hard_phrases = {
        'toilets': r'\b(?:must have|require|requires|need)\s+(?:a\s+)?toilets?\b',
        'potable_water': r'\b(?:must have|require|requires|need)\s+potable water\b',
        'wheelchair_accessible': r'\b(?:must have|require|requires|need)\s+(?:an?\s+)?(?:wheelchair access|accessible)\b',
        'public_transport_access': r'\b(?:must have|require|requires|need|using|use)\s+public transport\b',
        'campfire': r'\b(?:must have|require|requires)\s+(?:a\s+)?campfire\b',
    }
    for constraint, pattern in hard_phrases.items():
        if re.search(pattern, lowered):
            constraints.append(constraint)
    if no_fire:
        constraints.append('no_fires')
    values['mandatory_constraints'] = constraints
    if 'mandatory_constraints' not in explicit:
        clauses = [match.group(0).split(',')[0].strip() for match in re.finditer(r'\b(?:must|requires?)\b[^.;]*', lowered)]
        if any(not any(re.fullmatch(pattern, clause) for pattern in (*hard_phrases.values(), NO_FIRE_PATTERN)) for clause in clauses):
            error('mandatory_constraints', FieldErrorCode.UNSUPPORTED, 'An unrecognised/compound mandatory clause needs explicit structured constraints.')
    values.update(explicit)
    if {'ready-to-eat meals', 'self-catered meals'}.issubset(values['preferences']):
        error('preferences', FieldErrorCode.CONFLICTING, 'Choose one confirmed meal mode.')
    if 'no_fires' in values['mandatory_constraints'] and 'campfire' in values['mandatory_constraints']:
        error('mandatory_constraints', FieldErrorCode.CONFLICTING, 'Mandatory campfire and no-fire clauses conflict.')

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
        **artifact(input.demo_context, assumptions=['Limited English demo parser; explicit fields take precedence.'], uncertainties=['This output is not a confirmation event.']),
    )
