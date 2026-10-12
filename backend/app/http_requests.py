import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import Field, StrictBool, StrictInt, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from .application.request_rules import normalize
from .auth import User, fail
from .contracts.base import ContractModel
from .contracts.dto import InterpretRequestResult, TripRequirements
from .contracts.enums import ErrorCode, AllowedAction
from .contracts.errors import ContractError, ContractFailure
from .http_accounts import current_user, writing_user


class RequestInput(ContractModel):
    raw_text: str = Field(min_length=1, max_length=8000)
    explicit_fields: TripRequirements = Field(default_factory=TripRequirements)

    @field_validator('raw_text')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('请填写露营想法。')
        return value


class EditRequestInput(RequestInput):
    expected_revision: StrictInt = Field(ge=1)


class RevisionInput(ContractModel):
    expected_revision: StrictInt = Field(ge=1)


class ConfirmInput(RevisionInput):
    command_key: str = Field(min_length=16, max_length=128)
    acknowledged: StrictBool

    @field_validator('acknowledged')
    @classmethod
    def acknowledged_only(cls, value):
        if value is not True:
            raise ValueError('请阅读并确认当前摘要。')
        return value


router = APIRouter(prefix='/api/v1')


@router.get('/request-context')
def request_context(request: Request, user: User = Depends(current_user)):
    from .auth import require_role
    require_role(user, 'CAMPER')
    snapshot = request.app.state.runtime.resolve()
    return {'supported_destinations': snapshot.descriptor.regions, 'execution_mode': snapshot.demo.mode.value, 'demo_today': snapshot.demo.demo_today.isoformat(), 'planning_available': request.app.state.dispatcher.available}


@router.get('/requests')
def list_requests(request: Request, user: User = Depends(current_user)):
    return {'requests': request.app.state.requests.list(user)}


@router.post('/requests', status_code=201)
def create_request(body: RequestInput, request: Request, user: User = Depends(writing_user)):
    return request.app.state.requests.create(user, body.raw_text, body.explicit_fields)


@router.get('/requests/{request_id}')
def read_request(request_id: str, request: Request, user: User = Depends(current_user)):
    return planning_fields(request, user, request.app.state.requests.get(user, request_id))


def planning_fields(request, user, result):
    with request.app.state.database.transaction(write=False) as connection:
        plan = connection.execute('SELECT id FROM plans WHERE request_id=? AND owner_id=? ORDER BY created_at DESC LIMIT 1', (result['request_id'], user.id)).fetchone()
    return {**result, 'planning_plan_id': plan['id'] if plan else None,
            'planning_available': request.app.state.dispatcher.available}


@router.patch('/requests/{request_id}')
def edit_request(request_id: str, body: EditRequestInput, request: Request, user: User = Depends(writing_user)):
    return request.app.state.requests.edit(user, request_id, body.expected_revision, body.raw_text, body.explicit_fields)


@router.post('/requests/{request_id}/interpret')
async def interpret_request(request_id: str, body: RevisionInput, request: Request, user: User = Depends(writing_user)):
    # Authorization/ownership is checked before accessing datasets or calling B.
    repository = request.app.state.requests
    await run_in_threadpool(repository.get, user, request_id)
    snapshot = await run_in_threadpool(request.app.state.runtime.resolve)
    agent, config = snapshot.agent, request.app.state.settings
    if agent is None:
        fail(ErrorCode.AGENT_FAILURE, '当前解释器尚未接入；请求草稿已保留。')
    dataset, regions = snapshot.dataset, snapshot.descriptor.regions
    demo = snapshot.demo
    revision, input = await run_in_threadpool(repository.begin_analysis, user, request_id, body.expected_revision, demo, dataset)
    try:
        result = InterpretRequestResult.model_validate(await agent.interpret_request(input))
        if result.execution_mode != config.execution_mode:
            raise ValueError('Mode mismatch')
        normalized, status = normalize(result, input.explicit_fields, input.profile_snapshot, regions)
        return await run_in_threadpool(repository.finish_analysis, user, request_id, revision, normalized, status)
    except (ValidationError, ValueError) as exc:
        error = ContractError(code=ErrorCode.CONTRACT_INVALID, message='解释器输出不符合约定；请求未确认，可修改或重试。', allowed_actions=[AllowedAction.RETRY])
        await run_in_threadpool(repository.fail_analysis, user, request_id, revision, error)
        raise ContractFailure(error) from exc
    except ContractFailure as exc:
        await run_in_threadpool(repository.fail_analysis, user, request_id, revision, exc.error)
        raise
    except asyncio.CancelledError:
        error = ContractError(code=ErrorCode.AGENT_FAILURE, message='摘要生成中断，请重试。', recoverable=True, allowed_actions=[AllowedAction.RETRY])
        await asyncio.shield(run_in_threadpool(repository.fail_analysis, user, request_id, revision, error))
        raise
    except Exception as exc:
        error = ContractError(code=ErrorCode.AGENT_FAILURE, message='摘要生成失败，草稿已保留，请重试。', recoverable=True, allowed_actions=[AllowedAction.RETRY])
        await run_in_threadpool(repository.fail_analysis, user, request_id, revision, error)
        raise ContractFailure(error) from exc


@router.post('/requests/{request_id}/confirm')
def confirm_request(request_id: str, body: ConfirmInput, request: Request, user: User = Depends(writing_user)):
    request.app.state.requests.get(user, request_id)
    snapshot = request.app.state.runtime.resolve()
    dataset, demo = snapshot.dataset, snapshot.demo
    return planning_fields(request, user, request.app.state.requests.confirm(user, request_id, body.expected_revision, body.command_key, demo, dataset))
