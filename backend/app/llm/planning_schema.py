"""Internal model-output protocol; shared contracts/schema 1.0 are untouched."""
from ..contracts.revision_feedback import revision_goal
from datetime import date, timedelta
import re
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, field_validator

from ..contracts.base import ContractModel, Identifier
from ..contracts.dto import ItineraryResult, TripRequirements
from ..contracts.enums import ErrorCode, ExecutionMode
from ..contracts.errors import ContractFailure
from ..agents.rules.common import artifact, validate_itinerary_content
from ..agents.rules.planning import camp_entries, violations
from .client import model_failure, strict_json

VALIDATION_VERSION = 'b04-planning-validation-2'


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


class DailyChoice(ContractModel):
    date: date
    activity_id: Identifier

    @field_validator('date', mode='before')
    @classmethod
    def iso_date_only(cls, value):
        return PlanningProposal.iso_dates_only([value])[0]


class DetailedPlanningProposal(PlanningProposal):
    daily_plan: list[DailyChoice] = Field(max_length=30)


class SearchArguments(ContractModel):
    """No model-controlled paths, dates, budget, profile, or SQL parameters."""


class SearchAction(ContractModel):
    action: Literal['tool']
    name: Literal['search_campsites']
    arguments: SearchArguments


class FinalAction(ContractModel):
    action: Literal['final']
    proposal: PlanningProposal


class RequirementsChangeAction(ContractModel):
    """A proposal for reconfirmation, never permission to change saved input."""
    action: Literal['requirements_change']
    requested_requirement_changes: TripRequirements


ACTION = TypeAdapter(Annotated[SearchAction | FinalAction | RequirementsChangeAction, Field(discriminator='action')])


class DetailedFinalAction(FinalAction):
    proposal: DetailedPlanningProposal


DETAILED_ACTION = TypeAdapter(Annotated[SearchAction | DetailedFinalAction | RequirementsChangeAction, Field(discriminator='action')])
DETAILED_VALIDATION_VERSION = 'planning-validation-daily-1'


def parse_action(text, *, detailed=False):
    # Permit only an entire JSON fence, never extract a convenient substring.
    stripped = text.strip()
    if stripped.startswith('```json\n') and stripped.endswith('\n```'):
        stripped = stripped[8:-4]
    try:
        return (DETAILED_ACTION if detailed else ACTION).validate_python(strict_json(stripped))
    except (ValueError, TypeError, ValidationError, RecursionError):
        raise model_failure('The model did not return a valid planning action. JSON; No itinerary was adopted.',
            code=ErrorCode.CONTRACT_INVALID) from None


def validated_itinerary(dataset, input, proposal, exposed_ids):
    try:
        detailed = getattr(dataset, 'planning_reference', None) is not None
        proposal = (DetailedPlanningProposal if detailed else PlanningProposal).model_validate(proposal)
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
        if input.previous_version is not None:
            previous = input.previous_version.content
            feedback = revision_goal(input.feedback)
            if feedback in {'change campsite', 'Change campsite'} and proposal.campsite_id in previous.selected_campsite_ids:
                raise ValueError('The requested campsite change was not made')
            if feedback in {'cheaper campsite', 'Cheaper campsite'}:
                old_fees = [dataset.get_campsite(key).nightly_fee_cents for key in previous.selected_campsite_ids]
                if len(old_fees) != 1 or campsite.nightly_fee_cents >= old_fees[0]:
                    raise ValueError('The requested lower campsite fee was not achieved')
        entries, refs = camp_entries(campsite, input.confirmed_requirements), []
        if detailed:
            from ..adapters.planning_reference import available_activities, daily_entries
            activities = available_activities(dataset, campsite.campsite_id, input.confirmed_requirements)
            if activities:
                entries, refs = daily_entries(dataset, campsite, input.confirmed_requirements, proposal.daily_plan)
            elif proposal.daily_plan:
                raise ValueError('No applicable activity catalogue for this campsite')
        result = ItineraryResult(
            itinerary_entries=entries,
            selected_campsite_ids=[campsite.campsite_id],
            revision_reason=input.feedback.strip() if input.previous_version is not None else
                'Initial campus-qwen planned proposal; assessments remain required.',
            **artifact(input.demo_context, [campsite.source_ref, *refs], assumptions=[
                'Planning decision summary (model-generated, not a verified fact): ' + proposal.decision_summary,
                'Sydney-local draft times are placeholders, not verified check-in or travel times.',
            ], uncertainties=['Model choice is not a booking or safety clearance; transport, supplies, costs and safety still require assessment.']),
        )
        validate_itinerary_content(dataset, result, input.confirmed_requirements)
        return result
    except (ValueError, TypeError, ValidationError, ContractFailure):
        raise model_failure('The model itinerary does not match tool candidates, confirmed dates or hard constraints. No plan saved.',
            code=ErrorCode.CONTRACT_INVALID) from None
