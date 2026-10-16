# Frozen from 7eab8e7 for archived validation; do not route new model calls here.
"""Versioned pure advisory replay. Caller supplies authoritative saved facts."""
from types import MappingProxyType

from ...contracts.dto import SafetyInput, SafetyResult
from ...contracts.enums import ErrorCode
from ..client import model_failure
from ..coordinator import digest
from .safety_identity import validate_safety_identity, validate_selection_binding, daily_context
from .safety_schema import SafetyProposal, SafetyTrace, SAFETY_VALIDATION_VERSION, canonical
from .safety_tools import SafetyToolset, ValidatedSafetyPlan, check_payload_size


def proposal_from_plan(plan):
    return SafetyProposal(findings=[item.model_dump(exclude={'fact_refs'}) for item in plan.findings],
        action_priority=list(plan.action_priority), decision_summary_unverified=plan.decision_summary_unverified)


def validate_safety_payload(input, baseline, result, raw_plan, raw_trace, *, identity, selection):
    """No model, current key/clock, files or database. Returns (plan, trace).

    A must reconstruct input and selection from the pinned authorized snapshot,
    recompute the complete baseline with the registered kernel, then call this
    version. This function does not certify caller-supplied facts or ownership.
    """
    try:
        input = SafetyInput.model_validate(input)
        baseline = SafetyResult.model_validate(baseline)
        result = SafetyResult.model_validate(result)
        validate_safety_identity(identity)
        selection = validate_selection_binding(input,selection,identity['workflow_context'])
        check_payload_size(input,result,raw_plan,raw_trace)
        plan = ValidatedSafetyPlan.model_validate(raw_plan)
        trace = SafetyTrace.model_validate(raw_trace)
        if (canonical(raw_plan) != canonical(plan.model_dump(mode='json'))
                or canonical(raw_trace) != canonical(trace.model_dump(mode='json'))
                or canonical(result.model_dump(mode='json')) != canonical(baseline.model_dump(mode='json'))):
            raise ValueError('Plan/trace require coercion or result differs from the complete baseline')
        public = identity['model_client']
        if (trace.configuration_fingerprint != identity['configuration_fingerprint']
                or trace.prompt_sha256 != identity['prompt_sha256'] or trace.tool_version != identity['tool_version']
                or trace.requested_model != public['model'] or trace.turns > public['max_turns']
                or trace.http_attempts > trace.turns * public['max_attempts']
                or trace.input_sha256 != digest(input.model_dump_json())
                or trace.rule_facts_sha256 != digest(baseline.model_dump_json())):
            raise ValueError('Trace differs from registered input/baseline/identity/limits')
        tools = SafetyToolset(input, baseline, selection=selection,
            daily_snapshot=daily_context(identity['workflow_context']))
        proposal = proposal_from_plan(plan)
        replay = tools.evaluate_safety_plan(proposal)
        if (trace.proposal_sha256 != tools.proposal_hash(proposal)
                or canonical(plan.model_dump(mode='json')) != canonical(replay.model_dump(mode='json'))):
            raise ValueError('Plan differs from exact deterministic evaluation')
        check_payload_size(input,result,raw_plan,raw_trace)
        return plan, trace
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise model_failure('Safety artifacts differ from the registered strict advisory protocol.', code=ErrorCode.CONTRACT_INVALID) from None


SAFETY_VALIDATORS = MappingProxyType({SAFETY_VALIDATION_VERSION:validate_safety_payload})


def safety_validator_for(version):
    if version not in SAFETY_VALIDATORS:
        raise model_failure('Saved safety validation version is unavailable; do not regenerate its audit.', code=ErrorCode.PERSISTENCE_FAILURE)
    return SAFETY_VALIDATORS[version]
