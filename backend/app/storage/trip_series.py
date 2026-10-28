"""Explicit lineage, current-plan CAS and tombstones. Never groups by similarity."""
import json
from uuid import uuid4

from pydantic import Field, StrictInt, model_validator

from ..auth import fail, require_role
from ..contracts.base import ContractModel, Identifier
from ..contracts.enums import ErrorCode
from .repository import Repository, encode, fingerprint, now


class SuccessorInput(ContractModel):
    command_key: Identifier = Field(min_length=16, max_length=128)
    expected_series_revision: StrictInt = Field(ge=0)
    expected_current_version_id: Identifier | None
    expected_version_revision: StrictInt | None = Field(ge=0)
    expected_active_run_id: Identifier
    expected_run_revision: StrictInt = Field(ge=0)

    @model_validator(mode='after')
    def version_pair(self):
        if (self.expected_current_version_id is None) != (self.expected_version_revision is None):
            raise ValueError('版本 ID 和 revision 必须同时存在或同时为空。')
        return self


class DeleteSeriesInput(ContractModel):
    command_key: Identifier = Field(min_length=16, max_length=128)
    expected_series_revision: StrictInt = Field(ge=1)


def membership(connection, plan_id):
    return connection.execute('''SELECT s.*,m.predecessor_plan_id FROM trip_series s
        JOIN plan_series_members m ON m.series_id=s.id WHERE m.plan_id=?''', (plan_id,)).fetchone()


def require_current(connection, plan):
    series = membership(connection, plan['id'])
    if series:
        if series['deleted_at']:
            fail(ErrorCode.NOT_FOUND, '出行不存在。')
        if series['current_plan_id'] != plan['id']:
            fail(ErrorCode.STALE_CONTEXT, '此方案已被后继方案取代，不能修改或审批历史结果。')
    return series


def source_unchanged(connection, plan, context):
    series = require_current(connection, plan)
    if (series['revision'] if series else 0) != context['expected_series_revision']:
        fail(ErrorCode.VERSION_CONFLICT, '出行已更新，请重新载入后继预览。')
    run = connection.execute('SELECT revision,status FROM runs WHERE id=? AND plan_id=?',
        (plan['active_run_id'], plan['id'])).fetchone()
    version = connection.execute('SELECT revision FROM versions WHERE id=? AND plan_id=?',
        (plan['current_version_id'], plan['id'])).fetchone()
    if (plan['active_run_id'] != context['expected_active_run_id'] or not run
            or run['revision'] != context['expected_run_revision']
            or plan['current_version_id'] != context['expected_current_version_id']
            or (version['revision'] if version else None) != context['expected_version_revision']):
        fail(ErrorCode.STALE_CONTEXT, '来源版本或运行已变化，请重新载入预览。')
    if run['status'] in {'PENDING', 'RUNNING'}:
        fail(ErrorCode.INVALID_STATE, '来源方案仍在运行，请完成后再创建后继。')
    return series


def validate_successor(connection, user, request_id):
    origin = connection.execute('SELECT * FROM successor_requests WHERE request_id=?', (request_id,)).fetchone()
    if origin:
        plan = Repository.own_plan(connection, user, origin['predecessor_plan_id'])
        series = source_unchanged(connection, plan, json.loads(origin['source_context']))
        if not series or series['id'] != origin['series_id']:
            fail(ErrorCode.STALE_CONTEXT, '来源系列身份不一致。')
    return origin


def register_plan(connection, user, request_id, plan_id, run_id):
    origin = validate_successor(connection, user, request_id)
    if origin:
        series_id, predecessor = origin['series_id'], origin['predecessor_plan_id']
        source = Repository.own_plan(connection, user, predecessor)
        connection.execute('INSERT INTO series_replacements VALUES(?,?,?,?,?,?,?,?)',
            (uuid4().hex, series_id, predecessor, source['active_run_id'], source['current_version_id'], plan_id, run_id, now()))
        connection.execute('UPDATE trip_series SET current_plan_id=?,revision=revision+1 WHERE id=?', (plan_id, series_id))
    else:
        series_id, predecessor = uuid4().hex, None
        connection.execute('INSERT INTO trip_series VALUES(?,?,?,1,NULL,?)', (series_id, user.id, plan_id, now()))
    connection.execute('INSERT INTO plan_series_members VALUES(?,?,?,?)', (plan_id, series_id, predecessor, now()))


def plan_series_view(connection, plan_id):
    row = membership(connection, plan_id)
    if not row:
        return None
    # Never publish a deleted current pointer or a deleted historical member.
    current = connection.execute('SELECT id FROM plans WHERE id=? AND deleted_at IS NULL', (row['current_plan_id'],)).fetchone()
    predecessor = connection.execute('SELECT id FROM plans WHERE id=? AND deleted_at IS NULL', (row['predecessor_plan_id'],)).fetchone()
    return {'trip_series_id': row['id'], 'series_revision': row['revision'],
        'current_plan_id': current['id'] if current else None,
        'predecessor_plan_id': predecessor['id'] if predecessor else None,
        'is_current': bool(current and current['id'] == plan_id)}


class TripSeriesService:
    def __init__(self, database):
        self.db = database

    def create_successor(self, user, plan_id, body):
        from .requests import RequestRepository
        with self.db.transaction() as connection:
            source = Repository.own_plan(connection, user, plan_id)
            input_hash = fingerprint({'plan_id': plan_id, **body.model_dump(mode='json')})
            receipt = connection.execute('SELECT * FROM successor_commands WHERE owner_id=? AND command_key=?', (user.id, body.command_key)).fetchone()
            if receipt:
                if receipt['input_hash'] != input_hash:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, '后继命令 key 不能用于不同输入。')
                return RequestRepository(self.db).result(connection, RequestRepository.own(connection, user, receipt['request_id']))
            series = source_unchanged(connection, source, body.model_dump(mode='json'))
            if not series:
                series_id = uuid4().hex
                connection.execute('INSERT INTO trip_series VALUES(?,?,?,1,NULL,?)', (series_id, user.id, plan_id, now()))
                connection.execute('INSERT INTO plan_series_members VALUES(?,?,NULL,?)', (plan_id, series_id, now()))
            else:
                series_id = series['id']
            context = body.model_dump(mode='json', exclude={'command_key'})
            context['expected_series_revision'] = series['revision'] if series else 1
            confirmed = json.loads(connection.execute('SELECT confirmed_context FROM runs WHERE id=?', (source['active_run_id'],)).fetchone()['confirmed_context'])
            request_id = uuid4().hex
            connection.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)',
                (request_id, user.id, '', 'DRAFT', 1, encode(confirmed['requirements']), None, now()))
            connection.execute('INSERT INTO successor_requests VALUES(?,?,?,?)', (request_id, series_id, plan_id, encode(context)))
            connection.execute('INSERT INTO successor_commands VALUES(?,?,?,?)', (user.id, body.command_key, input_hash, request_id))
            return RequestRepository(self.db).result(connection, RequestRepository.own(connection, user, request_id))

    def list(self, user):
        from .plan_queries import PlanQueries
        require_role(user, 'CAMPER')
        # A single read transaction owns both current pointers and their rows.
        with self.db.transaction(write=False) as connection:
            rows = PlanQueries(self.db).list(user, connection=connection)
            by_id = {row['plan_id']: row for row in rows}
            series = connection.execute('SELECT * FROM trip_series WHERE owner_id=? AND deleted_at IS NULL ORDER BY created_at DESC,id', (user.id,)).fetchall()
            linked, result = set(), []
            for item in series:
                ids = [row['plan_id'] for row in connection.execute('SELECT plan_id FROM plan_series_members WHERE series_id=? ORDER BY created_at,plan_id', (item['id'],))]
                linked.update(ids)
                visible = [by_id[key] for key in ids if key in by_id]
                finals = [row['last_final'] for row in visible if row['last_final']]
                final = max(finals, key=lambda value: (value['finalised_at'], value['final_id']), default=None)
                if final:
                    final = {**final, 'is_current': final['plan_id'] == item['current_plan_id'] and final['is_current']}
                current = by_id.get(item['current_plan_id'])
                result.append({'trip_series_id': item['id'], 'revision': item['revision'],
                    'current_plan': current, 'latest_run': {'plan_id':current['plan_id'], 'run_id':current['active_run_id'], 'status':current['run_status']} if current else None,
                    'history': [row for row in visible if row['plan_id'] != item['current_plan_id']], 'last_final': final})
            return {'trip_series': result, 'independent_plans': [row for row in rows if row['plan_id'] not in linked]}

    def detail(self, user, series_id):
        require_role(user, 'CAMPER')
        result = next((row for row in self.list(user)['trip_series'] if row['trip_series_id'] == series_id), None)
        if result is None:
            fail(ErrorCode.NOT_FOUND, '出行不存在。')
        return result

    def delete(self, user, series_id, body):
        require_role(user, 'CAMPER')
        with self.db.transaction() as connection:
            series = connection.execute('SELECT * FROM trip_series WHERE id=? AND owner_id=?', (series_id, user.id)).fetchone()
            if not series:
                fail(ErrorCode.NOT_FOUND, '出行不存在。')
            digest = fingerprint({'series_id': series_id, **body.model_dump(mode='json')})
            receipt = connection.execute('SELECT * FROM series_delete_commands WHERE owner_id=? AND command_key=?', (user.id, body.command_key)).fetchone()
            if receipt:
                if receipt['input_hash'] != digest:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, '删除命令 key 不能用于不同内容。')
                return
            if series['deleted_at']:
                fail(ErrorCode.NOT_FOUND, '出行不存在。')
            if series['revision'] != body.expected_series_revision:
                fail(ErrorCode.VERSION_CONFLICT, '出行已更新，请重新确认删除。')
            if connection.execute("SELECT 1 FROM runs r JOIN plan_series_members m ON m.plan_id=r.plan_id WHERE m.series_id=? AND r.status IN ('PENDING','RUNNING')", (series_id,)).fetchone():
                fail(ErrorCode.INVALID_STATE, '出行仍有活动运行，不能删除。')
            timestamp = now()
            connection.execute('''INSERT OR IGNORE INTO deleted_requests(request_id,deleted_at)
                SELECT request_id,? FROM plans WHERE id IN (SELECT plan_id FROM plan_series_members WHERE series_id=?)
                UNION SELECT request_id,? FROM successor_requests WHERE series_id=?''', (timestamp, series_id, timestamp, series_id))
            connection.execute('UPDATE plans SET deleted_at=? WHERE deleted_at IS NULL AND id IN (SELECT plan_id FROM plan_series_members WHERE series_id=?)', (timestamp, series_id))
            connection.execute('UPDATE trip_series SET deleted_at=?,current_plan_id=NULL,revision=revision+1 WHERE id=?', (timestamp, series_id))
            connection.execute('INSERT INTO series_delete_commands VALUES(?,?,?,?)', (user.id, body.command_key, digest, series_id))
