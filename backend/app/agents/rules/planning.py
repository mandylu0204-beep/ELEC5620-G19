from datetime import datetime, time, timedelta
from decimal import Decimal

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


def vehicle_arrival_supported(campsite):
    # A road-accessible carpark with a documented walk is not a drive-in
    # campsite. Explicit vehicle_access hard constraints still require True.
    return campsite.vehicle_access is True or (
        campsite.walk_in_only is True
        and 'carpark with signed walking access to campsites' in campsite.facilities)


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
    if profile.transport.transport_type == 'CAR' and not vehicle_arrival_supported(campsite):
        reasons.append('Vehicle access is unavailable or unknown.')
    if profile.transport.transport_type == 'PUBLIC_TRANSPORT' and campsite.public_transport_access is not True:
        reasons.append('Public transport access is unavailable or unknown.')
    for requirement in profile.accessibility_requirements:
        normalized = requirement.strip().casefold()
        # Legacy facilities are a fallback only when the explicit attribute is
        # absent; they must never override a confirmed False value.
        supported = {
            'wheelchair-accessible toilet': campsite.wheelchair_accessible is True and campsite.toilets is True,
            'step-free path': (campsite.wheelchair_accessible is True and 'accessible path' in campsite.facilities)
                if campsite.step_free_path is None else campsite.step_free_path,
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
        if getattr(dataset, 'planning_reference', None) is not None:
            matches = [fact['text'] for fact in match_facts(campsite, requirements, profile)]
        for preference in requirements.preferences:
            normalized = preference.strip().casefold()
            feature = SOFT_FEATURES.get(normalized)
            if feature and getattr(campsite, feature) is True:
                score += 1
                matches.append(f'Soft preference {preference} matches source facilities.')
            elif normalized == 'quiet':
                if campsite.quiet_environment is True:
                    score += 1
                    matches.append('Synthetic quiet-environment attribute matches; it is not a real-world guarantee.')
                elif campsite.quiet_environment is None and any('quiet hours' in restriction.casefold() for restriction in campsite.mandatory_restrictions):
                    score += 1
                    matches.append('Source lists a quiet-hours policy, not a quietness guarantee.')
                if campsite.quiet_environment is not True:
                    uncertainties.append('Actual quietness is not supplied.')
            elif feature is None and normalized not in {'ready-to-eat meals', 'ready_to_eat', 'self-catered meals', 'self_catered'}:
                uncertainties.append(f'Preference {preference!r} has no verified source mapping.')
        if campsite.nightly_fee_cents is None:
            uncertainties.append('Campsite fee is unknown.')
        if profile.transport.transport_type is None:
            uncertainties.append('Transport type is not confirmed.')
        if getattr(dataset, 'planning_reference', None) is not None:
            from ...adapters.planning_reference import available_activities
            if not available_activities(dataset, campsite.campsite_id, requirements):
                uncertainties.append('这处营地在本次日期暂无适用的活动资料；仅提供住宿与休息草稿，不编造活动。')
        uncertainties.append('Recommendation is not booking availability or safety clearance.')
        ranked.append(((-score, campsite.nightly_fee_cents is None, campsite.nightly_fee_cents or 0, campsite.campsite_id), campsite, matches, uncertainties))
    ranked.sort(key=lambda item: item[0])
    candidates = [CampsiteCandidate(campsite_id=campsite.campsite_id, rank=rank, reasons=reasons, material_uncertainties=uncertainties) for rank, (_, campsite, reasons, uncertainties) in enumerate(ranked, 1)]
    return RecommendCampsitesResult(
        search_outcome='MATCHES' if candidates else 'NO_MATCH', candidates=candidates,
        excluded_candidates=excluded,
        **artifact(input.demo_context, sources, assumptions=[
            'Soft-match count, known nightly fee, then campsite ID determine stable ranking.',
            *(['v2 quiet and step-free fields are synthetic demo assumptions, not real-world verification.'] if dataset.has_v2_policy else []),
        ]),
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
    entries = camp_entries(campsite, requirements)
    from ...adapters.planning_reference import available_activities, daily_entries
    activities = available_activities(dataset, campsite.campsite_id, requirements)
    activity_refs = []
    if activities:
        from types import SimpleNamespace
        choices = [SimpleNamespace(date=requirements.start_date + timedelta(days=i),
            activity_id=activities[i % len(activities)].activity_id) for i in range(requirements.duration_nights)]
        entries, activity_refs = daily_entries(dataset, campsite, requirements, choices)
    result = ItineraryResult(
        itinerary_entries=entries, selected_campsite_ids=[campsite.campsite_id],
        revision_reason=input.feedback or ('Deterministic draft revision.' if input.previous_version else 'Initial deterministic draft.'),
        requested_requirement_changes=changes,
        **artifact(input.demo_context, [campsite.source_ref, *activity_refs],
                   assumptions=['Sydney-local draft times are placeholders, not verified check-in or travel times.'],
                   uncertainties=['Transport, supplies, booking and safety still require assessment.', *(['Proposed preference changes require user confirmation before execution.'] if changes else [])]),
    )
    validate_itinerary(dataset, result, requirements)
    return result


def camp_entries(campsite, requirements):
    """Conservative common renderer: no invented bookings, activities or travel."""
    entries = []
    for offset in range(requirements.duration_nights):
        day = requirements.start_date + timedelta(days=offset)
        start = datetime.combine(day, time(12 if offset == 0 else 17), TRIP_ZONE)
        end = datetime.combine(day + timedelta(days=1), time(10 if offset == requirements.duration_nights - 1 else 8), TRIP_ZONE)
        entries.append(ItineraryEntry(entry_kind='CAMP', start_at=start, end_at=end, campsite_id=campsite.campsite_id, description=camp_description(campsite)))
        if offset < requirements.duration_nights - 1:
            entries.append(ItineraryEntry(entry_kind='ACTIVITY', start_at=end, end_at=datetime.combine(day + timedelta(days=1), time(17), TRIP_ZONE), campsite_id=campsite.campsite_id, description=REST_DESCRIPTION))
    return entries


def match_facts(campsite, requirements, profile):
    """Host facts from the same confirmed input; never model-authored proof."""
    facts = []
    def add(code, expected, actual, text):
        facts.append({'code': code, 'expected': expected, 'actual': actual,
            'text': text, 'source_ref': campsite.source_ref.model_dump(mode='json')})
    add('REGION', requirements.destination, campsite.region, f'目的地区域：{campsite.region}，与本次选择一致。')
    add('GROUP_CAPACITY', profile.group_size, campsite.max_group_size,
        f'同行人数：本次 {profile.group_size} 人，登记人数上限 {campsite.max_group_size} 人。')
    mode = profile.transport.transport_type
    if mode == 'PUBLIC_TRANSPORT':
        add('TRANSPORT', mode, campsite.public_transport_access,
            '交通：资料登记支持公共交通抵达；实际往返班次及最后接驳仍需确认。')
    elif mode == 'CAR':
        add('TRANSPORT', mode, vehicle_arrival_supported(campsite),
            '交通：资料登记支持车辆抵达。' if campsite.vehicle_access is True
            else '交通：可驾车抵达停车处，之后需搬运装备步行进入营位；车辆不能直接进入营位。')
    fields = {**{key:value for key,value in HARD_FEATURES.items()}, 'step-free path':'step_free_path',
        'wheelchair access':'wheelchair_accessible', 'wheelchair-accessible toilet':'wheelchair_accessible'}
    names = {'toilets':'厕所','showers':'淋浴','potable_water':'饮用水','fire_allowed':'用火',
        'pets_allowed':'宠物同行','wheelchair_accessible':'无障碍设施','step_free_path':'无台阶通道',
        'vehicle_access':'车辆进入营地','public_transport_access':'公共交通抵达'}
    for condition in [*requirements.mandatory_constraints, *profile.accessibility_requirements]:
        field = fields.get(condition)
        if field:
            actual = getattr(campsite, field)
            add('REQUIRED_'+field, True, actual, f'必须条件：{names[field]}，登记信息为'+('支持。' if actual is True else '不支持。' if actual is False else '未知。'))
    for field in ('toilets','showers','potable_water'):
        actual = getattr(campsite, field)
        if actual is not None:
            add('FACILITY_'+field, None, actual, f'营地配套：{names[field]}'+('已登记提供。' if actual else '未提供，需另作安排。'))
    if campsite.nightly_fee_cents is not None:
        total = campsite.nightly_fee_cents * requirements.duration_nights
        add('CAMPSITE_COST', requirements.budget_cents, total,
            f'住宿费用：每晚 AUD {Decimal(campsite.nightly_fee_cents)/100:.2f}，{requirements.duration_nights} 晚合计 AUD {Decimal(total)/100:.2f}；仅为营地费，完整费用仍需检查。')
    return facts
