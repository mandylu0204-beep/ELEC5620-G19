"""Host-built form summaries, separate from legacy model prose interpretation."""
from typing import Literal
from pydantic import Field, StrictInt
from ..contracts.base import ContractModel
from ..contracts.dto import DemoContext, ProfileSnapshot, TripRequirements, InterpretRequestResult, Clarification
from ..contracts.enums import FieldErrorCode
from ..contracts.errors import FieldError
from ..storage.repository import fingerprint
from .requirement_choices import recognized, unknown_items
from ..agents.rules.request_terms import term_issues

STRUCTURED_SUMMARY_VERSION='structured-form-summary-1'

class StructuredRequestInput(ContractModel):
    explicit_fields: TripRequirements
    profile_snapshot: ProfileSnapshot
    demo_context: DemoContext

class StructuredSummaryMetadata(ContractModel):
    component_version: Literal['structured-form-summary-1']=STRUCTURED_SUMMARY_VERSION
    analysis_revision: StrictInt=Field(ge=1)
    input_sha256: str=Field(pattern=r'^[0-9a-f]{64}$')


def input_fingerprint(input):
    return fingerprint({'source':'STRUCTURED_FORM','component_version':STRUCTURED_SUMMARY_VERSION,
        'explicit_fields':input.explicit_fields.model_dump(mode='json',exclude_unset=True),
        'profile_snapshot':input.profile_snapshot.model_dump(mode='json'),
        'demo_context':input.demo_context.model_dump(mode='json')})


def summarize(input):
    if unknown_items(input.explicit_fields,input.profile_snapshot):
        raise ValueError('Other requirements need assistance before summary')
    fields=input.explicit_fields.model_dump(mode='json',exclude_unset=True)
    for field in ['preferences','mandatory_constraints']:
        fields[field]=list(dict.fromkeys(recognized(value,field) for value in getattr(input.explicit_fields,field) if value.strip()))
    requirements=TripRequirements.model_validate(fields)
    errors,questions=term_issues(requirements.preferences,requirements.mandatory_constraints)
    if requirements.start_date and requirements.start_date<input.demo_context.demo_today:
        message=f'Start date must be on or after the checking date ({input.demo_context.demo_today.isoformat()}, Australia/Sydney).'
        errors.append(FieldError(field='start_date',code=FieldErrorCode.INVALID,message=message))
        questions.append(Clarification(field='start_date',question=message,reason='The structured summary is still validated against this check date.'))
    return InterpretRequestResult(execution_mode=input.demo_context.mode,extracted_requirements=requirements,
        field_errors=errors,clarifications=questions,
        assumptions=['Summary assembled from structured form fields by the host; no model was invoked.'])
