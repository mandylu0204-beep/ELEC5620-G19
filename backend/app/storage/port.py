import json
import time
from uuid import uuid4

from ..auth import fail
from ..contracts.dto import (
    Blocker, ConfirmedContext, Eligibility, ItineraryResult, LogisticsResult,
    RecommendCampsitesResult, RouteResult, RunScope, RunSnapshot, SafetyResult,
    StoredAssessment, StoredRecommendations, StoredVersion, ValidReview, VersionContext,
)
from ..contracts.enums import (
    AllowedAction, AssessmentKind, AssessmentOutcome, DataQuality, ErrorCode,
    ExecutionMode, PlanVersionStatus, ReviewDecision, RoadState, RunStage, RunStatus,
)
from .database import Database
from .repository import Repository, encode, fingerprint, now
from ..application.model_audit import required as model_trace_required, trace_payload, validate_trace, trace_hash, load_model_trace
from ..application.logistics_audit import required as logistics_audit_required
from ..application.assessment_audits import load_audits
from ..application.safety_audit import required as safety_audit_required


class SqlitePersistencePort:
    """Server-created capability bound to one authorized owner and registered run.

    Every method checks the stored scope and current pointers in the same transaction
    as its writes. No port method writes FINALISED or creates a human review.
    """
    def __init__(self, database: Database, owner_id: str, scope: RunScope, *, attempt_id=None, clock=time.time):
        self.db, self.owner_id, self.scope = database, owner_id, scope
        self.attempt_id, self.clock = attempt_id, clock

    def active(self, connection, *, writing=False, execution=False):
        plan = connection.execute('SELECT * FROM plans WHERE id=? AND owner_id=?', (self.scope.plan_id, self.owner_id)).fetchone()
        run = connection.execute('SELECT * FROM runs WHERE id=? AND plan_id=?', (self.scope.run_id, self.scope.plan_id)).fetchone()
        if not plan or not run:
            fail(ErrorCode.NOT_FOUND, '运行不存在。')
        from .revision_choices import candidate_for, execution_active
        if run['scope'] != encode(self.scope) or (plan['active_run_id'] != self.scope.run_id and not candidate_for(connection, plan, self.scope.run_id)):
            fail(ErrorCode.STALE_CONTEXT, '运行已被新任务取代，请刷新。')
        if writing or execution:
            if not execution_active(connection, plan, self.scope.run_id):
                fail(ErrorCode.INVALID_STATE, '请先完成待选方案的选择。')
            from .trip_series import require_current
            require_current(connection, plan)
            if plan['deleted_at']:
                fail(ErrorCode.NOT_FOUND, '方案不存在。')
            lease = connection.execute('SELECT * FROM run_leases WHERE run_id=?', (self.scope.run_id,)).fetchone()
            if (self.attempt_id is not None and lease is None) or (lease and (lease['attempt_id'] != self.attempt_id or lease['expires_at'] <= self.clock())):
                fail(ErrorCode.STALE_CONTEXT, '执行尝试已失效，迟到任务不能继续读写。')
        if writing and run['status'] in {'FAILED','CANCELLED','SUPERSEDED'}:
            fail(ErrorCode.INVALID_STATE, '运行已结束，不能继续写入。')
        return plan, run

    def context(self, connection, context: VersionContext):
        plan, run = self.active(connection)
        stored = Repository.stored_version(connection, self.scope)
        from .revision_choices import version_current
        if stored.version_context != context or not version_current(connection, plan, self.scope.run_id, context.plan_version_id):
            fail(ErrorCode.STALE_CONTEXT, '版本或输入证据已变化，请刷新。')
        return plan, run, stored

    def validate_mode(self, artifact):
        if artifact.execution_mode != self.scope.demo_context.mode:
            fail(ErrorCode.CONTRACT_INVALID, '产物模式与运行模式不一致。')

    def write(self, operation, key, input_value, result_type, action):
        if not key or key != self.scope.write_keys.get(operation):
            fail(ErrorCode.IDEMPOTENCY_CONFLICT, '写入 key 不属于此运行步骤。')
        input_hash = fingerprint(input_value)
        with self.db.transaction() as connection:
            _, run = self.active(connection, writing=True)
            previous = connection.execute('SELECT * FROM write_receipts WHERE run_id=? AND write_key=?', (self.scope.run_id, key)).fetchone()
            if previous:
                if previous['operation'] != operation or previous['input_hash'] != input_hash:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, '同一个 key 不能提交不同内容。')
                return result_type.model_validate_json(previous['result'])
            if run['status'] == 'SUCCEEDED':
                fail(ErrorCode.INVALID_STATE, '成功运行只能回读原有写入结果。')
            result = action(connection)
            connection.execute('INSERT INTO write_receipts VALUES(?,?,?,?,?)', (self.scope.run_id, key, operation, input_hash, encode(result)))
            return result

    async def load_confirmed_context(self):
        with self.db.transaction(write=False) as connection:
            _, run = self.active(connection, execution=True)
            return ConfirmedContext.model_validate_json(run['confirmed_context'])

    async def save_recommendations(self, result: RecommendCampsitesResult, write_key: str):
        result = RecommendCampsitesResult.model_validate(result)
        self.validate_mode(result)
        def save(connection):
            stored = StoredRecommendations(recommendation_id=uuid4().hex, request_id=self.scope.request_id, run_id=self.scope.run_id, result=result)
            connection.execute('INSERT INTO recommendations VALUES(?,?,?)', (stored.recommendation_id, self.scope.run_id, encode(stored)))
            return stored
        return self.write('recommendations', write_key, result, StoredRecommendations, save)

    async def append_plan_version(self, expected_current_version_id, content: ItineraryResult, request_id: str, reason: str, write_key: str):
        if model_trace_required(self.scope):
            fail(ErrorCode.CONTRACT_INVALID, '已登记的模型规划必须同时保存版本和审计。')
        return self.append_version(expected_current_version_id, content, request_id, reason, write_key)

    async def append_model_plan(self, expected_current_version_id, content, request_id, reason, trace, write_key):
        if not self.attempt_id:
            fail(ErrorCode.STALE_CONTEXT, '模型保存必须使用已领取的执行端口。')
        return self.append_version(expected_current_version_id, content, request_id, reason, write_key, trace_payload(trace))

    def append_version(self, expected_current_version_id, content, request_id, reason, write_key, trace=None):
        if model_trace_required(self.scope) and trace is None:
            fail(ErrorCode.CONTRACT_INVALID, '模型版本不能绕过必要审计。')
        content = ItineraryResult.model_validate(content)
        self.validate_mode(content)
        if request_id != self.scope.request_id or expected_current_version_id != self.scope.expected_current_version_id or self.scope.operation == 'REASSESS':
            fail(ErrorCode.STALE_CONTEXT, '请求、版本或操作与运行不一致。')
        if content.requested_requirement_changes is not None:
            fail(ErrorCode.REQUEST_NOT_CONFIRMED, '需求变化必须重新确认后才能保存方案。')
        def save(connection):
            plan, run = self.active(connection)
            if trace is not None:
                row = connection.execute('SELECT payload FROM recommendations WHERE run_id=?', (self.scope.run_id,)).fetchone()
                if not row:
                    fail(ErrorCode.CONTRACT_INVALID, '模型版本必须基于本次保存的推荐。')
                validate_trace(self.scope, content, trace, StoredRecommendations.model_validate_json(row['payload']))
            if plan['current_version_id'] != expected_current_version_id:
                fail(ErrorCode.VERSION_CONFLICT, '方案已产生新版本。')
            version_id = uuid4().hex
            number = connection.execute('SELECT COALESCE(MAX(version_number),0)+1 FROM versions WHERE plan_id=?', (self.scope.plan_id,)).fetchone()[0]
            connection.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?)', (version_id, self.scope.plan_id, number, encode(content), 'ASSESSING', 0, now()))
            confirmed = ConfirmedContext.model_validate_json(run['confirmed_context'])
            Repository.bind_version(connection, self.scope, confirmed, version_id, content.model_dump(mode='json'))
            from .revision_choices import candidate_for
            if not candidate_for(connection, plan, self.scope.run_id):
                connection.execute('UPDATE plans SET current_version_id=? WHERE id=?', (version_id, self.scope.plan_id))
            version = Repository.stored_version(connection, self.scope)
            if trace is not None:
                connection.execute('INSERT INTO model_planning_traces VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (uuid4().hex, self.scope.plan_id, self.scope.run_id, version_id, self.owner_id,
                    version.version_context.input_fingerprint, self.attempt_id, encode(trace), trace_hash(trace), now()))
            return version
        payload = {'expected': expected_current_version_id, 'content': content.model_dump(mode='json'), 'request_id': request_id, 'reason': reason}
        if trace is not None:
            payload['model_planning_trace'] = trace.model_dump(mode='json')
        return self.write('version', write_key, payload, StoredVersion, save)

    async def save_assessment(self, context: VersionContext, kind: AssessmentKind, result, write_key: str):
        kind = AssessmentKind(kind)
        if kind == AssessmentKind.LOGISTICS and logistics_audit_required(self.scope):
            fail(ErrorCode.CONTRACT_INVALID, '模型物流必须同时保存结构化方案和独立审计。')
        if kind == AssessmentKind.SAFETY and safety_audit_required(self.scope):
            fail(ErrorCode.CONTRACT_INVALID, 'Model safety must save its independent audit atomically.')
        result = (LogisticsResult if kind == AssessmentKind.LOGISTICS else SafetyResult).model_validate(result)
        self.validate_mode(result)
        if result.version_context != context:
            fail(ErrorCode.CONTRACT_INVALID, '评估上下文不一致。')
        if kind == AssessmentKind.SAFETY and logistics_audit_required(self.scope):
            with self.db.transaction(write=False) as connection:
                self.active(connection, execution=True)
                load_audits(connection, self.scope, Repository.stored_version(connection, self.scope), must_exist=True)
        def save(connection):
            self.context(connection, context)
            assessment_id, gear_id = uuid4().hex, uuid4().hex if kind == AssessmentKind.LOGISTICS else None
            dependency = None if kind == AssessmentKind.LOGISTICS else result.depends_on_assessment_id
            if dependency:
                if logistics_audit_required(self.scope):
                    load_audits(connection, self.scope, Repository.stored_version(connection, self.scope), must_exist=True)
                row = connection.execute("SELECT 1 FROM assessments WHERE id=? AND run_id=? AND version_id=? AND kind='LOGISTICS'", (dependency, context.run_id, context.plan_version_id)).fetchone()
                if not row:
                    fail(ErrorCode.STALE_CONTEXT, '安全评估依赖的物流评估无效。')
            stored = StoredAssessment(assessment_id=assessment_id, version_context=context, kind=kind, result=result, gear_checklist_id=gear_id, depends_on_assessment_id=dependency)
            connection.execute('INSERT INTO assessments VALUES(?,?,?,?,?,?,?)', (assessment_id, context.run_id, context.plan_version_id, kind.value, encode(stored), dependency, now()))
            if gear_id:
                connection.execute('INSERT INTO gear_checklists VALUES(?,?,?)', (gear_id, assessment_id, encode([item.model_dump(mode='json') for item in result.gear_checklist])))
            return stored
        return self.write('logistics' if kind == AssessmentKind.LOGISTICS else 'safety', write_key, {'context': context.model_dump(mode='json'), 'kind': kind.value, 'result': result.model_dump(mode='json')}, StoredAssessment, save)

    def assessments(self, connection, context):
        load_audits(connection, self.scope, Repository.stored_version(connection, self.scope))
        return [StoredAssessment.model_validate_json(row['payload']) for row in connection.execute('SELECT payload FROM assessments WHERE run_id=? AND version_id=? ORDER BY kind', (context.run_id, context.plan_version_id))]

    def review(self, connection, context, assessment_ids):
        if len(set(assessment_ids)) != len(assessment_ids):
            return None
        rows = connection.execute("SELECT r.payload FROM reviews r JOIN users u ON u.id=r.reviewer_id WHERE r.run_id=? AND r.version_id=? AND u.role='FOUNDER' ORDER BY r.rowid DESC", (context.run_id, context.plan_version_id))
        for row in rows:
            review = ValidReview.model_validate_json(row['payload'])
            if review.version_context == context and sorted(review.assessment_ids) == sorted(assessment_ids):
                return review
        return None

    def decision(self, connection, context):
        _, run, version = self.context(connection, context)
        if model_trace_required(self.scope):
            load_model_trace(connection, self.scope, version)
        confirmed = ConfirmedContext.model_validate_json(run['confirmed_context'])
        rows = self.assessments(connection, context)
        by_kind = {item.kind: item for item in rows}
        blockers = []
        revision = False
        review_required = False
        def block(code, message):
            blockers.append(Blocker(code=code, message=message))
        # A stricter persisted B route must continue to prevent finalisation.
        if version.status in {PlanVersionStatus.BLOCKED, PlanVersionStatus.REJECTED, PlanVersionStatus.DRAFT, PlanVersionStatus.FINALISED}:
            block('VERSION_STATE', '当前版本状态不允许最终化。')
        revision |= version.status == PlanVersionStatus.REVISION_REQUIRED
        review_required |= version.status == PlanVersionStatus.ESCALATED
        if self.scope.demo_context.mode == ExecutionMode.STUB:
            block('STUB_RESULT', 'Stub 不能作为正式方案放行。')
        if len(by_kind) != 2:
            block('ASSESSMENTS_MISSING', '物流和安全评估尚未全部保存。')
        if not version.content.itinerary_entries or not version.content.selected_campsite_ids:
            block('ITINERARY_MISSING', '行程或适用营地为空。')
        for item in rows:
            blockers.extend(item.result.mandatory_blockers)
            if item.result.outcome == AssessmentOutcome.BLOCKED:
                block('ASSESSMENT_BLOCKED', '评估要求阻止放行。')
            revision |= item.result.outcome == AssessmentOutcome.REVISION
            review_required |= item.result.outcome == AssessmentOutcome.REVIEW
        if AssessmentKind.LOGISTICS in by_kind:
            logistics = by_kind[AssessmentKind.LOGISTICS].result
            categories = {item.category for item in logistics.cost_breakdown}
            if categories != {'CAMPSITE','TRANSPORT','FOOD','WATER','ADDITIONAL_GEAR'} or logistics.total_cents is None:
                block('COSTS_INCOMPLETE', '必要费用未知或类别未覆盖。')
            if logistics.transport_feasible is not True or logistics.clarifications or not logistics.gear_checklist:
                block('LOGISTICS_INCOMPLETE', '装备或交通尚未确认。')
            if logistics.total_cents is not None:
                expected = logistics.total_cents - confirmed.requirements.budget_cents
                if logistics.budget_difference_cents != expected:
                    block('BUDGET_MISMATCH', '预算差额与已确认预算不一致。')
                revision |= expected > 0
            if any(item.essential and (item.required_quantity is None or item.available_quantity is None or item.missing_quantity is None or item.missing_quantity > 0 or item.available_quantity < item.required_quantity or item.arrangement_status not in {'OWNED','CONFIRMED_RENTAL'}) for item in logistics.gear_checklist):
                revision = True
        if AssessmentKind.SAFETY in by_kind:
            safety = by_kind[AssessmentKind.SAFETY].result
            review_required |= safety.requires_human_review
            if AssessmentKind.LOGISTICS not in by_kind or safety.depends_on_assessment_id != by_kind[AssessmentKind.LOGISTICS].assessment_id:
                block('EVIDENCE_DEPENDENCY', '安全评估未基于当前物流评估。')
            kinds = {'WEATHER','FIRE','ROAD','RESTRICTION'}
            if not kinds.issubset(safety.data_quality) or any(value != DataQuality.AVAILABLE for value in safety.data_quality.values()):
                block('EVIDENCE_UNAVAILABLE', '必要安全证据缺失、过期或冲突。')
            for campsite_id in version.content.selected_campsite_ids:
                for kind in kinds:
                    evidence = [item for item in safety.evidence if item.kind == kind and any(source.record_id == campsite_id for source in item.source_refs)]
                    if not evidence or any(item.status != DataQuality.AVAILABLE or item.source_date is None or item.source_date > self.scope.demo_context.demo_today or item.valid_from is None or item.valid_to is None or item.valid_from > confirmed.requirements.start_date or item.valid_to < confirmed.requirements.end_date for item in evidence):
                        block('EVIDENCE_COVERAGE', f'{campsite_id} 的 {kind} 证据未覆盖整个行程。')
                    if kind == 'ROAD' and any(item.road_state != RoadState.OPEN for item in evidence):
                        block('ROAD_UNAVAILABLE', '道路关闭或通行情况未知。')
        review = self.review(connection, context, [item.assessment_id for item in rows]) if len(rows) == 2 else None
        if review and review.decision != ReviewDecision.APPROVE:
            revision = True
        awaiting_review = review_required and (review is None or review.decision != ReviewDecision.APPROVE)
        route = PlanVersionStatus.BLOCKED if blockers else PlanVersionStatus.REVISION_REQUIRED if revision else PlanVersionStatus.ESCALATED if awaiting_review else PlanVersionStatus.ELIGIBLE_FOR_FINALISATION
        reasons = list(blockers)
        if revision:
            reasons.append(Blocker(code='REVISION_REQUIRED', message='存在未解决的修订要求。'))
        if awaiting_review:
            reasons.append(Blocker(code='REVIEW_REQUIRED', message='需要 Founder 审核当前证据。'))
        if run['status'] != 'SUCCEEDED':
            reasons.append(Blocker(code='RUN_NOT_SUCCEEDED', message='工作流尚未成功结束。'))
        eligibility = Eligibility(eligible=not reasons, current_version_id=context.plan_version_id, active_run_id=context.run_id, blocking_reasons=reasons, review_required=review_required, valid_review_id=review.review_id if review else None, allowed_actions=[AllowedAction.REQUEST_REVISION] if blockers or revision else [AllowedAction.WAIT_FOR_REVIEW] if awaiting_review else [])
        return route, eligibility

    async def route_assessed_version(self, context, proposed_route, reason, write_key):
        # Audit validation precedes receipt replay as well as first routing.
        with self.db.transaction(write=False) as connection:
            self.active(connection, execution=True)
            load_audits(connection, self.scope, Repository.stored_version(connection, self.scope), must_exist=(logistics_audit_required(self.scope) or safety_audit_required(self.scope)))
        proposed_route = PlanVersionStatus(proposed_route)
        if proposed_route not in {PlanVersionStatus.BLOCKED, PlanVersionStatus.REVISION_REQUIRED, PlanVersionStatus.ESCALATED, PlanVersionStatus.ELIGIBLE_FOR_FINALISATION}:
            fail(ErrorCode.INVALID_STATE, 'Agent 不允许设置此版本状态。')
        def save(connection):
            route, eligibility = self.decision(connection, context)
            # A can enforce a stricter route than B proposes. Never relax B's route.
            order = [PlanVersionStatus.BLOCKED, PlanVersionStatus.REVISION_REQUIRED, PlanVersionStatus.ESCALATED, PlanVersionStatus.ELIGIBLE_FOR_FINALISATION]
            route = order[min(order.index(route), order.index(proposed_route))]
            connection.execute('UPDATE versions SET status=?,revision=revision+1 WHERE id=?', (route.value, context.plan_version_id))
            return RouteResult(version_context=context, status=route, eligibility=eligibility)
        return self.write('route', write_key, {'context': context.model_dump(mode='json'), 'route': proposed_route.value, 'reason': reason}, RouteResult, save)

    async def load_review_result(self, context, assessment_ids):
        with self.db.transaction(write=False) as connection:
            self.context(connection, context)
            actual = [item.assessment_id for item in self.assessments(connection, context)]
            return self.review(connection, context, assessment_ids) if sorted(actual) == sorted(assessment_ids) and len(actual) == 2 else None

    async def evaluate_eligibility(self, context):
        with self.db.transaction(write=False) as connection:
            return self.decision(connection, context)[1]

    def validate_completion(self, connection, stage):
        if connection.execute('SELECT 1 FROM run_versions WHERE run_id=?', (self.scope.run_id,)).fetchone():
            load_audits(connection, self.scope, Repository.stored_version(connection, self.scope), must_exist=(logistics_audit_required(self.scope) or safety_audit_required(self.scope)))
        if model_trace_required(self.scope) and connection.execute('SELECT 1 FROM run_versions WHERE run_id=?', (self.scope.run_id,)).fetchone():
            load_model_trace(connection, self.scope, Repository.stored_version(connection, self.scope))
        recommendation = connection.execute('SELECT payload FROM recommendations WHERE run_id=?', (self.scope.run_id,)).fetchone()
        no_match = recommendation and StoredRecommendations.model_validate_json(recommendation['payload']).result.search_outcome == 'NO_MATCH' and not connection.execute('SELECT 1 FROM run_versions WHERE run_id=?', (self.scope.run_id,)).fetchone()
        if stage != RunStage.COMPLETED or not (no_match or connection.execute("SELECT 1 FROM write_receipts WHERE run_id=? AND operation='route'", (self.scope.run_id,)).fetchone()):
            fail(ErrorCode.INVALID_STATE, '保存路由后才能结束工作流。')

    async def report_stage(self, stage: RunStage, status: RunStatus, error):
        stage, status = RunStage(stage), RunStatus(status)
        if status not in {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.SUCCEEDED}:
            fail(ErrorCode.INVALID_STATE, '此状态只能由 A 的工作流服务设置。')
        if (status == RunStatus.FAILED) != (error is not None):
            fail(ErrorCode.CONTRACT_INVALID, '失败状态必须携带错误，其他状态不能携带错误。')
        with self.db.transaction() as connection:
            _, run = self.active(connection, writing=True)
            stages = list(RunStage)
            if run['status'] in {'SUCCEEDED','FAILED','CANCELLED','SUPERSEDED'} or stages.index(stage) < stages.index(RunStage(run['stage'])):
                fail(ErrorCode.INVALID_STATE, '已结束或陈旧的阶段不能重新推进。')
            if status == RunStatus.SUCCEEDED:
                self.validate_completion(connection, stage)
            elif stage == RunStage.COMPLETED:
                fail(ErrorCode.INVALID_STATE, 'COMPLETED 必须与 SUCCEEDED 一致。')
            connection.execute('UPDATE runs SET stage=?,status=?,revision=revision+1,error=? WHERE id=?', (stage.value, status.value, encode(error) if error else None, self.scope.run_id))
            connection.execute('INSERT INTO run_events(run_id,stage,status,error,created_at) VALUES(?,?,?,?,?)', (self.scope.run_id, stage.value, status.value, encode(error) if error else None, now()))
            return RunSnapshot(run_id=self.scope.run_id, execution_mode=self.scope.demo_context.mode, run_status=status, stage=stage, revision=run['revision'] + 1, error=error)
