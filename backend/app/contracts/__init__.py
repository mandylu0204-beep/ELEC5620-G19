"""Shared contract boundary. DTOs/enums are also importable from their modules."""

from .base import DEMO_DISCLAIMER, SCHEMA_VERSION
from .errors import ContractError, ContractFailure, ErrorEnvelope, FieldError
from .ports import AgentPort, PersistencePort

__all__ = [
    "AgentPort", "PersistencePort", "ContractError", "ContractFailure",
    "ErrorEnvelope", "FieldError", "DEMO_DISCLAIMER", "SCHEMA_VERSION",
]
