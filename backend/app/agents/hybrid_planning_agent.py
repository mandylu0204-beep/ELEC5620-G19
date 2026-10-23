"""AgentPort: campus planning and opt-in assessment roles with guarded kernels.

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
from ..llm.coordinator import PlanningCoordinator, PlanningOutcome, canonical, digest
from ..llm.client import strict_json
from ..llm.logistics_agent import LogisticsOutcome
from ..llm.logistics_validation import validate_logistics_payload
from ..llm.safety_agent import SafetyOutcome
from ..workflow.configuration import WorkflowConfiguration, failure
from .rules import interpretation, logistics, planning, safety
from .rules.common import RULES_VERSION, ensure_execution_mode, input_failure

HYBRID_VERSION = 'b05-hybrid-planning-3'


def _identity(coordinator):
    return {
        'hybrid_agent_version': HYBRID_VERSION,
        'hybrid_kernel_version': RULES_VERSION,
        'hybrid_planning_fingerprint': coordinator.identity['configuration_fingerprint'],
    }


def build_hybrid_configuration(dataset, coordinator, *, safety_case_ids=(), scenarios=(), feedback=None, registered_context=None):
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
                                 feedback=feedback, registered_context=registered)


class HybridPlanningAgent:
    """Complete AgentPort: model planning and opt-in registered assessment roles.

    agent denotes the mixed runtime, not a claim that every step uses an LLM.
    Only PLAN/REVISE generate a model itinerary; REASSESS does not call it.
    """
    supported_operations = frozenset({'PLAN', 'REVISE', 'REASSESS'})
    rules_version = HYBRID_VERSION
    logistics_audit_contract = '1.0'
    safety_audit_contract = '1.0'

    def __init__(self, dataset, coordinator: PlanningCoordinator, *, workflow_configuration=None,
                 heartbeat_interval=20, logistics_agent=None, safety_agent=None):
        if coordinator.dataset is not dataset:
            raise failure(ErrorCode.STALE_CONTEXT, 'Coordinator must consume the same loaded dataset object.')
        self.dataset, self.coordinator = dataset, coordinator
        self.workflow_configuration = workflow_configuration or build_hybrid_configuration(dataset, coordinator)
        self.logistics_agent = logistics_agent
        self.safety_agent = safety_agent
        self.heartbeat_interval = heartbeat_interval
        self._check_configuration()

    def _check_configuration(self):
        context = self.workflow_configuration.context
        if (self.coordinator.dataset is not self.dataset
                or context.dataset_version != self.dataset.context.dataset_version
                or any(context.file_digests.get(key) != value for key, value in self.dataset.context.file_digests.items())
                or any(context.selection_config.get(key) != value for key, value in _identity(self.coordinator).items())):
            raise failure(ErrorCode.STALE_CONTEXT, 'Hybrid dataset/model/kernel configuration changed; start a new run.')
        choices = context.selection_config
        if choices.get('a_logistics_mode') == 'model':
            try:
                role = self.logistics_agent
                seed = strict_json(choices['a_logistics_identity_seed'])
                identity = role.identity
                if (choices.get('a_logistics_audit_required') != '1'
                        or choices.get('a_logistics_audit_contract') != self.logistics_audit_contract
                        or role.dataset is not self.dataset or role.configuration.context != context
                        or role.client.settings.max_turns < 3
                        or identity['workflow_context'] != context.model_dump(mode='json')
                        or identity['configuration_fingerprint'] != digest(canonical({
                            **seed, 'workflow_context': context.model_dump(mode='json')}))
                        or seed != {key: value for key, value in identity.items()
                                    if key not in {'workflow_context', 'configuration_fingerprint'}}):
                    raise ValueError('Logistics identity differs')
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise failure(ErrorCode.STALE_CONTEXT, 'Hybrid logistics component is missing or differs from registered identity.') from exc
        elif self.logistics_agent is not None or any(key.startswith('a_logistics_') for key in choices):
            raise failure(ErrorCode.STALE_CONTEXT, 'Unregistered logistics component or conflicting model markers.')
        if choices.get('a_safety_mode') == 'model':
            try:
                from ..llm.safety_support import matches_live_protocol
                role = self.safety_agent
                seed = strict_json(choices['a_safety_identity_seed'])
                identity = role.identity
                if (choices.get('a_safety_audit_required') != '1'
                        or choices.get('a_safety_audit_contract') != self.safety_audit_contract
                        or not matches_live_protocol(context.dataset_version, seed)
                        or role.dataset is not self.dataset or role.configuration.context != context
                        or role.client.settings.max_turns < 3
                        or not all(callable(getattr(role, name, None)) for name in
                            ('assess_safety_with_trace', 'validate_safety_artifacts'))
                        or identity['workflow_context'] != context.model_dump(mode='json')
                        or identity['configuration_fingerprint'] != digest(canonical({
                            **seed, 'workflow_context': context.model_dump(mode='json')}))
                        or seed != role.identity_seed):
                    raise ValueError('Safety identity differs')
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise failure(ErrorCode.STALE_CONTEXT, 'Hybrid safety component is missing or differs from registered identity.') from exc
        elif self.safety_agent is not None or any(key.startswith('a_safety_') for key in choices):
            raise failure(ErrorCode.STALE_CONTEXT, 'Unregistered safety component or conflicting model markers.')

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
        # No deterministic fallback on any model planning/revision failure.
        return (await self.plan_with_trace(input)).itinerary

    async def assess_gear_and_logistics(self, input: LogisticsInput) -> LogisticsResult:
        if self.logistics_agent is not None:
            return (await self.assess_logistics_with_trace(input)).assessment
        validated = self._input(LogisticsInput, input)
        ids = json.loads(self.workflow_configuration.context.selection_config['safety_case_ids'])
        return self._rule_result(logistics.assess(self.dataset, validated,
            expected_mode=ExecutionMode.AGENT, safety_case_ids=ids), 'gear and costs')

    async def assess_logistics_with_trace(self, input: LogisticsInput) -> LogisticsOutcome:
        validated = self._input(LogisticsInput, input)
        if self.logistics_agent is None:
            raise failure(ErrorCode.CONTRACT_INVALID, 'Model logistics was not registered; no rules fallback.')
        outcome = await self.logistics_agent.assess_with_trace(validated)
        self._check_configuration()
        self.validate_logistics_artifacts(validated, outcome.assessment,
            outcome.plan.model_dump(mode='json'), outcome.trace.model_dump(mode='json'))
        return outcome

    def validate_logistics_artifacts(self, input, result, plan, trace):
        """Pure replay check; never requests a model or persists an audit."""
        validated = self._input(LogisticsInput, input)
        if self.logistics_agent is None:
            raise failure(ErrorCode.CONTRACT_INVALID, 'Model logistics was not registered.')
        ids = json.loads(self.workflow_configuration.context.selection_config['safety_case_ids'])
        baseline = logistics.assess(self.dataset, validated, expected_mode=ExecutionMode.AGENT, safety_case_ids=ids)
        return validate_logistics_payload(validated, baseline, result, plan, trace,
            identity=self.logistics_agent.identity)

    async def assess_safety(self, input: SafetyInput) -> SafetyResult:
        if self.safety_agent is not None:
            return (await self.assess_safety_with_trace(input)).assessment
        return self._rule_result(safety.assess(self.dataset, self._input(SafetyInput, input),
            expected_mode=ExecutionMode.AGENT), 'safety assessment')

    async def assess_safety_with_trace(self, input: SafetyInput) -> SafetyOutcome:
        validated = self._input(SafetyInput, input)
        if self.safety_agent is None:
            raise failure(ErrorCode.CONTRACT_INVALID, 'Model safety was not registered; no rules fallback.')
        outcome = await self.safety_agent.assess_safety_with_trace(validated)
        self._check_configuration()
        self.validate_safety_artifacts(validated, outcome.assessment,
            outcome.plan.model_dump(mode='json'), outcome.trace.model_dump(mode='json'))
        # Do not apply _rule_result: the formal result must equal the complete
        # authoritative baseline byte-for-byte; model advice/trace stay separate.
        return outcome

    def validate_safety_artifacts(self, input, result, plan, trace):
        """Pure replay over the registered pinned facts; no model/persistence IO."""
        validated = self._input(SafetyInput, input)
        if self.safety_agent is None:
            raise failure(ErrorCode.CONTRACT_INVALID, 'Model safety was not registered.')
        return self.safety_agent.validate_safety_artifacts(validated, result, plan, trace)

    async def orchestrate(self, input: OrchestrateInput, persistence: PersistencePort) -> RunResult:
        from ..workflow.orchestration import Orchestrator
        try:
            validated = OrchestrateInput.model_validate(input)
        except (ValidationError, ValueError, TypeError) as exc:
            raise failure(ErrorCode.CONTRACT_INVALID, 'Hybrid orchestration input violates contract 1.0.') from exc
        if validated.run_scope.operation not in self.supported_operations:
            raise input_failure('Unsupported Hybrid operation.', 'operation')
        # The shared orchestrator checks mode/config against A's checkpoint,
        # renews leases during model waits and reuses all saved artifacts.
        return await Orchestrator(self, self.workflow_configuration, persistence,
            heartbeat_interval=self.heartbeat_interval).run(validated)
