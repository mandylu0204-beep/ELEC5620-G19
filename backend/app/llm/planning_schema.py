"""Internal model-output protocol; shared contracts/schema 1.0 are untouched."""
from datetime import date, timedelta
import re
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, field_validator

from ..contracts.base import ContractModel, Identifier
from ..contracts.dto import ItineraryResult
from ..contracts.enums import ErrorCode, ExecutionMode
from ..contracts.errors import ContractFailure
from ..agents.rules.common import artifact, validate_itinerary_content
from ..agents.rules.planning import camp_entries, violations
from .client import model_failure, strict_json

VALIDATION_VERSION = 'b04-planning-validation-1'


class PlanningProposal(ContractModel):
    campsite_id: Identifier
    nights: list[date] = Field(min_length=1, max_length=30)
    decision_summary: str = Field(min_length=1, max_length=1200)

    @field_validator('nights', mode='before')
    @classmethod
    def iso_dates_only(cls, values):
        if not isinstance(values, list) or any(
                type(value) is not date and (not isinstance(value, str)
                    or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is None)
                for value in values):
            raise ValueError('Night dates must be ISO date strings, not numeric timestamps.')
        return values


class SearchArguments(ContractModel):
    """No model-controlled paths, dates, budget, profile, or SQL parameters."""


class SearchAction(ContractModel):
    action: Literal['tool']
    name: Literal['search_campsites']
    arguments: SearchArguments


class FinalAction(ContractModel):
    action: Literal['final']
    proposal: PlanningProposal


ACTION = TypeAdapter(Annotated[SearchAction | FinalAction, Field(discriminator='action')])


def parse_action(text):
    # Permit only an entire JSON fence, never extract a convenient substring.
    stripped = text.strip()
    if stripped.startswith('```json\n') and stripped.endswith('\n```'):
        stripped = stripped[8:-4]
    try:
        return ACTION.validate_python(strict_json(stripped))
    except (ValueError, TypeError, ValidationError, RecursionError):
        raise model_failure('模型未返回合法的规划动作 JSON；没有采纳任何行程。',
            code=ErrorCode.CONTRACT_INVALID) from None


def validated_itinerary(dataset, input, proposal, exposed_ids):
    try:
        proposal = PlanningProposal.model_validate(proposal)
        if (input.demo_context.mode != ExecutionMode.AGENT
                or input.recommendations.execution_mode != ExecutionMode.AGENT):
            raise ValueError('Model proposals require agent execution mode')
        saved_ids = {item.campsite_id for item in input.recommendations.candidates}
        if proposal.campsite_id not in exposed_ids or proposal.campsite_id not in saved_ids:
            raise ValueError('Site was not exposed by the tool')
        expected = [input.confirmed_requirements.start_date + timedelta(days=offset)
            for offset in range(input.confirmed_requirements.duration_nights)]
        if proposal.nights != expected or not proposal.decision_summary.strip():
            raise ValueError('Night coverage or explanation is invalid')
        campsite = dataset.get_campsite(proposal.campsite_id)
        if violations(campsite, input.confirmed_requirements, input.profile_snapshot):
            raise ValueError('Hard campsite constraints are not satisfied')
        result = ItineraryResult(
            itinerary_entries=camp_entries(campsite, input.confirmed_requirements),
            selected_campsite_ids=[campsite.campsite_id],
            revision_reason='Initial campus-qwen planned proposal; assessments remain required.',
            **artifact(input.demo_context, [campsite.source_ref], assumptions=[
                'Planning decision summary (model-generated, not a verified fact): ' + proposal.decision_summary,
                'Sydney-local draft times are placeholders, not verified check-in or travel times.',
            ], uncertainties=['Model choice is not a booking or safety clearance; transport, supplies, costs and safety still require assessment.']),
        )
        validate_itinerary_content(dataset, result, input.confirmed_requirements)
        return result
    except (ValueError, TypeError, ValidationError, ContractFailure):
        raise model_failure('模型行程不符合工具候选、确认日期或硬约束；未保存方案。',
            code=ErrorCode.CONTRACT_INVALID) from None
