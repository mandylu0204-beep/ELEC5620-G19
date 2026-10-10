from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from ..auth import User, fail, require_role
from ..contracts.dto import (
    ConfirmedContext, DatasetContext, DemoContext, ProfileSnapshot, RunScope,
    StoredVersion, VersionContext,
)
from ..contracts.enums import ErrorCode
from .database import Database


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


class Repository:
    def __init__(self, database: Database):
        self.db = database

    def get_profile(self, user: User):
        require_role(user, 'CAMPER')
        with self.db.transaction(write=False) as connection:
            row = connection.execute('SELECT * FROM profiles WHERE owner_id=?', (user.id,)).fetchone()
            return self.profile_result(row) if row else {'profile': None, 'revision': 0}

    @staticmethod
    def profile_result(row):
        return {'profile': json.loads(row['payload']), 'revision': row['revision']}

    def save_profile(self, user: User, profile: ProfileSnapshot, expected_revision: int):
        require_role(user, 'CAMPER')
        with self.db.transaction() as connection:
            row = connection.execute('SELECT * FROM profiles WHERE owner_id=?', (user.id,)).fetchone()
            if expected_revision != (row['revision'] if row else 0):
                fail(ErrorCode.VERSION_CONFLICT, '资料已更新，请刷新后再保存。')
            if profile.profile_id is not None:
                fail(ErrorCode.INPUT_INVALID, 'profile_id 由服务器生成，不能在请求中指定。')
            stored = profile.model_copy(update={'profile_id': row['profile_id'] if row else uuid4().hex})
            connection.execute('INSERT INTO profiles VALUES(?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated_at=excluded.updated_at', (user.id, stored.profile_id, encode(stored), expected_revision + 1, now()))
            return {'profile': stored.model_dump(mode='json'), 'revision': expected_revision + 1}

    @staticmethod
    def own_plan(connection, user: User, plan_id: str):
        require_role(user, 'CAMPER')
        row = connection.execute('SELECT * FROM plans WHERE id=? AND owner_id=?', (plan_id, user.id)).fetchone()
        if not row:
            fail(ErrorCode.NOT_FOUND, '方案不存在。')
        return row

    def list_plans(self, user: User):
        require_role(user, 'CAMPER')
        with self.db.transaction(write=False) as connection:
            return [dict(row) for row in connection.execute('SELECT id AS plan_id,current_version_id,final_version_id,active_run_id,created_at FROM plans WHERE owner_id=? ORDER BY created_at DESC', (user.id,))]

    def history(self, user: User, plan_id: str):
        with self.db.transaction(write=False) as connection:
            self.own_plan(connection, user, plan_id)
            versions = [dict(row) for row in connection.execute('SELECT id AS plan_version_id,version_number,status,revision,content,created_at FROM versions WHERE plan_id=? ORDER BY version_number', (plan_id,))]
            for version in versions:
                version['content'] = json.loads(version['content'])
            return versions

    def review_queue(self, user: User):
        require_role(user, 'FOUNDER')
        with self.db.transaction(write=False) as connection:
            # Only current escalated versions; profiles and unrelated plans are not exposed.
            return [dict(row) for row in connection.execute("SELECT p.id AS plan_id,v.id AS plan_version_id,p.active_run_id AS run_id,v.status FROM plans p JOIN versions v ON p.current_version_id=v.id WHERE v.status='ESCALATED' ORDER BY v.created_at")]

    def record_confirmed_request(self, user: User, raw_text: str, context: ConfirmedContext):
        """Internal A service only. A-05 must perform revision/confirmation checks first.

        No HTTP confirmation endpoint invokes this until that flow is implemented.
        """
        require_role(user, 'CAMPER')
        context = ConfirmedContext.model_validate(context)
        with self.db.transaction() as connection:
            connection.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)', (context.request_id, user.id, raw_text, 'CONFIRMED', 1, encode(context.requirements), encode(context), now()))

    def begin_run(self, user: User, request_id: str, demo: DemoContext, dataset: DatasetContext, *, plan_id=None, operation='PLAN', expected_current_version_id=None):
        """Only trusted A workflow services call this; no B-supplied RunScope accepted."""
        require_role(user, 'CAMPER')
        if operation not in {'PLAN', 'REVISE', 'REASSESS'}:
            fail(ErrorCode.INPUT_INVALID, '运行操作无效。')
        with self.db.transaction() as connection:
            request = connection.execute('SELECT * FROM requests WHERE id=? AND owner_id=?', (request_id, user.id)).fetchone()
            if not request:
                fail(ErrorCode.NOT_FOUND, '请求不存在。')
            if request['status'] != 'CONFIRMED':
                fail(ErrorCode.REQUEST_NOT_CONFIRMED, '请先确认请求。')
            context = ConfirmedContext.model_validate_json(request['confirmed_context'])
            context = ConfirmedContext.model_validate(context.model_copy(update={'demo_context': demo, 'dataset_context': dataset}))
            if plan_id is None:
                if operation != 'PLAN' or expected_current_version_id is not None:
                    fail(ErrorCode.INVALID_STATE, '新方案只能发起 PLAN。')
                plan_id = uuid4().hex
                connection.execute('INSERT INTO plans VALUES(?,?,?,?,?,?,?)', (plan_id, user.id, request_id, None, None, None, now()))
            else:
                plan = self.own_plan(connection, user, plan_id)
                if operation == 'PLAN' or plan['current_version_id'] != expected_current_version_id or expected_current_version_id is None:
                    fail(ErrorCode.VERSION_CONFLICT, '当前版本已变化。')
                if plan['active_run_id']:
                    connection.execute("UPDATE runs SET status='SUPERSEDED',revision=revision+1 WHERE id=? AND status IN ('PENDING','RUNNING')", (plan['active_run_id'],))
            scope = RunScope(command_id=uuid4().hex, run_id=uuid4().hex, plan_id=plan_id, request_id=request_id, operation=operation, expected_current_version_id=expected_current_version_id, demo_context=demo, dataset_context=dataset, write_keys={name: uuid4().hex for name in ('recommendations','version','logistics','safety','route')})
            connection.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)', (scope.run_id, plan_id, request_id, encode(scope), encode(context), 'PENDING', 'RECOMMENDING', 0, None, now()))
            connection.execute('UPDATE plans SET active_run_id=?,request_id=? WHERE id=?', (scope.run_id, request_id, plan_id))
            if operation == 'REASSESS':
                version = connection.execute('SELECT * FROM versions WHERE id=?', (expected_current_version_id,)).fetchone()
                self.bind_version(connection, scope, context, version['id'], json.loads(version['content']))
                connection.execute("UPDATE versions SET status='ASSESSING',revision=revision+1 WHERE id=?", (version['id'],))
            return scope

    @staticmethod
    def input_fingerprint(scope, confirmed, content):
        return fingerprint({'version_content': content, 'confirmed_requirements': confirmed.requirements.model_dump(mode='json'), 'profile_snapshot': confirmed.profile_snapshot.model_dump(mode='json'), 'demo_context': scope.demo_context.model_dump(mode='json'), 'dataset_context': scope.dataset_context.model_dump(mode='json')})

    @staticmethod
    def bind_version(connection, scope, confirmed, version_id, content):
        value = Repository.input_fingerprint(scope, confirmed, content)
        connection.execute('INSERT INTO run_versions VALUES(?,?,?,?)', (scope.run_id, version_id, scope.plan_id, value))
        return VersionContext(plan_id=scope.plan_id, plan_version_id=version_id, run_id=scope.run_id, input_fingerprint=value)

    def bind_port(self, user: User, run_id: str):
        from .port import SqlitePersistencePort
        with self.db.transaction(write=False) as connection:
            row = connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if not row:
                fail(ErrorCode.NOT_FOUND, '运行不存在。')
            self.own_plan(connection, user, row['plan_id'])
            return SqlitePersistencePort(self.db, user.id, RunScope.model_validate_json(row['scope']))

    @staticmethod
    def stored_version(connection, scope):
        row = connection.execute('SELECT v.*,rv.fingerprint FROM run_versions rv JOIN versions v ON v.id=rv.version_id WHERE rv.run_id=?', (scope.run_id,)).fetchone()
        if not row:
            fail(ErrorCode.INVALID_STATE, '尚未保存版本。')
        return StoredVersion(version_context=VersionContext(plan_id=scope.plan_id, plan_version_id=row['id'], run_id=scope.run_id, input_fingerprint=row['fingerprint']), version_number=row['version_number'], content=json.loads(row['content']), status=row['status'], revision=row['revision'])
