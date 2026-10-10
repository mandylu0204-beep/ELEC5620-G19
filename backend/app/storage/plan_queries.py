"""Read persisted artifacts from exactly one authorized run, never mix evaluations."""
import json

from ..auth import fail, require_role
from ..contracts.dto import RunScope, StoredAssessment, StoredRecommendations, RouteResult
from ..contracts.enums import ErrorCode
from .port import SqlitePersistencePort
from .repository import Repository


def unpack(row, column):
    return json.loads(row[column]) if row and row[column] else None


class PlanQueries:
    def __init__(self, database):
        self.db = database

    def list(self, user):
        require_role(user, 'CAMPER')
        with self.db.transaction(write=False) as connection:
            rows = connection.execute('''SELECT p.id AS plan_id,p.request_id,p.current_version_id,
                p.final_version_id,p.active_run_id,p.created_at,r.status AS run_status,r.stage,
                r.scope,v.status AS version_status,v.version_number,r.confirmed_context
                FROM plans p LEFT JOIN runs r ON r.id=p.active_run_id
                LEFT JOIN versions v ON v.id=p.current_version_id
                WHERE p.owner_id=? ORDER BY p.created_at DESC,p.id''', (user.id,))
            result = []
            for row in rows:
                item = dict(row)
                scope, confirmed = unpack(row, 'scope'), unpack(row, 'confirmed_context')
                item.pop('scope'); item.pop('confirmed_context')
                item['execution_mode'] = scope['demo_context']['mode'] if scope else None
                item['destination'] = confirmed['requirements']['destination'] if confirmed else None
                result.append(item)
            return result

    def detail(self, user, plan_id, run_id=None, *, review=False):
        with self.db.transaction(write=False) as connection:
            if review:
                require_role(user, 'FOUNDER')
                plan = connection.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
                if not plan:
                    fail(ErrorCode.NOT_FOUND, '方案不存在。')
            else:
                plan = Repository.own_plan(connection, user, plan_id)
            selected = run_id if run_id is not None else plan['active_run_id']
            run = connection.execute('SELECT * FROM runs WHERE id=? AND plan_id=?', (selected, plan_id)).fetchone()
            if run_id is not None and not run:
                fail(ErrorCode.NOT_FOUND, '运行不存在。')
            history = [dict(row) for row in connection.execute('''SELECT r.id AS run_id,r.status,r.stage,
                r.created_at,rv.version_id AS plan_version_id,v.version_number
                FROM runs r LEFT JOIN run_versions rv ON rv.run_id=r.id
                LEFT JOIN versions v ON v.id=rv.version_id WHERE r.plan_id=? ORDER BY r.created_at DESC,r.id''', (plan_id,))]
            result = {'plan': {'plan_id': plan_id, **{key: plan[key] for key in ('request_id','current_version_id','active_run_id','final_version_id','created_at')}},
                      'run': None, 'run_history': history, 'confirmed_context': None, 'events': [],
                      'recommendations': None, 'version': None, 'assessments': [], 'route': None,
                      'eligibility': None, 'reviews': [], 'planning_available': False, 'finalisation_available': False}
            if not run:
                return result
            scope = RunScope.model_validate_json(run['scope'])
            active = plan['active_run_id'] == run['id']
            result['run'] = {'run_id': run['id'], 'status': run['status'], 'stage': run['stage'],
                'revision': run['revision'], 'error': unpack(run, 'error'), 'created_at': run['created_at'],
                'execution_mode': scope.demo_context.mode.value, 'operation': scope.operation, 'is_active': active}
            result['confirmed_context'] = unpack(run, 'confirmed_context')
            result['events'] = [{**dict(row), 'error': unpack(row, 'error')} for row in connection.execute(
                'SELECT id,stage,status,error,created_at FROM run_events WHERE run_id=? ORDER BY id', (run['id'],))]
            recommendation = connection.execute('SELECT payload FROM recommendations WHERE run_id=?', (run['id'],)).fetchone()
            if recommendation:
                result['recommendations'] = StoredRecommendations.model_validate_json(recommendation['payload']).model_dump(mode='json')
            binding = connection.execute('SELECT version_id FROM run_versions WHERE run_id=?', (run['id'],)).fetchone()
            route = connection.execute("SELECT result FROM write_receipts WHERE run_id=? AND operation='route'", (run['id'],)).fetchone()
            if route:
                result['route'] = RouteResult.model_validate_json(route['result']).model_dump(mode='json')
            if binding:
                result['reviews'] = [unpack(row, 'payload') for row in connection.execute(
                    'SELECT payload FROM reviews WHERE run_id=? AND version_id=? ORDER BY rowid', (run['id'], binding['version_id']))]
                version = Repository.stored_version(connection, scope)
                # Reassessment changes the mutable version status. Historical runs
                # display their own saved routing result instead of the latest run's.
                stored = version.model_dump(mode='json')
                if not active:
                    stored['status'] = result['route']['status'] if result['route'] else 'ASSESSING'
                result['version'] = stored
                result['assessments'] = [StoredAssessment.model_validate_json(row['payload']).model_dump(mode='json')
                    for row in connection.execute('SELECT payload FROM assessments WHERE run_id=? AND version_id=? ORDER BY kind', (run['id'], binding['version_id']))]
                if active and plan['current_version_id'] == binding['version_id']:
                    result['eligibility'] = SqlitePersistencePort(self.db, plan['owner_id'], scope).decision(connection, version.version_context)[1].model_dump(mode='json')
            if review:
                result['run_history'] = []
            return result

    def run(self, user, run_id):
        require_role(user, 'CAMPER')
        with self.db.transaction(write=False) as connection:
            row = connection.execute('SELECT r.plan_id FROM runs r JOIN plans p ON p.id=r.plan_id WHERE r.id=? AND p.owner_id=?', (run_id, user.id)).fetchone()
            if not row:
                fail(ErrorCode.NOT_FOUND, '运行不存在。')
            plan_id = row['plan_id']
        return self.detail(user, plan_id, run_id)
