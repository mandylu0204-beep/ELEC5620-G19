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
                fail(ErrorCode.VERSION_CONFLICT, 'Profile updated. Refresh before saving.')
            if profile.profile_id is not None:
                fail(ErrorCode.INPUT_INVALID, 'profile_id  is server-generated and cannot be specified in a request.')
            stored = profile.model_copy(update={'profile_id': row['profile_id'] if row else uuid4().hex})
            connection.execute('INSERT INTO profiles VALUES(?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated_at=excluded.updated_at', (user.id, stored.profile_id, encode(stored), expected_revision + 1, now()))
            return {'profile': stored.model_dump(mode='json'), 'revision': expected_revision + 1}

    @staticmethod
    def own_plan(connection, user: User, plan_id: str):
        require_role(user, 'CAMPER')
        row = connection.execute('SELECT * FROM plans WHERE id=? AND owner_id=? AND deleted_at IS NULL', (plan_id, user.id)).fetchone()
        if not row:
            fail(ErrorCode.NOT_FOUND, 'Plan not found.')
        return row

    def delete_plan(self, user: User, plan_id: str):
        # Keep immutable audit/final records; deletion removes owner access.
        with self.db.transaction() as connection:
            self.own_plan(connection, user, plan_id)
            active = connection.execute("SELECT 1 FROM runs WHERE plan_id=? AND status IN ('PENDING','RUNNING')", (plan_id,)).fetchone()
            if active:
                fail(ErrorCode.INVALID_STATE, 'Plan generation or checks are still running. Wait before deleting.')
            connection.execute('UPDATE plans SET deleted_at=? WHERE id=?', (now(), plan_id))
            from .trip_series import membership
            series = membership(connection, plan_id)
            if series and series['current_plan_id'] == plan_id:
                connection.execute('UPDATE trip_series SET current_plan_id=NULL,revision=revision+1 WHERE id=?', (series['id'],))

    def list_plans(self, user: User):
        require_role(user, 'CAMPER')
        with self.db.transaction(write=False) as connection:
            return [dict(row) for row in connection.execute('SELECT id AS plan_id,current_version_id,final_version_id,active_run_id,created_at FROM plans WHERE owner_id=? AND deleted_at IS NULL ORDER BY created_at DESC', (user.id,))]

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
            return [dict(row) for row in connection.execute("SELECT p.id AS plan_id,v.id AS plan_version_id,p.active_run_id AS run_id,v.status FROM plans p JOIN versions v ON p.current_version_id=v.id WHERE p.deleted_at IS NULL AND v.status='ESCALATED' ORDER BY v.created_at")]

    def record_confirmed_request(self, user: User, raw_text: str, context: ConfirmedContext):
        """Internal A service only. A-05 must perform revision/confirmation checks first.

        No HTTP confirmation endpoint invokes this until that flow is implemented.
        """
        require_role(user, 'CAMPER')
        context = ConfirmedContext.model_validate(context)
        with self.db.transaction() as connection:
            connection.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)', (context.request_id, user.id, raw_text, 'CONFIRMED', 1, encode(context.requirements), encode(context), now()))

    def begin_run(self, user: User, request_id: str, demo: DemoContext, dataset: DatasetContext, *, plan_id=None, operation='PLAN', expected_current_version_id=None, command_key=None, expected_active_run_id=None, expected_request_revision=None, single_plan=False, expected_version_revision=None, expected_run_revision=None, revision_check=None, revision_selection=False):
        """Only trusted A workflow services call this; no B-supplied RunScope accepted."""
        require_role(user, 'CAMPER')
        if operation not in {'PLAN', 'REVISE', 'REASSESS'}:
            fail(ErrorCode.INPUT_INVALID, 'Invalid run operation.')
        if command_key is not None and (not isinstance(command_key, str) or not command_key.strip() or len(command_key) > 128):
            fail(ErrorCode.INPUT_INVALID, 'command_key must contain 1 to 128 nonblank characters.')
        input_hash = fingerprint({'operation': operation, 'request_id': request_id, 'plan_id': plan_id,
            'expected_current_version_id': expected_current_version_id, 'expected_active_run_id': expected_active_run_id,
            'expected_request_revision': expected_request_revision, 'single_plan': single_plan,
            'expected_version_revision': expected_version_revision, 'expected_run_revision': expected_run_revision,
            'demo': demo.model_dump(mode='json'), 'dataset': dataset.model_dump(mode='json'),
            **({'revision_selection': True} if revision_selection else {})})
        if revision_selection and (operation != 'REVISE' or plan_id is None
                or expected_run_revision is None or expected_version_revision is None):
            fail(ErrorCode.INPUT_INVALID, 'Only revisions of existing plans can generate a proposed version.')
        new_plan = plan_id is None
        with self.db.transaction() as connection:
            if command_key is not None:
                previous = connection.execute('SELECT * FROM workflow_commands WHERE owner_id=? AND command_key=?', (user.id, command_key)).fetchone()
                if previous:
                    if previous['operation'] != 'START' or previous['input_hash'] != input_hash:
                        fail(ErrorCode.IDEMPOTENCY_CONFLICT, 'The same key  cannot start different tasks.')
                    saved_scope = RunScope.model_validate_json(previous['result'])
                    from .trip_series import require_current
                    require_current(connection, self.own_plan(connection, user, saved_scope.plan_id))
                    return saved_scope
            request = connection.execute('SELECT * FROM requests WHERE id=? AND owner_id=?', (request_id, user.id)).fetchone()
            if not request:
                fail(ErrorCode.NOT_FOUND, 'Request not found.')
            if operation == 'PLAN' and connection.execute('SELECT 1 FROM deleted_requests WHERE request_id=?', (request_id,)).fetchone():
                fail(ErrorCode.NOT_FOUND, 'Request not found.')
            if request['status'] != 'CONFIRMED':
                fail(ErrorCode.REQUEST_NOT_CONFIRMED, 'Confirm the request first.')
            if expected_request_revision is not None and request['revision'] != expected_request_revision:
                fail(ErrorCode.VERSION_CONFLICT, 'Request record updated. Refresh before starting planning.')
            if single_plan and connection.execute('SELECT 1 FROM plans WHERE request_id=? AND owner_id=?', (request_id, user.id)).fetchone():
                fail(ErrorCode.INVALID_STATE, 'This request already has planning records. View the existing plan or retry the failed run.')
            context = ConfirmedContext.model_validate_json(request['confirmed_context'])
            from ..agents.rules.transport import require_supported
            require_supported(context.profile_snapshot, dataset)
            context = ConfirmedContext.model_validate(context.model_copy(update={'demo_context': demo, 'dataset_context': dataset}))
            if plan_id is None:
                if operation != 'PLAN' or expected_current_version_id is not None:
                    fail(ErrorCode.INVALID_STATE, 'New plans can only start  PLAN.')
                plan_id = uuid4().hex
                from .trip_series import validate_successor
                validate_successor(connection, user, request_id)
                connection.execute('INSERT INTO plans(id,owner_id,request_id,current_version_id,active_run_id,final_version_id,created_at) VALUES(?,?,?,?,?,?,?)', (plan_id, user.id, request_id, None, None, None, now()))
            else:
                plan = self.own_plan(connection, user, plan_id)
                from .trip_series import require_current
                require_current(connection, plan)
                from .revision_choices import require_decided
                require_decided(connection, plan_id)
                if command_key is not None and plan['active_run_id'] != expected_active_run_id:
                    fail(ErrorCode.STALE_CONTEXT, 'Current run changed. Refresh before starting a new task.')
                if expected_run_revision is not None:
                    current_run = connection.execute('SELECT revision,status FROM runs WHERE id=?', (plan['active_run_id'],)).fetchone()
                    current_version = connection.execute('SELECT revision FROM versions WHERE id=? AND plan_id=?', (expected_current_version_id, plan_id)).fetchone()
                    if not current_run or not current_version or current_run['revision'] != expected_run_revision or current_version['revision'] != expected_version_revision:
                        fail(ErrorCode.VERSION_CONFLICT, 'Version or run updated. Refresh.')
                    if current_run['status'] in {'PENDING','RUNNING'}:
                        fail(ErrorCode.INVALID_STATE, 'A task is still running. Wait before starting another.')
                    if plan['request_id'] != request_id:
                        fail(ErrorCode.STALE_CONTEXT, 'Plan requirements changed. Refresh.')
                restart_before_version = operation == 'PLAN' and command_key is not None and plan['current_version_id'] is None and expected_current_version_id is None
                if not restart_before_version and (operation == 'PLAN' or plan['current_version_id'] != expected_current_version_id or expected_current_version_id is None):
                    fail(ErrorCode.VERSION_CONFLICT, 'The current version has changed.')
                if revision_selection and not connection.execute('''SELECT 1 FROM runs r JOIN run_versions rv ON rv.run_id=r.id
                    WHERE r.id=? AND r.plan_id=? AND rv.version_id=? AND r.status='SUCCEEDED' AND r.stage='COMPLETED' ''',
                    (plan['active_run_id'], plan_id, plan['current_version_id'])).fetchone():
                    fail(ErrorCode.INVALID_STATE, 'Current plan checks are incomplete. Continue the original task or view a completed historical plan.')
                if operation == 'REVISE' and revision_check is not None:
                    # Run after ownership, idempotency and revision guards, before
                    # any pointer, status, receipt or assessment can be changed.
                    version = connection.execute('SELECT content FROM versions WHERE id=? AND plan_id=?',
                        (expected_current_version_id, plan_id)).fetchone()
                    if not version:
                        fail(ErrorCode.VERSION_CONFLICT, 'The current version has changed.')
                    revision_check(context, json.loads(version['content']))
                if plan['active_run_id']:
                    connection.execute("UPDATE runs SET status='SUPERSEDED',revision=revision+1 WHERE id=? AND status IN ('PENDING','RUNNING')", (plan['active_run_id'],))
            scope = RunScope(command_id=uuid4().hex, run_id=uuid4().hex, plan_id=plan_id, request_id=request_id, operation=operation, expected_current_version_id=expected_current_version_id, demo_context=demo, dataset_context=dataset, write_keys={name: uuid4().hex for name in ('recommendations','version','logistics','safety','route')})
            connection.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)', (scope.run_id, plan_id, request_id, encode(scope), encode(context), 'PENDING', 'RECOMMENDING', 0, None, now()))
            if revision_selection:
                base_run = connection.execute('SELECT revision FROM runs WHERE id=?', (plan['active_run_id'],)).fetchone()
                base_version = connection.execute('SELECT revision FROM versions WHERE id=?', (plan['current_version_id'],)).fetchone()
                connection.execute('''INSERT INTO revision_proposals(id,plan_id,base_run_id,base_version_id,
                    base_run_revision,base_version_revision,candidate_run_id,created_at) VALUES(?,?,?,?,?,?,?,?)''',
                    (uuid4().hex, plan_id, plan['active_run_id'], plan['current_version_id'],
                     base_run['revision'], base_version['revision'], scope.run_id, now()))
            else:
                connection.execute('UPDATE plans SET active_run_id=?,request_id=? WHERE id=?', (scope.run_id, request_id, plan_id))
            if new_plan:
                from .trip_series import register_plan
                register_plan(connection, user, request_id, plan_id, scope.run_id)
            if operation == 'REASSESS':
                version = connection.execute('SELECT * FROM versions WHERE id=?', (expected_current_version_id,)).fetchone()
                self.bind_version(connection, scope, context, version['id'], json.loads(version['content']))
                connection.execute("UPDATE versions SET status='ASSESSING',revision=revision+1 WHERE id=?", (version['id'],))
            if command_key is not None:
                connection.execute('INSERT INTO workflow_commands VALUES(?,?,?,?,?,?)', (user.id, command_key, 'START', scope.run_id, input_hash, encode(scope)))
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
                fail(ErrorCode.NOT_FOUND, 'Run not found.')
            self.own_plan(connection, user, row['plan_id'])
            return SqlitePersistencePort(self.db, user.id, RunScope.model_validate_json(row['scope']))

    @staticmethod
    def stored_version(connection, scope):
        row = connection.execute('SELECT v.*,rv.fingerprint FROM run_versions rv JOIN versions v ON v.id=rv.version_id WHERE rv.run_id=?', (scope.run_id,)).fetchone()
        if not row:
            fail(ErrorCode.INVALID_STATE, 'No saved version yet.')
        return StoredVersion(version_context=VersionContext(plan_id=scope.plan_id, plan_version_id=row['id'], run_id=scope.run_id, input_fingerprint=row['fingerprint']), version_number=row['version_number'], content=json.loads(row['content']), status=row['status'], revision=row['revision'])
