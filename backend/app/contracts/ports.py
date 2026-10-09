from typing import Protocol, runtime_checkable

from .dto import (
    ConfirmedContext, Eligibility, InterpretRequestInput, InterpretRequestResult,
    ItineraryInput, ItineraryResult, LogisticsInput, LogisticsResult, OrchestrateInput,
    RecommendCampsitesInput, RecommendCampsitesResult, RouteResult, RunResult,
    RunSnapshot, SafetyInput, SafetyResult, StoredAssessment, StoredRecommendations,
    StoredVersion, ValidReview, VersionContext,
)
from .enums import AssessmentKind, PlanVersionStatus, RunStage, RunStatus
from .errors import ContractError


@runtime_checkable
class PersistencePort(Protocol):
    """A's SqlitePersistencePort binds an authorized, server-registered RunScope."""

    async def load_confirmed_context(self) -> ConfirmedContext: ...

    async def save_recommendations(self, result: RecommendCampsitesResult, write_key: str) -> StoredRecommendations: ...

    async def append_plan_version(self, expected_current_version_id: str | None, content: ItineraryResult, request_id: str, reason: str, write_key: str) -> StoredVersion: ...

    async def save_assessment(self, context: VersionContext, kind: AssessmentKind, result: LogisticsResult | SafetyResult, write_key: str) -> StoredAssessment: ...

    async def report_stage(self, stage: RunStage, status: RunStatus, error: ContractError | None) -> RunSnapshot: ...

    async def route_assessed_version(self, context: VersionContext, proposed_route: PlanVersionStatus, reason: str, write_key: str) -> RouteResult: ...

    async def load_review_result(self, context: VersionContext, assessment_ids: list[str]) -> ValidReview | None: ...

    async def evaluate_eligibility(self, context: VersionContext) -> Eligibility: ...


@runtime_checkable
class AgentPort(Protocol):
    """B implements these six entries; no implementation is selected implicitly."""

    async def interpret_request(self, input: InterpretRequestInput) -> InterpretRequestResult: ...

    async def recommend_campsites(self, input: RecommendCampsitesInput) -> RecommendCampsitesResult: ...

    async def generate_or_revise_itinerary(self, input: ItineraryInput) -> ItineraryResult: ...

    async def assess_gear_and_logistics(self, input: LogisticsInput) -> LogisticsResult: ...

    async def assess_safety(self, input: SafetyInput) -> SafetyResult: ...

    async def orchestrate(self, input: OrchestrateInput, persistence: PersistencePort) -> RunResult: ...
