"""Read-only fact/quote and Decimal budget tools; never confirm procurement."""
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from ..contracts.base import ContractModel, MoneyCents, Quantity
from ..contracts.dto import CostLine, GearItem, LogisticsResult, SourceRef
from ..contracts.enums import AssessmentOutcome, ErrorCode
from .client import model_failure
from .coordinator import canonical, digest
from .logistics_schema import GearChoice, LogisticsProposal, SupplyMethod

LOGISTICS_TOOL_VERSION = 'logistics-read-only-tools-1'
REFERENCE_METHODS = {
    'cost-06': 'PROPOSE_RENTAL', 'cost-07': 'PROPOSE_RENTAL', 'cost-08': 'PROPOSE_RENTAL',
    'cost-09': 'PROPOSE_PURCHASE', 'cost-10': 'PROPOSE_PURCHASE', 'cost-11': 'PROPOSE_PURCHASE',
    'cost-12': 'PROPOSE_RENTAL', 'cost-13': 'PROPOSE_PURCHASE', 'cost-16': 'PROPOSE_PURCHASE',
}
REFERENCE_ITEMS = {
    'cost-06': 'tent', 'cost-07': 'sleeping_bag', 'cost-08': 'camping_stove',
    'cost-09': 'first_aid_kit', 'cost-10': 'torch', 'cost-11': 'rain_jacket',
    'cost-12': 'sleeping_mat', 'cost-13': 'power_bank', 'cost-16': 'offline_map',
}


class SupplyPlan(ContractModel):
    fact: GearItem
    method: SupplyMethod
    procurement_quantity: Quantity | None
    procurement_unit: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    estimated_cost_cents: MoneyCents | None
    cost_line_id: Annotated[StrictStr, Field(min_length=1, max_length=200)] | None
    price_source: SourceRef | None
    confirmation_required: StrictBool
    reason_unverified: Annotated[StrictStr, Field(min_length=1, max_length=240)]


class BudgetAllocation(ContractModel):
    line_id: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    required_cents: MoneyCents | None
    allocated_cents: MoneyCents | None
    unfunded_cents: MoneyCents | None


class ValidatedLogisticsPlan(ContractModel):
    gear_actions: list[SupplyPlan] = Field(min_length=1, max_length=64)
    budget_allocations: list[BudgetAllocation] = Field(min_length=1, max_length=128)
    projected_cost_breakdown: list[CostLine] = Field(min_length=1, max_length=128)
    projected_total_cents: MoneyCents | None
    known_subtotal_cents: StrictInt = Field(ge=0)
    budget_difference_cents: StrictInt | None
    budget_feasible: StrictBool | None
    unallocated_known_budget_cents: StrictInt = Field(ge=0)
    requires_user_confirmation: StrictBool
    decision_summary_unverified: Annotated[StrictStr, Field(min_length=1, max_length=1200)]
    source_refs: list[SourceRef]

    @model_validator(mode='after')
    def complete_unique_choices(self):
        keys = [item.fact.item_key for item in self.gear_actions]
        lines = [item.line_id for item in self.budget_allocations]
        if (len(set(keys)) != len(keys) or len(set(lines)) != len(lines)
                or not self.decision_summary_unverified.strip()
                or any(not item.reason_unverified.strip() for item in self.gear_actions)):
            raise ValueError('Duplicate choices or blank model explanations')
        return self


class LogisticsToolset:
    """One invocation's snapshot. No files, SQL, network, writes or oracles."""
    def __init__(self, input, baseline: LogisticsResult):
        self.input = input.model_copy(deep=True)
        self.baseline = baseline.model_copy(deep=True)
        self._gear = {item.item_key: item for item in self.baseline.gear_checklist}
        self._costs = {f'line-{i}': line for i, line in enumerate(self.baseline.cost_breakdown)}
        if (len(self._gear) != len(self.baseline.gear_checklist)
                or not 1 <= len(self._gear) <= 64 or not 1 <= len(self._costs) <= 128):
            raise model_failure('规则事实的装备或费用清单超出受控范围。', code=ErrorCode.CONTRACT_INVALID)
        self._quotes = {}
        for line_id, line in self._costs.items():
            if line.category != 'ADDITIONAL_GEAR':
                continue
            key = REFERENCE_ITEMS.get(line.item_key, line.item_key)
            if key in self._gear:
                if key in self._quotes:
                    raise model_failure('装备费用来源存在重复关联。', code=ErrorCode.CONTRACT_INVALID)
                self._quotes[key] = (line_id, line)
        for item in self.baseline.gear_checklist:
            if (item.item_key not in self._quotes and item.missing_quantity != 0
                    and item.item_key not in {'drinking_water', 'meal_supplies', 'transport_itinerary', 'fire_free_meal_plan'}):
                # The rule estimate prices essential gear only. If the model
                # also plans an unpriced optional item, do not omit its possible
                # expense from the projected plan or silently treat it as free.
                key = f'unpriced-{item.item_key}'
                line = CostLine(category='ADDITIONAL_GEAR', item_key=item.item_key,
                    quantity=item.missing_quantity, unit=item.unit, unit_price_cents=None,
                    subtotal_cents=None, source_ref=None,
                    assumption='No registered price for this proposed gear arrangement; cost remains unknown.')
                self._costs[key] = line
                self._quotes[item.item_key] = (key, line)
        if len(self._costs) > 128:
            raise model_failure('方案费用清单超出受控范围。', code=ErrorCode.CONTRACT_INVALID)

    def options(self, item):
        if item.missing_quantity is None:
            return ['ASK_USER'] if item.essential else ['ASK_USER', 'DEFER_OPTIONAL']
        if item.missing_quantity == 0:
            return ['KEEP_CONFIRMED']
        allowed = ['PROPOSE_BORROW', 'ASK_USER']
        quote = self._quotes.get(item.item_key)
        if quote and quote[1].subtotal_cents is not None and quote[1].item_key in REFERENCE_METHODS:
            allowed.insert(0, REFERENCE_METHODS[quote[1].item_key])
        if not item.essential:
            allowed.insert(0, 'DEFER_OPTIONAL')
        return allowed

    def read_logistics_facts(self):
        return {
            'tool': 'read_logistics_facts', 'read_only': True, 'source_type': 'SYNTHETIC',
            'demo_only': True, 'currency': 'AUD',
            'scope': 'Proposals only. No stock/rental confirmation, purchase, booking, budget change or safety clearance.',
            'confirmed_requirements': self.input.confirmed_requirements.model_dump(mode='json'),
            'gear': [{**item.model_dump(mode='json'), 'allowed_methods': self.options(item),
                'quote_line_id': self._quotes[item.item_key][0] if item.item_key in self._quotes else None}
                for item in self.baseline.gear_checklist],
            'costs': [{'line_id': key, **line.model_dump(mode='json')} for key, line in self._costs.items()],
            'transport_feasible': self.baseline.transport_feasible,
            'mandatory_blockers': [item.model_dump(mode='json') for item in self.baseline.mandatory_blockers],
            'clarifications': [item.model_dump(mode='json') for item in self.baseline.clarifications],
            'rule_outcome': self.baseline.outcome.value,
            'source_refs': [item.model_dump(mode='json') for item in self.baseline.source_refs],
            'assumptions': list(self.baseline.assumptions),
        }

    def evaluate_logistics_plan(self, raw):
        proposal = LogisticsProposal.model_validate(raw)
        keys = [choice.item_key for choice in proposal.gear_choices]
        if len(keys) != len(set(keys)) or set(keys) != set(self._gear):
            raise model_failure('模型必须逐项覆盖原装备清单，不能遗漏、重复或发明物品。', code=ErrorCode.CONTRACT_INVALID)
        if len(proposal.cost_priority) != len(set(proposal.cost_priority)) or set(proposal.cost_priority) != set(self._costs):
            raise model_failure('模型费用优先级必须覆盖全部原费用行，不能删除必要费用。', code=ErrorCode.CONTRACT_INVALID)
        if not proposal.decision_summary.strip() or any(not choice.reason.strip() for choice in proposal.gear_choices):
            raise model_failure('模型方案说明不能为空。', code=ErrorCode.CONTRACT_INVALID)
        actions, projected = [], {key: line.model_copy(deep=True) for key, line in self._costs.items()}
        for choice in proposal.gear_choices:
            item = self._gear[choice.item_key]
            if choice.method not in self.options(item):
                raise model_failure('模型补缺方式不符合已确认数量或实际参考价格。', code=ErrorCode.CONTRACT_INVALID)
            quote = self._quotes.get(item.item_key)
            priced = choice.method in {'PROPOSE_RENTAL', 'PROPOSE_PURCHASE'}
            confirmed = choice.method == 'KEEP_CONFIRMED'
            deferred = choice.method == 'DEFER_OPTIONAL'
            actions.append(SupplyPlan(
                fact=item, method=choice.method,
                procurement_quantity=quote[1].quantity if priced else Decimal(0) if confirmed or deferred else item.missing_quantity,
                procurement_unit=quote[1].unit if priced else item.unit,
                estimated_cost_cents=quote[1].subtotal_cents if priced else 0 if confirmed or deferred else None,
                cost_line_id=quote[0] if quote else None,
                price_source=quote[1].source_ref if priced else None,
                confirmation_required=not (confirmed or deferred), reason_unverified=choice.reason,
            ))
            if quote and deferred:
                projected[quote[0]] = CostLine(category='ADDITIONAL_GEAR', item_key=item.item_key,
                    quantity=Decimal(0), unit='not_procured', unit_price_cents=0, subtotal_cents=0,
                    source_ref=None, assumption='Optional procurement explicitly deferred; no equipment or free supplier rate is claimed.')
            elif quote and choice.method in {'PROPOSE_BORROW', 'ASK_USER'}:
                # An unconfirmed alternative is not a free quote. Original rule
                # facts remain in baseline; this is an explicitly unknown draft.
                projected[quote[0]] = quote[1].model_copy(update={
                    'quantity': None, 'unit_price_cents': None, 'subtotal_cents': None,
                    'assumption': f'{choice.method}: cost is unknown until independently confirmed; not a free supply.',
                })
        ordered = [projected[key] for key in proposal.cost_priority]
        known = sum(line.subtotal_cents for line in ordered if line.subtotal_cents is not None)
        total = None if any(line.subtotal_cents is None for line in ordered) else known
        remaining, allocations = self.input.confirmed_requirements.budget_cents, []
        for key, line in zip(proposal.cost_priority, ordered):
            required = line.subtotal_cents
            allocated = None if required is None else min(required, remaining)
            if allocated is not None:
                remaining -= allocated
            allocations.append(BudgetAllocation(line_id=key, required_cents=required,
                allocated_cents=allocated, unfunded_cents=None if required is None else required - allocated))
        return ValidatedLogisticsPlan(
            gear_actions=actions, budget_allocations=allocations, projected_cost_breakdown=ordered,
            projected_total_cents=total, known_subtotal_cents=known,
            budget_difference_cents=None if total is None else total - self.input.confirmed_requirements.budget_cents,
            budget_feasible=None if total is None else total <= self.input.confirmed_requirements.budget_cents,
            unallocated_known_budget_cents=remaining,
            requires_user_confirmation=any(item.confirmation_required for item in actions) or bool(self.baseline.clarifications),
            decision_summary_unverified=proposal.decision_summary, source_refs=self.baseline.source_refs,
        )

    def result(self, plan):
        # Defense in depth for later callers: even a typed tool result is not
        # allowed to carry tampered stock, capacity, totals or source references.
        verified = self.evaluate_logistics_plan(LogisticsProposal(
            gear_choices=[GearChoice(item_key=item.fact.item_key, method=item.method, reason=item.reason_unverified)
                for item in plan.gear_actions],
            cost_priority=[item.line_id for item in plan.budget_allocations],
            decision_summary=plan.decision_summary_unverified,
        ))
        if verified != plan:
            raise model_failure('装备方案的数量、价格、预算或来源与确定性计算不符。', code=ErrorCode.CONTRACT_INVALID)
        # Preserve ALL actual stock, blocker, clarification and transport facts.
        # Proposal choices can reorder gear and change prospective gap estimates,
        # but can never turn an unresolved original verdict into PASSED.
        result = self.baseline.model_copy(update={
            'gear_checklist': [item.fact for item in plan.gear_actions],
            'cost_breakdown': plan.projected_cost_breakdown,
            'known_subtotal_cents': plan.known_subtotal_cents, 'total_cents': plan.projected_total_cents,
            'budget_difference_cents': plan.budget_difference_cents,
            'outcome': self.baseline.outcome if plan.projected_total_cents is not None else AssessmentOutcome.REVISION,
            'assumptions': [*self.baseline.assumptions,
                'Campus LogisticsAgent selected supply methods and budget priority; all quantities/prices/totals are host-computed.',
                'Proposed rental, purchase or borrowing is unconfirmed and never resolves missing gear or safety blockers.',
                'Model decision summary (not a verified fact): ' + plan.decision_summary_unverified],
            'uncertainties': [*self.baseline.uncertainties,
                'Unallocated known budget is not spare cash: unknown costs and unconfirmed arrangements remain unresolved.'],
        })
        return LogisticsResult.model_validate_json(result.model_dump_json())

    @staticmethod
    def proposal_hash(proposal):
        return digest(canonical(proposal.model_dump(mode='json')))
