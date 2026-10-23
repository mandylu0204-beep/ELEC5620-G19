"""Sydney 2.2 safety protocol: mixed-source facts, unchanged official decisions.

No IO in identity/tool/replay functions. Uses the existing client and durable
audit ports; never relabels an archived 2.1/v2 record as v3.
"""
from datetime import date
import re
from typing import Literal

from .client import model_failure
from .coordinator import digest
from .safety_agent import SafetyAgent as SafetyAgentV2
from .safety_identity import (SafetyIdentitySeed as SeedV2, SAFETY_SYSTEM_PROMPT as PROMPT_V2,
    validate_selection_binding, daily_context)
from .safety_schema import (SAFETY_ACTION, SafetyProposal, SafetyTrace as TraceV2, canonical)
from .safety_tools import SafetyToolset as ToolsV2, ValidatedSafetyPlan, check_payload_size
from .safety_validation import proposal_from_plan
from ..contracts.dto import DatasetContext, SafetyInput, SafetyResult
from ..contracts.enums import ErrorCode
from ..agents.rules.common import RULES_VERSION

AGENT_VERSION = 'campus-safety-advisory-agent-3'
TOOL_VERSION = 'safety-read-only-tools-3'
VALIDATION_VERSION = 'safety-advisory-validation-3'
KERNEL = 'b02-v1-rules-2/a-meal-clarification-v1/a-profile-essentials-v1'
RULES = 'b02-v2-rules-2/a-meal-clarification-v1/a-profile-essentials-v1/trip-evidence-selection-1'
SYSTEM_PROMPT = PROMPT_V2.replace('Use only host-provided synthetic facts.',
    'Use only host-provided versioned facts. Static location information has a\n'
    'sealed source catalogue; weather, dynamic road/fire conditions remain simulated.\n'
    'Reference costs are planning assumptions, not live booking quotes. No source\n'
    'is current official clearance. Never browse source links or invent live checks.')
PROMPT_SHA256 = digest(SYSTEM_PROMPT + canonical(SAFETY_ACTION.json_schema()))


class SafetyIdentitySeed(SeedV2):
    model_config = {'json_schema_extra': {'anyOf': [{'properties': {
        'kernel_version': {'const': KERNEL}, 'dataset_rules_version': {'const': RULES}}}]}}
    agent_version: Literal['campus-safety-advisory-agent-3']
    tool_version: Literal['safety-read-only-tools-3']
    validation_version: Literal['safety-advisory-validation-3']
    kernel_version: Literal[KERNEL]
    dataset_rules_version: Literal[RULES]
    prompt_sha256: Literal[PROMPT_SHA256]


class SafetyTrace(TraceV2):
    tool_version: Literal['safety-read-only-tools-3']


def checked_context(raw):
    context = DatasetContext.model_validate(raw).model_dump(mode='json')
    files, choices = context['file_digests'], context['selection_config']
    if context['dataset_version'] != '2.2.0' or any(
            not re.fullmatch('[0-9a-f]{64}', files.get(name, '')) for name in
            ('source_catalogue.json', 'manifest.json', 'runtime_safety_evidence.json')):
        raise ValueError('V3 requires a registered 2.2 catalogue and evidence snapshot')
    daily = daily_context(context)
    snapshot_keys = {'a_snapshot_date', 'a_snapshot_base', 'a_clock_mode'}
    if daily:
        if (date.fromisoformat(choices['a_snapshot_date']).isoformat() != choices['a_snapshot_date']
                or not re.fullmatch('[0-9a-f]{64}', choices['a_snapshot_base'])
                or choices['a_clock_mode'] not in {'fixed', 'current'}):
            raise ValueError('Incomplete daily snapshot registration')
    elif snapshot_keys & choices.keys():
        raise ValueError('Partial daily snapshot registration')
    return context


def safety_identity_seed(dataset, public_client):
    checked_context(dataset.context)
    return SafetyIdentitySeed.model_validate({
        'agent_version': AGENT_VERSION, 'tool_version': TOOL_VERSION,
        'validation_version': VALIDATION_VERSION, 'kernel_version': RULES_VERSION,
        'dataset_rules_version': dataset.rules_version, 'prompt_sha256': PROMPT_SHA256,
        'model_client': public_client}).model_dump(mode='json', exclude_none=True)


def compose_safety_identity(seed, workflow_context):
    checked = SafetyIdentitySeed.model_validate(seed).model_dump(mode='json', exclude_none=True)
    if canonical(checked) != canonical(seed):
        raise ValueError('Safety seed requires coercion or implicit fields')
    values = {**checked, 'workflow_context': checked_context(workflow_context)}
    return {**values, 'configuration_fingerprint': digest(canonical(values))}


def validate_safety_identity(identity):
    seed = {key: value for key, value in identity.items()
        if key not in {'workflow_context', 'configuration_fingerprint'}}
    if canonical(compose_safety_identity(seed, identity['workflow_context'])) != canonical(identity):
        raise ValueError('V3 identity differs from its complete canonical fingerprint')


class SafetyToolset(ToolsV2):
    dataset_version = '2.2.0'

    def __init__(self, input, baseline, *, selection, workflow_context):
        try:
            self._source_context = checked_context(workflow_context)
            input = SafetyInput.model_validate(input)
            demo = input.demo_context
            if (demo.dataset_version != '2.2.0' or (daily_context(self._source_context)
                    and self._source_context['selection_config']['a_snapshot_date'] != demo.demo_today.isoformat())):
                raise ValueError('Input date/version differs from the pinned snapshot')
            validate_selection_binding(input, selection, self._source_context)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise model_failure('V3 safety source registration differs from the pinned input.',
                code=ErrorCode.STALE_CONTEXT) from None
        super().__init__(input, baseline, selection=selection, daily_snapshot=daily_context(self._source_context))

    def _decorate_facts(self, wire):
        # Frozen SourceRef source family stays SYNTHETIC. This small explicit
        # projection is not the full catalogue, URLs, or a live provenance claim.
        wire['source_provenance'] = {
            'dataset_version': '2.2.0',
            'location_information': 'SEALED_SOURCE_CATALOGUE',
            'dynamic_conditions': 'SIMULATED_NOT_LIVE',
            'costs': 'PLANNING_ASSUMPTIONS_NOT_BOOKING_QUOTES',
            'source_catalogue_sha256': self._source_context['file_digests']['source_catalogue.json'],
            'official_clearance': False}
        return wire


def validate_safety_payload(input, baseline, result, raw_plan, raw_trace, *, identity, selection):
    try:
        input, baseline, result = (SafetyInput.model_validate(input),
            SafetyResult.model_validate(baseline), SafetyResult.model_validate(result))
        validate_safety_identity(identity)
        selection = validate_selection_binding(input, selection, identity['workflow_context'])
        check_payload_size(input, result, raw_plan, raw_trace)
        plan, trace = ValidatedSafetyPlan.model_validate(raw_plan), SafetyTrace.model_validate(raw_trace)
        if (canonical(raw_plan) != canonical(plan.model_dump(mode='json'))
                or canonical(raw_trace) != canonical(trace.model_dump(mode='json'))
                or canonical(result.model_dump(mode='json')) != canonical(baseline.model_dump(mode='json'))):
            raise ValueError('Artifacts require coercion or differ from complete rules baseline')
        public = identity['model_client']
        if (trace.configuration_fingerprint != identity['configuration_fingerprint']
                or trace.prompt_sha256 != identity['prompt_sha256'] or trace.tool_version != TOOL_VERSION
                or trace.requested_model != public['model'] or trace.turns > public['max_turns']
                or trace.http_attempts > trace.turns * public['max_attempts']
                or trace.input_sha256 != digest(input.model_dump_json())
                or trace.rule_facts_sha256 != digest(baseline.model_dump_json())):
            raise ValueError('Trace differs from registered identity, input or limits')
        tools = SafetyToolset(input, baseline, selection=selection, workflow_context=identity['workflow_context'])
        proposal = proposal_from_plan(plan)
        replay = tools.evaluate_safety_plan(proposal)
        if (trace.proposal_sha256 != tools.proposal_hash(proposal)
                or canonical(plan.model_dump(mode='json')) != canonical(replay.model_dump(mode='json'))):
            raise ValueError('Proposal differs from exact deterministic evaluation')
        check_payload_size(input, result, raw_plan, raw_trace)
        return plan, trace
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise model_failure('Safety artifacts differ from the registered strict v3 protocol.',
            code=ErrorCode.CONTRACT_INVALID) from None


class SafetyAgent(SafetyAgentV2):
    """Explicit 2.2 role, using the v2 loop without changing archived v2 policy."""
    dataset_version = '2.2.0'
    system_prompt = SYSTEM_PROMPT
    tool_version = TOOL_VERSION
    trace_type = SafetyTrace
    compose_identity = staticmethod(compose_safety_identity)
    make_identity_seed = staticmethod(safety_identity_seed)
    validate_payload = staticmethod(validate_safety_payload)

    def _check_configuration(self):
        super()._check_configuration()
        try:
            checked_context(self.configuration.context)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise model_failure('V3 safety requires complete catalogue/snapshot registration.',
                code=ErrorCode.STALE_CONTEXT) from None

    def make_tools(self, input, baseline, selection, identity):
        return SafetyToolset(input, baseline, selection=selection, workflow_context=identity['workflow_context'])


def safety_contract_document():
    from .safety_contract import safety_contract_document as v2_document
    document = v2_document()
    document.update(status='IMPLEMENTED_OFFLINE_LIVE_ACCEPTANCE_PENDING', agent_version=AGENT_VERSION,
        tool_version=TOOL_VERSION, validation_version=VALIDATION_VERSION, prompt_sha256=PROMPT_SHA256,
        supported_dataset_versions=['2.2.0'],
        supported_kernel_rule_pairs=[{'kernel_version': KERNEL, 'dataset_rules_version': RULES}])
    document['schemas']['identity_seed'] = SafetyIdentitySeed.model_json_schema()
    document['schemas']['trace'] = SafetyTrace.model_json_schema()
    document['notes'] = [
        'Default safety remains rules. Explicit model mode requires complete registered production wiring.',
        'Shared schema and audit envelope remain 1.0; this is a distinct 2.2/v3 advisory protocol.',
        'Sealed static location sources are distinct from simulated conditions and reference cost assumptions.',
        'All existing v2 text/action/size/finding limits apply; no truncation, fallback or authority from model advice.',
        'V1/V2 archived validators and prompt identities remain available without regeneration.']
    return document
