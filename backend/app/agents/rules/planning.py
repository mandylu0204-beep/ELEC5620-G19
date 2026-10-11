from datetime import datetime, time, timedelta

from ...contracts.dto import (
    CampsiteCandidate, ExcludedCandidate, ItineraryEntry, ItineraryResult,
    RecommendCampsitesResult, TripRequirements,
)
from .common import REST_DESCRIPTION, TRIP_ZONE, artifact, camp_description, input_failure, validate_itinerary

HARD_FEATURES = {
    'toilets': 'toilets', 'potable_water': 'potable_water', 'showers': 'showers',
    'fire_allowed': 'fire_allowed', 'campfire': 'fire_allowed', 'pets_allowed': 'pets_allowed',
    'wheelchair_accessible': 'wheelchair_accessible', 'vehicle_access': 'vehicle_access',
    'public_transport_access': 'public_transport_access',
}
SOFT_FEATURES = {
    'toilets': 'toilets', 'showers': 'showers', 'potable water': 'potable_water',
    'public transport': 'public_transport_access', 'wheelchair accessible': 'wheelchair_accessible',
    'campfire': 'fire_allowed', 'pets': 'pets_allowed',
}


def _season(day):
    return ('summer' if day.month in {12, 1, 2} else 'autumn' if day.month in {3, 4, 5} else 'winter' if day.month in {6, 7, 8} else 'spring')


def validate_constraints(requirements):
    for constraint in requirements.mandatory_constraints:
        if constraint not in HARD_FEATURES and constraint not in {'no_fires', 'walk_in_only'}:
            raise input_failure(f'Unsupported hard constraint: {constraint}.', 'mandatory_constraints')
    if 'no_fires' in requirements.mandatory_constraints and any(item in requirements.mandatory_constraints for item in ('campfire', 'fire_allowed')):
        raise input_failure('Mandatory fire and no-fire requirements conflict.', 'mandatory_constraints')


def violations(campsite, requirements, profile, *, include_budget=True):
    reasons = []
    if campsite.region != requirements.destination:
        reasons.append('Destination does not match.')
    if profile.group_size is None:
        raise input_failure('Known group size is required.', 'profile.group_size')
    if campsite.max_group_size is None or campsite.max_group_size < profile.group_size:
        reasons.append('Group capacity is insufficient or unknown.')
    seasons = {_season(requirements.start_date + timedelta(days=offset)) for offset in range(requirements.duration_nights)}
    if 'all' not in campsite.supported_seasons and not seasons.issubset(campsite.supported_seasons):
        reasons.append('Trip season is unsupported or unknown.')
    if profile.transport.transport_type == 'CAR' and campsite.vehicle_access is not True:
        reasons.append('Vehicle access is unavailable or unknown.')
    if profile.transport.transport_type == 'PUBLIC_TRANSPORT' and campsite.public_transport_access is not True:
        reasons.append('Public transport access is unavailable or unknown.')
    for requirement in profile.accessibility_requirements:
        normalized = requirement.strip().casefold()
        supported = {
            'wheelchair-accessible toilet': campsite.wheelchair_accessible is True and campsite.toilets is True,
            'step-free path': campsite.wheelchair_accessible is True and 'accessible path' in campsite.facilities,
            'wheelchair access': campsite.wheelchair_accessible is True,
        }
        if supported.get(normalized) is not True:
            reasons.append(f'Accessible requirement {requirement!r} is unavailable or unverified.')
    for constraint in requirements.mandatory_constraints:
        feature = HARD_FEATURES.get(constraint)
        if feature and getattr(campsite, feature) is not True:
            reasons.append(f'Mandatory feature {constraint} is unavailable or unknown.')
        if constraint == 'walk_in_only' and campsite.vehicle_access is not False:
            reasons.append('Walk-in-only access is not established.')
    if include_budget and campsite.nightly_fee_cents is not None and campsite.nightly_fee_cents * requirements.duration_nights > requirements.budget_cents:
        reasons.append('Campsite fee alone exceeds the confirmed group budget.')
    return reasons


def recommend(dataset, input) -> RecommendCampsitesResult:
    requirements, profile = input.confirmed_requirements, input.profile_snapshot
    validate_constraints(requirements)
    ranked, excluded, sources = [], [], []
    for campsite in dataset.campsites:
        sources.append(campsite.source_ref)
        reasons = violations(campsite, requirements, profile)
        if reasons:
            excluded.append(ExcludedCandidate(campsite_id=campsite.campsite_id, reasons=reasons))
            continue
        score, matches, uncertainties = 0, ['Registered synthetic region, capacity and known hard constraints match.'], []
        for preference in requirements.preferences:
            normalized = preference.strip().casefold()
            feature = SOFT_FEATURES.get(normalized)
            if feature and getattr(campsite, feature) is True:
                score += 1
                matches.append(f'Soft preference {preference} matches source facilities.')
            elif normalized == 'quiet':
                if any('quiet hours' in restriction.casefold() for restriction in campsite.mandatory_restrictions):
                    score += 1
                    matches.append('Source lists a quiet-hours policy, not a quietness guarantee.')
                uncertainties.append('Actual quietness is not supplied.')
            elif feature is None and normalized not in {'ready-to-eat meals', 'ready_to_eat', 'self-catered meals', 'self_catered'}:
                uncertainties.append(f'Preference {preference!r} has no verified source mapping.')
        if campsite.nightly_fee_cents is None:
            uncertainties.append('Campsite fee is unknown.')
        if profile.transport.transport_type is None:
            uncertainties.append('Transport type is not confirmed.')
        uncertainties.append('Recommendation is not booking availability or safety clearance.')
        ranked.append(((-score, campsite.nightly_fee_cents is None, campsite.nightly_fee_cents or 0, campsite.campsite_id), campsite, matches, uncertainties))
    ranked.sort(key=lambda item: item[0])
    candidates = [CampsiteCandidate(campsite_id=campsite.campsite_id, rank=rank, reasons=reasons, material_uncertainties=uncertainties) for rank, (_, campsite, reasons, uncertainties) in enumerate(ranked, 1)]
    return RecommendCampsitesResult(
        search_outcome='MATCHES' if candidates else 'NO_MATCH', candidates=candidates,
        excluded_candidates=excluded,
        **artifact(input.demo_context, sources, assumptions=['Soft-match count, known nightly fee, then campsite ID determine stable ranking.']),
    )


def itinerary(dataset, input) -> ItineraryResult:
    requirements, profile = input.confirmed_requirements, input.profile_snapshot
    validate_constraints(requirements)
    candidates = input.recommendations.candidates
    if input.recommendations.execution_mode != input.demo_context.mode or not candidates:
        raise input_failure('Matching deterministic recommendations are required.', 'recommendations')
    if len({item.campsite_id for item in candidates}) != len(candidates) or len({item.rank for item in candidates}) != len(candidates):
        raise input_failure('Recommendation IDs and ranks must be unique.', 'recommendations')
    viable = [item for item in candidates if not violations(dataset.get_campsite(item.campsite_id), requirements, profile)]
    if not viable:
        raise input_failure('No supplied candidate satisfies the confirmed hard constraints.', 'recommendations')
    viable.sort(key=lambda item: (item.rank, item.campsite_id))
    feedback = (input.feedback or '').strip().casefold()
    changes = None
    if input.previous_version is not None:
        validate_itinerary(dataset, input.previous_version.content, requirements)
    if feedback:
        if feedback in {'cheaper campsite', 'change campsite', 'lower campsite fee'}:
            if input.previous_version is None:
                raise input_failure('Campsite revision requires a previous version.', 'previous_version')
            previous_ids = set(input.previous_version.content.selected_campsite_ids)
            alternatives = [item for item in viable if item.campsite_id not in previous_ids]
            if feedback != 'change campsite':
                previous_prices = [dataset.get_campsite(key).nightly_fee_cents for key in previous_ids]
                if any(price is None for price in previous_prices):
                    raise input_failure('Previous campsite price is unknown; cannot promise a cheaper revision.', 'feedback')
                alternatives = [item for item in alternatives if dataset.get_campsite(item.campsite_id).nightly_fee_cents is not None and dataset.get_campsite(item.campsite_id).nightly_fee_cents < min(previous_prices)]
                alternatives.sort(key=lambda item: (dataset.get_campsite(item.campsite_id).nightly_fee_cents, item.rank, item.campsite_id))
            if not alternatives:
                raise input_failure('No valid requested alternative exists; adjust and reconfirm requirements.', 'feedback')
            viable = alternatives
        elif feedback in {'remove campfire', 'no campfire'}:
            changes = TripRequirements(
                preferences=[item for item in requirements.preferences if item.strip().casefold() != 'campfire'],
                mandatory_constraints=list(dict.fromkeys([*(item for item in requirements.mandatory_constraints if item not in {'campfire', 'fire_allowed'}), 'no_fires'])),
            )
        else:
            raise input_failure('Unsupported revision feedback; use structured, reconfirmed requirements.', 'feedback')
    campsite = dataset.get_campsite(viable[0].campsite_id)
    entries = []
    for offset in range(requirements.duration_nights):
        day = requirements.start_date + timedelta(days=offset)
        start = datetime.combine(day, time(12 if offset == 0 else 17), TRIP_ZONE)
        end = datetime.combine(day + timedelta(days=1), time(10 if offset == requirements.duration_nights - 1 else 8), TRIP_ZONE)
        entries.append(ItineraryEntry(entry_kind='CAMP', start_at=start, end_at=end, campsite_id=campsite.campsite_id, description=camp_description(campsite)))
        if offset < requirements.duration_nights - 1:
            entries.append(ItineraryEntry(entry_kind='ACTIVITY', start_at=end, end_at=datetime.combine(day + timedelta(days=1), time(17), TRIP_ZONE), campsite_id=campsite.campsite_id, description=REST_DESCRIPTION))
    result = ItineraryResult(
        itinerary_entries=entries, selected_campsite_ids=[campsite.campsite_id],
        revision_reason=input.feedback or ('Deterministic draft revision.' if input.previous_version else 'Initial deterministic draft.'),
        requested_requirement_changes=changes,
        **artifact(input.demo_context, [campsite.source_ref],
                   assumptions=['Sydney-local draft times are placeholders, not verified check-in or travel times.'],
                   uncertainties=['Transport, supplies, booking and safety still require assessment.', *(['Proposed preference changes require user confirmation before execution.'] if changes else [])]),
    )
    validate_itinerary(dataset, result, requirements)
    return result
