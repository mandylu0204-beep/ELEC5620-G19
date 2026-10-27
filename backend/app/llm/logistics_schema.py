"""Internal logistics proposal protocol; no new shared contract fields."""
from typing import Annotated, Literal
import json

from pydantic import Field, StrictStr, TypeAdapter, ValidationError

from ..contracts.base import ContractModel
from .client import strict_json
from .logistics_diagnostics import protocol_failure, schema_errors

LOGISTICS_VALIDATION_VERSION = 'logistics-proposal-validation-1'
SupplyMethod = Literal['KEEP_CONFIRMED', 'PROPOSE_RENTAL', 'PROPOSE_PURCHASE', 'PROPOSE_BORROW', 'ASK_USER', 'DEFER_OPTIONAL']
Key = Annotated[StrictStr, Field(min_length=1, max_length=100)]


class GearChoice(ContractModel):
    item_key: Key
    method: SupplyMethod
    reason: str = Field(min_length=1, max_length=240)


class LogisticsProposal(ContractModel):
    gear_choices: list[GearChoice] = Field(min_length=1, max_length=64)
    cost_priority: list[Key] = Field(min_length=1, max_length=128)
    decision_summary: str = Field(min_length=1, max_length=1200)


class EmptyArguments(ContractModel):
    pass


class ReadFactsAction(ContractModel):
    action: Literal['tool']
    name: Literal['read_logistics_facts']
    arguments: EmptyArguments


class EvaluateAction(ContractModel):
    action: Literal['tool']
    name: Literal['evaluate_logistics_plan']
    arguments: LogisticsProposal


class FinalLogisticsAction(ContractModel):
    action: Literal['final']
    proposal: LogisticsProposal


LOGISTICS_ACTION = TypeAdapter(ReadFactsAction | EvaluateAction | FinalLogisticsAction)


def parse_logistics_action(text):
    stripped = text.strip()
    if stripped.startswith('```json\n') and stripped.endswith('\n```'):
        stripped = stripped[8:-4]
    try:
        value = strict_json(stripped)
    except json.JSONDecodeError as exc:
        raise protocol_failure('JSON_PARSE', [{'loc': (), 'type': 'json_invalid'}], line=exc.lineno, column=exc.colno) from None
    except RecursionError:
        raise protocol_failure('JSON_PARSE', [{'loc': (), 'type': 'recursion_limit'}]) from None
    except (ValueError, TypeError) as exc:
        kind = {'Duplicate JSON key': 'duplicate_key', 'Non-finite JSON value': 'nonfinite_json'}.get(str(exc), 'invalid_json_value')
        raise protocol_failure('JSON_PARSE', [{'loc': (), 'type': kind}]) from None
    try:
        action = LOGISTICS_ACTION.validate_python(value)
    except ValidationError as exc:
        raise protocol_failure('SCHEMA_VALIDATION', schema_errors(exc, value)) from None
    except (ValueError, TypeError, RecursionError):
        raise protocol_failure('SCHEMA_VALIDATION', [{'loc': (), 'type': 'invalid_json_value'}]) from None
    if isinstance(action, ReadFactsAction):
        return action
    proposal = action.arguments if isinstance(action, EvaluateAction) else action.proposal
    root = 'arguments' if isinstance(action, EvaluateAction) else 'proposal'
    blanks = ([{'loc': (root, 'decision_summary'), 'type': 'blank_explanation'}] if not proposal.decision_summary.strip() else [])
    blanks.extend({'loc': (root, 'gear_choices', index, 'reason'), 'type': 'blank_explanation'}
        for index, choice in enumerate(proposal.gear_choices) if not choice.reason.strip())
    if blanks:
        raise protocol_failure('EXPLANATION_VALIDATION', blanks)
    return action
