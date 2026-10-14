"""Internal logistics proposal protocol; no new shared contract fields."""
from typing import Annotated, Literal

from pydantic import Field, StrictStr, TypeAdapter, ValidationError

from ..contracts.base import ContractModel
from ..contracts.enums import ErrorCode
from .client import model_failure, strict_json

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
        action = LOGISTICS_ACTION.validate_python(strict_json(stripped))
        if isinstance(action, ReadFactsAction):
            return action
        proposal = action.arguments if isinstance(action, EvaluateAction) else action.proposal
        if not proposal.decision_summary.strip() or any(not choice.reason.strip() for choice in proposal.gear_choices):
            raise ValueError('Blank explanations')
        return action
    except (ValueError, TypeError, ValidationError, RecursionError):
        raise model_failure('模型装备方案不符合受控 JSON 协议；未采纳任何方案。', code=ErrorCode.CONTRACT_INVALID) from None
