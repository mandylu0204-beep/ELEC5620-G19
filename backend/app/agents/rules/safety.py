"""Qualitative synthetic-evidence rules; no copied risk/confidence labels."""
import re

from ...contracts.dto import Blocker, Evidence, SafetyResult, StoredAssessment
from ...contracts.enums import (
    AssessmentKind, AssessmentOutcome, Confidence, DataQuality, ExecutionMode, PlanVersionStatus, RiskLevel, RoadState,
)
from .common import REST_DESCRIPTION, artifact, camp_description, ensure_execution_mode, input_failure, validate_itinerary

KINDS = ('WEATHER', 'FIRE', 'ROAD', 'RESTRICTION')
QUALITY_ORDER = {DataQuality.AVAILABLE: 0, DataQuality.MISSING: 1, DataQuality.STALE: 2, DataQuality.CONFLICTING: 3}


def _covers(start, end, requirements):
    return start is not None and end is not None and start <= requirements.start_date and end >= requirements.end_date


def _weather_risk(summary):
    text = (summary or '').strip().casefold()
    if any(phrase in text for phrase in ('extreme heat', 'extreme cold', 'strong wind', 'heavy rain', 'flood')):
        return RiskLevel.HIGH
    if 'cold' in text or 'rain' in text or 'wind' in text:
        return RiskLevel.MEDIUM
    if text in {'mild synthetic conditions.', 'dry synthetic conditions.', 'no adverse synthetic weather.'}:
        return RiskLevel.LOW
    return RiskLevel.UNKNOWN


def assess(dataset, input, *, expected_mode=ExecutionMode.DETERMINISTIC_DEMO) -> SafetyResult:
    ensure_execution_mode(dataset, input.demo_context, expected_mode)
    requirements, scenario = input.confirmed_requirements, input.scenario_context
    selected = set(validate_itinerary(dataset, input.saved_itinerary, requirements, expected_mode=expected_mode))
    selector = getattr(dataset, 'trip_evidence_selector', None)
    if selector is not None:
        resolved = selector.resolve_trip_evidence(requirements, sorted(selected), input.demo_context)
        if scenario != resolved.scenario_context:
            raise input_failure('Safety and gear must use the same registered trip evidence selection.', 'scenario_context')
    if not selected.issubset(scenario.campsite_ids):
        raise input_failure('Scenario does not apply to every selected campsite.', 'scenario_context.campsite_ids')
    if input.saved_logistics_assessment.result.execution_mode != input.demo_context.mode:
        raise input_failure('Saved logistics mode differs from safety execution mode.', 'saved_logistics_assessment')
    blockers, conflicts, hazards, evidence, uncertainties, sources = [], [], [], [], [], []
    quality = {kind: DataQuality.AVAILABLE for kind in KINDS}
    weather_risks = []
    context_covered = _covers(scenario.valid_from, scenario.valid_to, requirements)
    if not context_covered:
        uncertainties.append('Scenario validity does not cover the entire confirmed trip.')
    planned_fire = any(
        re.search(r'\b(?:campfire|bonfire|open fire)\b', entry.description.casefold())
        and not re.search(r'\b(?:no|without|avoid|remove)\s+(?:a\s+)?(?:campfires?|bonfires?|open fire)\b', entry.description.casefold())
        for entry in input.saved_itinerary.itinerary_entries
    )
    unknown_activities = [
        entry.description for entry in input.saved_itinerary.itinerary_entries
        if not (entry.entry_kind == 'CAMP' and entry.description == camp_description(dataset.get_campsite(entry.campsite_id)))
        and not (entry.entry_kind == 'ACTIVITY' and entry.description == REST_DESCRIPTION)
    ]
    if unknown_activities:
        hazards.extend(f'Unclassified activity/travel requires human review: {description}' for description in unknown_activities)
        uncertainties.append('B-02 does not claim to assess arbitrary activities or travel segments.')

    def block(code, message, refs=()):
        if not any(item.code == code and item.message == message for item in blockers):
            blockers.append(Blocker(code=code, message=message, source_refs=list(refs)))

    for campsite_id in sorted(selected):
        campsite = dataset.get_campsite(campsite_id)
        sources.append(campsite.source_ref)
        campfire = bool(planned_fire) or 'campfire' in {preference.strip().casefold() for preference in requirements.preferences} or any(value in requirements.mandatory_constraints for value in ('campfire', 'fire_allowed'))
        if campfire and (campsite.fire_allowed is False or 'no_fires' in requirements.mandatory_constraints):
            block('FIRE_PROHIBITED', f'{campsite_id}: requested campfire conflicts with a prohibition.', [campsite.source_ref])
        if any(any(phrase in restriction.casefold() for phrase in ('campsite closure', 'campsite closed', 'closed campsite')) for restriction in campsite.mandatory_restrictions):
            block('CAMPSITE_CLOSED', f'{campsite_id}: source states campsite closure.', [campsite.source_ref])
        for kind in KINDS:
            matches = [item for item in scenario.evidence if item.kind == kind and any(ref.record_id == campsite_id for ref in item.source_refs)]
            if not matches:
                quality[kind] = max(quality[kind], DataQuality.MISSING, key=QUALITY_ORDER.get)
                evidence.append(Evidence(kind=kind, summary=None, source_date=None, status=DataQuality.MISSING, valid_from=None, valid_to=None, source_refs=[]))
                uncertainties.append(f'{campsite_id}: {kind} evidence is missing or has no matching source.')
                continue
            facts = {(item.summary, item.road_state) for item in matches if item.status == DataQuality.AVAILABLE}
            disagrees = len(facts) > 1
            if disagrees:
                conflicts.append(f'{campsite_id}: {kind} source facts disagree.')
            for item in matches:
                sources.extend(item.source_refs)
                status = item.status
                if disagrees or status == DataQuality.CONFLICTING:
                    status = DataQuality.CONFLICTING
                    conflicts.append(f'{campsite_id}: unresolved {kind} evidence conflict.')
                elif status == DataQuality.AVAILABLE:
                    if not context_covered or not _covers(item.valid_from, item.valid_to, requirements) or item.source_date is None or item.source_date > input.demo_context.demo_today or not item.summary:
                        status = DataQuality.MISSING
                        uncertainties.append(f'{campsite_id}: {kind} coverage, source date or content is incomplete/future-dated.')
                    if any((ref.valid_from is not None or ref.valid_to is not None) and not _covers(ref.valid_from, ref.valid_to, requirements) for ref in item.source_refs):
                        status = DataQuality.MISSING
                        uncertainties.append(f'{campsite_id}: a source reference has a narrower/unknown applicability interval.')
                if kind == 'ROAD' and item.road_state not in {RoadState.OPEN, RoadState.CLOSED}:
                    status = max(status, DataQuality.MISSING, key=QUALITY_ORDER.get)
                    uncertainties.append(f'{campsite_id}: road state is unknown, not OPEN.')
                text = (item.summary or '').strip().casefold()
                if status == DataQuality.AVAILABLE and 'conflict' in text:
                    status = DataQuality.CONFLICTING
                    conflicts.append(f'{campsite_id}: {kind} summary states a source conflict.')
                if status == DataQuality.AVAILABLE and 'stale' in text:
                    status = DataQuality.STALE
                    uncertainties.append(f'{campsite_id}: {kind} summary states stale data.')
                if status == DataQuality.AVAILABLE and any(phrase in text for phrase in ('unverified', 'unknown', 'unavailable')):
                    status = DataQuality.MISSING
                    uncertainties.append(f'{campsite_id}: {kind} summary explicitly lacks verified facts.')
                if kind == 'FIRE' and status == DataQuality.AVAILABLE and text not in {'no synthetic fire restriction.', 'synthetic comprehensive no-fire restriction.'}:
                    status = DataQuality.MISSING
                    uncertainties.append(f'{campsite_id}: unsupported qualitative fire facts require clarification.')
                if kind == 'WEATHER' and status == DataQuality.AVAILABLE and _weather_risk(item.summary) == RiskLevel.UNKNOWN:
                    status = DataQuality.MISSING
                    uncertainties.append(f'{campsite_id}: weather summary does not support a known qualitative rule.')
                if kind == 'ROAD' and item.road_state == RoadState.OPEN and any(phrase in text for phrase in ('closed in synthetic scenario', 'road closed')):
                    status = DataQuality.CONFLICTING
                    conflicts.append(f'{campsite_id}: road summary and road state disagree.')
                    block('ROAD_CLOSED', f'{campsite_id}: road summary states closure.', item.source_refs)
                normalized = Evidence.model_validate(item.model_dump() | {'status': status})
                evidence.append(normalized)
                quality[kind] = max(quality[kind], status, key=QUALITY_ORDER.get)
                if kind == 'WEATHER':
                    weather_risks.append(_weather_risk(item.summary))
                    if _weather_risk(item.summary) in {RiskLevel.HIGH, RiskLevel.MEDIUM}:
                        hazards.append(f'{campsite_id}: {item.summary}')
                if kind == 'ROAD' and item.road_state == RoadState.CLOSED:
                    block('ROAD_CLOSED', f'{campsite_id}: road access is closed.', item.source_refs)
                    hazards.append('Closed road access.')
                if kind == 'RESTRICTION' and any(phrase in text for phrase in ('campsite closure', 'campsite closed', 'closed campsite')):
                    block('CAMPSITE_CLOSED', f'{campsite_id}: source states campsite closure.', item.source_refs)
                fire_banned = campsite.fire_allowed is False or 'no_fires' in requirements.mandatory_constraints or any(phrase in text for phrase in ('no-fire restriction', 'no fires', 'fires prohibited', 'fire prohibition'))
                if kind in {'FIRE', 'RESTRICTION'} and campfire and fire_banned:
                    block('FIRE_PROHIBITED', f'{campsite_id}: requested campfire conflicts with a prohibition.', [campsite.source_ref, *item.source_refs])
    physical_blockers = bool(blockers)
    # Mandatory gear blockers remain visible, not cleared by a safety judgement.
    blockers.extend(input.saved_logistics_assessment.result.mandatory_blockers)
    high = any(risk == RiskLevel.HIGH for risk in weather_risks) or physical_blockers
    incomplete = any(value != DataQuality.AVAILABLE for value in quality.values())
    unknown_risk = bool(unknown_activities) or not weather_risks or any(risk == RiskLevel.UNKNOWN for risk in weather_risks)
    if high:
        risk = RiskLevel.HIGH
    elif incomplete or unknown_risk:
        risk = RiskLevel.UNKNOWN
    elif any(item == RiskLevel.MEDIUM for item in weather_risks):
        risk = RiskLevel.MEDIUM
    else:
        risk = RiskLevel.LOW
    confidence = Confidence.UNKNOWN if incomplete or unknown_risk else Confidence.HIGH
    requires_review = risk in {RiskLevel.HIGH, RiskLevel.UNKNOWN} or confidence in {Confidence.LOW, Confidence.UNKNOWN} or bool(conflicts)
    if physical_blockers:
        outcome = AssessmentOutcome.BLOCKED
    elif requires_review:
        outcome = AssessmentOutcome.REVIEW
    elif blockers:
        outcome = AssessmentOutcome.REVISION
    else:
        outcome = AssessmentOutcome.PASSED
    actions = ['Recheck evidence and arrangements before any real-world use; this is only a synthetic demo.']
    if blockers:
        actions.append('Resolve blockers in a new/updated confirmed plan; human approval cannot override them.')
    if incomplete or conflicts:
        actions.append('Obtain complete, nonconflicting, trip-covering evidence and start a new evidence run.')
    if requires_review:
        actions.append('Escalate the current evidence to an authorised Founder; missing evidence remains unresolved.')
    if input.saved_logistics_assessment.result.outcome != AssessmentOutcome.PASSED:
        actions.append('Resolve logistics requirements independently before finalisation.')
    return SafetyResult(
        version_context=input.version_context, depends_on_assessment_id=input.saved_logistics_assessment.assessment_id,
        risk_level=risk, confidence=confidence, data_quality=quality, evidence=evidence,
        hazards=list(dict.fromkeys(hazards)), mandatory_blockers=blockers,
        recommended_actions=actions, outcome=outcome, requires_human_review=requires_review,
        unresolved_conflicts=list(dict.fromkeys(conflicts)),
        **artifact(input.demo_context, sources,
                   assumptions=['Qualitative v1 synthetic summary rules; no temperature, wind-speed or probability is fabricated.',
                       *(['Trip evidence selection digest: ' + resolved.selection_digest + '.'] if selector is not None else [])],
                   uncertainties=list(dict.fromkeys(uncertainties))),
    )


def propose_route(saved_logistics: StoredAssessment, safety: SafetyResult) -> PlanVersionStatus:
    """A still validates/persists the actual route; this never finalises anything."""
    if saved_logistics.kind != AssessmentKind.LOGISTICS or safety.depends_on_assessment_id != saved_logistics.assessment_id:
        raise input_failure('Safety does not depend on this saved logistics assessment.', 'assessments')
    logistics = saved_logistics.result
    if logistics.version_context != safety.version_context or logistics.execution_mode != safety.execution_mode:
        raise input_failure('Assessment contexts/modes do not match.', 'assessments')
    if logistics.mandatory_blockers or safety.mandatory_blockers or AssessmentOutcome.BLOCKED in {logistics.outcome, safety.outcome}:
        return PlanVersionStatus.BLOCKED
    if safety.requires_human_review or AssessmentOutcome.REVIEW in {logistics.outcome, safety.outcome}:
        return PlanVersionStatus.ESCALATED
    if AssessmentOutcome.REVISION in {logistics.outcome, safety.outcome}:
        return PlanVersionStatus.REVISION_REQUIRED
    if logistics.outcome == safety.outcome == AssessmentOutcome.PASSED:
        return PlanVersionStatus.ELIGIBLE_FOR_FINALISATION
    return PlanVersionStatus.BLOCKED
