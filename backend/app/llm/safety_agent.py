"""Opt-in standalone campus safety adviser. No persistence or registration."""
from dataclasses import dataclass
import time

from ..agents.rules import safety
from ..agents.rules.common import ensure_execution_mode
from ..contracts.dto import SafetyInput, SafetyResult
from ..contracts.enums import ErrorCode, ExecutionMode
from ..contracts.errors import ContractFailure
from .client import model_failure
from .coordinator import digest
from .safety_identity import (SAFETY_SYSTEM_PROMPT, compose_safety_identity, safety_identity_seed,
    validate_selection_binding, daily_context)
from .safety_schema import (SAFETY_ACTION, SAFETY_TOOL_VERSION, EvaluateSafetyAction, FinalSafetyAction,
    ReadSafetyFactsAction, SafetyTrace, canonical, parse_safety_action)
from .safety_tools import SafetyToolset, ValidatedSafetyPlan, check_payload_size
from .safety_validation import validate_safety_payload


@dataclass(frozen=True)
class SafetyOutcome:
    assessment: SafetyResult
    plan: ValidatedSafetyPlan
    trace: SafetyTrace


class SafetyAgent:
    """B component only. A30 persistence/factory/Hybrid wiring is NOT enabled.

    Once A freezes the contract, Hybrid can delegate the trace-returning method
    and pure replay helper here. Never discard the advice/trace and save only a
    relabeled rules result. No last_trace slot or global result cache exists.
    """
    def __init__(self, dataset, client, *, workflow_configuration):
        self.dataset, self.client, self.configuration = dataset, client, workflow_configuration
        self._check_configuration()
        try:
            compose_safety_identity(safety_identity_seed(dataset,client.identity),self.configuration.context)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise model_failure('Safety client identity or tool limits are unsupported.',code=ErrorCode.CONTRACT_INVALID) from None

    def _check_configuration(self):
        context = self.configuration.context
        if (context.dataset_version != '2.1.0' or self.dataset.context.dataset_version != context.dataset_version
                or getattr(self.dataset,'trip_evidence_selector',None) is None
                or any(context.file_digests.get(key) != value for key,value in self.dataset.context.file_digests.items())):
            raise model_failure('Safety component requires the registered agent/2.1 evidence snapshot.', code=ErrorCode.STALE_CONTEXT)

    @property
    def identity_seed(self):
        try:
            return safety_identity_seed(self.dataset,self.client.identity)
        except (ValueError,TypeError,KeyError,AttributeError):
            raise model_failure('Safety public identity changed to an unsupported configuration.',code=ErrorCode.STALE_CONTEXT) from None

    @property
    def identity(self):
        try:
            return compose_safety_identity(self.identity_seed,self.configuration.context)
        except (ValueError,TypeError,KeyError,AttributeError):
            raise model_failure('Safety workflow identity is invalid.',code=ErrorCode.STALE_CONTEXT) from None

    def _facts(self, input):
        self._check_configuration()
        selection = self.configuration.resolve_trip_evidence(input.confirmed_requirements,
            input.saved_itinerary.selected_campsite_ids,input.demo_context)
        if selection.scenario_context != input.scenario_context:
            raise model_failure('Safety scenario differs from the pinned trip evidence selection.', code=ErrorCode.STALE_CONTEXT)
        baseline = safety.assess(self.dataset,input,expected_mode=ExecutionMode.AGENT)
        try:
            validate_selection_binding(input,selection,self.configuration.context.model_dump(mode='json'))
        except (ValueError,TypeError,KeyError):
            raise model_failure('Safety selection does not match its registered snapshot identity.',code=ErrorCode.STALE_CONTEXT) from None
        return baseline, selection

    def _input(self, raw):
        try:
            input = SafetyInput.model_validate(raw).model_copy(deep=True)
        except (ValueError, TypeError):
            raise model_failure('Safety input violates the shared contract.', code=ErrorCode.CONTRACT_INVALID) from None
        ensure_execution_mode(self.dataset,input.demo_context,ExecutionMode.AGENT)
        if (input.confirmed_requirements.start_date < input.demo_context.demo_today
                or input.confirmed_requirements.duration_nights > 30):
            raise model_failure('Safety component supports confirmed future trips of at most thirty nights.', code=ErrorCode.INPUT_INVALID)
        return input

    def validate_safety_artifacts(self, input, result, plan, trace):
        validated = self._input(input)
        baseline, selection = self._facts(validated)
        return validate_safety_payload(validated,baseline,result,plan,trace,identity=self.identity,selection=selection)

    async def assess_safety_with_trace(self, raw):
        input = self._input(raw)
        identity = self.identity
        baseline, selection = self._facts(input)
        facts_hash, selection_hash = digest(baseline.model_dump_json()), selection.selection_digest
        tools = SafetyToolset(input,baseline,selection=selection,
            daily_snapshot=daily_context(identity['workflow_context']))
        messages = [
            {'role':'system','content':SAFETY_SYSTEM_PROMPT+'\nACTION_SCHEMA='+canonical(SAFETY_ACTION.json_schema())},
            {'role':'user','content':canonical({'operation':'SAFETY_ADVISORY',
                'selected_campsite_ids':list(input.saved_itinerary.selected_campsite_ids),
                'confirmed_requirements':input.confirmed_requirements.model_dump(mode='json'),
                'demo_context':input.demo_context.model_dump(mode='json')})}]
        calls, hashes, served, usage = [], [], [], {}
        last_proposal, last_plan = None, None
        attempts, started = 0, time.monotonic()
        for turn in range(1,self.client.settings.max_turns+1):
            try:
                response = await self.client.complete(messages)
            except ContractFailure as exc:
                raise ContractFailure(exc.error.model_copy(update={'context':{
                    **exc.error.context,'role':'SAFETY','safety_turn':str(turn),
                    'elapsed_ms':str(int((time.monotonic()-started)*1000)),
                    'request_message_bytes':str(sum(len(item['content'].encode('utf-8')) for item in messages))}})) from None
            current, current_selection = self._facts(input)
            if (self.identity != identity or digest(current.model_dump_json()) != facts_hash
                    or current_selection.selection_digest != selection_hash):
                raise model_failure('Safety identity or pinned facts changed during inference.',code=ErrorCode.STALE_CONTEXT)
            attempts += response.attempts
            hashes.append(digest(response.content))
            if response.served_model and response.served_model not in served:
                served.append(response.served_model)
            for key,value in response.usage.items():
                usage[key] = usage.get(key,0)+value
            action = parse_safety_action(response.content)
            if turn == 1 and not isinstance(action,ReadSafetyFactsAction):
                raise model_failure('Safety model must first read the registered facts.',code=ErrorCode.CONTRACT_INVALID)
            if isinstance(action,FinalSafetyAction):
                if last_plan is None or canonical(action.proposal.model_dump(mode='json')) != last_proposal:
                    raise model_failure('Safety final must reproduce the last evaluated proposal exactly.',code=ErrorCode.CONTRACT_INVALID)
                trace = SafetyTrace(role='SAFETY',requested_model=self.client.settings.model,served_models=served,
                    configuration_fingerprint=identity['configuration_fingerprint'],input_sha256=digest(input.model_dump_json()),
                    rule_facts_sha256=facts_hash,proposal_sha256=tools.proposal_hash(action.proposal),
                    prompt_sha256=identity['prompt_sha256'],tool_version=SAFETY_TOOL_VERSION,turns=turn,
                    http_attempts=attempts,elapsed_ms=int((time.monotonic()-started)*1000),tool_calls=calls,
                    response_sha256=hashes,usage=usage,validation_passed=True)
                plan, trace = validate_safety_payload(input,baseline,baseline,last_plan.model_dump(mode='json'),
                    trace.model_dump(mode='json'),identity=identity,selection=selection)
                check_payload_size(input,baseline,plan.model_dump(mode='json'),trace.model_dump(mode='json'))
                return SafetyOutcome(baseline.model_copy(deep=True),plan,trace)
            if isinstance(action,ReadSafetyFactsAction):
                output = tools.read_safety_facts()
            elif isinstance(action,EvaluateSafetyAction):
                last_plan = tools.evaluate_safety_plan(action.arguments)
                last_proposal = canonical(action.arguments.model_dump(mode='json'))
                output = {'tool':'evaluate_safety_plan','read_only':True,
                    'evaluated_proposal':action.arguments.model_dump(mode='json'),
                    'official_checks_unchanged':True,'advice_is_not_approval':True}
            calls.append(action.name)
            messages.extend([{'role':'assistant','content':canonical(action.model_dump(mode='json'))},
                {'role':'user','content':'TOOL_RESULT='+canonical(output)}])
        raise model_failure('Safety tool loop exhausted without a validated advisory.',code=ErrorCode.CONTRACT_INVALID)
