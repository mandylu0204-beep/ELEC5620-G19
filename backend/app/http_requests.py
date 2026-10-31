import asyncio

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, StrictBool, StrictInt, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from .application.request_rules import normalize
from .application.requirement_choices import choices
from .application.structured_summary import StructuredRequestInput, StructuredSummaryMetadata, summarize, input_fingerprint as structured_fingerprint
from .auth import User, fail
from .contracts.base import ContractModel
from .contracts.dto import InterpretRequestResult, TripRequirements
from .contracts.enums import ErrorCode, AllowedAction
from .contracts.errors import ContractError, ContractFailure
from .http_accounts import current_user, writing_user
from .application.presentation import request_response
from .storage.requests import (
    RequestInterpretationIdentity, RequestInterpretationMetadata,
    RequestInterpretationObservation, request_input_fingerprint,
)


class RequestInput(ContractModel):
    raw_text: str = Field(default='', max_length=8000)
    explicit_fields: TripRequirements = Field(default_factory=TripRequirements)



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
            raise ValueError('Read and confirm the current summary.')
        return value


router = APIRouter(prefix='/api/v1')


@router.get('/request-context')
def request_context(request: Request, user: User = Depends(current_user)):
    from .auth import require_role
    require_role(user, 'CAMPER')
    snapshot = request.app.state.runtime.resolve()
    from .agents.rules.transport import SUPPORTED_MODES, POLICY_KEY, POLICY_VERSION
    return {'supported_destinations': snapshot.descriptor.regions, 'execution_mode': snapshot.demo.mode.value,
        'demo_today': snapshot.demo.demo_today.isoformat(), 'clock_mode': request.app.state.settings.clock_mode,
        'supported_transport_modes': list(SUPPORTED_MODES),
        'system_preparation': snapshot.dataset.selection_config.get(POLICY_KEY) == POLICY_VERSION,
        'planning_origin': {'id':'sydney_city_demo','label':'Central Sydney (fixed demonstration origin)'} if snapshot.dataset.selection_config.get(POLICY_KEY) == POLICY_VERSION else None,
        'requirement_choices': choices(),
        'planning_available': request.app.state.dispatcher.available}


@router.get('/requirement-choices')
def requirement_choices(user: User = Depends(current_user)):
    return choices()


@router.get('/requests')
def list_requests(request: Request, user: User = Depends(current_user)):
    return {'requests': request.app.state.requests.list(user)}


@router.post('/requests', status_code=201)
def create_request(body: RequestInput, request: Request, user: User = Depends(writing_user)):
    return request.app.state.requests.create(user, body.raw_text, body.explicit_fields)


@router.delete('/requests/{request_id}', status_code=204)
def delete_request(request_id: str, request: Request, user: User = Depends(writing_user)):
    request.app.state.requests.delete(user, request_id)
    return Response(status_code=204)


@router.get('/requests/{request_id}')
def read_request(request_id: str, request: Request, user: User = Depends(current_user)):
    return planning_fields(request, user, request.app.state.requests.get(user, request_id))


def planning_fields(request, user, result):
    with request.app.state.database.transaction(write=False) as connection:
        plan = connection.execute('SELECT id FROM plans WHERE request_id=? AND owner_id=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1', (result['request_id'], user.id)).fetchone()
    return request_response({**result, 'planning_plan_id': plan['id'] if plan else None,
            'planning_available': request.app.state.dispatcher.available})


@router.patch('/requests/{request_id}')
def edit_request(request_id: str, body: EditRequestInput, request: Request, user: User = Depends(writing_user)):
    current=request.app.state.requests.get(user,request_id)
    raw=body.raw_text if 'raw_text' in body.model_fields_set else current['raw_text']
    return request.app.state.requests.edit(user, request_id, body.expected_revision, raw, body.explicit_fields)


@router.post('/requests/{request_id}/interpret')
async def interpret_request(request_id: str, body: RevisionInput, request: Request, user: User = Depends(writing_user)):
    # Authorization/ownership is checked before accessing datasets or calling B.
    repository = request.app.state.requests
    current=await run_in_threadpool(repository.get,user,request_id)
    if current.get('requirement_help') and current['requirement_help']['needed']:
        fail(ErrorCode.INVALID_STATE,'Other requirements do not map to existing conditions. Submit request assistance first. No model was called.')
    snapshot = await run_in_threadpool(request.app.state.runtime.resolve)
    agent, config = snapshot.agent, request.app.state.settings
    if agent is None and current['raw_text'].strip():
        fail(ErrorCode.AGENT_FAILURE, 'The current interpreter is not connected. The request draft is retained.')
    dataset, regions = snapshot.dataset, snapshot.descriptor.regions
    demo = snapshot.demo
    revision, input = await run_in_threadpool(repository.begin_analysis, user, request_id, body.expected_revision, demo, dataset)
    try:
        from .agents.rules.transport import require_supported
        require_supported(input.profile_snapshot, dataset)
        structured=isinstance(input,StructuredRequestInput)
        interpreted_terms = not structured and getattr(agent, 'model_request_terms', False) is True
        metadata = None
        structured_metadata=None
        if structured:
            result=summarize(input)
            structured_metadata=StructuredSummaryMetadata(analysis_revision=revision,input_sha256=structured_fingerprint(input))
        elif interpreted_terms:
            if demo.mode.value != 'agent':
                raise ValueError('Model interpretation requires agent mode')
            identity = RequestInterpretationIdentity.model_validate(agent.request_interpretation_identity)
            observe = getattr(agent, 'interpret_request_with_observation', None)
            if not callable(observe):
                raise ValueError('Model interpretation observation is unavailable')
            outcome = await observe(input)
            observation = RequestInterpretationObservation.model_validate(outcome.observation)
            current = RequestInterpretationIdentity.model_validate(agent.request_interpretation_identity)
            if observation.identity != identity or current != identity:
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT,
                    message='Interpretation settings changed. Regenerate the summary.'))
            result = InterpretRequestResult.model_validate(outcome.result)
            metadata = RequestInterpretationMetadata(**observation.model_dump(mode='json'),
                analysis_revision=revision, input_sha256=request_input_fingerprint(input))
        else:
            result = InterpretRequestResult.model_validate(await agent.interpret_request(input))
        if result.execution_mode != config.execution_mode:
            raise ValueError('Mode mismatch')
        normalized, status = normalize(result, input.explicit_fields, input.profile_snapshot, regions,
            interpreted_terms=interpreted_terms or structured)
        options = {'interpretation_metadata': metadata} if metadata is not None else {}
        if structured_metadata is not None:options['structured_metadata']=structured_metadata
        saved = await run_in_threadpool(repository.finish_analysis, user, request_id, revision,
            normalized, status, **options)
        return request_response(saved)
    except (ValidationError, ValueError) as exc:
        error = ContractError(code=ErrorCode.CONTRACT_INVALID, message='Interpreter output does not match the contract. The request is unconfirmed; edit or retry.', allowed_actions=[AllowedAction.RETRY])
        await run_in_threadpool(repository.fail_analysis, user, request_id, revision, error)
        raise ContractFailure(error) from exc
    except ContractFailure as exc:
        await run_in_threadpool(repository.fail_analysis, user, request_id, revision, exc.error)
        raise
    except asyncio.CancelledError:
        error = ContractError(code=ErrorCode.AGENT_FAILURE, message='Summary generation interrupted. Please retry.', recoverable=True, allowed_actions=[AllowedAction.RETRY])
        await asyncio.shield(run_in_threadpool(repository.fail_analysis, user, request_id, revision, error))
        raise
    except Exception as exc:
        error = ContractError(code=ErrorCode.AGENT_FAILURE, message='Summary generation failed. The draft is retained. Please retry.', recoverable=True, allowed_actions=[AllowedAction.RETRY])
        await run_in_threadpool(repository.fail_analysis, user, request_id, revision, error)
        raise ContractFailure(error) from exc


@router.post('/requests/{request_id}/confirm')
def confirm_request(request_id: str, body: ConfirmInput, request: Request, user: User = Depends(writing_user)):
    current=request.app.state.requests.get(user, request_id)
    snapshot = request.app.state.runtime.resolve()
    dataset, demo = snapshot.dataset, snapshot.demo
    options = {}
    if current['raw_text'].strip() and getattr(snapshot.agent, 'model_request_terms', False) is True:
        options['interpretation_identity'] = snapshot.agent.request_interpretation_identity
    return planning_fields(request, user, request.app.state.requests.confirm(user, request_id,
        body.expected_revision, body.command_key, demo, dataset, **options))
