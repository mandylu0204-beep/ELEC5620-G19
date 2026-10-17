"""Checkpoint-first orchestration against A's concrete recovery extension."""
import asyncio
import math
from contextlib import suppress

from pydantic import ValidationError

from ..contracts.dto import (
    ConfirmedContext, ItineraryInput, LogisticsInput, OrchestrateInput,
    RecommendCampsitesInput, RouteResult, RunResult, SafetyInput,
    StoredAssessment, StoredRecommendations, StoredVersion,
)
from ..contracts.enums import AssessmentKind, ErrorCode, RunStage, RunStatus
from ..contracts.errors import ContractFailure
from ..agents.rules.safety import propose_route
from .configuration import failure


class Orchestrator:
    safety_audit_contract = '1.0'

    def __init__(self, agent, configuration, persistence, *, heartbeat_interval=20):
        if isinstance(heartbeat_interval, bool) or not math.isfinite(heartbeat_interval) or heartbeat_interval <= 0:
            raise ValueError('heartbeat_interval must be finite and positive')
        self.agent, self.config, self.port = agent, configuration, persistence
        self.interval = heartbeat_interval
        self.stage = RunStage.RECOMMENDING
        self.refs = {}
        self.route = None
        self.blockers = []

    async def call(self, action):
        """Renew before each operation and during async waits; leave no tasks.

        A must still avoid blocking the event loop with long sync model calls and
        choose an interval below one third of its configured lease duration.
        """
        await self.port.heartbeat()
        task = asyncio.create_task(action())
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=self.interval)
                if done:
                    return task.result()
                await self.port.heartbeat()
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def advance(self, stage):
        # A's checkpoint may already be ahead of a missing atomic write.
        target = max((self.stage, stage), key=list(RunStage).index)
        self.stage = target
        await self.call(lambda: self.port.report_stage(target, RunStatus.RUNNING, None))

    def result(self, scope, status, error=None):
        return RunResult(
            run_id=scope.run_id, execution_mode=scope.demo_context.mode,
            run_status=status, stage=self.stage, artifact_refs=self.refs,
            route=self.route, blockers=self.blockers, error=error,
        )

    def safety_input(self, scope, confirmed, version, logistics):
        return SafetyInput(
            version_context=version.version_context, saved_itinerary=version.content,
            confirmed_requirements=confirmed.requirements, saved_logistics_assessment=logistics,
            scenario_context=self.config.scenario_for(version.content.selected_campsite_ids,
                confirmed_requirements=confirmed.requirements, demo_context=scope.demo_context),
            demo_context=scope.demo_context,
        )

    def validate_checkpoint_audits(self, value, scope, confirmed, version, logistics, safety):
        """Validate exactly the enabled AND saved assessment-role set, never infer.

        Empty/partial/NO_MATCH checkpoints do not require an unsaved audit. A
        committed assessment without its required audit is terminal corruption,
        not permission to regenerate model output under the original write key.
        """
        saved = {'LOGISTICS':logistics, 'SAFETY':safety}
        expected_roles = {role for role, assessment in saved.items() if assessment is not None
            and scope.dataset_context.selection_config.get(f'a_{role.lower()}_audit_required') == '1'}
        try:
            audits = value.get('model_assessment_audits', {})
            if not isinstance(audits, dict) or set(audits) != expected_roles:
                raise ValueError('Missing or unexpected assessment audit')
            for role in sorted(expected_roles):
                assessment, audit = saved[role], audits[role]
                expected = {'audit_contract_version':'1.0', 'kind':role,
                    'plan_id':scope.plan_id, 'run_id':scope.run_id,
                    'plan_version_id':version.version_context.plan_version_id,
                    'assessment_id':assessment.assessment_id,
                    'input_fingerprint':version.version_context.input_fingerprint}
                if role == 'LOGISTICS':
                    expected['gear_checklist_id'] = assessment.gear_checklist_id
                else:
                    if logistics is None or assessment.gear_checklist_id is not None:
                        raise ValueError('Safety lacks its exact saved logistics dependency')
                    expected['depends_on_assessment_id'] = logistics.assessment_id
                    if assessment.depends_on_assessment_id != logistics.assessment_id:
                        raise ValueError('Saved safety dependency differs')
                if (any(audit[key] != item for key, item in expected.items())
                        or any(not isinstance(audit[key], str) or not audit[key] for key in
                            ('audit_id', 'attempt_id', 'created_at'))
                        or audit['configuration_fingerprint'] != audit['trace']['configuration_fingerprint']):
                    raise ValueError('Audit associations differ')
                if role == 'LOGISTICS':
                    input = LogisticsInput(version_context=version.version_context, saved_itinerary=version.content,
                        confirmed_requirements=confirmed.requirements, profile_snapshot=confirmed.profile_snapshot,
                        demo_context=scope.demo_context)
                    self.agent.validate_logistics_artifacts(input, assessment.result, audit['plan'], audit['trace'])
                else:
                    input = self.safety_input(scope, confirmed, version, logistics)
                    self.agent.validate_safety_artifacts(input, assessment.result, audit['plan'], audit['trace'])
                from ..llm.coordinator import canonical, digest
                hashed = digest(canonical({'context':version.version_context.model_dump(mode='json'),
                    'kind':role, 'result':assessment.result.model_dump(mode='json'),
                    'plan':audit['plan'], 'trace':audit['trace']}))
                if audit['payload_sha256'] != hashed:
                    raise ValueError('Audit payload hash differs')
        except (ContractFailure, KeyError, TypeError, ValueError, AttributeError) as exc:
            if isinstance(exc, ContractFailure) and exc.error.code == ErrorCode.STALE_CONTEXT:
                raise
            raise failure(ErrorCode.PERSISTENCE_FAILURE,
                'Saved assessment model audit is incomplete or inconsistent; do not regenerate it.') from exc

    def checkpoint(self, input, value):
        try:
            self.stage = RunStage(value['stage'])
            status = RunStatus(value['run_status'])
            confirmed = ConfirmedContext.model_validate(value['confirmed_context'])
            recommendations = StoredRecommendations.model_validate(value['recommendations']) if value['recommendations'] is not None else None
            version = StoredVersion.model_validate(value['version']) if value['version'] is not None else None
            assessments = [StoredAssessment.model_validate(item) for item in value['assessments']]
            route = RouteResult.model_validate(value['route']) if value['route'] is not None else None
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise failure(ErrorCode.CONTRACT_INVALID, 'Recovery checkpoint is invalid.') from exc
        scope = input.run_scope
        if status != RunStatus.RUNNING or self.stage == RunStage.COMPLETED:
            raise failure(ErrorCode.INVALID_STATE, 'A must claim a running attempt before orchestration.')
        if confirmed != input.confirmed_context or confirmed.request_id != scope.request_id or confirmed.demo_context != scope.demo_context or confirmed.dataset_context != scope.dataset_context:
            raise failure(ErrorCode.STALE_CONTEXT, 'Caller confirmation differs from A checkpoint/scope.')
        if recommendations and (recommendations.run_id != scope.run_id or recommendations.request_id != scope.request_id or recommendations.result.execution_mode != scope.demo_context.mode):
            raise failure(ErrorCode.STALE_CONTEXT, 'Saved recommendations belong to another run/request/mode.')
        if scope.operation == 'REASSESS' and version is None:
            raise failure(ErrorCode.CONTRACT_INVALID, 'REASSESS requires an A-bound saved version.')
        if version:
            context = version.version_context
            if context.run_id != scope.run_id or context.plan_id != scope.plan_id or version.content.execution_mode != scope.demo_context.mode:
                raise failure(ErrorCode.STALE_CONTEXT, 'Saved version belongs to another run/plan/mode.')
            if scope.operation == 'REASSESS' and context.plan_version_id != scope.expected_current_version_id:
                raise failure(ErrorCode.STALE_CONTEXT, 'REASSESS version differs from the bound version.')
            self.refs['version'] = context.plan_version_id
        if recommendations:
            self.refs['recommendations'] = recommendations.recommendation_id
        by_kind = {}
        for assessment in assessments:
            if version is None or assessment.version_context != version.version_context or assessment.kind in by_kind or assessment.result.execution_mode != scope.demo_context.mode:
                raise failure(ErrorCode.CONTRACT_INVALID, 'Checkpoint assessments have invalid associations/duplicates.')
            by_kind[assessment.kind] = assessment
            self.refs[assessment.kind.value.lower()] = assessment.assessment_id
        logistics, safety = by_kind.get(AssessmentKind.LOGISTICS), by_kind.get(AssessmentKind.SAFETY)
        self.validate_checkpoint_audits(value, scope, confirmed, version, logistics, safety)
        if safety and (logistics is None or safety.depends_on_assessment_id != logistics.assessment_id):
            raise failure(ErrorCode.CONTRACT_INVALID, 'Saved safety does not depend on saved logistics.')
        if route:
            if version is None or logistics is None or safety is None or route.version_context != version.version_context:
                raise failure(ErrorCode.CONTRACT_INVALID, 'Saved route lacks its exact version and assessments.')
            self.route = route.status
        if recommendations and recommendations.result.search_outcome == 'NO_MATCH' and (version or assessments or route):
            raise failure(ErrorCode.CONTRACT_INVALID, 'NO_MATCH cannot contain saved plan artifacts.')
        return confirmed, recommendations, version, logistics, safety, route

    async def run(self, raw):
        # No recovery extension -> fail before ANY writes; no unsafe restart fallback.
        if not all(callable(getattr(self.port, name, None)) for name in ('load_checkpoint', 'heartbeat')):
            raise failure(ErrorCode.CONTRACT_INVALID, 'B-03 requires A RecoveryPort.load_checkpoint() and heartbeat().')
        try:
            input = OrchestrateInput.model_validate(raw)
        except ValidationError as exc:
            raise failure(ErrorCode.CONTRACT_INVALID, 'Orchestration input violates contract 1.0.') from exc
        scope = input.run_scope
        # Obtain A's stage FIRST; failures must never report an earlier stage.
        checkpoint = await self.call(self.port.load_checkpoint)
        try:
            confirmed, recommendations, version, logistics, safety, route = self.checkpoint(input, checkpoint)
            self.agent._input(RecommendCampsitesInput, RecommendCampsitesInput(
                confirmed_requirements=confirmed.requirements, profile_snapshot=confirmed.profile_snapshot,
                demo_context=scope.demo_context,
            ))
            if scope.dataset_context != self.config.context:
                raise failure(ErrorCode.STALE_CONTEXT, 'Dataset bytes, rules or workflow choices changed; start a new run.')
            for role in ('logistics', 'safety'):
                choices = scope.dataset_context.selection_config
                if any(key.startswith(f'a_{role}_') for key in choices) and choices.get(f'a_{role}_audit_required') != '1':
                    raise failure(ErrorCode.CONTRACT_INVALID, f'Conflicting or incomplete {role} audit registration.')
                if choices.get(f'a_{role}_audit_required') == '1' and (
                        scope.demo_context.mode != 'agent'
                        or choices.get(f'a_{role}_mode') != 'model'
                        or choices.get(f'a_{role}_audit_contract') != '1.0'
                        or getattr(self.agent, f'{role}_audit_contract', None) != '1.0'
                        or not all(callable(getattr(self.agent, name, None)) for name in
                            (f'assess_{role}_with_trace', f'validate_{role}_artifacts'))
                        or not callable(getattr(self.port, f'save_model_{role}_assessment', None))):
                    raise failure(ErrorCode.CONTRACT_INVALID,
                        f'Registered model {role} requires complete agent/audit persistence capabilities.')
            if any(not scope.write_keys.get(key) for key in ('recommendations', 'version', 'logistics', 'safety', 'route')) or len(set(scope.write_keys.values())) != len(scope.write_keys):
                raise failure(ErrorCode.CONTRACT_INVALID, 'A must register distinct write keys for all steps.')
            if self.config.feedback and scope.operation != 'REVISE':
                raise failure(ErrorCode.INPUT_INVALID, 'Revision feedback is allowed only for REVISE.')
            if scope.operation == 'REVISE' and version is None:
                previous = input.previous_version
                if previous is None or previous.version_context.plan_id != scope.plan_id or previous.version_context.plan_version_id != scope.expected_current_version_id:
                    raise failure(ErrorCode.STALE_CONTEXT, 'REVISE requires A current previous-version snapshot.')
                if scope.demo_context.mode == 'agent':
                    if not self.config.feedback:
                        raise failure(ErrorCode.INPUT_INVALID, 'Model revision requires registered feedback.')
                    if checkpoint.get('previous_version') is None or StoredVersion.model_validate(checkpoint['previous_version']) != previous:
                        raise failure(ErrorCode.STALE_CONTEXT, 'Caller previous version differs from A checkpoint.')
            # Saved route means no recommendation/generation/assessment calls at all.
            if route is None:
                if version is None:
                    if recommendations is None:
                        await self.advance(RunStage.RECOMMENDING)
                        result = await self.call(lambda: self.agent.recommend_campsites(RecommendCampsitesInput(
                            confirmed_requirements=confirmed.requirements, profile_snapshot=confirmed.profile_snapshot, demo_context=scope.demo_context,
                        )))
                        recommendations = await self.call(lambda: self.port.save_recommendations(result, scope.write_keys['recommendations']))
                        self.refs['recommendations'] = recommendations.recommendation_id
                    if recommendations.result.search_outcome == 'NO_MATCH':
                        return await self.finish(scope)
                    await self.advance(RunStage.GENERATING)
                    itinerary_input = ItineraryInput(
                        confirmed_requirements=confirmed.requirements, profile_snapshot=confirmed.profile_snapshot,
                        recommendations=recommendations.result, previous_version=input.previous_version if scope.operation == 'REVISE' else None,
                        feedback=self.config.feedback, demo_context=scope.demo_context,
                    )
                    if scope.dataset_context.selection_config.get('a_model_trace_required') == '1':
                        outcome = await self.call(lambda: self.agent.plan_with_trace(itinerary_input))
                        content = outcome.itinerary
                    else:
                        outcome = None
                        content = await self.call(lambda: self.agent.generate_or_revise_itinerary(itinerary_input))
                    if content.requested_requirement_changes is not None:
                        raise failure(ErrorCode.REQUEST_NOT_CONFIRMED, 'Proposed requirements must be reconfirmed before creating a version.')
                    await self.advance(RunStage.SAVING_VERSION)
                    if outcome is not None:
                        version = await self.call(lambda: self.port.append_model_plan(scope.expected_current_version_id, content, scope.request_id, content.revision_reason, outcome.trace.model_dump(mode='json'), scope.write_keys['version']))
                    else:
                        version = await self.call(lambda: self.port.append_plan_version(scope.expected_current_version_id, content, scope.request_id, content.revision_reason, scope.write_keys['version']))
                    self.refs['version'] = version.version_context.plan_version_id
                context = version.version_context
                if logistics is None:
                    await self.advance(RunStage.ASSESSING_LOGISTICS)
                    logistics_input = LogisticsInput(
                        version_context=context, saved_itinerary=version.content, confirmed_requirements=confirmed.requirements,
                        profile_snapshot=confirmed.profile_snapshot, demo_context=scope.demo_context,
                    )
                    if scope.dataset_context.selection_config.get('a_logistics_audit_required') == '1':
                        outcome = await self.call(lambda: self.agent.assess_logistics_with_trace(logistics_input))
                        logistics = await self.call(lambda: self.port.save_model_logistics_assessment(
                            context, outcome.assessment, outcome.plan.model_dump(mode='json'),
                            outcome.trace.model_dump(mode='json'), scope.write_keys['logistics']))
                    else:
                        result = await self.call(lambda: self.agent.assess_gear_and_logistics(logistics_input))
                        logistics = await self.call(lambda: self.port.save_assessment(context, AssessmentKind.LOGISTICS, result, scope.write_keys['logistics']))
                    self.refs['logistics'] = logistics.assessment_id
                if safety is None:
                    await self.advance(RunStage.ASSESSING_SAFETY)
                    safety_input = self.safety_input(scope, confirmed, version, logistics)
                    if scope.dataset_context.selection_config.get('a_safety_audit_required') == '1':
                        outcome = await self.call(lambda: self.agent.assess_safety_with_trace(safety_input))
                        safety = await self.call(lambda: self.port.save_model_safety_assessment(
                            context, outcome.assessment, outcome.plan.model_dump(mode='json'),
                            outcome.trace.model_dump(mode='json'), scope.write_keys['safety']))
                    else:
                        result = await self.call(lambda: self.agent.assess_safety(safety_input))
                        safety = await self.call(lambda: self.port.save_assessment(context, AssessmentKind.SAFETY, result, scope.write_keys['safety']))
                    self.refs['safety'] = safety.assessment_id
                await self.advance(RunStage.ROUTING)
                route = await self.call(lambda: self.port.route_assessed_version(context, propose_route(logistics, safety.result), 'B-03 saved logistics/safety route proposal.', scope.write_keys['route']))
                self.route = route.status
            self.blockers = route.eligibility.blocking_reasons
            # A owns the post-success eligibility calculation.
            return await self.finish(scope)
        except asyncio.CancelledError:
            # No false durable FAILED claim. A expires/retries an abandoned lease.
            raise
        except Exception as exc:
            if self.stage == RunStage.COMPLETED:
                # The completion intent was already accepted; do not report a
                # contradictory failure after the returned success result.
                raise
            error = exc.error if isinstance(exc, ContractFailure) else failure(ErrorCode.AGENT_FAILURE, 'Unexpected workflow failure; retry resumes persisted steps.', recoverable=True).error
            try:
                await self.call(lambda: self.port.report_stage(self.stage, RunStatus.FAILED, error))
            except Exception as recording_error:
                exc.add_note(f'FAILED persistence could not be confirmed: {type(recording_error).__name__}. A must inspect/expire the lease.')
                raise exc from recording_error
            return self.result(scope, RunStatus.FAILED, error)

    async def finish(self, scope):
        # Completion is an intent/result for A to validate and commit. A11's
        # dispatcher owns the durable success transition and final eligibility.
        # The A-09 standalone adapter commits this call directly; both preserve
        # the same B-facing order and RunResult contract.
        await self.call(lambda: self.port.report_stage(RunStage.COMPLETED, RunStatus.SUCCEEDED, None))
        self.stage = RunStage.COMPLETED
        # The saved route receipt predates A's success commit and therefore
        # contains RUN_NOT_SUCCEEDED. It is an execution-order artifact, not a
        # final business blocker; A computes final eligibility after commit.
        self.blockers = [item for item in self.blockers if item.code != 'RUN_NOT_SUCCEEDED']
        return self.result(scope, RunStatus.SUCCEEDED)
