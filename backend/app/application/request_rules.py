"""A-side input integrity checks. No prose parsing or trip/safety inference."""
from datetime import timedelta

from ..contracts.dto import Clarification, InterpretRequestResult, ProfileSnapshot, TripRequirements
from ..contracts.enums import ErrorCode, FieldErrorCode, RequestStatus
from ..contracts.errors import FieldError

from .datasets import inspect_dataset
from ..agents.rules.request_terms import merge_explicit_terms, term_issues


def data_context(settings):
    descriptor = inspect_dataset(settings)
    return descriptor.context, descriptor.regions


def normalize(result: InterpretRequestResult, explicit: TripRequirements, profile: ProfileSnapshot, regions: list[str], *, interpreted_terms=False):
    extracted = result.extracted_requirements.model_dump(mode='json')
    # Explicit user input has authority over interpretation output.
    for field, value in explicit.model_dump(mode='json', exclude_unset=True).items():
        if value is not None and field not in {'preferences', 'mandatory_constraints'}:
            extracted[field] = value
    # Scalar controls are authoritative. Text lists are semantic input, not an
    # instruction to erase conditions found in the user's original idea. The
    # model path has already validated every source clause and projected it to
    # canonical terms; never overwrite that projection with its raw wording.
    if not interpreted_terms:
        extracted['preferences'], extracted['mandatory_constraints'] = merge_explicit_terms(
            extracted.get('preferences', []), extracted.get('mandatory_constraints', []), explicit)
    requirements = TripRequirements.model_validate(extracted)
    errors = list(result.field_errors)
    questions = list(result.clarifications)
    term_errors, term_questions = term_issues(requirements.preferences, requirements.mandatory_constraints, require_meal=False)
    for item in term_errors:
        if item not in errors:
            errors.append(item)
    for item in term_questions:
        if item not in questions:
            questions.append(item)

    def issue(field, message, code=FieldErrorCode.MISSING):
        if not any(item.field == field and item.code == code for item in errors):
            errors.append(FieldError(field=field, code=code, message=message))
        if not any(item.field == field for item in questions):
            questions.append(Clarification(field=field, question=message, reason='Specify this before confirmation.'))

    values = requirements.model_dump()
    destination = (requirements.destination or '').strip()
    if not destination:
        issue('destination', 'Select a demo destination.')
    else:
        canonical = next((region for region in regions if region.casefold() == destination.casefold()), None)
        if canonical is None:
            issue('destination', 'Destination is outside the current  synthetic  demo region. Select a supported region.', FieldErrorCode.UNSUPPORTED)
        else:
            values['destination'] = canonical
    if requirements.start_date is None:
        issue('start_date', 'Enter a start date.')
    if requirements.duration_nights is None:
        issue('duration_nights', 'Specify nights. Days or dates alone cannot confirm nights for you.')
    else:
        days = requirements.duration_nights + 1
        if requirements.duration_days is not None and requirements.duration_days != days:
            issue('duration_days', f'{requirements.duration_nights}  nights should span  {days}  days. Correct the conflicting duration.', FieldErrorCode.CONFLICTING)
        else:
            values['duration_days'] = days
        if requirements.start_date is not None:
            try:
                end = requirements.start_date + timedelta(days=requirements.duration_nights)
                if requirements.end_date is not None and requirements.end_date != end:
                    issue('end_date', f'End date should be  {end.isoformat()}, . Correct the conflicting date.', FieldErrorCode.CONFLICTING)
                else:
                    values['end_date'] = end
            except OverflowError:
                issue('duration_nights', 'Nights exceed the representable date range. Please revise.', FieldErrorCode.INVALID)
    if requirements.budget_cents is None:
        issue('budget_cents', 'Enter the whole group  AUD  budget.')
    if profile.group_size is None:
        issue('profile.group_size', 'Save group size first, then regenerate the summary.')
    # A has derived these optional fields; an Agent's missing-only message no longer applies.
    questions = [item for item in questions if not (item.field in {'duration_days','end_date'} and values.get(item.field) is not None and not any(error.field == item.field for error in errors))]
    normalized = InterpretRequestResult.model_validate(result.model_dump(mode='json') | {
        'extracted_requirements': TripRequirements.model_validate(values).model_dump(mode='json'),
        'field_errors': [item.model_dump(mode='json') for item in errors],
        'clarifications': [item.model_dump(mode='json') for item in questions],
    })
    status = RequestStatus.UNSUPPORTED if any(item.code == FieldErrorCode.UNSUPPORTED and item.field == 'destination' for item in errors) else RequestStatus.NEEDS_CLARIFICATION if errors or questions else RequestStatus.AWAITING_CONFIRMATION
    return normalized, status
