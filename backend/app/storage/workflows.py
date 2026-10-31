"""A-owned durable command/recovery boundary; no B business rules.

The trusted dispatcher supplies current demo/data context and passes only the
claimed persistence capability to B. Attempt IDs never come from HTTP or B.
"""
from dataclasses import dataclass
from typing import Mapping
import time
from uuid import uuid4

from ..auth import fail, require_role
from ..contracts.dto import ConfirmedContext, RunScope, RunSnapshot, StoredRecommendations, StoredAssessment, RouteResult, VersionContext, LogisticsResult, SafetyResult
from ..contracts.enums import ErrorCode, RunStage, RunStatus
from ..contracts.errors import ContractError
from .port import SqlitePersistencePort
from .repository import Repository, encode, fingerprint, now
from ..application.model_audit import load_model_trace
from ..application.assessment_audits import load_audits
from ..application.logistics_audit import save as save_logistics
from ..application.safety_audit import save as save_safety


@dataclass(frozen=True)
class Attempt:
    scope: RunScope
    attempt_id: str
    generation: int


class RecoveryPort(SqlitePersistencePort):
    """Concrete A adapter extensions; neither changes the shared 1.0 protocol."""
    def __init__(self, workflow, user, attempt):
        super().__init__(workflow.db, user.id, attempt.scope, attempt_id=attempt.attempt_id, clock=workflow.clock)
        self.workflow, self.user, self.attempt = workflow, user, attempt

    def active(self, connection, *, writing=False, execution=False):
        if self.workflow.context_provider is not None:
            demo, dataset = self.workflow.context_provider(self.scope)
            if demo != self.scope.demo_context or dataset != self.scope.dataset_context:
                fail(ErrorCode.STALE_CONTEXT, 'Run data, mode or clock changed. Start a new  run.')
        return super().active(connection, writing=writing, execution=execution)

    async def load_checkpoint(self):
        return self.workflow.checkpoint(self.user, self.attempt)

    async def save_model_logistics_assessment(self, context: VersionContext, result: LogisticsResult,
            plan: Mapping[str, object], trace: Mapping[str, object], write_key: str) -> StoredAssessment:
        return await save_logistics(self, context, result, plan, trace, write_key)

    async def save_model_safety_assessment(self, context: VersionContext, result: SafetyResult,
            plan: Mapping[str, object], trace: Mapping[str, object], write_key: str) -> StoredAssessment:
        return await save_safety(self, context, result, plan, trace, write_key)

    async def heartbeat(self):
        self.workflow.renew(self.user, self.attempt)

    async def report_stage(self, stage, status, error):
        if self.workflow.context_provider is not None and RunStatus(status) == RunStatus.SUCCEEDED:
            # The dispatcher commits success only after validating orchestrate's
            # return. Until then finalisation must remain unavailable.
            with self.db.transaction(write=False) as connection:
                _, run = self.active(connection, writing=True)
                if run['status'] != 'RUNNING' or error is not None:
                    fail(ErrorCode.INVALID_STATE, 'The current run cannot finish.')
                self.validate_completion(connection, RunStage(stage))
                return RunSnapshot(run_id=self.scope.run_id, execution_mode=self.scope.demo_context.mode,
                    run_status='SUCCEEDED', stage='COMPLETED', revision=run['revision'] + 1)
        return await super().report_stage(stage, status, error)

    async def commit_success(self):
        return await super().report_stage('COMPLETED', 'SUCCEEDED', None)


class WorkflowService:
    def __init__(self, database, *, clock=time.time, lease_seconds=120, context_provider=None):
        if lease_seconds <= 0:
            raise ValueError('lease_seconds must be positive')
        self.db, self.clock, self.lease_seconds = database, clock, lease_seconds
        self.repository = Repository(database)
        self.context_provider = context_provider
        self.logistics_facts_provider = None
        self.safety_facts_provider = None

    @staticmethod
    def command_key(key):
        if not isinstance(key, str) or not key.strip() or len(key) > 128:
            fail(ErrorCode.INPUT_INVALID, 'command_key must contain 1 to 128 nonblank characters.')

    def start(self, user, request_id, demo, dataset, *, command_key, plan_id=None,
              operation='PLAN', expected_current_version_id=None, expected_active_run_id=None,
              expected_request_revision=None, single_plan=False,
              expected_version_revision=None, expected_run_revision=None, revision_check=None, revision_selection=False):
        self.command_key(command_key)
        return self.repository.begin_run(user, request_id, demo, dataset, plan_id=plan_id,
            operation=operation, expected_current_version_id=expected_current_version_id,
            expected_active_run_id=expected_active_run_id, command_key=command_key,
            expected_request_revision=expected_request_revision, single_plan=single_plan,
            expected_version_revision=expected_version_revision, expected_run_revision=expected_run_revision,
            revision_check=revision_check, revision_selection=revision_selection)

    def fail_dispatch(self, user, run_id, error, *, attempt=None):
        """A can record execution failure even when current data no longer matches.

        An old attempt never overwrites a replacement. A malformed final return
        may invalidate provisional success reported by B before it returned.
        """
        with self.db.transaction() as connection:
            _, run, _ = self.owned_active(connection, user, run_id)
            if attempt is None:
                if run['status'] != 'PENDING':
                    return
            else:
                lease = connection.execute('SELECT * FROM run_leases WHERE run_id=?', (run_id,)).fetchone()
                if not lease or lease['attempt_id'] != attempt.attempt_id or lease['expires_at'] <= self.clock() or run['status'] not in {'RUNNING', 'SUCCEEDED'}:
                    return
            stage = 'ROUTING' if run['stage'] == 'COMPLETED' else run['stage']
            connection.execute("UPDATE runs SET status='FAILED',stage=?,revision=revision+1,error=? WHERE id=?", (stage, encode(error), run_id))
            connection.execute('INSERT INTO run_events(run_id,stage,status,error,created_at) VALUES(?,?,?,?,?)', (run_id, stage, 'FAILED', encode(error), now()))
            connection.execute('UPDATE run_leases SET expires_at=0 WHERE run_id=?', (run_id,))

    def owned_active(self, connection, user, run_id):
        require_role(user, 'CAMPER')
        row = connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        if not row:
            fail(ErrorCode.NOT_FOUND, 'Run not found.')
        plan = self.repository.own_plan(connection, user, row['plan_id'])
        from .trip_series import require_current
        require_current(connection, plan)
        from .revision_choices import execution_active
        if not execution_active(connection, plan, run_id):
            fail(ErrorCode.STALE_CONTEXT, 'Run superseded by a new task.')
        return plan, row, RunScope.model_validate_json(row['scope'])

    def unchanged(self, connection, plan, run, scope, demo, dataset):
        if scope.demo_context != demo or scope.dataset_context != dataset:
            fail(ErrorCode.STALE_CONTEXT, 'Demo clock, mode or data evidence changed. Start a new  run.')
        confirmed = ConfirmedContext.model_validate_json(run['confirmed_context'])
        binding = connection.execute('SELECT * FROM run_versions WHERE run_id=?', (scope.run_id,)).fetchone()
        if binding:
            version = Repository.stored_version(connection, scope)
            load_audits(connection, scope, version)
            from .revision_choices import version_current
            if not version_current(connection, plan, scope.run_id, version.version_context.plan_version_id) or Repository.input_fingerprint(scope, confirmed, version.content.model_dump(mode='json')) != binding['fingerprint']:
                fail(ErrorCode.STALE_CONTEXT, ' version or  fingerprint  changed. The old run cannot resume.')
        elif plan['current_version_id'] != scope.expected_current_version_id:
            fail(ErrorCode.STALE_CONTEXT, 'The current version changed. The old run cannot resume.')

    def claim(self, user, run_id, demo, dataset):
        """One worker wins. Each claim replaces the capability of the old attempt."""
        with self.db.transaction() as connection:
            plan, run, scope = self.owned_active(connection, user, run_id)
            self.unchanged(connection, plan, run, scope, demo, dataset)
            if run['status'] != 'PENDING':
                fail(ErrorCode.INVALID_STATE, 'Only queued runs can be claimed.')
            lease = connection.execute('SELECT * FROM run_leases WHERE run_id=?', (run_id,)).fetchone()
            attempt = Attempt(scope, uuid4().hex, lease['generation'] + 1 if lease else 1)
            connection.execute('INSERT INTO run_leases VALUES(?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET attempt_id=excluded.attempt_id,generation=excluded.generation,expires_at=excluded.expires_at',
                (run_id, attempt.attempt_id, attempt.generation, self.clock() + self.lease_seconds))
            connection.execute("UPDATE runs SET status='RUNNING',revision=revision+1,error=NULL WHERE id=?", (run_id,))
            connection.execute('INSERT INTO run_events(run_id,stage,status,error,created_at) VALUES(?,?,?,?,?)', (run_id, run['stage'], 'RUNNING', None, now()))
            return attempt

    def port(self, user, attempt):
        # All authorization, scope, current-attempt and lease checks run again on use.
        require_role(user, 'CAMPER')
        return RecoveryPort(self, user, attempt)

    def renew(self, user, attempt):
        with self.db.transaction() as connection:
            port = self.port(user, attempt)
            _, run = port.active(connection, writing=True)
            if run['status'] != 'RUNNING':
                fail(ErrorCode.INVALID_STATE, 'Ended runs cannot be renewed.')
            connection.execute('UPDATE run_leases SET expires_at=? WHERE run_id=? AND attempt_id=?', (self.clock() + self.lease_seconds, attempt.scope.run_id, attempt.attempt_id))

    def expire(self, user, run_id):
        """Explicit startup/operator recovery of a crashed worker, never stealing a live lease."""
        with self.db.transaction() as connection:
            _, run, _ = self.owned_active(connection, user, run_id)
            lease = connection.execute('SELECT * FROM run_leases WHERE run_id=?', (run_id,)).fetchone()
            if run['status'] != 'RUNNING' or not lease or lease['expires_at'] > self.clock():
                fail(ErrorCode.INVALID_STATE, 'The run has no expired execution lease.')
            error = ContractError(code='AGENT_FAILURE', message='Execution interrupted or lease expired. Resume from saved outputs.', recoverable=True, allowed_actions=['RETRY'])
            connection.execute("UPDATE runs SET status='FAILED',revision=revision+1,error=? WHERE id=?", (encode(error), run_id))
            connection.execute('INSERT INTO run_events(run_id,stage,status,error,created_at) VALUES(?,?,?,?,?)', (run_id, run['stage'], 'FAILED', encode(error), now()))

    def retry(self, user, run_id, demo, dataset, *, command_key, expected_run_revision):
        self.command_key(command_key)
        if type(expected_run_revision) is not int or expected_run_revision < 0:
            fail(ErrorCode.INPUT_INVALID, 'expected_run_revision  must be a nonnegative whole number.')
        input_hash = fingerprint({'run_id': run_id, 'demo': demo.model_dump(mode='json'),
            'dataset': dataset.model_dump(mode='json'), 'expected_run_revision': expected_run_revision})
        with self.db.transaction() as connection:
            plan, run, scope = self.owned_active(connection, user, run_id)
            self.unchanged(connection, plan, run, scope, demo, dataset)
            previous = connection.execute('SELECT * FROM workflow_commands WHERE owner_id=? AND command_key=?', (user.id, command_key)).fetchone()
            if previous:
                if previous['operation'] != 'RETRY' or previous['input_hash'] != input_hash:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, 'The same key  cannot retry different content.')
                return RunScope.model_validate_json(previous['result'])
            if expected_run_revision != run['revision']:
                fail(ErrorCode.VERSION_CONFLICT, 'Run updated. Refresh and retry.')
            error = ContractError.model_validate_json(run['error']) if run['error'] else None
            if run['status'] != 'FAILED' or not error or not error.recoverable:
                fail(ErrorCode.INVALID_STATE, 'Only recoverable failed runs can be retried.')
            # Revoke old capabilities immediately, even before another worker claims.
            connection.execute('INSERT INTO run_leases VALUES(?,?,1,0) ON CONFLICT(run_id) DO UPDATE SET attempt_id=excluded.attempt_id,expires_at=0', (run_id, uuid4().hex))
            connection.execute("UPDATE runs SET status='PENDING',revision=revision+1,error=NULL WHERE id=?", (run_id,))
            connection.execute('INSERT INTO run_events(run_id,stage,status,error,created_at) VALUES(?,?,?,?,?)', (run_id, run['stage'], 'PENDING', None, now()))
            connection.execute('INSERT INTO workflow_commands VALUES(?,?,?,?,?,?)', (user.id, command_key, 'RETRY', run_id, input_hash, encode(scope)))
            return scope

    def checkpoint(self, user, attempt):
        """B adapter reads persisted results before regenerating or advancing stages.

        A-side extension; the shared PersistencePort 1.0 remains unchanged.
        Do not recompute a saved step with new LLM output and reuse its write key.
        """
        with self.db.transaction(write=False) as connection:
            port = self.port(user, attempt)
            plan, run = port.active(connection, execution=True)
            self.unchanged(connection, plan, run, attempt.scope, attempt.scope.demo_context, attempt.scope.dataset_context)
            recommendations = connection.execute('SELECT payload FROM recommendations WHERE run_id=?', (attempt.scope.run_id,)).fetchone()
            binding = connection.execute('SELECT 1 FROM run_versions WHERE run_id=?', (attempt.scope.run_id,)).fetchone()
            route = connection.execute("SELECT result FROM write_receipts WHERE run_id=? AND operation='route'", (attempt.scope.run_id,)).fetchone()
            previous_version = None
            if not binding and attempt.scope.operation == 'REVISE':
                previous = connection.execute('''SELECT r.scope FROM runs r JOIN run_versions rv ON rv.run_id=r.id
                    WHERE rv.plan_id=? AND rv.version_id=? ORDER BY r.created_at DESC,r.id DESC LIMIT 1''',
                    (attempt.scope.plan_id, attempt.scope.expected_current_version_id)).fetchone()
                if previous is None:
                    fail(ErrorCode.STALE_CONTEXT, 'Original plan version not found.')
                previous_version = Repository.stored_version(connection, RunScope.model_validate_json(previous['scope']))
            return {
                'stage': run['stage'], 'run_status': run['status'],
                'confirmed_context': ConfirmedContext.model_validate_json(run['confirmed_context']),
                'recommendations': StoredRecommendations.model_validate_json(recommendations['payload']) if recommendations else None,
                'version': Repository.stored_version(connection, attempt.scope) if binding else None,
                'model_planning_trace': load_model_trace(connection, attempt.scope, Repository.stored_version(connection, attempt.scope)) if binding else None,
                'model_assessment_audits': load_audits(connection, attempt.scope, Repository.stored_version(connection, attempt.scope)) if binding else {},
                'previous_version': previous_version,
                'assessments': [StoredAssessment.model_validate_json(row['payload']) for row in connection.execute('SELECT payload FROM assessments WHERE run_id=? ORDER BY kind', (attempt.scope.run_id,))],
                'route': RouteResult.model_validate_json(route['result']) if route else None,
            }
