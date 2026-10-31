"""Founder commands: compare exact evidence, persist once, then re-evaluate."""
import json
from uuid import uuid4

from pydantic import Field, StrictInt, field_validator

from ..auth import fail, require_role
from ..contracts.base import ContractModel, Identifier
from ..contracts.dto import RunScope, ValidReview, VersionContext
from ..contracts.enums import ErrorCode, ReviewDecision
from ..contracts.errors import ContractFailure
from .plan_queries import PlanQueries
from .port import SqlitePersistencePort
from .repository import Repository, encode, fingerprint, now
from ..application.assessment_audits import load_audits
from ..application.review_policy import approval_required, REVIEW_POLICY_VERSION


class ReviewInput(ContractModel):
    command_key: Identifier
    version_context: VersionContext
    assessment_ids: list[Identifier] = Field(min_length=2, max_length=2)
    expected_version_revision: StrictInt = Field(ge=0)
    expected_run_revision: StrictInt = Field(ge=0)
    decision: ReviewDecision
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError('Review reason cannot be blank.')
        return value.strip()


class ReviewService:
    def __init__(self, database, *, context_guard=None):
        self.db, self.context_guard = database, context_guard

    def queue(self, user, *, assistance=False):
        require_role(user, 'FOUNDER')
        with self.db.transaction(write=False) as connection:
            rows = connection.execute('''SELECT p.id AS plan_id,
                v.id AS plan_version_id,p.active_run_id AS run_id,v.status,v.version_number,v.created_at,
                r.confirmed_context,v.content,u.display_name AS owner_display_name
                FROM plans p JOIN versions v ON v.id=p.current_version_id
                JOIN runs r ON r.id=p.active_run_id
                JOIN run_versions rv ON rv.run_id=r.id AND rv.version_id=v.id
                JOIN users u ON u.id=p.owner_id
                WHERE p.deleted_at IS NULL AND v.status IN ('ESCALATED','BLOCKED','REVISION_REQUIRED') AND r.status='SUCCEEDED'
                AND NOT EXISTS (SELECT 1 FROM revision_proposals q WHERE q.plan_id=p.id AND q.decision IS NULL)
                AND NOT EXISTS (SELECT 1 FROM plan_series_members m JOIN trip_series s ON s.id=m.series_id
                    WHERE m.plan_id=p.id AND (s.deleted_at IS NOT NULL OR s.current_plan_id IS NOT p.id))
                AND NOT EXISTS (SELECT 1 FROM reviews h WHERE h.run_id=r.id AND h.version_id=v.id)
                ORDER BY v.created_at,p.id''').fetchall()
            result = []
            for row in rows:
                item = dict(row)
                scope = RunScope.model_validate_json(connection.execute('SELECT scope FROM runs WHERE id=?', (item['run_id'],)).fetchone()['scope'])
                load_audits(connection, scope, Repository.stored_version(connection, scope))
                confirmed = json.loads(item.pop('confirmed_context'))
                content = json.loads(item.pop('content'))
                # Project only this active run's bound version. Older evidence
                # must never supply the queue's risk or cost summary.
                assessments = {saved['kind']: json.loads(saved['payload'])['result']
                    for saved in connection.execute(
                        'SELECT kind,payload FROM assessments WHERE run_id=? AND version_id=?',
                        (item['run_id'], item['plan_version_id']))}
                logistics, safety = assessments.get('LOGISTICS', {}), assessments.get('SAFETY', {})
                version = Repository.stored_version(connection, scope)
                current_eligibility = SqlitePersistencePort(self.db, scope_owner(connection, item['plan_id']), scope).decision(connection, version.version_context)[1].model_dump(mode='json')
                approval = approval_required([{'kind': key, 'result': value} for key, value in assessments.items()], current_eligibility)
                if approval == assistance:
                    continue
                from .review_assistance import saved_notes
                notes = saved_notes(connection,item['plan_id'],item['run_id'],item['plan_version_id'])
                item['last_assistance'] = {key:notes[-1][key] for key in ['decision','problem','next_action','recheck_on']} if notes else None
                item['task_kind'] = 'ASSISTANCE' if assistance else 'RISK_APPROVAL'
                item['review_policy_version'] = REVIEW_POLICY_VERSION
                route = connection.execute(
                    "SELECT result FROM write_receipts WHERE run_id=? AND operation='route'",
                    (item['run_id'],)).fetchone()
                eligibility = json.loads(route['result'])['eligibility'] if route else {}
                requirements = confirmed['requirements']
                item['summary'] = {
                    'campsite_ids': content['selected_campsite_ids'],
                    'destination': requirements['destination'],
                    'start_date': requirements['start_date'], 'end_date': requirements['end_date'],
                    'total_cents': logistics.get('total_cents'),
                    'budget_difference_cents': logistics.get('budget_difference_cents'),
                    'risk_level': safety.get('risk_level'), 'confidence': safety.get('confidence'),
                    'data_quality': safety.get('data_quality', {}),
                    # The routing receipt precedes terminal completion. Its
                    # execution-state warning is obsolete for this SUCCEEDED
                    # queue; the current version status is shown separately.
                    'blocking_reasons': [reason for reason in eligibility.get('blocking_reasons', [])
                        if reason['code'] not in {'RUN_NOT_SUCCEEDED', 'VERSION_STATE'}],
                }
                result.append(item)
            return result

    def detail(self, user, plan_id, run_id=None):
        data = PlanQueries(self.db).detail(user, plan_id, run_id, review=True)
        with self.db.transaction(write=False) as connection:
            owner = connection.execute('SELECT u.display_name FROM users u JOIN plans p ON p.owner_id=u.id WHERE p.id=?', (plan_id,)).fetchone()
        data['owner_display_name'] = owner['display_name'] if owner else None
        if not data['version'] or not data['route'] or data['run']['status'] != 'SUCCEEDED':
            fail(ErrorCode.INVALID_STATE, 'Assessment and routing are incomplete for the current run. Please wait.')
        if data['version']['status'] not in {'ESCALATED','BLOCKED','REVISION_REQUIRED'} and not data['reviews'] and not data.get('review_assistance_notes'):
            fail(ErrorCode.FORBIDDEN, 'This plan is outside human-review scope.')
        historical = not data['run']['is_active'] or bool(data.get('trip_series') and not data['trip_series']['is_current'])
        data['review_available'] = not historical and not data['reviews'] and approval_required(data['assessments'], data['eligibility'])
        data['review_policy_version'] = REVIEW_POLICY_VERSION
        data['review_scope'] = 'HISTORY' if historical else 'APPROVAL' if data['review_available'] else 'CORRECTION'
        if self.context_guard is not None:
            with self.db.transaction(write=False) as connection:
                run = connection.execute('SELECT scope FROM runs WHERE id=?', (data['run']['run_id'],)).fetchone()
            try:
                self.context_guard(RunScope.model_validate_json(run['scope']))
            except ContractFailure as exc:
                data['review_available'] = False
                data['current_inputs_error'] = exc.error.message
        from .revision_choices import pending
        with self.db.transaction(write=False) as connection:
            choosing = pending(connection,plan_id) is not None
        data['assistance_available'] = not historical and not choosing and not data['reviews'] and not data['review_available'] and data['version']['status'] in {'ESCALATED','BLOCKED','REVISION_REQUIRED'}
        return data

    def submit(self, user, plan_id, body: ReviewInput):
        require_role(user, 'FOUNDER')
        with self.db.transaction() as connection:
            plan = connection.execute('SELECT * FROM plans WHERE id=? AND deleted_at IS NULL', (plan_id,)).fetchone()
            if not plan:
                fail(ErrorCode.NOT_FOUND, 'Plan not found.')
            from .trip_series import require_current
            require_current(connection, plan)
            from .revision_choices import require_decided
            require_decided(connection, plan_id)
            run = connection.execute('SELECT * FROM runs WHERE id=?', (plan['active_run_id'],)).fetchone()
            if not run or body.version_context.plan_id != plan_id:
                fail(ErrorCode.STALE_CONTEXT, 'Review context changed. Refresh.')
            scope = RunScope.model_validate_json(run['scope'])
            if self.context_guard is not None:
                self.context_guard(scope)
            port = SqlitePersistencePort(self.db, plan['owner_id'], scope)
            _, _, version = port.context(connection, body.version_context)
            assessments = port.assessments(connection, body.version_context)
            actual = sorted(item.assessment_id for item in assessments)
            if len(set(body.assessment_ids)) != 2 or sorted(body.assessment_ids) != actual:
                fail(ErrorCode.STALE_CONTEXT, 'Review must bind both current assessment records.')
            previous = connection.execute('SELECT * FROM review_commands WHERE reviewer_id=? AND command_key=?', (user.id, body.command_key)).fetchone()
            input_hash = fingerprint(body)
            if previous:
                if previous['input_hash'] != input_hash:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, 'The same submission key cannot be used for different review content.')
                return json.loads(previous['result'])
            if version.revision != body.expected_version_revision or run['revision'] != body.expected_run_revision:
                fail(ErrorCode.VERSION_CONFLICT, 'Plan or run changed. Refresh before reviewing again.')
            if run['status'] != 'SUCCEEDED' or version.status not in {'ESCALATED','BLOCKED','REVISION_REQUIRED'} or port.review(connection, body.version_context, actual):
                fail(ErrorCode.INVALID_STATE, 'The current version no longer accepts reviews. Refresh.')
            if not connection.execute("SELECT 1 FROM write_receipts WHERE run_id=? AND operation='route'", (scope.run_id,)).fetchone():
                fail(ErrorCode.INVALID_STATE, 'Current run routing is not saved.')
            eligibility_before = port.decision(connection, body.version_context)[1].model_dump(mode='json')
            if not approval_required([item.model_dump(mode='json') for item in assessments], eligibility_before):
                fail(ErrorCode.INVALID_STATE, 'This result needs completion or correction and is not a risk-approval task. Approval cannot remove hard gaps.')
            review = ValidReview(review_id=uuid4().hex, version_context=body.version_context,
                assessment_ids=actual, reviewer_user_id=user.id, decision=body.decision, reason=body.reason)
            connection.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?)', (review.review_id, scope.run_id, body.version_context.plan_version_id, user.id, encode(review), now()))
            if body.decision == ReviewDecision.APPROVE:
                route, eligibility = port.decision(connection, body.version_context)
                if not eligibility.eligible:
                    fail(ErrorCode.INVALID_STATE, 'There is a  blocker, , insufficient required evidence or an unresolved revision. Approval is unavailable; request revision or reject.')
                status = route.value
            else:
                status = 'REJECTED' if body.decision == ReviewDecision.REJECT else 'REVISION_REQUIRED'
            connection.execute('UPDATE versions SET status=?,revision=revision+1 WHERE id=?', (status, body.version_context.plan_version_id))
            eligibility = port.decision(connection, body.version_context)[1]
            result = {'review': review.model_dump(mode='json'), 'status': status,
                'version_revision': version.revision + 1, 'eligibility': eligibility.model_dump(mode='json'),
                'revision_execution_available': False, 'finalisation_available': False}
            connection.execute('INSERT INTO review_commands VALUES(?,?,?,?,?)', (user.id, body.command_key, review.review_id, input_hash, encode(result)))
            return result


def scope_owner(connection, plan_id):
    return connection.execute('SELECT owner_id FROM plans WHERE id=?', (plan_id,)).fetchone()['owner_id']
