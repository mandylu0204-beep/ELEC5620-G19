"""Read-only reassessment feedback; never changes routing or eligibility."""
from ..contracts.dto import StoredAssessment


def results(connection, run_id, version_id):
    pair = {}
    try:
        for row in connection.execute('SELECT payload FROM assessments WHERE run_id=?', (run_id,)):
            item = StoredAssessment.model_validate_json(row['payload'])
            if item.version_context.run_id != run_id or item.version_context.plan_version_id != version_id:
                return None
            pair[item.kind.value] = item
        if set(pair) != {'LOGISTICS', 'SAFETY'}:
            return None
        if pair['SAFETY'].result.depends_on_assessment_id != pair['LOGISTICS'].assessment_id:
            return None
        # New run identifiers are not business changes. Evidence and unknowns
        # remain part of the comparison; transient model usage does not.
        return {kind: item.result.model_dump(mode='json', exclude={
            'version_context', 'depends_on_assessment_id',
        }) for kind, item in pair.items()}
    except ValueError:
        # Unusable history must not produce an "unchanged" claim. Current
        # artifact integrity remains enforced by the ordinary read path.
        return None


def reassessment_feedback(connection, plan_id, run, scope, version_id):
    if scope.operation != 'REASSESS':
        return None
    feedback = {'status': 'INCOMPLETE', 'started_at': run['created_at'],
        'completed_at': None, 'comparison': 'NOT_COMPARABLE',
        'compared_run_id': None, 'changed_sections': []}
    if run['status'] in {'PENDING', 'RUNNING'}:
        feedback['status'] = 'IN_PROGRESS'
        return feedback
    if run['status'] != 'SUCCEEDED' or run['stage'] != 'COMPLETED':
        feedback['status'] = 'FAILED' if run['status'] == 'FAILED' else 'INCOMPLETE'
        return feedback
    current = results(connection, run['id'], version_id)
    if current is None:
        return feedback
    feedback['status'] = 'COMPLETED'
    event = connection.execute("""SELECT created_at FROM run_events
        WHERE run_id=? AND stage='COMPLETED' AND status='SUCCEEDED'
        ORDER BY id DESC LIMIT 1""", (run['id'],)).fetchone()
    feedback['completed_at'] = event['created_at'] if event else None
    previous = connection.execute("""SELECT r.id FROM runs r
        JOIN run_versions rv ON rv.run_id=r.id
        WHERE r.plan_id=? AND rv.version_id=? AND r.status='SUCCEEDED'
        AND r.stage='COMPLETED' AND r.rowid<(SELECT rowid FROM runs WHERE id=?)
        ORDER BY r.rowid DESC LIMIT 1""", (plan_id, version_id, run['id'])).fetchone()
    if previous is None:
        return feedback
    prior = results(connection, previous['id'], version_id)
    if prior is None:
        return feedback
    feedback['compared_run_id'] = previous['id']
    feedback['changed_sections'] = [kind for kind in ('LOGISTICS', 'SAFETY') if current[kind] != prior[kind]]
    feedback['comparison'] = 'CHANGED' if feedback['changed_sections'] else 'UNCHANGED'
    return feedback
