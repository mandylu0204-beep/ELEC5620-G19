from fastapi import APIRouter, Depends, Request
from pydantic import Field, StrictInt, field_validator

from .auth import User
from .contracts.base import ContractModel
from .contracts.errors import ContractFailure
from .contracts.enums import ErrorCode
from .http_accounts import current_user, writing_user
from .storage.finalisation import FinaliseInput

router = APIRouter(prefix='/api/v1')


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


@router.post('/requests/{request_id}/plan', status_code=202)
async def start_planning(request_id: str, body: StartPlanningInput, request: Request, user: User = Depends(writing_user)):
    state = request.app.state
    state.requests.get(user, request_id)  # Owner check before capability/data access.
    state.dispatcher.require_available()
    demo, dataset = state.dispatcher.context()
    scope = state.workflows.start(user, request_id, demo, dataset, command_key=body.command_key,
        expected_request_revision=body.expected_request_revision, single_plan=True)
    state.dispatcher.enqueue(user, scope.run_id)
    return {'plan_id': scope.plan_id, 'run_id': scope.run_id}


@router.post('/runs/{run_id}/retry', status_code=202)
async def retry_planning(run_id: str, body: RetryPlanningInput, request: Request, user: User = Depends(writing_user)):
    state = request.app.state
    state.plan_queries.run(user, run_id)
    state.dispatcher.require_available()
    demo, dataset = state.dispatcher.context()
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
                demo, dataset = state.dispatcher.context()
                with state.database.transaction(write=False) as connection:
                    plan, row, scope = state.workflows.owned_active(connection, user, run['run_id'])
                    state.workflows.unchanged(connection, plan, row, scope, demo, dataset)
                data['retry_available'] = True
            except ContractFailure as exc:
                if exc.error.code not in {ErrorCode.STALE_CONTEXT, ErrorCode.ADAPTER_FAILURE}:
                    raise
                reason = exc.error.message
        data['retry_unavailable_reason'] = None if data['retry_available'] else reason
    return data


@router.post('/plans/{plan_id}/finalise')
def finalise(plan_id: str, body: FinaliseInput, request: Request, user: User = Depends(writing_user)):
    return request.app.state.finalisation.submit(user, plan_id, body)


@router.get('/plans/{plan_id}/finals/{final_id}')
def final_snapshot(plan_id: str, final_id: str, request: Request, user: User = Depends(current_user)):
    return request.app.state.finalisation.detail(user, plan_id, final_id)


@router.get('/plans/{plan_id}')
def plan_detail(plan_id: str, request: Request, run_id: str | None = None, user: User = Depends(current_user)):
    return retry_fields(request, user, request.app.state.plan_queries.detail(user, plan_id, run_id))


@router.get('/runs/{run_id}')
def run_detail(run_id: str, request: Request, user: User = Depends(current_user)):
    return retry_fields(request, user, request.app.state.plan_queries.run(user, run_id))
