"""A's local task supervisor. Business decisions remain in B's AgentPort."""
import asyncio
import logging

from pydantic import ValidationError

from ..auth import User, fail
from ..contracts.dto import OrchestrateInput, RunResult
from ..contracts.enums import ErrorCode, ExecutionMode
from ..contracts.errors import ContractError, ContractFailure
from ..storage.repository import Repository

logger = logging.getLogger(__name__)


class PlanningDispatcher:
    def __init__(self, state):
        self.state = state
        self.tasks = {}
        self.redeliveries = {}
        self.closing = False
        state.workflows.context_provider = self.context

    @property
    def available(self):
        if self.closing or not self.state.settings.planning_enabled or self.state.settings.execution_mode == ExecutionMode.STUB:
            return False
        try:
            return self.state.runtime.resolve().agent is not None
        except ContractFailure as exc:
            self.state.runtime.error = exc.error
            return False

    def require_available(self):
        if not self.available:
            fail(ErrorCode.AGENT_FAILURE, '规划流程尚未启用；需接入对应模式的 Agent 和 Adapter。Stub 不生成方案。')

    def context(self, scope=None):
        snapshot = self.state.runtime.for_scope(scope) if scope is not None else self.state.runtime.resolve()
        return snapshot.demo, snapshot.dataset

    def enqueue(self, user, run_id):
        self.require_available()
        if run_id not in self.tasks:
            task = asyncio.create_task(self.execute(user, run_id), name='campmate-plan-' + run_id)
            self.tasks[run_id] = task
            task.add_done_callback(lambda done: self.finished(run_id, done))
        else:
            # A retry can arrive after FAILED was saved but before the previous
            # supervisor's finally block finished cancelling its worker.
            self.redeliveries[run_id] = user

    def finished(self, run_id, task):
        self.tasks.pop(run_id, None)
        if not task.cancelled() and task.exception() is not None:
            logger.error('Planning supervisor failed: run=%s type=%s', run_id, type(task.exception()).__name__)
        user = self.redeliveries.pop(run_id, None)
        if user is not None and self.available:
            self.enqueue(user, run_id)

    async def recover(self):
        """Resume durable PENDING commands; expire crashed workers only after their lease."""
        if not self.available:
            return
        with self.state.database.transaction(write=False) as connection:
            rows = [dict(row) for row in connection.execute("""SELECT r.id AS run_id,r.status,u.*
                FROM runs r JOIN plans p ON p.active_run_id=r.id JOIN users u ON u.id=p.owner_id
                WHERE r.status IN ('PENDING','RUNNING') AND u.role='CAMPER'""")]
        for row in rows:
            user = User(row['id'], row['username'], row['display_name'], row['role'])
            if row['status'] == 'PENDING':
                self.enqueue(user, row['run_id'])
            else:
                self.expire_if_needed(user, row['run_id'])

    def expire_if_needed(self, user, run_id):
        try:
            self.state.workflows.expire(user, run_id)
        except ContractFailure as exc:
            if exc.error.code not in {ErrorCode.INVALID_STATE, ErrorCode.STALE_CONTEXT}:
                raise

    async def close(self):
        self.closing = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def keep_alive(self, user, attempt):
        while True:
            await asyncio.sleep(self.state.workflows.lease_seconds / 3)
            self.state.workflows.renew(user, attempt)

    def validate_return(self, user, attempt, raw):
        result = RunResult.model_validate(raw)
        if result.run_id != attempt.scope.run_id or result.execution_mode != attempt.scope.demo_context.mode:
            raise ValueError('Run or mode mismatch')
        with self.state.database.transaction(write=False) as connection:
            port = self.state.workflows.port(user, attempt)
            _, run = port.active(connection, execution=True)
            if result.run_status == 'SUCCEEDED':
                if result.stage != 'COMPLETED' or result.error is not None or run['status'] != 'RUNNING':
                    raise ValueError('Invalid completion')
                port.validate_completion(connection, result.stage)
                if result.route is not None:
                    version = Repository.stored_version(connection, attempt.scope)
                    if result.route != version.status:
                        raise ValueError('Route mismatch')
            elif result.run_status == 'FAILED':
                if result.error is None or result.stage != run['stage'] or run['status'] not in {'RUNNING', 'FAILED'}:
                    raise ValueError('Invalid failure')
                if run['status'] == 'FAILED' and ContractError.model_validate_json(run['error']) != result.error:
                    raise ValueError('Error mismatch')
            else:
                raise ValueError('orchestrate must return a terminal result')
            ids = {row[0] for table in ('recommendations', 'assessments')
                   for row in connection.execute(f'SELECT id FROM {table} WHERE run_id=?', (attempt.scope.run_id,))}
            ids.update(row[0] for row in connection.execute('SELECT version_id FROM run_versions WHERE run_id=?', (attempt.scope.run_id,)))
            ids.update(row[0] for row in connection.execute('SELECT g.id FROM gear_checklists g JOIN assessments a ON a.id=g.assessment_id WHERE a.run_id=?', (attempt.scope.run_id,)))
            if any(value not in ids for value in result.artifact_refs.values()):
                raise ValueError('Unknown artifact reference')
        return result

    async def execute(self, user, run_id):
        attempt = None
        worker = heartbeat = None
        workflow = self.state.workflows
        try:
            # Re-delivered HTTP receipts do not restart an already running/ended run.
            with workflow.db.transaction(write=False) as connection:
                _, run, scope = workflow.owned_active(connection, user, run_id)
                if run['status'] != 'PENDING':
                    return
            snapshot = self.state.runtime.for_scope(scope)
            demo, dataset = snapshot.demo, snapshot.dataset
            attempt = workflow.claim(user, run_id, demo, dataset)
            port = workflow.port(user, attempt)
            checkpoint = workflow.checkpoint(user, attempt)
            input = OrchestrateInput(run_scope=attempt.scope, confirmed_context=checkpoint['confirmed_context'],
                                     previous_version=checkpoint['version'] or checkpoint['previous_version'])
            worker = asyncio.create_task(snapshot.agent.orchestrate(input, port))
            heartbeat = asyncio.create_task(self.keep_alive(user, attempt))
            done, _ = await asyncio.wait({worker, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done:
                await heartbeat
            result = self.validate_return(user, attempt, await worker)
            if result.run_status == 'SUCCEEDED':
                await port.commit_success()
            else:
                workflow.fail_dispatch(user, run_id, result.error, attempt=attempt)
        except asyncio.CancelledError:
            workflow.fail_dispatch(user, run_id, ContractError(code='AGENT_FAILURE', message='服务退出，执行已中断；已保存产物可在重启后重试。', recoverable=True, allowed_actions=['RETRY']), attempt=attempt)
            raise
        except (ValidationError, ValueError):
            workflow.fail_dispatch(user, run_id, ContractError(code='CONTRACT_INVALID', message='工作流返回内容与保存记录不一致，请联系开发负责人。', allowed_actions=['CONTACT_OPERATOR']), attempt=attempt)
        except ContractFailure as exc:
            error = exc.error
            if error.code == ErrorCode.PERSISTENCE_FAILURE:
                error = error.model_copy(update={'recoverable': True, 'allowed_actions': ['RETRY']})
            try:
                workflow.fail_dispatch(user, run_id, error, attempt=attempt)
            except ContractFailure:
                logger.info('Run no longer writable: run=%s', run_id)
        except Exception:
            workflow.fail_dispatch(user, run_id, ContractError(code='AGENT_FAILURE', message='工作流执行失败；可从已保存产物重试。', recoverable=True, allowed_actions=['RETRY']), attempt=attempt)
        finally:
            for task in (worker, heartbeat):
                if task is not None:
                    task.cancel()
            await asyncio.gather(*(task for task in (worker, heartbeat) if task is not None), return_exceptions=True)
