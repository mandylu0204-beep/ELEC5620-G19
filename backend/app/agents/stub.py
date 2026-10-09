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
            "destination": "请明确目的地。", "start_date": "请明确开始日期。",
            "duration_nights": "请明确露营晚数。", "budget_cents": "请明确小组预算。",
        }
        clarifications = [
            Clarification(field=field, question=question, reason="Stub 不解析自然语言，仅回显明确填写的字段。")
            for field, question in required.items()
            if getattr(requirements, field) is None
        ]
        return InterpretRequestResult(
            execution_mode=ExecutionMode.STUB,
            extracted_requirements=requirements,
            clarifications=clarifications,
            uncertainties=["此结果来自开发 stub，未执行 Agent 推理；它本身不确认请求或启动规划。"],
        )

    def _unavailable(self) -> ContractFailure:
        return ContractFailure(ContractError(
            code=ErrorCode.AGENT_FAILURE,
            message="该业务能力尚未接入 B；stub 不提供规划、评估或工作流成功结果。",
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
