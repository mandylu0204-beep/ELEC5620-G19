from pydantic import Field

from .base import ContractModel
from .enums import AllowedAction, ErrorCode, FieldErrorCode


class FieldError(ContractModel):
    field: str
    code: FieldErrorCode
    message: str


class ContractError(ContractModel):
    code: ErrorCode
    message: str
    field_errors: list[FieldError] = Field(default_factory=list)
    recoverable: bool = False
    allowed_actions: list[AllowedAction] = Field(default_factory=list)
    context: dict[str, str] = Field(default_factory=dict)


class ErrorEnvelope(ContractModel):
    error: ContractError
    trace_id: str


class ContractFailure(Exception):
    """Internal port failure; the HTTP boundary converts it to an error envelope."""

    def __init__(self, error: ContractError):
        self.error = error
        super().__init__(error.message)


HTTP_STATUS = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.INPUT_INVALID: 422,
    ErrorCode.REQUEST_NOT_CONFIRMED: 409,
    ErrorCode.STALE_CONTEXT: 409,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.INVALID_STATE: 409,
    ErrorCode.FINALISATION_BLOCKED: 409,
    ErrorCode.CONTRACT_INVALID: 502,
    ErrorCode.ADAPTER_FAILURE: 503,
    ErrorCode.AGENT_FAILURE: 503,
    ErrorCode.PERSISTENCE_FAILURE: 503,
}
