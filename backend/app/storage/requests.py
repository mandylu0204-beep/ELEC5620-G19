import json
from uuid import uuid4

from ..auth import fail, require_role
from ..contracts.dto import ConfirmedContext, ConfirmedRequirements, DemoContext, InterpretRequestInput, ProfileSnapshot, TripRequirements
from ..contracts.enums import ErrorCode
from .repository import encode, fingerprint, now


class RequestRepository:
    def __init__(self, database):
        self.db = database

    @staticmethod
    def own(connection, user, request_id):
        require_role(user, 'CAMPER')
        row = connection.execute('SELECT * FROM requests WHERE id=? AND owner_id=? AND NOT EXISTS (SELECT 1 FROM deleted_requests d WHERE d.request_id=requests.id)', (request_id, user.id)).fetchone()
        if not row:
            fail(ErrorCode.NOT_FOUND, '请求不存在。')
        return row

    @staticmethod
    def check_revision(row, expected):
        if row['revision'] != expected:
            fail(ErrorCode.VERSION_CONFLICT, '请求摘要已变化，请刷新后再操作。')

    def result(self, connection, row):
        summary = connection.execute('SELECT * FROM request_summaries WHERE request_id=?', (row['id'],)).fetchone()
        result = {
            'request_id': row['id'], 'raw_text': row['raw_text'], 'explicit_fields': json.loads(row['payload']),
            'status': row['status'], 'revision': row['revision'], 'created_at': row['created_at'],
            'summary': json.loads(summary['result']) if summary and summary['result'] else None,
            'profile_snapshot': json.loads(summary['profile_snapshot']) if summary else None,
            'profile_revision': summary['profile_revision'] if summary else None,
            'error': json.loads(summary['error']) if summary and summary['error'] else None,
            'confirmed_context': json.loads(row['confirmed_context']) if row['confirmed_context'] else None,
            'planning_available': False,
        }
        origin = connection.execute('SELECT o.*,s.revision FROM successor_requests o JOIN trip_series s ON s.id=o.series_id WHERE o.request_id=? AND s.deleted_at IS NULL', (row['id'],)).fetchone()
        if origin:
            source = connection.execute('SELECT id FROM plans WHERE id=? AND deleted_at IS NULL', (origin['predecessor_plan_id'],)).fetchone()
            result.update(trip_series_id=origin['series_id'], predecessor_plan_id=source['id'] if source else None,
                series_revision=origin['revision'])
            original = connection.execute('SELECT s.profile_revision FROM plans p JOIN request_summaries s ON s.request_id=p.request_id WHERE p.id=?', (origin['predecessor_plan_id'],)).fetchone()
            result['source_profile_revision'] = original['profile_revision'] if original else None
            if source:
                # Read the immutable run named by the origin, not the latest
                # personal profile or an accidentally newer source run.
                context = json.loads(origin['source_context'])
                pinned = connection.execute('SELECT confirmed_context FROM runs WHERE id=? AND plan_id=?',
                    (context['expected_active_run_id'], origin['predecessor_plan_id'])).fetchone()
                if pinned:
                    snapshot = json.loads(pinned['confirmed_context'])
                    result['source_profile_snapshot'] = snapshot['profile_snapshot']
                    result['source_requirements'] = snapshot['requirements']
        return result

    def create(self, user, raw_text, explicit):
        require_role(user, 'CAMPER')
        request_id = uuid4().hex
        with self.db.transaction() as connection:
            connection.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)', (request_id, user.id, raw_text, 'DRAFT', 1, encode(explicit.model_dump(mode='json', exclude_unset=True)), None, now()))
            return self.result(connection, self.own(connection, user, request_id))

    def get(self, user, request_id):
        with self.db.transaction(write=False) as connection:
            return self.result(connection, self.own(connection, user, request_id))

    def list(self, user):
        require_role(user, 'CAMPER')
        with self.db.transaction(write=False) as connection:
            return [dict(row) for row in connection.execute('''SELECT q.id AS request_id,q.status,q.revision,q.raw_text,q.created_at,
                o.series_id AS trip_series_id,CASE WHEN o.request_id IS NULL THEN 0 ELSE 1 END AS is_trip_update
                FROM requests q LEFT JOIN successor_requests o ON o.request_id=q.id
                WHERE q.owner_id=? AND NOT EXISTS (SELECT 1 FROM deleted_requests d WHERE d.request_id=q.id)
                ORDER BY q.created_at DESC''', (user.id,))]

    def delete(self, user, request_id):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            if row['status'] == 'ANALYSING':
                fail(ErrorCode.INVALID_STATE, '请求正在生成摘要，请完成后再删除。')
            # Existing plans keep their immutable confirmed snapshots and history.
            connection.execute('INSERT INTO deleted_requests VALUES(?,?)', (request_id, now()))

    def edit(self, user, request_id, expected_revision, raw_text, explicit):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            from .trip_series import validate_successor
            validate_successor(connection, user, request_id)
            self.check_revision(row, expected_revision)
            if row['status'] == 'CONFIRMED':
                fail(ErrorCode.INVALID_STATE, '已确认需求不能原地修改，请新建请求。')
            connection.execute("UPDATE requests SET raw_text=?,payload=?,status='DRAFT',revision=revision+1 WHERE id=?", (raw_text, encode(explicit.model_dump(mode='json', exclude_unset=True)), request_id))
            connection.execute('DELETE FROM request_summaries WHERE request_id=?', (request_id,))
            return self.result(connection, self.own(connection, user, request_id))

    def begin_analysis(self, user, request_id, expected_revision, demo, dataset):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            from .trip_series import validate_successor
            validate_successor(connection, user, request_id)
            self.check_revision(row, expected_revision)
            if row['status'] in {'CONFIRMED','ANALYSING'}:
                fail(ErrorCode.INVALID_STATE, '此请求已确认或正在处理。')
            saved_profile = connection.execute('SELECT * FROM profiles WHERE owner_id=?', (user.id,)).fetchone()
            profile = ProfileSnapshot.model_validate_json(saved_profile['payload']) if saved_profile else ProfileSnapshot()
            profile_revision = saved_profile['revision'] if saved_profile else 0
            revision = row['revision'] + 1
            connection.execute("UPDATE requests SET status='ANALYSING',revision=? WHERE id=?", (revision, request_id))
            connection.execute('INSERT INTO request_summaries VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET analysis_revision=excluded.analysis_revision,profile_revision=excluded.profile_revision,profile_snapshot=excluded.profile_snapshot,demo_context=excluded.demo_context,dataset_context=excluded.dataset_context,result=NULL,error=NULL', (request_id, revision, profile_revision, encode(profile), encode(demo), encode(dataset), None, None))
            return revision, InterpretRequestInput(raw_text=row['raw_text'], explicit_fields=TripRequirements.model_validate_json(row['payload']), profile_snapshot=profile, demo_context=demo)

    def finish_analysis(self, user, request_id, analysis_revision, result, status):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            if row['revision'] != analysis_revision or row['status'] != 'ANALYSING':
                fail(ErrorCode.STALE_CONTEXT, '较旧的分析结果未应用；请求已修改。')
            connection.execute('UPDATE request_summaries SET result=?,error=NULL WHERE request_id=?', (encode(result), request_id))
            connection.execute('UPDATE requests SET status=?,revision=revision+1 WHERE id=?', (status.value, request_id))
            return self.result(connection, self.own(connection, user, request_id))

    def fail_analysis(self, user, request_id, analysis_revision, error):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            if row['revision'] == analysis_revision and row['status'] == 'ANALYSING':
                connection.execute('UPDATE request_summaries SET error=? WHERE request_id=?', (encode(error), request_id))
                connection.execute("UPDATE requests SET status='DRAFT',revision=revision+1 WHERE id=?", (request_id,))

    def confirm(self, user, request_id, expected_revision, command_key, demo, dataset):
        input_hash = fingerprint({'request_id': request_id, 'expected_revision': expected_revision, 'acknowledged': True})
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            receipt = connection.execute('SELECT * FROM request_confirmations WHERE owner_id=? AND command_key=?', (user.id, command_key)).fetchone()
            if receipt:
                if receipt['request_id'] != request_id or receipt['input_hash'] != input_hash:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, '同一确认 key 不能提交不同请求或摘要。')
                return self.result(connection, row)
            from .trip_series import validate_successor
            validate_successor(connection, user, request_id)
            self.check_revision(row, expected_revision)
            if row['status'] != 'AWAITING_CONFIRMATION':
                fail(ErrorCode.INVALID_STATE, '请先完成澄清并查看最新摘要。')
            summary = connection.execute('SELECT * FROM request_summaries WHERE request_id=?', (request_id,)).fetchone()
            profile = connection.execute('SELECT revision FROM profiles WHERE owner_id=?', (user.id,)).fetchone()
            if not summary or not profile or profile['revision'] != summary['profile_revision']:
                fail(ErrorCode.VERSION_CONFLICT, '露营资料已修改，请重新生成摘要后确认。')
            if summary['dataset_context'] != encode(dataset) or summary['demo_context'] != encode(demo):
                fail(ErrorCode.STALE_CONTEXT, '数据或演示上下文已变化，请重新生成摘要。')
            context = ConfirmedContext(request_id=request_id, confirmed_at=now(), requirements=ConfirmedRequirements.model_validate(json.loads(summary['result'])['extracted_requirements']), profile_snapshot=ProfileSnapshot.model_validate_json(summary['profile_snapshot']), demo_context=demo, dataset_context=dataset)
            connection.execute('INSERT INTO request_confirmations VALUES(?,?,?,?,?)', (request_id, user.id, command_key, input_hash, context.confirmed_at.isoformat()))
            connection.execute("UPDATE requests SET status='CONFIRMED',revision=revision+1,confirmed_context=? WHERE id=?", (encode(context), request_id))
            return self.result(connection, self.own(connection, user, request_id))
