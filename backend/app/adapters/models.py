"""Adapter-local source records; these do not change shared contract 1.0."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from ..contracts.base import ContractModel, Identifier, MoneyCents, PositiveInt
from ..contracts.dto import ProfileSnapshot, ScenarioContext, SourceRef

CostCategory = Literal['CAMPSITE', 'TRANSPORT', 'FOOD', 'WATER', 'ADDITIONAL_GEAR']


class CampsiteRecord(ContractModel):
    campsite_id: Identifier
    name: str
    region: str
    subregion: str
    latitude: Decimal | None = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: Decimal | None = Field(ge=-180, le=180, allow_inf_nan=False)
    nightly_fee_cents: MoneyCents | None
    fee_unit: Literal['per_night']
    booking_required: bool | None
    vehicle_access: bool | None
    public_transport_access: bool | None
    max_group_size: PositiveInt | None
    toilets: bool | None
    potable_water: bool | None
    showers: bool | None
    fire_allowed: bool | None
    pets_allowed: bool | None
    wheelchair_accessible: bool | None
    supported_seasons: list[str]
    facilities: list[str]
    mandatory_restrictions: list[str]
    risk_tags: list[str]
    walk_in_only: bool | None = None
    quiet_environment: bool | None = None
    step_free_path: bool | None = None
    source_ref: SourceRef


class GearRuleRecord(ContractModel):
    gear_rule_id: Identifier
    category: str
    item_name: str
    trigger_conditions: str
    quantity_rule: str
    essential: bool
    severity_if_missing: Literal['LOW', 'MEDIUM', 'HIGH', 'MANDATORY_BLOCKER']
    substitute_allowed: bool
    substitute_example: str | None
    reason: str
    source_ref: SourceRef


class CostReferenceRecord(ContractModel):
    cost_id: Identifier
    category: CostCategory
    item_name: str
    unit: Literal['per_night', 'per_kilometre', 'per_person', 'per_person_per_day', 'per_item', 'per_vehicle', 'one_time']
    low_cents: MoneyCents | None
    typical_cents: MoneyCents | None
    high_cents: MoneyCents | None
    calculation_rule: str
    assumption: str
    source_ref: SourceRef


class ProfileRecord(ContractModel):
    profile_id: Identifier
    snapshot: ProfileSnapshot
    uncertainties: list[str]
    source_ref: SourceRef


class RequestRecord(ContractModel):
    request_id: Identifier
    profile_id: Identifier
    raw_text: str = Field(min_length=1, max_length=8000)
    source_ref: SourceRef


class SafetyRecord(ContractModel):
    safety_case_id: Identifier
    campsite_id: Identifier
    scenario_date: date | None
    scenario_context: ScenarioContext
    campsite_restrictions: list[str]
    risk_tags: list[str]
    raw_road_status: str
    uncertainties: list[str]
    source_ref: SourceRef
