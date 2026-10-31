from ..contracts.dto import (
    Clarification, InterpretRequestInput, InterpretRequestResult, ItineraryInput,
    LogisticsInput, OrchestrateInput, RecommendCampsitesInput, SafetyInput,
)
from ..contracts.enums import AllowedAction, ErrorCode, ExecutionMode
from ..contracts.errors import ContractError, ContractFailure
from ..contracts.ports import PersistencePort


class StubAgent:
    """Development echo only. It does not parse prose, assess safety or plan trips."""

    async def interpret_request(self, input: InterpretRequestInput) -> InterpretRequestResult:
        requirements = input.explicit_fields
        required = {
            "destination": "Specify a destination.", "start_date": "Specify a start date.",
            "duration_nights": "Specify the number of camping nights.", "budget_cents": "Specify the group budget.",
        }
        clarifications = [
            Clarification(field=field, question=question, reason="Stub No natural-language parsing; explicitly entered fields are echoed only.")
            for field, question in required.items()
            if getattr(requirements, field) is None
        ]
        return InterpretRequestResult(
            execution_mode=ExecutionMode.STUB,
            extracted_requirements=requirements,
            clarifications=clarifications,
            uncertainties=["This result is from the development  stub, . No  Agent  inference was performed. This does not confirm a request or start planning."],
        )

    def _unavailable(self) -> ContractFailure:
        return ContractFailure(ContractError(
            code=ErrorCode.AGENT_FAILURE,
            message="This capability is not connected to  B; stub  and does not produce successful planning, assessment or workflow results.",
            allowed_actions=[AllowedAction.CONTACT_OPERATOR],
        ))

    async def recommend_campsites(self, input: RecommendCampsitesInput):
        raise self._unavailable()

    async def generate_or_revise_itinerary(self, input: ItineraryInput):
        raise self._unavailable()

    async def assess_gear_and_logistics(self, input: LogisticsInput):
        raise self._unavailable()

    async def assess_safety(self, input: SafetyInput):
        raise self._unavailable()

    async def orchestrate(self, input: OrchestrateInput, persistence: PersistencePort):
        raise self._unavailable()
