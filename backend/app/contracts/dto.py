from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from .base import ContractModel, Identifier, MoneyCents, NonNegativeInt, PositiveInt, Quantity
from .enums import (
    AllowedAction, AssessmentKind, AssessmentOutcome, Confidence, DataQuality,
    ExecutionMode, PlanVersionStatus, ReviewDecision, RiskLevel, RoadState,
    RunStage, RunStatus,
)
from .errors import ContractError, FieldError


class Provenance(ContractModel):
    source_type: Literal["SYNTHETIC"] = "SYNTHETIC"
    source_name: Literal["CampMate Synthetic Demo Dataset v1", "CampMate Synthetic Demo Dataset v2"] = "CampMate Synthetic Demo Dataset v1"
    source_date: Literal["2026-10-07"] = "2026-10-07"
    demo_only: Literal[True] = True

    @field_validator("demo_only", mode="before")
    @classmethod
    def true_only(cls, value):
        if value is not True:
            raise ValueError("demo_only must be the boolean true")
        return value


class DemoContext(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    mode: ExecutionMode
    demo_today: date
    dataset_version: str = "v1"


class DatasetContext(ContractModel):
    dataset_version: str
    file_digests: dict[str, str]
    fixture_digests: dict[str, str] = Field(default_factory=dict)
    selection_config: dict[str, str] = Field(default_factory=dict)
    rules_version: str


class SourceRef(ContractModel):
    dataset_file: str
    record_id: Identifier
    provenance: Provenance = Field(default_factory=Provenance)
    valid_from: date | None = None
    valid_to: date | None = None


class EquipmentItem(ContractModel):
    item_key: str
    label: str
    quantity: NonNegativeInt | None = None
    unit: str
    capacity_persons: PositiveInt | None = None
    confirmed: bool


class Transport(ContractModel):
    transport_type: str | None = None
    vehicle_count: PositiveInt | None = None
    estimated_km: Quantity | None = None
    assumptions: list[str] = Field(default_factory=list)


class ProfileSnapshot(ContractModel):
    profile_id: Identifier | None = None
    group_size: PositiveInt | None = None
    experience_level: str | None = None
    has_children: bool | None = None
    children_count: NonNegativeInt | None = None
    equipment: list[EquipmentItem] = Field(default_factory=list)
    transport: Transport = Field(default_factory=Transport)
    accessibility_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def children_consistent(self):
        if self.children_count is not None:
            if self.group_size is not None and self.children_count > self.group_size:
                raise ValueError("children_count cannot exceed group_size")
            if self.has_children is False and self.children_count > 0:
                raise ValueError("children_count conflicts with has_children")
        return self


class TripRequirements(ContractModel):
    destination: str | None = None
    start_date: date | None = None
    duration_nights: PositiveInt | None = None
    end_date: date | None = None
    duration_days: PositiveInt | None = None
    budget_cents: PositiveInt | None = None
    currency: Literal["AUD"] = "AUD"
    preferences: list[str] = Field(default_factory=list)
    mandatory_constraints: list[str] = Field(default_factory=list)


class ConfirmedRequirements(TripRequirements):
    destination: str = Field(min_length=1)
    start_date: date
    duration_nights: PositiveInt
    end_date: date
    duration_days: PositiveInt
    budget_cents: PositiveInt

    @model_validator(mode="after")
    def validate_dates(self):
        if not self.destination.strip():
            raise ValueError("destination must not be blank")
        if self.end_date != self.start_date + timedelta(days=self.duration_nights):
            raise ValueError("end_date conflicts with duration_nights")
        if self.duration_days != self.duration_nights + 1:
            raise ValueError("duration_days must equal duration_nights + 1")
        return self


class Clarification(ContractModel):
    field: str
    question: str
    reason: str


class Artifact(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    execution_mode: ExecutionMode
    source_refs: list[SourceRef] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class InterpretRequestInput(ContractModel):
    raw_text: str = Field(min_length=1, max_length=8000)
    profile_snapshot: ProfileSnapshot | None = None
    explicit_fields: TripRequirements = Field(default_factory=TripRequirements)
    demo_context: DemoContext

    @model_validator(mode="after")
    def nonblank_text(self):
        if not self.raw_text.strip():
            raise ValueError("raw_text must not be blank")
        return self


class InterpretRequestResult(Artifact):
    extracted_requirements: TripRequirements
    clarifications: list[Clarification] = Field(default_factory=list)
    field_errors: list[FieldError] = Field(default_factory=list)


class RecommendCampsitesInput(ContractModel):
    confirmed_requirements: ConfirmedRequirements
    profile_snapshot: ProfileSnapshot
    demo_context: DemoContext


class CampsiteCandidate(ContractModel):
    campsite_id: Identifier
    rank: PositiveInt
    reasons: list[str]
    material_uncertainties: list[str] = Field(default_factory=list)


class ExcludedCandidate(ContractModel):
    campsite_id: Identifier
    reasons: list[str]


class RecommendCampsitesResult(Artifact):
    search_outcome: Literal["MATCHES", "NO_MATCH"]
    candidates: list[CampsiteCandidate]
    excluded_candidates: list[ExcludedCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def candidates_match_outcome(self):
        if (self.search_outcome == "MATCHES") != bool(self.candidates):
            raise ValueError("search_outcome is inconsistent with candidates")
        return self


class VersionContext(ContractModel):
    plan_id: Identifier
    plan_version_id: Identifier
    run_id: Identifier
    input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ItineraryEntry(ContractModel):
    entry_kind: Literal["TRAVEL", "CAMP", "ACTIVITY"]
    start_at: datetime
    end_at: datetime
    campsite_id: Identifier | None = None
    description: str

    @model_validator(mode="after")
    def validate_interval(self):
        if self.start_at.utcoffset() is None or self.end_at.utcoffset() is None:
            raise ValueError("itinerary timestamps must include a timezone")
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.entry_kind == "CAMP" and self.campsite_id is None:
            raise ValueError("CAMP entries require campsite_id")
        return self


class ItineraryResult(Artifact):
    itinerary_entries: list[ItineraryEntry]
    selected_campsite_ids: list[Identifier]
    revision_reason: str
    requested_requirement_changes: TripRequirements | None = None


class StoredVersion(ContractModel):
    version_context: VersionContext
    version_number: PositiveInt
    content: ItineraryResult
    status: PlanVersionStatus
    revision: NonNegativeInt


class ItineraryInput(ContractModel):
    confirmed_requirements: ConfirmedRequirements
    profile_snapshot: ProfileSnapshot
    recommendations: RecommendCampsitesResult
    previous_version: StoredVersion | None = None
    feedback: str | None = None
    demo_context: DemoContext


class Blocker(ContractModel):
    code: str
    message: str
    source_refs: list[SourceRef] = Field(default_factory=list)


class GearItem(ContractModel):
    item_key: str
    required_quantity: Quantity | None
    available_quantity: Quantity | None
    missing_quantity: Quantity | None
    unit: str
    capacity_requirement: PositiveInt | None = None
    arrangement_status: Literal["OWNED", "CONFIRMED_RENTAL", "UNCONFIRMED", "MISSING"]
    essential: bool


class CostLine(ContractModel):
    category: Literal["CAMPSITE", "TRANSPORT", "FOOD", "WATER", "ADDITIONAL_GEAR"]
    item_key: str
    quantity: Quantity | None
    unit: str
    unit_price_cents: MoneyCents | None
    subtotal_cents: MoneyCents | None
    source_ref: SourceRef | None
    assumption: str | None = None

    @model_validator(mode="after")
    def validate_subtotal(self):
        expected = None
        if self.quantity is not None and self.unit_price_cents is not None:
            expected = int((self.quantity * Decimal(self.unit_price_cents)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ))
        if self.subtotal_cents != expected:
            raise ValueError("subtotal_cents must match ROUND_HALF_UP(quantity * unit_price_cents)")
        return self


class LogisticsInput(ContractModel):
    version_context: VersionContext
    saved_itinerary: ItineraryResult
    confirmed_requirements: ConfirmedRequirements
    profile_snapshot: ProfileSnapshot
    demo_context: DemoContext


class LogisticsResult(Artifact):
    version_context: VersionContext
    gear_checklist: list[GearItem]
    transport_feasible: bool | None
    cost_breakdown: list[CostLine]
    total_cents: MoneyCents | None
    known_subtotal_cents: MoneyCents
    budget_difference_cents: StrictInt | None
    outcome: AssessmentOutcome
    mandatory_blockers: list[Blocker] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_totals(self):
        known = sum(line.subtotal_cents or 0 for line in self.cost_breakdown)
        if self.known_subtotal_cents != known:
            raise ValueError("known_subtotal_cents must equal known line amounts")
        incomplete = not self.cost_breakdown or any(line.subtotal_cents is None for line in self.cost_breakdown)
        if incomplete and self.total_cents is not None:
            raise ValueError("incomplete costs require total_cents=null")
        if not incomplete and self.total_cents != known:
            raise ValueError("total_cents must equal rounded line amounts")
        if self.total_cents is None and self.budget_difference_cents is not None:
            raise ValueError("unknown total requires unknown budget difference")
        if self.outcome == AssessmentOutcome.PASSED:
            if self.mandatory_blockers or self.clarifications or self.transport_feasible is not True or self.total_cents is None:
                raise ValueError("PASSED cannot contain blockers or incomplete logistics")
            if any(item.essential and (item.missing_quantity is None or item.missing_quantity > 0 or item.arrangement_status not in {"OWNED", "CONFIRMED_RENTAL"}) for item in self.gear_checklist):
                raise ValueError("essential gear must be resolved before PASSED")
        return self


class Evidence(ContractModel):
    kind: Literal["WEATHER", "FIRE", "ROAD", "RESTRICTION"]
    summary: str | None
    source_date: date | None
    status: DataQuality
    valid_from: date | None
    valid_to: date | None
    road_state: RoadState | None = None
    source_refs: list[SourceRef]

    @model_validator(mode="after")
    def validate_range(self):
        if self.valid_from is not None and self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("evidence valid_to must not precede valid_from")
        return self


class SafetyResult(Artifact):
    version_context: VersionContext
    depends_on_assessment_id: Identifier
    risk_level: RiskLevel
    confidence: Confidence
    data_quality: dict[str, DataQuality]
    evidence: list[Evidence]
    hazards: list[str]
    mandatory_blockers: list[Blocker]
    recommended_actions: list[str]
    outcome: AssessmentOutcome
    requires_human_review: bool
    unresolved_conflicts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_passed(self):
        review_trigger = self.risk_level in {RiskLevel.HIGH, RiskLevel.UNKNOWN} or self.confidence in {Confidence.LOW, Confidence.UNKNOWN} or bool(self.unresolved_conflicts)
        if review_trigger and not self.requires_human_review:
            raise ValueError("risk, low/unknown confidence or conflict requires human review")
        if self.outcome == AssessmentOutcome.PASSED:
            invalid_evidence = not self.evidence or any(
                item.status != DataQuality.AVAILABLE or item.valid_from is None or item.valid_to is None
                for item in self.evidence
            )
            if self.mandatory_blockers or self.requires_human_review or not self.data_quality or any(value != DataQuality.AVAILABLE for value in self.data_quality.values()) or invalid_evidence:
                raise ValueError("PASSED requires complete evidence and no blockers or pending review")
        return self


class StoredAssessment(ContractModel):
    assessment_id: Identifier
    version_context: VersionContext
    kind: AssessmentKind
    result: LogisticsResult | SafetyResult
    gear_checklist_id: Identifier | None
    depends_on_assessment_id: Identifier | None

    @model_validator(mode="after")
    def validate_association(self):
        if self.result.version_context != self.version_context:
            raise ValueError("assessment and result contexts must match")
        if self.kind == AssessmentKind.LOGISTICS:
            if not isinstance(self.result, LogisticsResult) or self.gear_checklist_id is None or self.depends_on_assessment_id is not None:
                raise ValueError("LOGISTICS requires its saved checklist and no assessment dependency")
        elif not isinstance(self.result, SafetyResult) or self.depends_on_assessment_id != self.result.depends_on_assessment_id:
            raise ValueError("SAFETY must reference the logistics assessment it used")
        return self


class ScenarioContext(ContractModel):
    scenario_id: Identifier
    campsite_ids: list[Identifier]
    valid_from: date | None
    valid_to: date | None
    evidence: list[Evidence]
    template_id: Identifier | None = None


class SafetyInput(ContractModel):
    version_context: VersionContext
    saved_itinerary: ItineraryResult
    confirmed_requirements: ConfirmedRequirements
    saved_logistics_assessment: StoredAssessment
    scenario_context: ScenarioContext
    demo_context: DemoContext

    @model_validator(mode="after")
    def validate_logistics_context(self):
        if self.saved_logistics_assessment.kind != AssessmentKind.LOGISTICS or self.saved_logistics_assessment.version_context != self.version_context:
            raise ValueError("safety must use saved logistics from the same version and run")
        return self


class ConfirmedContext(ContractModel):
    request_id: Identifier
    confirmed_at: datetime
    requirements: ConfirmedRequirements
    profile_snapshot: ProfileSnapshot
    demo_context: DemoContext
    dataset_context: DatasetContext

    @model_validator(mode="after")
    def validate_confirmation(self):
        if self.confirmed_at.utcoffset() is None or self.profile_snapshot.group_size is None:
            raise ValueError("confirmed context requires a timestamp and known group size")
        return self


class RunScope(ContractModel):
    command_id: Identifier
    run_id: Identifier
    plan_id: Identifier
    request_id: Identifier
    operation: Literal["PLAN", "REVISE", "REASSESS"]
    expected_current_version_id: Identifier | None
    demo_context: DemoContext
    dataset_context: DatasetContext
    write_keys: dict[str, str]


class OrchestrateInput(ContractModel):
    run_scope: RunScope
    confirmed_context: ConfirmedContext
    previous_version: StoredVersion | None = None


class RunResult(ContractModel):
    run_id: Identifier
    execution_mode: ExecutionMode
    run_status: RunStatus
    stage: RunStage
    artifact_refs: dict[str, str] = Field(default_factory=dict)
    route: PlanVersionStatus | None = None
    blockers: list[Blocker] = Field(default_factory=list)
    error: ContractError | None = None


class RunSnapshot(RunResult):
    revision: NonNegativeInt


class StoredRecommendations(ContractModel):
    recommendation_id: Identifier
    request_id: Identifier
    run_id: Identifier
    result: RecommendCampsitesResult


class ValidReview(ContractModel):
    review_id: Identifier
    version_context: VersionContext
    assessment_ids: list[Identifier]
    reviewer_user_id: Identifier
    decision: ReviewDecision
    reason: str = Field(min_length=1)


class Eligibility(ContractModel):
    eligible: bool
    current_version_id: Identifier
    active_run_id: Identifier
    blocking_reasons: list[Blocker]
    review_required: bool
    valid_review_id: Identifier | None
    allowed_actions: list[AllowedAction]


class RouteResult(ContractModel):
    version_context: VersionContext
    status: PlanVersionStatus
    eligibility: Eligibility
