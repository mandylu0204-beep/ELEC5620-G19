import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from .application.agent_runtime import AgentRuntime
from .application.dispatcher import PlanningDispatcher
from .application.datasets import BUSINESS_FILES, inspect_dataset
from .auth import AuthService
from .http_accounts import router as accounts_router
from .http_requests import router as requests_router
from .http_plans import router as plans_router
from .http_reviews import router as reviews_router
from .storage.reviews import ReviewService
from .storage.finalisation import FinalisationService
from .storage.workflows import WorkflowService
from .storage.plan_queries import PlanQueries
from .storage.requests import RequestRepository
from .storage.database import Database
from .storage.repository import Repository
from .config import Settings
from .contracts import DEMO_DISCLAIMER, SCHEMA_VERSION
from .contracts.base import ContractModel
from .contracts.dto import DemoContext, InterpretRequestInput, InterpretRequestResult, ProfileSnapshot, TripRequirements
from .contracts.enums import AllowedAction, ErrorCode, ExecutionMode, FieldErrorCode
from .contracts.errors import ContractError, ContractFailure, ErrorEnvelope, FieldError, HTTP_STATUS

logger = logging.getLogger(__name__)


class PreviewRequest(ContractModel):
    raw_text: str
    explicit_fields: TripRequirements
    profile_snapshot: ProfileSnapshot | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    database = Database(config.database_path)
    auth = AuthService(database, config.session_hours)

    @asynccontextmanager
    async def lifespan(application):
        database.initialize()
        if config.seed_demo_accounts:
            auth.seed_demo_accounts()
        await application.state.dispatcher.recover()
        try:
            yield
        finally:
            await application.state.dispatcher.close()

    application = FastAPI(title='CampMate AI', version='0.6.0', description='Local synthetic demo: Founder review and immutable final snapshots. B planning is pending.', lifespan=lifespan)
    application.state.settings = config
    application.state.runtime = AgentRuntime(application.state)
    application.state.database = database
    application.state.auth = auth
    application.state.repository = Repository(database)
    application.state.requests = RequestRepository(database)
    application.state.plan_queries = PlanQueries(database)
    application.state.reviews = ReviewService(database)
    application.state.finalisation = FinalisationService(database)
    application.state.workflows = WorkflowService(database)
    application.state.dispatcher = PlanningDispatcher(application.state)
    application.include_router(accounts_router)
    application.include_router(requests_router)
    application.include_router(plans_router)
    application.include_router(reviews_router)

    @application.middleware('http')
    async def trace_request(request: Request, call_next):
        request.state.trace_id = uuid4().hex
        response = await call_next(request)
        response.headers['X-Trace-ID'] = request.state.trace_id
        if request.url.path.startswith('/api/v1'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def error_response(request: Request, error: ContractError, status_code: int) -> JSONResponse:
        trace_id = getattr(request.state, 'trace_id', uuid4().hex)
        return JSONResponse(status_code=status_code, content=ErrorEnvelope(error=error, trace_id=trace_id).model_dump(mode='json'), headers={'X-Trace-ID': trace_id})

    @application.exception_handler(ContractFailure)
    async def contract_failure(request: Request, exc: ContractFailure):
        return error_response(request, exc.error, HTTP_STATUS[exc.error.code])

    @application.exception_handler(RequestValidationError)
    async def input_failure(request: Request, exc: RequestValidationError):
        fields = [FieldError(field='.'.join(str(part) for part in item['loc'] if part != 'body'), code=FieldErrorCode.INVALID, message=item['msg']) for item in exc.errors()]
        return error_response(request, ContractError(code=ErrorCode.INPUT_INVALID, message='输入格式不符合接口约定。', field_errors=fields, allowed_actions=[AllowedAction.EDIT_INPUT]), 422)

    @application.exception_handler(HTTPException)
    async def http_failure(request: Request, exc: HTTPException):
        code = {401: ErrorCode.UNAUTHENTICATED, 403: ErrorCode.FORBIDDEN, 404: ErrorCode.NOT_FOUND}.get(exc.status_code, ErrorCode.INVALID_STATE)
        return error_response(request, ContractError(code=code, message='接口不存在。' if exc.status_code == 404 else '当前请求不能执行。'), exc.status_code)

    @application.exception_handler(Exception)
    async def unexpected_failure(request: Request, exc: Exception):
        logger.error('Unexpected application failure: trace=%s type=%s', getattr(request.state, 'trace_id', 'unknown'), type(exc).__name__)
        return error_response(request, ContractError(code=ErrorCode.AGENT_FAILURE, message='服务发生错误，请保留 trace_id 供开发排查。', allowed_actions=[AllowedAction.CONTACT_OPERATOR]), 503)

    @application.get('/api/v1/health/live')
    async def liveness():
        return {'status': 'alive', 'service': 'campmate-api'}

    @application.get('/api/v1/health/ready')
    def readiness():
        missing = []
        for name in BUSINESS_FILES:
            try:
                with (config.dataset_path / 'data' / name).open('rb') as source:
                    source.read(1)
            except OSError:
                missing.append(name)
        try:
            descriptor = inspect_dataset(config)
        except ContractFailure:
            descriptor = None
        sqlite_available = database.ready()
        try:
            runtime = application.state.runtime.resolve()
            agent_available = runtime.agent is not None
            application.state.runtime.error = None
        except ContractFailure as exc:
            application.state.runtime.error = exc.error
            agent_available = False
        ready = not missing and descriptor is not None and sqlite_available and agent_available
        return JSONResponse(status_code=200 if ready else 503, content={
            'status': 'ready' if ready else 'not_ready', 'scope': 'development_foundation',
            'execution_mode': config.execution_mode.value,
            'checks': {'dataset_readable': not missing, 'dataset_context_valid': descriptor is not None, 'sqlite_driver': sqlite_available, 'database_migrated': sqlite_available, 'configured_agent_available': agent_available},
            'dataset_version': descriptor.context.dataset_version if descriptor else None,
            'missing_files': missing,
            'business_persistence_implemented': True,
            'business_workflows_implemented': application.state.dispatcher.available,
            'real_agents_implemented': False,
            'rule_agents_available': agent_available and config.execution_mode == ExecutionMode.DETERMINISTIC_DEMO,
            'agent_configuration_error': application.state.runtime.error.model_dump(mode='json') if application.state.runtime.error else None,
            'planning_available': application.state.dispatcher.available,
        })

    @application.get('/api/v1/meta')
    def metadata():
        try:
            descriptor = inspect_dataset(config)
        except ContractFailure:
            descriptor = None
        return {
            'project': 'CampMate AI', 'version': '0.6.0', 'schema_version': SCHEMA_VERSION,
            'execution_mode': config.execution_mode.value, 'demo_today': config.demo_today.isoformat(),
            'disclaimer': DEMO_DISCLAIMER,
            'provenance': descriptor.provenance.model_dump(mode='json') if descriptor else None,
            'dataset_version': descriptor.context.dataset_version if descriptor else None,
            'features': {'request_preview': config.execution_mode == ExecutionMode.STUB and application.state.agent is not None, 'authentication': True, 'persistence': True, 'profiles': True, 'request_confirmation': True, 'plan_reading': True, 'planning': application.state.dispatcher.available, 'human_review': True, 'finalisation': True},
            'agent_configuration_error': application.state.runtime.error.model_dump(mode='json') if application.state.runtime.error else None,
        }

    @application.post('/api/v1/dev/interpret', response_model=InterpretRequestResult)
    async def interpret_preview(body: PreviewRequest):
        if config.execution_mode != ExecutionMode.STUB or application.state.agent is None:
            raise ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE, message='契约预览仅支持 stub；配置的其他模式尚未接入，不会自动回退。', allowed_actions=[AllowedAction.CONTACT_OPERATOR]))
        try:
            descriptor = inspect_dataset(config)
            input = InterpretRequestInput(
                raw_text=body.raw_text, explicit_fields=body.explicit_fields,
                profile_snapshot=body.profile_snapshot,
                demo_context=DemoContext(mode=config.execution_mode, demo_today=config.demo_today, dataset_version=descriptor.context.dataset_version),
            )
        except ValidationError as exc:
            raise ContractFailure(ContractError(code=ErrorCode.INPUT_INVALID, message='请求内容无效。', field_errors=[FieldError(field='.'.join(map(str, item['loc'])), code=FieldErrorCode.INVALID, message=item['msg']) for item in exc.errors()], allowed_actions=[AllowedAction.EDIT_INPUT])) from exc
        result = await application.state.agent.interpret_request(input)
        try:
            validated = InterpretRequestResult.model_validate(result)
            if validated.execution_mode != config.execution_mode:
                raise ValueError('Agent mode does not match the registered mode')
            return validated
        except (ValidationError, ValueError) as exc:
            raise ContractFailure(ContractError(code=ErrorCode.CONTRACT_INVALID, message='Agent 输出不符合共享 schema，结果未保存。', allowed_actions=[AllowedAction.CONTACT_OPERATOR])) from exc

    return application


app = create_app()
