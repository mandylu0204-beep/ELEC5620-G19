from datetime import timedelta
from zoneinfo import ZoneInfo

from ...adapters import SyntheticDataset
from ...contracts.base import DEMO_DISCLAIMER
from ...contracts.dto import DemoContext, ItineraryResult, SourceRef
from ...contracts.enums import AllowedAction, ErrorCode, ExecutionMode
from ...contracts.errors import ContractError, ContractFailure

RULES_VERSION = 'b02-v1-rules-1'
TRIP_ZONE = ZoneInfo('Australia/Sydney')
REST_DESCRIPTION = 'Uncommitted rest period at campsite; no travel time or activity availability inferred.'


def camp_description(campsite) -> str:
    return f'Synthetic overnight stay at {campsite.name}; no booking implied.'


def input_failure(message: str, field: str = '') -> ContractFailure:
    return ContractFailure(ContractError(
        code=ErrorCode.INPUT_INVALID, message=message,
        allowed_actions=[AllowedAction.EDIT_INPUT], context={'field': field} if field else {},
    ))


def rule_failure(message: str, field: str) -> ContractFailure:
    return ContractFailure(ContractError(
        code=ErrorCode.ADAPTER_FAILURE, message=message,
        allowed_actions=[AllowedAction.CONTACT_OPERATOR], context={'field': field},
    ))


def ensure_demo(dataset: SyntheticDataset, demo: DemoContext) -> None:
    if demo.mode != ExecutionMode.DETERMINISTIC_DEMO:
        raise ContractFailure(ContractError(
            code=ErrorCode.AGENT_FAILURE,
            message='RuleAgent only implements deterministic_demo, not stub or an LLM agent.',
            allowed_actions=[AllowedAction.CONTACT_OPERATOR],
        ))
    if demo.dataset_version != dataset.context.dataset_version:
        raise ContractFailure(ContractError(
            code=ErrorCode.STALE_CONTEXT, message='RuleAgent and DemoContext dataset versions differ.',
            allowed_actions=[AllowedAction.REFRESH],
        ))


def unique_sources(sources: list[SourceRef]) -> list[SourceRef]:
    result, seen = [], set()
    for source in sources:
        identity = source.model_dump_json()
        if identity not in seen:
            result.append(source)
            seen.add(identity)
    return result


def artifact(demo: DemoContext, sources=(), assumptions=(), uncertainties=()) -> dict:
    return {
        'execution_mode': demo.mode, 'source_refs': unique_sources(list(sources)),
        'assumptions': [DEMO_DISCLAIMER, *assumptions], 'uncertainties': list(uncertainties),
    }


def validate_itinerary(dataset: SyntheticDataset, itinerary: ItineraryResult, requirements) -> dict[str, int]:
    """Count occupied nights, rejecting overlaps, wrong dates and unbound camps."""
    if itinerary.execution_mode != ExecutionMode.DETERMINISTIC_DEMO:
        raise input_failure('Itinerary must come from deterministic_demo.', 'saved_itinerary')
    selected = itinerary.selected_campsite_ids
    if not selected or len(selected) != len(set(selected)):
        raise input_failure('Selected campsite IDs must be nonempty and unique.', 'selected_campsite_ids')
    for campsite_id in selected:
        dataset.get_campsite(campsite_id)
    entries = itinerary.itinerary_entries
    if not entries:
        raise input_failure('Itinerary entries are missing.', 'itinerary_entries')
    ordered = sorted(entries, key=lambda entry: entry.start_at)
    if entries != ordered or any(left.end_at > right.start_at for left, right in zip(entries, entries[1:])):
        raise input_failure('Itinerary must be ordered and nonoverlapping.', 'itinerary_entries')
    occupied = {}
    for entry in entries:
        start = entry.start_at.astimezone(TRIP_ZONE)
        end = entry.end_at.astimezone(TRIP_ZONE)
        if start.date() < requirements.start_date or end.date() > requirements.end_date:
            raise input_failure('Itinerary lies outside confirmed trip dates.', 'itinerary_entries')
        if entry.campsite_id is not None and entry.campsite_id not in selected:
            raise input_failure('An entry references an unselected campsite.', 'itinerary_entries')
        if entry.entry_kind == 'CAMP':
            day = start.date()
            while day < end.date():
                if day in occupied:
                    raise input_failure('A trip night is allocated twice.', 'itinerary_entries')
                occupied[day] = entry.campsite_id
                day += timedelta(days=1)
    expected = {requirements.start_date + timedelta(days=offset) for offset in range(requirements.duration_nights)}
    if set(occupied) != expected or set(occupied.values()) != set(selected):
        raise input_failure('CAMP entries must cover every confirmed night and selected campsite.', 'itinerary_entries')
    return {campsite_id: list(occupied.values()).count(campsite_id) for campsite_id in selected}


def meal_mode(requirements) -> str | None:
    preferences = {item.strip().casefold() for item in requirements.preferences}
    ready = bool(preferences & {'ready-to-eat meals', 'ready_to_eat'})
    self_catered = bool(preferences & {'self-catered meals', 'self_catered'})
    if ready and self_catered:
        return None
    return 'READY_TO_EAT' if ready else 'SELF_CATERED' if self_catered else None
