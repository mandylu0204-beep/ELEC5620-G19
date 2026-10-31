"""Versioned pure verifier. No model, persistence, files or mutable trace cache."""
from pydantic import ValidationError

from ..contracts.dto import LogisticsResult
from ..contracts.enums import ErrorCode
from .client import model_failure
from .coordinator import canonical, digest
from .logistics_agent import trace_model
from .logistics_schema import LogisticsProposal
from .logistics_tools import LogisticsToolset, ValidatedLogisticsPlan


def validate_logistics_payload(input, baseline, result, raw_plan, raw_trace, *, identity):
    """Verify caller JSON against trusted input, baseline and registered identity.

    The application still owns authorization, archived verifier selection,
    payload size, transaction and receipt association checks.
    """
    try:
        for action in raw_plan['gear_actions']:
            value = action['procurement_quantity']
            if value is not None and not isinstance(value, str):
                raise ValueError('JSON quantities require decimal strings')
        plan = ValidatedLogisticsPlan.model_validate(raw_plan)
        trace = trace_model(identity['agent_version']).model_validate(raw_trace)
        result = LogisticsResult.model_validate(result)
        if (canonical(raw_plan) != canonical(plan.model_dump(mode='json'))
                or canonical(raw_trace) != canonical(trace.model_dump(mode='json'))):
            raise ValueError('Payload requires coercion or implicit fields')
        public = identity['model_client']
        if (trace.configuration_fingerprint != identity['configuration_fingerprint']
                or trace.prompt_sha256 != identity['prompt_sha256']
                or trace.tool_version != identity['tool_version']
                or trace.requested_model != public['model']
                or trace.turns > public['max_turns']
                or trace.http_attempts > trace.turns * public['max_attempts']
                or trace.input_sha256 != digest(input.model_dump_json())
                or trace.rule_facts_sha256 != digest(baseline.model_dump_json())):
            raise ValueError('Trace does not match registered input/facts/identity')
        tools = LogisticsToolset(input, baseline)
        proposal = LogisticsProposal.model_validate({
            'gear_choices': [{'item_key': item.fact.item_key, 'method': item.method,
                             'reason': item.reason_unverified} for item in plan.gear_actions],
            'cost_priority': [item.line_id for item in plan.budget_allocations],
            'decision_summary': plan.decision_summary_unverified,
        })
        recomputed_plan = tools.evaluate_logistics_plan(proposal)
        recomputed_result = tools.result(recomputed_plan)
        if (trace.proposal_sha256 != tools.proposal_hash(proposal)
                or canonical(plan.model_dump(mode='json')) != canonical(recomputed_plan.model_dump(mode='json'))
                or canonical(result.model_dump(mode='json')) != canonical(recomputed_result.model_dump(mode='json'))):
            raise ValueError('Result/proposal does not match deterministic tools')
        return plan, trace
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise model_failure('Logistics model payload does not match registered facts or the strict protocol.', code=ErrorCode.CONTRACT_INVALID) from exc
