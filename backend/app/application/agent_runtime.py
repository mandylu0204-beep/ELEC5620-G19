"""Trusted application bindings. Factories consume the inspected dataset snapshot.

Legacy factories remain useful for stub and independent test doubles. Dataset
factories return the actual Agent together with its complete workflow context.
"""
from dataclasses import dataclass, replace
import hashlib
import json
from inspect import signature, unwrap
from threading import RLock

from pydantic import ValidationError

from ..contracts.dto import DatasetContext, DemoContext, ScenarioContext
from ..contracts.enums import ErrorCode, ExecutionMode
from ..contracts.errors import ContractError, ContractFailure
from ..contracts.ports import AgentPort
from .agent_registry import create_agent
from .datasets import DatasetDescriptor, inspect_dataset, scenario_path
from ..agents.rules.transport import POLICY_KEY, POLICY_VERSION, MINIMAL_POLICY_VERSION, checked_policy
from ..adapters.planning_reference import (POLICY_KEY as PLANNING_KEY, POLICY_VERSION as PLANNING_VERSION, checked_policy as checked_planning)
from ..llm.safety_feedback import (POLICY_KEY as FEEDBACK_KEY, POLICY_VERSION as FEEDBACK_VERSION,
    checked_policy as checked_feedback)
from .weather_events import POLICY_VERSION as WEATHER_VERSION, POLICY_KEY as WEATHER_KEY, validate_saved as validate_weather


@dataclass(frozen=True)
class AgentBinding:
    agent: AgentPort
    context: DatasetContext


@dataclass(frozen=True)
class RuntimeSnapshot:
    agent: AgentPort | None
    demo: DemoContext
    dataset: DatasetContext
    descriptor: DatasetDescriptor

    @property
    def supported_operations(self):
        if self.agent is None or self.demo.mode == ExecutionMode.STUB:
            return frozenset()
        return getattr(self.agent, 'supported_operations', frozenset({'PLAN','REVISE','REASSESS'}))

    def require_operation(self, operation, requirements=None):
        if operation not in self.supported_operations:
            raise ContractFailure(ContractError(code=ErrorCode.INPUT_INVALID, message='This mode does not support the operation. Create and confirm a new request.'))
        if self.demo.mode == ExecutionMode.AGENT and requirements is not None and requirements.duration_nights > 30:
            raise ContractFailure(ContractError(code=ErrorCode.INPUT_INVALID, message='Initial hybrid planning supports at most 30 nights. No run created.'))


def configured_scenarios(settings, descriptor):
    scenarios = []
    for name in settings.dataset_scenario_files:
        try:
            payload = scenario_path(settings.dataset_path, name).read_bytes()
        except (OSError, ValueError) as exc:
            raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Scenario file became unreadable during loading. Reload it.')) from exc
        if hashlib.sha256(payload).hexdigest() != descriptor.context.fixture_digests[name]:
            raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Scenario file changed during loading. Reload it.'))
        try:
            value = json.loads(payload.decode('utf-8-sig'))
            scenarios.extend(ScenarioContext.model_validate(item) for item in (value if isinstance(value, list) else [value]))
        except (ValueError, TypeError, ValidationError) as exc:
            raise ContractFailure(ContractError(code=ErrorCode.ADAPTER_FAILURE, message='The registered scenario is not valid  ScenarioContext.', context={'dataset_file': name})) from exc
    return scenarios


def build_v1_rule_binding(settings, descriptor):
    # Import on demand: default stub installation does not load business rules.
    from ..adapters import SyntheticDatasetAdapter
    from ..agents.rule_agent import RuleAgent
    from ..workflow import WorkflowConfiguration

    dataset = SyntheticDatasetAdapter(settings.dataset_path).load()
    if dataset.context.dataset_version != descriptor.context.dataset_version or any(
        descriptor.context.file_digests.get(name) != value for name, value in dataset.context.file_digests.items()
    ):
        raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Adapter Consumed bytes do not match registered application inputs.'))
    base = descriptor.context.model_copy(update={'rules_version': descriptor.context.rules_version + '/a-runtime-bindings-v2'})
    configuration = WorkflowConfiguration(dataset, safety_case_ids=settings.workflow_safety_case_ids,
        scenarios=configured_scenarios(settings, descriptor), registered_context=base,
        feedback=base.selection_config.get('a_revision_feedback') or None)
    return AgentBinding(RuleAgent(dataset, workflow_configuration=configuration), configuration.context)


def build_v2_binding(settings, descriptor, *, parsed_snapshots=None, snapshot_key=()):
    """Bind the sealed v2 bytes and explicit safety selections to a real RuleAgent."""
    from ..adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
    from ..agents.rule_agent import RuleAgent
    from ..workflow import WorkflowConfiguration

    dataset = SyntheticDatasetV2Adapter(settings.dataset_path).load(expected_context=descriptor.context,
        parsed_snapshots=parsed_snapshots, snapshot_key=snapshot_key)
    from ..adapters.transport_reference import bind_reference
    bind_reference(dataset, descriptor.context)
    from ..adapters.planning_reference import bind_reference as bind_planning
    bind_planning(dataset, descriptor.context)
    dataset.selected_safety_case_ids = tuple(settings.workflow_safety_case_ids)
    base = descriptor.context.model_copy(update={'rules_version': descriptor.context.rules_version + '/a-runtime-bindings-v2'})
    configuration = WorkflowConfiguration(dataset, safety_case_ids=settings.workflow_safety_case_ids,
        scenarios=configured_scenarios(settings, descriptor), registered_context=base,
        feedback=base.selection_config.get('a_revision_feedback') or None)
    return AgentBinding(RuleAgent(dataset, workflow_configuration=configuration), configuration.context)


# B can register v2 under its own explicit source family. No fallback to v1.
def build_v2_hybrid_binding(settings, descriptor, *, parsed_snapshots=None, snapshot_key=()):
    from ..adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
    from ..agents.hybrid_planning_agent import HybridPlanningAgent, build_hybrid_configuration
    from ..llm.config import CampusModelSettings
    from ..llm.client import CampusModelClient
    from ..llm.coordinator import PlanningCoordinator
    from ..workflow import WorkflowConfiguration
    from .logistics_audit import identity_seed, canonical, digest
    roles = {'logistics':settings.logistics_execution, 'safety':settings.safety_execution}
    if settings.safety_protocol == 'compact' and (
            settings.safety_execution != 'model' or descriptor.context.dataset_version != '2.2.0'):
        raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
            message='Compact safety requires model safety with the 2.2 dataset.'))
    for role, mode in roles.items():
        if mode == 'rules' and any(key.startswith(f'a_{role}_') for key in descriptor.context.selection_config):
            raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT,
                message=f'Rule {role} configuration cannot carry model registration markers.'))
    if settings.safety_execution == 'model':
        from ..workflow.orchestration import Orchestrator
        from ..llm.safety_support import selected_protocol
        if (selected_protocol(descriptor.context.dataset_version, settings.safety_protocol) is None
                or getattr(HybridPlanningAgent,'safety_audit_contract',None) != '1.0'
                or not callable(getattr(HybridPlanningAgent,'assess_safety_with_trace',None))
                or getattr(Orchestrator,'safety_audit_contract',None) != '1.0'):
            raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
                message='Model safety requires a supported dataset and complete Hybrid/Orchestrator audit integration.'))
    try:
        client = CampusModelClient(CampusModelSettings())
    except (ValidationError, ValueError):
        raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
            message='Campus model local configuration is invalid.')) from None
    client.validate_configuration()
    dataset = SyntheticDatasetV2Adapter(settings.dataset_path).load(expected_context=descriptor.context,
        parsed_snapshots=parsed_snapshots,
        snapshot_key=(snapshot_key, json.dumps(client.settings.public_identity(), sort_keys=True)))
    from ..adapters.transport_reference import bind_reference
    bind_reference(dataset, descriptor.context)
    from ..adapters.planning_reference import bind_reference as bind_planning
    bind_planning(dataset, descriptor.context)
    coordinator = PlanningCoordinator(dataset, client)
    identity = coordinator.identity
    choices = {**descriptor.context.selection_config, 'a_model_trace_required':'1', 'a_model_trace_contract':'1.0',
        'a_model_trace_binding':'origin-version-v1',
        'a_model_prompt_sha256':identity['prompt_sha256'], 'a_model_tool_version':identity['tool_version'],
        'a_model_requested_model':client.settings.model}
    base = descriptor.context.model_copy(update={'selection_config':choices,
        'rules_version':descriptor.context.rules_version + '/a-runtime-bindings-v2/a-model-audit-v2'})
    scenarios = configured_scenarios(settings, descriptor)
    feedback = base.selection_config.get('a_revision_feedback') or None
    seeds, constructors = {}, {}
    if any(mode == 'model' for mode in roles.values()):
        if client.settings.max_turns < 3:
            raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
                message='Model assessment roles require at least three supported turns.'))
        temporary = WorkflowConfiguration(dataset,safety_case_ids=settings.workflow_safety_case_ids,
            scenarios=scenarios,registered_context=base,feedback=feedback)
        if settings.logistics_execution == 'model':
            from ..llm.logistics_agent import LogisticsAgent
            if (not callable(getattr(HybridPlanningAgent,'assess_logistics_with_trace',None))
                    or getattr(HybridPlanningAgent,'logistics_audit_contract',None) != '1.0'):
                raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
                    message='Model logistics audit integration is incomplete.'))
            constructors['logistics'] = LogisticsAgent
            seeds['logistics'] = identity_seed(LogisticsAgent(dataset,client,workflow_configuration=temporary))
        if settings.safety_execution == 'model':
            if settings.safety_protocol == 'compact':
                from ..llm.safety_v4 import SafetyAgent
            elif dataset.context.dataset_version == '2.2.0':
                from ..llm.safety_v3 import SafetyAgent
            else:
                from ..llm.safety_agent import SafetyAgent
            constructors['safety'] = SafetyAgent
            seeds['safety'] = SafetyAgent(dataset,client,workflow_configuration=temporary).identity_seed
    # Collect every seed before binding any component to the final context.
    for role, seed in seeds.items():
        markers = {f'a_{role}_mode':'model',f'a_{role}_audit_required':'1',
            f'a_{role}_audit_contract':'1.0',f'a_{role}_identity_seed':canonical(seed)}
        if any(key in base.selection_config and base.selection_config[key] != value for key,value in markers.items()):
            raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT,
                message=f'Conflicting {role} model registration.'))
        base = base.model_copy(update={'selection_config':{**base.selection_config,**markers},
            'rules_version':base.rules_version+f'/a-model-{role}-audit-v1'})
    configuration = build_hybrid_configuration(dataset,coordinator,
        safety_case_ids=settings.workflow_safety_case_ids,scenarios=scenarios,registered_context=base,feedback=feedback)
    components = {}
    for role, constructor in constructors.items():
        component = constructor(dataset,client,workflow_configuration=configuration)
        expected = digest(canonical({**seeds[role],'workflow_context':configuration.context.model_dump(mode='json')}))
        if component.identity['configuration_fingerprint'] != expected:
            raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT,
                message=f'{role} component identity differs from the final workflow context.'))
        components[f'{role}_agent'] = component
    try:
        agent = HybridPlanningAgent(dataset,coordinator,workflow_configuration=configuration,
            request_interpretation=True,**components)
    except TypeError:
        raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
            message='Hybrid does not accept the registered model assessment components.')) from None
    if (getattr(agent, 'model_request_terms', False) is not True
            or not callable(getattr(agent, 'interpret_request_with_observation', None))
            or not getattr(agent, 'request_interpretation_identity', None)):
        raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
            message='Hybrid did not bind the registered request interpretation capability.'))
    for name, component in components.items():
        if getattr(agent,name,None) is not component:
            raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
                message='Hybrid did not bind the registered assessment component.'))
    return AgentBinding(agent, configuration.context)


DATASET_AGENT_FACTORIES = {
    (ExecutionMode.DETERMINISTIC_DEMO, 'CampMate Synthetic Demo Dataset v1'): build_v1_rule_binding,
    (ExecutionMode.DETERMINISTIC_DEMO, 'CampMate Synthetic Demo Dataset v2'): build_v2_binding,
    (ExecutionMode.AGENT, 'CampMate Synthetic Demo Dataset v2'): build_v2_hybrid_binding,
}

PARSED_SNAPSHOT_FACTORIES = (build_v2_binding, build_v2_hybrid_binding)


class AgentRuntime:
    def __init__(self, state):
        from .parsed_snapshots import ParsedSnapshots
        self.state = state
        self._lock = RLock()
        self._parsed_snapshots = ParsedSnapshots(capacity=4)
        self.configured_agent = None
        state.agent = create_agent(state.settings.execution_mode)
        self.managed_mode = state.settings.execution_mode if state.agent is None and state.settings.execution_mode in {ExecutionMode.DETERMINISTIC_DEMO, ExecutionMode.AGENT} else None
        self.error = None
        if self.managed_mode is not None:
            try:
                self.resolve()
            except ContractFailure as exc:
                self.error = exc.error

    def resolve(self, *, feedback=None, snapshot_day=None, safety_protocol=None, transport_policy=POLICY_VERSION,
                safety_feedback_policy=FEEDBACK_VERSION, planning_policy=PLANNING_VERSION, weather_policy=WEATHER_VERSION):
        # HTTP reads run in worker threads while the supervisor runs on asyncio.
        # Keep the managed Agent marker and state.agent replacement consistent.
        with self._lock:
            with self._parsed_snapshots.transaction():
                return self._resolve(feedback=feedback, snapshot_day=snapshot_day, safety_protocol=safety_protocol,
                    transport_policy=transport_policy, safety_feedback_policy=safety_feedback_policy, planning_policy=planning_policy,
                    weather_policy=weather_policy)

    def for_scope(self, scope):
        choices=scope.dataset_context.selection_config
        # Read external extension bytes against the SAVED digest before any
        # current registration/cache can substitute a different distance table.
        from ..adapters.transport_reference import register_reference
        register_reference(scope.dataset_context)
        from ..adapters.planning_reference import register_reference as register_planning
        register_planning(scope.dataset_context)
        validate_weather(scope.dataset_context)
        # Recovery consumes its registered date/snapshot even after midnight.
        # Eligibility/finalisation uses validate_scope's CURRENT resolution.
        pinned=scope.demo_context.demo_today if choices.get('a_daily_snapshot')=='synthetic-daily-v1' else None
        if choices.get('a_safety_mode') == 'model':
            from ..llm.safety_support import protocol_for_seed
            from .logistics_audit import decode
            try:
                protocol = protocol_for_seed(scope.dataset_context.dataset_version,
                    decode(choices['a_safety_identity_seed']))
            except (ValueError, TypeError, KeyError):
                protocol = None
            if protocol is None:
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT,
                    message='Saved safety protocol is unknown or incomplete; do not change its identity.'))
            if protocol != self.state.settings.safety_protocol:
                # Reconstruct the registered protocol only. All other current
                # flags, client configuration, bytes and scope checks still run.
                return self.resolve(feedback=choices.get('a_revision_feedback') or None,
                    snapshot_day=pinned, safety_protocol=protocol, transport_policy=choices.get(POLICY_KEY),
                    safety_feedback_policy=choices.get(FEEDBACK_KEY), planning_policy=choices.get(PLANNING_KEY),
                    weather_policy=choices.get(WEATHER_KEY))
        return self.resolve(feedback=choices.get('a_revision_feedback') or None, snapshot_day=pinned,
            transport_policy=choices.get(POLICY_KEY), safety_feedback_policy=choices.get(FEEDBACK_KEY), planning_policy=choices.get(PLANNING_KEY),
            weather_policy=choices.get(WEATHER_KEY))

    def validate_scope(self, scope):
        # Internal legacy fixtures predate runtime bindings. All HTTP-created
        # runs from the managed runtime carry this server-owned marker.
        choices = scope.dataset_context.selection_config
        if choices.get('a_runtime_bound') != '1' and '/a-runtime-bindings-v1/' not in scope.dataset_context.rules_version:
            return
        snapshot = self.resolve(feedback=choices.get('a_revision_feedback') or None)
        if snapshot.demo != scope.demo_context or snapshot.dataset != scope.dataset_context:
            raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Run data, settings or clock changed. Reassess.'))
        return snapshot

    def _resolve(self, *, feedback=None, snapshot_day=None, safety_protocol=None, transport_policy=POLICY_VERSION,
                 safety_feedback_policy=FEEDBACK_VERSION, planning_policy=PLANNING_VERSION, weather_policy=WEATHER_VERSION):
        checked_policy(transport_policy)
        checked_feedback(safety_feedback_policy)
        checked_planning(planning_policy)
        settings = self.state.settings
        if safety_protocol is not None:
            if safety_protocol not in {'standard', 'compact'}:
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Unknown safety protocol.'))
            settings = settings.model_copy(update={'safety_protocol': safety_protocol})
        today=settings.checking_date()
        if snapshot_day is not None:
            today=snapshot_day
        from .daily_snapshot import effective_settings
        descriptor=inspect_dataset(settings)
        effective=effective_settings(settings,today,base=descriptor,weather_policy=weather_policy)
        if effective is not settings:
            descriptor=inspect_dataset(effective)
        settings=effective
        if (settings.logistics_execution == 'model' or settings.safety_execution == 'model') and settings.execution_mode != ExecutionMode.AGENT:
            raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE, message='Model assessment roles require registered agent mode.'))
        if settings.safety_protocol == 'compact' and (settings.execution_mode != ExecutionMode.AGENT
                or settings.safety_execution != 'model' or descriptor.context.dataset_version != '2.2.0'):
            raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
                message='Compact safety requires agent mode, model safety and the 2.2 dataset.'))
        agent, context = self.state.agent, descriptor.context
        managed = (self.configured_agent is not None and agent is self.configured_agent) or (
            self.configured_agent is None and agent is None and self.managed_mode is not None)
        if managed:
            choices = {key: value for key, value in descriptor.context.selection_config.items() if key != 'a_revision_feedback'}
            choices['a_runtime_bound'] = '1'
            if settings.safety_execution == 'model' and descriptor.context.dataset_version == '2.2.0':
                if safety_feedback_policy is not None:
                    if choices.get(FEEDBACK_KEY, safety_feedback_policy) != safety_feedback_policy:
                        raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Conflicting safety feedback policy registration.'))
                    choices[FEEDBACK_KEY] = safety_feedback_policy
                elif FEEDBACK_KEY in choices:
                    raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='An old run cannot adopt a new safety feedback policy.'))
            if descriptor.context.dataset_version.startswith('2.'):
                if transport_policy == POLICY_VERSION and descriptor.context.dataset_version != '2.2.0':
                    transport_policy = MINIMAL_POLICY_VERSION
                # A server-owned policy dimension, pinned by the complete
                # context fingerprint. for_scope reconstructs absence for old runs.
                if transport_policy is not None:
                    if choices.get(POLICY_KEY, transport_policy) != transport_policy:
                        raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Conflicting transport rule registration.'))
                    choices[POLICY_KEY] = transport_policy
                elif POLICY_KEY in choices:
                    raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='An old run cannot adopt new transport rules.'))
            if descriptor.context.dataset_version == '2.2.0' and planning_policy is not None:
                if choices.get(PLANNING_KEY, planning_policy) != planning_policy:
                    raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Conflicting itinerary reference registration.'))
                choices[PLANNING_KEY] = planning_policy
            elif PLANNING_KEY in choices:
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='An old run cannot adopt new itinerary reference data.'))
            if feedback is not None:
                choices['a_revision_feedback'] = feedback
            descriptor = replace(descriptor, context=descriptor.context.model_copy(update={'selection_config': choices}))
            from ..adapters.transport_reference import register_reference
            descriptor = replace(descriptor, context=register_reference(descriptor.context))
            from ..adapters.planning_reference import register_reference as register_planning
            descriptor = replace(descriptor, context=register_planning(descriptor.context))
            if settings.execution_mode != self.managed_mode:
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Execution mode changed. Restart the application in the corresponding mode.'))
            factory = DATASET_AGENT_FACTORIES.get((settings.execution_mode, descriptor.provenance.source_name))
            if factory is None:
                raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE, message='Business support for this data version  Adapter  is not registered. Planning cannot start.', context={'dataset_version': context.dataset_version}))
            snapshot_options = dict(parsed_snapshots=self._parsed_snapshots,
                snapshot_key=(today.isoformat(), settings.model_dump_json(), factory))
            accepts_snapshot_options = False
            if unwrap(factory) in PARSED_SNAPSHOT_FACTORIES:
                try:
                    # @wraps exposes the original signature by default, but the
                    # callable wrapper may still accept only the legacy pair.
                    signature(factory, follow_wrapped=False).bind(settings, descriptor, **snapshot_options)
                except (TypeError, ValueError):
                    pass
                else:
                    accepts_snapshot_options = True
            if accepts_snapshot_options:
                binding = factory(settings, descriptor, parsed_snapshots=self._parsed_snapshots,
                    snapshot_key=snapshot_options['snapshot_key'])
            else:
                binding = factory(settings, descriptor)
            agent, context = binding.agent, binding.context
            if feedback is not None and context.selection_config.get('revision_feedback') != feedback:
                raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE, message='Current Adapter Revision feedback is not connected. Revision cannot start.'))
            if context.dataset_version != descriptor.context.dataset_version or any(
                context.file_digests.get(name) != value for name, value in descriptor.context.file_digests.items()
            ) or any(context.fixture_digests.get(name) != value for name, value in descriptor.context.fixture_digests.items()) or any(
                context.selection_config.get(name) != value for name, value in descriptor.context.selection_config.items()
            ) or not context.rules_version.startswith(descriptor.context.rules_version + '/'):
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='Business settings omit or change registered application data, selections or rule identity.'))
            self.configured_agent = agent
            self.state.agent = agent
        elif feedback is not None:
            raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE, message='Current Agent Plan revision is not connected.'))
        if settings.logistics_execution == 'model' and (
                context.selection_config.get('a_logistics_audit_required') != '1'
                or context.selection_config.get('a_logistics_mode') != 'model'
                or getattr(agent, 'logistics_audit_contract', None) != '1.0'
                or not callable(getattr(agent, 'assess_logistics_with_trace', None))):
            raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE, message='The current run has no complete logistics model capability registration.'))
        if settings.safety_execution == 'model':
            from ..workflow.orchestration import Orchestrator
            from ..llm.safety_support import matches_live_protocol
            from .logistics_audit import decode
            try:
                protocol_matches = matches_live_protocol(context.dataset_version,
                    decode(context.selection_config['a_safety_identity_seed']), protocol=settings.safety_protocol)
            except (ValueError, TypeError, KeyError, AttributeError):
                protocol_matches = False
            if (not protocol_matches or context.selection_config.get('a_safety_audit_required') != '1'
                    or context.selection_config.get('a_safety_audit_contract') != '1.0'
                    or context.selection_config.get('a_safety_mode') != 'model'
                    or getattr(agent,'safety_audit_contract',None) != '1.0'
                    or not callable(getattr(agent,'assess_safety_with_trace',None))
                    or getattr(Orchestrator,'safety_audit_contract',None) != '1.0'):
                raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
                    message='The current runtime does not provide registered model safety capability.'))
        self.error = None
        return RuntimeSnapshot(agent, DemoContext(mode=settings.execution_mode, demo_today=today,
            dataset_version=context.dataset_version), context, descriptor)
