"""AgentPort: real campus planning, explicit deterministic business kernels.

No application registration, private trace cache, audit sink or new database.
"""
import json

from pydantic import ValidationError

from ..contracts.dto import (
    DatasetContext, InterpretRequestInput, InterpretRequestResult, ItineraryInput,
    ItineraryResult, LogisticsInput, LogisticsResult, OrchestrateInput,
    RecommendCampsitesInput, RecommendCampsitesResult, RunResult, SafetyInput, SafetyResult,
)
from ..contracts.enums import ErrorCode, ExecutionMode
from ..contracts.ports import PersistencePort
from ..llm.coordinator import PlanningCoordinator, PlanningOutcome
from ..workflow.configuration import WorkflowConfiguration, failure
from .rules import interpretation, logistics, planning, safety
from .rules.common import RULES_VERSION, ensure_execution_mode, input_failure

HYBRID_VERSION = 'b05-hybrid-planning-1'


def _identity(coordinator):
    return {
        'hybrid_agent_version': HYBRID_VERSION,
        'hybrid_kernel_version': RULES_VERSION,
        'hybrid_planning_fingerprint': coordinator.identity['configuration_fingerprint'],
    }


def build_hybrid_configuration(dataset, coordinator, *, safety_case_ids=(), scenarios=(), registered_context=None):
    """A must register this exact context BEFORE confirming/starting an agent run.

    Preserve A's complete source/fixture/selection identity. Key collisions fail
    closed; this helper does not mutate the dataset or a registered run scope.
    """
    if coordinator.dataset is not dataset:
        raise failure(ErrorCode.STALE_CONTEXT, 'Coordinator must consume the same loaded dataset object.')
    base = DatasetContext.model_validate(registered_context) if registered_context is not None else dataset.context
    identity = _identity(coordinator)
    if any(key in base.selection_config and base.selection_config[key] != value for key, value in identity.items()):
        raise failure(ErrorCode.STALE_CONTEXT, 'Registered hybrid model/kernel identity differs.')
    registered = base.model_copy(update={
        'selection_config': {**base.selection_config, **identity},
        'rules_version': f'{base.rules_version}/{HYBRID_VERSION}/{identity["hybrid_planning_fingerprint"]}',
    }, deep=True)
    return WorkflowConfiguration(dataset, safety_case_ids=safety_case_ids, scenarios=scenarios,
                                 registered_context=registered)


class HybridPlanningAgent:
    """Complete six-method AgentPort, with first PLAN as the MVP operation.

    agent denotes the mixed runtime, not a claim that every step uses an LLM.
    Only generate_or_revise_itinerary invokes the model; REVISE/REASSESS are
    explicitly unsupported until implemented and enabled by A.
    """
    supported_operations = frozenset({'PLAN'})
    rules_version = HYBRID_VERSION

    def __init__(self, dataset, coordinator: PlanningCoordinator, *, workflow_configuration=None,
                 heartbeat_interval=20):
        if coordinator.dataset is not dataset:
            raise failure(ErrorCode.STALE_CONTEXT, 'Coordinator must consume the same loaded dataset object.')
        self.dataset, self.coordinator = dataset, coordinator
        self.workflow_configuration = workflow_configuration or build_hybrid_configuration(dataset, coordinator)
        self.heartbeat_interval = heartbeat_interval
        self._check_configuration()

    def _check_configuration(self):
        context = self.workflow_configuration.context
        if (self.coordinator.dataset is not self.dataset
                or context.dataset_version != self.dataset.context.dataset_version
                or any(context.file_digests.get(key) != value for key, value in self.dataset.context.file_digests.items())
                or any(context.selection_config.get(key) != value for key, value in _identity(self.coordinator).items())):
            raise failure(ErrorCode.STALE_CONTEXT, 'Hybrid dataset/model/kernel configuration changed; start a new run.')

    def _input(self, model, value):
        self._check_configuration()
        try:
            result = model.model_validate(value).model_copy(deep=True)
        except (ValidationError, ValueError, TypeError) as exc:
            raise failure(ErrorCode.CONTRACT_INVALID, 'HybridPlanningAgent input violates shared contract 1.0.') from exc
        ensure_execution_mode(self.dataset, result.demo_context, ExecutionMode.AGENT)
        requirements = getattr(result, 'confirmed_requirements', None)
        if requirements is not None:
            if requirements.start_date < result.demo_context.demo_today:
                raise input_failure('Confirmed trip precedes the fixed demonstration date.', 'start_date')
            if requirements.duration_nights > 30:
                raise input_failure('Hybrid PLAN supports at most 30 nights.', 'duration_nights')
        return result

    @staticmethod
    def _rule_result(result, capability):
        # Add honest provenance, never change execution_mode or demo_context.
        return result.model_copy(update={'assumptions': [*result.assumptions,
            f'HybridPlanningAgent: {capability} uses deterministic rules, not an LLM.']})

    async def interpret_request(self, input: InterpretRequestInput) -> InterpretRequestResult:
        return self._rule_result(interpretation.interpret(self.dataset, self._input(InterpretRequestInput, input)), 'request interpretation')

    async def recommend_campsites(self, input: RecommendCampsitesInput) -> RecommendCampsitesResult:
        return self._rule_result(planning.recommend(self.dataset, self._input(RecommendCampsitesInput, input)), 'campsite filtering')

    async def plan_with_trace(self, input: ItineraryInput) -> PlanningOutcome:
        """Caller-owned transient trace; not a substitute for A's audit receipt."""
        outcome = await self.coordinator.plan(self._input(ItineraryInput, input))
        self._check_configuration()  # Reject identity drift during a model wait.
        if (outcome.itinerary.execution_mode != ExecutionMode.AGENT
                or outcome.trace.configuration_fingerprint != self.coordinator.identity['configuration_fingerprint']):
            raise failure(ErrorCode.STALE_CONTEXT, 'Model outcome differs from the registered agent identity.')
        return outcome

    async def generate_or_revise_itinerary(self, input: ItineraryInput) -> ItineraryResult:
        # Coordinator rejects revision; no deterministic fallback on any failure.
        return (await self.plan_with_trace(input)).itinerary

    async def assess_gear_and_logistics(self, input: LogisticsInput) -> LogisticsResult:
        validated = self._input(LogisticsInput, input)
        ids = json.loads(self.workflow_configuration.context.selection_config['safety_case_ids'])
        return self._rule_result(logistics.assess(self.dataset, validated,
            expected_mode=ExecutionMode.AGENT, safety_case_ids=ids), 'gear and costs')

    async def assess_safety(self, input: SafetyInput) -> SafetyResult:
        return self._rule_result(safety.assess(self.dataset, self._input(SafetyInput, input),
            expected_mode=ExecutionMode.AGENT), 'safety assessment')

    async def orchestrate(self, input: OrchestrateInput, persistence: PersistencePort) -> RunResult:
        from ..workflow.orchestration import Orchestrator
        try:
            validated = OrchestrateInput.model_validate(input)
        except (ValidationError, ValueError, TypeError) as exc:
            raise failure(ErrorCode.CONTRACT_INVALID, 'Hybrid orchestration input violates contract 1.0.') from exc
        if validated.run_scope.operation not in self.supported_operations:
            raise input_failure('Hybrid MVP supports PLAN only; model revision/reassessment is not enabled.', 'operation')
        # The shared orchestrator checks mode/config against A's checkpoint,
        # renews leases during model waits and reuses all saved artifacts.
        return await Orchestrator(self, self.workflow_configuration, persistence,
            heartbeat_interval=self.heartbeat_interval).run(validated)
