from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, StrictInt, field_validator

from .auth import User
from .contracts.base import ContractModel
from .contracts.dto import RunScope
from .contracts.errors import ContractError, ContractFailure
from .contracts.enums import ErrorCode
from .http_accounts import current_user, writing_user
from .storage.finalisation import FinaliseInput
from .storage.repository import Repository
from .application.presentation import plan_response

router = APIRouter(prefix='/api/v1')


@router.delete('/plans/{plan_id}', status_code=204)
def delete_plan(plan_id: str, request: Request, user: User = Depends(writing_user)):
    request.app.state.repository.delete_plan(user, plan_id)
    return Response(status_code=204)


class CommandInput(ContractModel):
    command_key: str = Field(min_length=16, max_length=128)

    @field_validator('command_key')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('command_key 不能为空。')
        return value


class StartPlanningInput(CommandInput):
    expected_request_revision: StrictInt = Field(ge=1)


class RetryPlanningInput(CommandInput):
    expected_run_revision: StrictInt = Field(ge=0)


class NewEvaluationInput(CommandInput):
    expected_current_version_id: str = Field(min_length=1, max_length=128)
    expected_active_run_id: str = Field(min_length=1, max_length=128)
    expected_version_revision: StrictInt = Field(ge=0)
    expected_run_revision: StrictInt = Field(ge=0)


class RevisePlanningInput(NewEvaluationInput):
    feedback: str = Field(min_length=1, max_length=4000)

    @field_validator('feedback')
    @classmethod
    def meaningful_feedback(cls, value):
        if not value.strip():
            raise ValueError('请填写修改意见。')
        return value.strip()


async def new_evaluation(plan_id, body, request, user, operation):
    state = request.app.state
    with state.database.transaction(write=False) as connection:
        plan = dict(Repository.own_plan(connection, user, plan_id))
    state.dispatcher.require_available()
    state.runtime.resolve().require_operation(operation)
    snapshot = state.runtime.resolve(feedback=body.feedback if operation == 'REVISE' else None)
    scope = state.workflows.start(user, plan['request_id'], snapshot.demo, snapshot.dataset,
        command_key=body.command_key, plan_id=plan_id, operation=operation,
        expected_current_version_id=body.expected_current_version_id,
        expected_active_run_id=body.expected_active_run_id,
        expected_version_revision=body.expected_version_revision,
        expected_run_revision=body.expected_run_revision)
    state.dispatcher.enqueue(user, scope.run_id)
    return {'plan_id': scope.plan_id, 'run_id': scope.run_id}


@router.post('/plans/{plan_id}/revise', status_code=202)
async def revise_planning(plan_id: str, body: RevisePlanningInput, request: Request, user: User = Depends(writing_user)):
    return await new_evaluation(plan_id, body, request, user, 'REVISE')


@router.post('/plans/{plan_id}/reassess', status_code=202)
async def reassess_planning(plan_id: str, body: NewEvaluationInput, request: Request, user: User = Depends(writing_user)):
    return await new_evaluation(plan_id, body, request, user, 'REASSESS')


@router.post('/requests/{request_id}/plan', status_code=202)
async def start_planning(request_id: str, body: StartPlanningInput, request: Request, user: User = Depends(writing_user)):
    state = request.app.state
    state.requests.get(user, request_id)  # Owner check before capability/data access.
    state.dispatcher.require_available()
    snapshot = state.runtime.resolve()
    confirmed = state.requests.get(user, request_id).get('confirmed_context')
    from .contracts.dto import ConfirmedRequirements
    snapshot.require_operation('PLAN', ConfirmedRequirements.model_validate(confirmed['requirements']) if confirmed else None)
    demo, dataset = snapshot.demo, snapshot.dataset
    scope = state.workflows.start(user, request_id, demo, dataset, command_key=body.command_key,
        expected_request_revision=body.expected_request_revision, single_plan=True)
    state.dispatcher.enqueue(user, scope.run_id)
    return {'plan_id': scope.plan_id, 'run_id': scope.run_id}


@router.post('/runs/{run_id}/retry', status_code=202)
async def retry_planning(run_id: str, body: RetryPlanningInput, request: Request, user: User = Depends(writing_user)):
    state = request.app.state
    state.plan_queries.run(user, run_id)
    state.dispatcher.require_available()
    with state.database.transaction(write=False) as connection:
        _, _, existing_scope = state.workflows.owned_active(connection, user, run_id)
    demo, dataset = state.dispatcher.context(existing_scope)
    scope = state.workflows.retry(user, run_id, demo, dataset, command_key=body.command_key,
        expected_run_revision=body.expected_run_revision)
    state.dispatcher.enqueue(user, scope.run_id)
    return {'plan_id': scope.plan_id, 'run_id': scope.run_id}


def retry_fields(request, user, data):
    state = request.app.state
    run = data['run']
    available = state.dispatcher.available
    if available and run and run['is_active'] and run['status'] == 'RUNNING':
        state.dispatcher.expire_if_needed(user, run['run_id'])
        data = state.plan_queries.run(user, run['run_id'])
        run = data['run']
    data.update(planning_available=available, retry_available=False, retry_unavailable_reason=None)
    if run and run['status'] == 'FAILED':
        reason = '此运行已被取代，请查看当前运行。' if not run['is_active'] else '规划流程尚未启用。' if not available else '此故障不能自动重试，请联系开发负责人。'
        if available and run['is_active'] and run['error'] and run['error']['recoverable']:
            try:
                with state.database.transaction(write=False) as connection:
                    plan, row, scope = state.workflows.owned_active(connection, user, run['run_id'])
                    demo, dataset = state.dispatcher.context(scope)
                    state.workflows.unchanged(connection, plan, row, scope, demo, dataset)
                data['retry_available'] = True
            except ContractFailure as exc:
                if exc.error.code not in {ErrorCode.STALE_CONTEXT, ErrorCode.ADAPTER_FAILURE, ErrorCode.AGENT_FAILURE}:
                    raise
                reason = exc.error.message
        data['retry_unavailable_reason'] = None if data['retry_available'] else reason
    can_change = bool(available and data['current_version_revision'] is not None and run and run['is_active'] and run['status'] not in {'PENDING','RUNNING'})
    operations = state.runtime.resolve().supported_operations if available else frozenset()
    data['revision_available'] = can_change and 'REVISE' in operations
    data['reassessment_available'] = can_change and 'REASSESS' in operations
    data['current_inputs_error'] = None
    data['current_inputs_state'] = None
    data['trip_evidence_coverage'] = None
    if run and run['is_active']:
        with state.database.transaction(write=False) as connection:
            row = connection.execute('SELECT scope FROM runs WHERE id=?', (run['run_id'],)).fetchone()
        try:
            scope = RunScope.model_validate_json(row['scope'])
            snapshot = state.runtime.validate_scope(scope)
            from .application.trip_coverage import guidance as coverage_guidance
            data['trip_evidence_coverage'] = coverage_guidance(data, snapshot, scope)
        except ContractFailure as exc:
            data['current_inputs_error'] = exc.error.message
            data['current_inputs_state'] = 'CHANGED' if exc.error.code == ErrorCode.STALE_CONTEXT else 'UNAVAILABLE'
            data['finalisation_available'] = False
            if data['current_inputs_state'] == 'UNAVAILABLE':
                data['revision_available'] = data['reassessment_available'] = False
    recommendation = (data.get('recommendations') or {}).get('result')
    data['recommendation_guidance'] = None
    if recommendation and recommendation['search_outcome'] == 'NO_MATCH':
        from .application.near_matches import guidance
        dataset, note = None, None
        try:
            with state.database.transaction(write=False) as connection:
                row = connection.execute('SELECT scope FROM runs WHERE id=?', (run['run_id'],)).fetchone()
            scope = RunScope.model_validate_json(row['scope'])
            snapshot = state.runtime.for_scope(scope)
            if snapshot.dataset != scope.dataset_context or snapshot.demo != scope.demo_context:
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='比较资料的输入身份已变化。'))
            dataset = getattr(snapshot.agent, 'dataset', None)
        except ContractFailure:
            note = '当前来源或运行配置已变化，仅根据本次保存的排除理由比较；原报价、容量和设施值无法核对，保持未知。'
        data['recommendation_guidance'] = guidance(data, dataset, metadata_note=note)
    return data


@router.post('/plans/{plan_id}/finalise')
def finalise(plan_id: str, body: FinaliseInput, request: Request, user: User = Depends(writing_user)):
    return request.app.state.finalisation.submit(user, plan_id, body)


@router.get('/plans/{plan_id}/finals/{final_id}')
def final_snapshot(plan_id: str, final_id: str, request: Request, user: User = Depends(current_user)):
    return plan_response(request.app.state.finalisation.detail(user, plan_id, final_id), user)


@router.get('/plans/{plan_id}')
def plan_detail(plan_id: str, request: Request, run_id: str | None = None, user: User = Depends(current_user)):
    return plan_response(retry_fields(request, user, request.app.state.plan_queries.detail(user, plan_id, run_id)), user)


@router.get('/runs/{run_id}')
def run_detail(run_id: str, request: Request, user: User = Depends(current_user)):
    return plan_response(retry_fields(request, user, request.app.state.plan_queries.run(user, run_id)), user)
