"""Authorized, read-only coverage guidance from the exact registered snapshot."""
from ..agents.rules.planning import violations
from ..contracts.dto import ConfirmedContext, ConfirmedRequirements


def clear_access(selection, requirements):
    # Full source coverage is not itself approval. Do not suggest a campsite
    # when those very sources explicitly state road/campsite closure.
    fire_requested = 'campfire' in {value.strip().lower() for value in requirements.preferences} or any(
        value in requirements.mandatory_constraints for value in ('campfire', 'fire_allowed'))
    return not selection.coverage_issues and not any(
        item.road_state == 'CLOSED' or (item.kind == 'RESTRICTION' and any(
            word in (item.summary or '').lower() for word in ('campsite closure', 'campsite closed', 'closed campsite')))
        or (fire_requested and item.kind in {'FIRE', 'RESTRICTION'} and any(
            word in (item.summary or '').lower() for word in ('no-fire restriction', 'no fires', 'fires prohibited', 'fire prohibition')))
        for item in selection.scenario_context.evidence)


def guidance(data, snapshot, scope):
    if not snapshot or not data.get('version') or not data['run']['is_active']:
        return None
    if snapshot.dataset != scope.dataset_context or snapshot.demo != scope.demo_context:
        return None
    configuration = getattr(snapshot.agent, 'workflow_configuration', None)
    dataset = getattr(snapshot.agent, 'dataset', None)
    if not configuration or not dataset or not getattr(dataset, 'trip_evidence_selector', None):
        return None
    confirmed = ConfirmedContext.model_validate(data['confirmed_context'])
    req, profile = confirmed.requirements, confirmed.profile_snapshot
    sites = data['version']['content']['selected_campsite_ids']
    selection = configuration.resolve_trip_evidence(req, sites, scope.demo_context)
    result = {'dataset_version': scope.dataset_context.dataset_version,
        'checked_on': scope.demo_context.demo_today.isoformat(),
        'selection_digest': selection.selection_digest,
        'issues': [item.model_dump(mode='json') for item in selection.coverage_issues],
        'alternative_campsites': [], 'alternative_dates': []}
    if not selection.coverage_issues:
        return result
    # Suggestions never enter the saved request, Agent candidates or eligibility.
    # Preserve all confirmed hard constraints and the basic campsite-fee check;
    # total logistics costs and a complete safety assessment remain outstanding.
    for camp in sorted(dataset.campsites, key=lambda item: (
            item.nightly_fee_cents is None, item.nightly_fee_cents or 0, item.campsite_id)):
        if camp.campsite_id in sites or violations(camp, req, profile):
            continue
        candidate = configuration.resolve_trip_evidence(req, [camp.campsite_id], scope.demo_context)
        if clear_access(candidate, req):
            result['alternative_campsites'].append({'campsite_id': camp.campsite_id,
                'start_date': req.start_date.isoformat(), 'end_date': req.end_date.isoformat()})
        if len(result['alternative_campsites']) == 3:
            break
    # Derive optional date suggestions from actual already-observed records,
    # then re-query every selected campsite and kind. Never advertise a union of
    # partial ranges as complete coverage or propose a past departure date.
    starts = {value for issue in selection.coverage_issues for interval in issue.available_ranges
        for value in (interval.start, interval.end - (req.end_date - req.start_date))
        if value >= scope.demo_context.demo_today}
    for start in sorted(starts, key=lambda value: (abs((value - req.start_date).days), value))[:32]:
        if start == req.start_date:
            continue
        raw = req.model_dump()
        raw.update(start_date=start, end_date=start + (req.end_date - req.start_date))
        proposed = ConfirmedRequirements.model_validate(raw)
        if any(violations(dataset.get_campsite(site), proposed, profile) for site in sites):
            continue
        candidate = configuration.resolve_trip_evidence(proposed, sites, scope.demo_context)
        if clear_access(candidate, proposed):
            result['alternative_dates'].append({'start_date': proposed.start_date.isoformat(),
                'end_date': proposed.end_date.isoformat()})
        if len(result['alternative_dates']) == 3:
            break
    return result
