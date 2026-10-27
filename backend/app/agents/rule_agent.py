"""Deterministic business capabilities and B-03 checkpoint orchestration."""
from pydantic import ValidationError

from ..adapters import SyntheticDataset
from ..contracts.dto import (
    InterpretRequestInput, InterpretRequestResult, ItineraryInput, ItineraryResult,
    LogisticsInput, LogisticsResult, OrchestrateInput, RecommendCampsitesInput,
    RecommendCampsitesResult, RunResult, SafetyInput, SafetyResult,
)
from ..contracts.enums import AllowedAction, ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from ..contracts.ports import PersistencePort
from .rules import interpretation, logistics, planning, safety
from .rules.common import RULES_VERSION, ensure_demo, input_failure


class RuleAgent:
    rules_version = RULES_VERSION

    def __init__(self, dataset: SyntheticDataset, *, workflow_configuration=None, heartbeat_interval=20):
        self.dataset = dataset
        self.workflow_configuration = workflow_configuration
        self.heartbeat_interval = heartbeat_interval

    def _input(self, model, value):
        try:
            result = model.model_validate(value)
        except ValidationError as exc:
            raise ContractFailure(ContractError(
                code=ErrorCode.CONTRACT_INVALID, message='RuleAgent input does not match shared contract 1.0.',
                allowed_actions=[AllowedAction.CONTACT_OPERATOR],
            )) from exc
        ensure_demo(self.dataset, result.demo_context)
        requirements = getattr(result, 'confirmed_requirements', None)
        if requirements is not None and requirements.start_date < result.demo_context.demo_today:
            raise input_failure('Confirmed trip precedes the fixed demonstration date.', 'start_date')
        return result

    async def interpret_request(self, input: InterpretRequestInput) -> InterpretRequestResult:
        return interpretation.interpret(self.dataset, self._input(InterpretRequestInput, input))

    async def recommend_campsites(self, input: RecommendCampsitesInput) -> RecommendCampsitesResult:
        return planning.recommend(self.dataset, self._input(RecommendCampsitesInput, input))

    async def generate_or_revise_itinerary(self, input: ItineraryInput) -> ItineraryResult:
        return planning.itinerary(self.dataset, self._input(ItineraryInput, input))

    async def assess_gear_and_logistics(self, input: LogisticsInput) -> LogisticsResult:
        from .rules.transport import POLICY_KEY
        policy = self.workflow_configuration.context.selection_config.get(POLICY_KEY) if self.workflow_configuration else None
        return logistics.assess(self.dataset, self._input(LogisticsInput, input), transport_policy=policy)

    async def assess_safety(self, input: SafetyInput) -> SafetyResult:
        return safety.assess(self.dataset, self._input(SafetyInput, input))

    async def orchestrate(self, input: OrchestrateInput, persistence: PersistencePort) -> RunResult:
        from ..workflow.configuration import WorkflowConfiguration
        from ..workflow.orchestration import Orchestrator
        configuration = self.workflow_configuration or WorkflowConfiguration(self.dataset)
        if any(configuration.context.file_digests.get(key) != value for key, value in self.dataset.context.file_digests.items()) or configuration.context.dataset_version != self.dataset.context.dataset_version:
            raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Workflow configuration belongs to a different dataset snapshot.'))
        return await Orchestrator(self, configuration, persistence, heartbeat_interval=self.heartbeat_interval).run(input)
