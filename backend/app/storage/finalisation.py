"""Camper-owned finalisation. All guards and snapshot writes share one transaction."""
import json
from uuid import uuid4

from pydantic import Field, StrictBool, StrictInt, field_validator

from ..auth import fail, require_role
from ..contracts.base import ContractModel, Identifier, SCHEMA_VERSION
from ..contracts.dto import ConfirmedContext, RunScope, VersionContext
from ..contracts.enums import ErrorCode
from .port import SqlitePersistencePort
from .repository import Repository, encode, fingerprint, now
from ..application.model_audit import load_model_trace
from ..application.assessment_audits import load_audits


class FinaliseInput(ContractModel):
    command_key: Identifier
    version_context: VersionContext
    assessment_ids: list[Identifier] = Field(min_length=2, max_length=2)
    expected_review_id: Identifier | None
    expected_version_revision: StrictInt = Field(ge=0)
    expected_run_revision: StrictInt = Field(ge=0)
    acknowledged: StrictBool

    @field_validator('acknowledged')
    @classmethod
    def explicit_confirmation(cls, value):
        if not value:
            raise ValueError('请确认已阅读方案及其证据。')
        return value


def final_index(row, plan):
    value = json.loads(row['payload'])
    return {'plan_id': row['plan_id'], 'final_id': row['id'], 'plan_version_id': row['version_id'], 'run_id': row['run_id'],
        'version_number': value['version_number'], 'finalised_at': row['created_at'],
        'is_current': plan['current_version_id'] == row['version_id'] and plan['active_run_id'] == row['run_id']
            and plan['final_version_id'] == row['version_id']}


class FinalisationService:
    def __init__(self, database, *, context_guard=None):
        self.db, self.context_guard = database, context_guard

    def detail(self, user, plan_id, final_id):
        with self.db.transaction(write=False) as connection:
            plan = Repository.own_plan(connection, user, plan_id)
            row = connection.execute('SELECT * FROM final_records WHERE id=? AND plan_id=?', (final_id, plan_id)).fetchone()
            if not row:
                fail(ErrorCode.NOT_FOUND, '最终方案不存在。')
            snapshot = json.loads(row['payload'])
            run = connection.execute('SELECT scope FROM runs WHERE id=?', (row['run_id'],)).fetchone()
            scope = RunScope.model_validate_json(run['scope'])
            audits = load_audits(connection, scope, Repository.stored_version(connection, scope))
            if snapshot.get('model_assessment_audits', {}) != audits:
                from ..application.logistics_audit import integrity
                integrity()
            index = final_index(row, plan)
            from .trip_series import plan_series_view
            series = plan_series_view(connection, plan_id)
            if series and not series['is_current']:
                index['is_current'] = False
            return {'final_record': snapshot, **index}

    def submit(self, user, plan_id, body: FinaliseInput):
        require_role(user, 'CAMPER')
        with self.db.transaction() as connection:
            plan = Repository.own_plan(connection, user, plan_id)
            run = connection.execute('SELECT * FROM runs WHERE id=?', (plan['active_run_id'],)).fetchone()
            from .trip_series import require_current
            require_current(connection, plan)
            from .revision_choices import require_decided
            require_decided(connection, plan_id)
            if not run or body.version_context.plan_id != plan_id:
                fail(ErrorCode.STALE_CONTEXT, '最终化上下文已变化，请刷新。')
            scope = RunScope.model_validate_json(run['scope'])
            if self.context_guard is not None:
                self.context_guard(scope)
            port = SqlitePersistencePort(self.db, user.id, scope)
            _, _, version = port.context(connection, body.version_context)
            assessments = port.assessments(connection, body.version_context)
            actual = sorted(item.assessment_id for item in assessments)
            if len(set(body.assessment_ids)) != 2 or sorted(body.assessment_ids) != actual:
                fail(ErrorCode.STALE_CONTEXT, '最终化必须绑定当前两份评估记录。')
            review = port.review(connection, body.version_context, actual)
            if body.expected_review_id != (review.review_id if review else None):
                fail(ErrorCode.STALE_CONTEXT, '审核决定已变化，请刷新。')
            previous = connection.execute('SELECT * FROM final_commands WHERE owner_id=? AND command_key=?', (user.id, body.command_key)).fetchone()
            input_hash = fingerprint(body)
            if previous:
                if previous['input_hash'] != input_hash:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, '同一提交编号不能用于不同最终化内容。')
                return json.loads(previous['result'])
            if body.expected_version_revision != version.revision or body.expected_run_revision != run['revision']:
                fail(ErrorCode.VERSION_CONFLICT, '版本或运行已变化，请刷新。')
            confirmed = ConfirmedContext.model_validate_json(run['confirmed_context'])
            calculated = Repository.input_fingerprint(scope, confirmed, version.content.model_dump(mode='json'))
            if calculated != body.version_context.input_fingerprint:
                fail(ErrorCode.STALE_CONTEXT, '版本内容与登记输入指纹不一致，不能最终化。')
            request = connection.execute('SELECT status FROM requests WHERE id=? AND owner_id=?', (scope.request_id, user.id)).fetchone()
            route = connection.execute("SELECT result FROM write_receipts WHERE run_id=? AND operation='route'", (scope.run_id,)).fetchone()
            if not request or request['status'] != 'CONFIRMED' or run['status'] != 'SUCCEEDED' or run['stage'] != 'COMPLETED' or not route:
                fail(ErrorCode.FINALISATION_BLOCKED, '请求未确认或工作流尚未成功完成，不能最终化。')
            _, eligibility = port.decision(connection, body.version_context)
            if version.status != 'ELIGIBLE_FOR_FINALISATION' or not eligibility.eligible:
                fail(ErrorCode.FINALISATION_BLOCKED, '当前方案存在未解决的审核、修订或 blocker，不能最终化。')
            final_id, timestamp = uuid4().hex, now()
            recommendation = connection.execute('SELECT payload FROM recommendations WHERE run_id=?', (scope.run_id,)).fetchone()
            events = [{**dict(row), 'error': json.loads(row['error']) if row['error'] else None} for row in connection.execute(
                'SELECT id,stage,status,error,created_at FROM run_events WHERE run_id=? ORDER BY id', (scope.run_id,))]
            snapshot = {'schema_version': SCHEMA_VERSION, 'final_id': final_id, 'status': 'FINALISED',
                'finalised_at': timestamp, 'finalised_by': user.id, 'execution_mode': scope.demo_context.mode.value,
                'version_context': body.version_context.model_dump(mode='json'), 'version_number': version.version_number,
                'version_revision': version.revision + 1, 'confirmed_context': confirmed.model_dump(mode='json'),
                'content': version.content.model_dump(mode='json'), 'assessments': [item.model_dump(mode='json') for item in assessments],
                'model_planning_trace': load_model_trace(connection, scope, version),
                'model_assessment_audits': load_audits(connection, scope, version),
                'review': review.model_dump(mode='json') if review else None,
                'eligibility_at_finalisation': eligibility.model_dump(mode='json'),
                'recommendations': json.loads(recommendation['payload']) if recommendation else None,
                'route': json.loads(route['result']), 'events': events,
                'run': {'run_id': run['id'], 'status': run['status'], 'stage': run['stage'], 'revision': run['revision'],
                    'error': None, 'created_at': run['created_at'], 'execution_mode': scope.demo_context.mode.value, 'operation': scope.operation}}
            connection.execute('INSERT INTO final_records VALUES(?,?,?,?,?,?)', (final_id, plan_id, body.version_context.plan_version_id, scope.run_id, encode(snapshot), timestamp))
            connection.execute("UPDATE versions SET status='FINALISED',revision=revision+1 WHERE id=?", (body.version_context.plan_version_id,))
            connection.execute('UPDATE plans SET final_version_id=? WHERE id=?', (body.version_context.plan_version_id, plan_id))
            result = {'final_id': final_id, 'status': 'FINALISED', 'version_context': body.version_context.model_dump(mode='json'), 'finalised_at': timestamp}
            connection.execute('INSERT INTO final_commands VALUES(?,?,?,?,?)', (user.id, body.command_key, final_id, input_hash, encode(result)))
            return result
