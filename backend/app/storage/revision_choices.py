"""A candidate execution is distinct from the camper's selected plan version."""
import json
from typing import Literal

from pydantic import Field, StrictInt

from ..auth import fail, require_role
from ..contracts.base import ContractModel, Identifier
from ..contracts.dto import RunScope
from ..contracts.enums import ErrorCode
from .repository import Repository, encode, fingerprint


def pending(connection, plan_id):
    return connection.execute('SELECT * FROM revision_proposals WHERE plan_id=? AND decision IS NULL',
        (plan_id,)).fetchone()


def require_decided(connection, plan_id):
    if pending(connection, plan_id):
        fail(ErrorCode.INVALID_STATE, '请先采用新方案或保留原方案，再进行其他操作。')


def candidate_for(connection, plan, run_id):
    row = pending(connection, plan['id'])
    if (row and row['candidate_run_id'] == run_id and plan['active_run_id'] == row['base_run_id']
            and plan['current_version_id'] == row['base_version_id']):
        return row
    return None


def execution_active(connection, plan, run_id):
    row = pending(connection, plan['id'])
    return bool(candidate_for(connection, plan, run_id)) if row else plan['active_run_id'] == run_id


def version_current(connection, plan, run_id, version_id):
    if plan['active_run_id'] == run_id and plan['current_version_id'] == version_id:
        return True
    return bool(candidate_for(connection, plan, run_id) and connection.execute(
        'SELECT 1 FROM run_versions WHERE run_id=? AND plan_id=? AND version_id=?',
        (run_id, plan['id'], version_id)).fetchone())


def summary(connection, run_id):
    run = connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
    version = connection.execute('''SELECT v.* FROM versions v JOIN run_versions rv ON rv.version_id=v.id
        WHERE rv.run_id=? AND rv.plan_id=v.plan_id''', (run_id,)).fetchone()
    content = json.loads(version['content']) if version else {}
    confirmed = json.loads(run['confirmed_context'])
    saved = connection.execute("SELECT payload FROM assessments WHERE run_id=? AND kind='LOGISTICS'", (run_id,)).fetchone()
    logistics = json.loads(saved['payload'])['result'] if saved else {}
    saved_safety = connection.execute("SELECT payload FROM assessments WHERE run_id=? AND kind='SAFETY'", (run_id,)).fetchone()
    safety = json.loads(saved_safety['payload'])['result'] if saved_safety else {}
    camp = [line for line in logistics.get('cost_breakdown', []) if line['category'] == 'CAMPSITE']
    camp_fee = sum(line['subtotal_cents'] for line in camp) if camp and all(line['subtotal_cents'] is not None for line in camp) else None
    nightly = camp[0]['unit_price_cents'] if len(camp) == 1 and camp[0]['unit'] == 'per_night' else None
    return {'run': {'run_id': run_id, 'status': run['status'], 'stage': run['stage'], 'revision': run['revision']},
        'version_id': version['id'] if version else None, 'version_number': version['version_number'] if version else None,
        'campsite_ids': content.get('selected_campsite_ids', []),
        'duration_nights': confirmed['requirements']['duration_nights'], 'nightly_fee_cents': nightly,
        'camp_fee_cents': camp_fee, 'total_cents': logistics.get('total_cents'), 'safety_outcome':safety.get('outcome')}


class ChoiceInput(ContractModel):
    command_key: Identifier = Field(min_length=16, max_length=128)
    decision: Literal['ADOPT', 'KEEP']
    expected_proposal_revision: StrictInt = Field(ge=0)
    expected_candidate_run_revision: StrictInt = Field(ge=0)


class RevisionChoices:
    def __init__(self, database, *, context_guard=None):
        self.db, self.context_guard = database, context_guard

    def view(self, user, plan_id):
        with self.db.transaction(write=False) as db:
            plan = Repository.own_plan(db, user, plan_id)
            row = db.execute('SELECT * FROM revision_proposals WHERE plan_id=? ORDER BY rowid DESC LIMIT 1', (plan_id,)).fetchone()
            legacy = False
            selected_id = (row['candidate_run_id'] if row['decision']=='ADOPT' else row['base_run_id']) if row else None
            if not row or (row['decision'] and plan['active_run_id'] != selected_id):
                # Existing revisions remain selected as saved. Add only a
                # read-only comparison; never fabricate a pending decision.
                active = db.execute('SELECT scope,created_at FROM runs WHERE id=?', (plan['active_run_id'],)).fetchone()
                if not active:
                    return None
                scope = RunScope.model_validate_json(active['scope'])
                if scope.operation != 'REVISE' or not scope.expected_current_version_id:
                    return None
                previous = db.execute('''SELECT r.id FROM runs r JOIN run_versions rv ON rv.run_id=r.id
                    WHERE r.plan_id=? AND rv.version_id=? AND r.created_at<?
                    ORDER BY r.created_at DESC,r.id DESC LIMIT 1''',
                    (plan_id,scope.expected_current_version_id,active['created_at'])).fetchone()
                if not previous:
                    return None
                row = {'id':'previous-'+scope.run_id,'revision':0,'decision':'ADOPT',
                    'base_run_id':previous['id'],'candidate_run_id':scope.run_id}
                legacy = True
            before, after = summary(db, row['base_run_id']), summary(db, row['candidate_run_id'])
            if legacy and not after['version_id']:
                return None
            ready = after['run']['status'] == 'SUCCEEDED' and after['version_id'] is not None
            selectable = not row['decision'] and candidate_for(db, plan, row['candidate_run_id']) is not None
            return {'proposal_id': row['id'], 'revision': row['revision'], 'decision': row['decision'], 'legacy':legacy,
                'status': row['decision'] or ('READY' if ready else 'GENERATING' if after['run']['status'] in {'PENDING','RUNNING'} else 'FAILED'),
                'before': before, 'after': after, 'can_adopt': selectable and ready,
                'can_keep': selectable and after['run']['status'] not in {'PENDING','RUNNING'},
                'camp_saving_cents': before['camp_fee_cents']-after['camp_fee_cents'] if before['camp_fee_cents'] is not None and after['camp_fee_cents'] is not None else None,
                'total_saving_cents': before['total_cents']-after['total_cents'] if before['total_cents'] is not None and after['total_cents'] is not None else None}

    def choose(self, user, plan_id, proposal_id, body):
        require_role(user, 'CAMPER')
        with self.db.transaction() as db:
            plan = Repository.own_plan(db, user, plan_id)
            from .trip_series import require_current
            require_current(db, plan)
            row = db.execute('SELECT * FROM revision_proposals WHERE id=? AND plan_id=?', (proposal_id, plan_id)).fetchone()
            if not row:
                fail(ErrorCode.NOT_FOUND, '待选方案不存在。')
            key = fingerprint({'plan_id': plan_id, 'proposal_id': proposal_id, 'body': body.model_dump(mode='json')})
            receipt = db.execute('SELECT * FROM revision_choice_commands WHERE owner_id=? AND command_key=?', (user.id, body.command_key)).fetchone()
            if receipt:
                if receipt['input_hash'] != key:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, '同一个提交编号不能用于不同选择。')
                return json.loads(receipt['result'])
            if row['decision'] or row['revision'] != body.expected_proposal_revision or not candidate_for(db, plan, row['candidate_run_id']):
                fail(ErrorCode.VERSION_CONFLICT, '方案或选择状态已变化，请刷新。')
            base_run = db.execute('SELECT revision FROM runs WHERE id=?', (row['base_run_id'],)).fetchone()
            base_version = db.execute('SELECT revision FROM versions WHERE id=?', (row['base_version_id'],)).fetchone()
            if base_run['revision'] != row['base_run_revision'] or base_version['revision'] != row['base_version_revision']:
                fail(ErrorCode.STALE_CONTEXT, '原方案的检查结果已变化，请刷新。')
            run = db.execute('SELECT * FROM runs WHERE id=?', (row['candidate_run_id'],)).fetchone()
            if run['revision'] != body.expected_candidate_run_revision:
                fail(ErrorCode.VERSION_CONFLICT, '新方案检查进度已变化，请刷新。')
            if run['status'] in {'PENDING','RUNNING'}:
                fail(ErrorCode.INVALID_STATE, '请等待新方案生成结束后再选择。')
            if body.decision == 'ADOPT':
                if run['status'] != 'SUCCEEDED' or run['stage'] != 'COMPLETED':
                    fail(ErrorCode.INVALID_STATE, '新方案尚未完成，不能采用。')
                scope = RunScope.model_validate_json(run['scope'])
                if self.context_guard:
                    self.context_guard(scope)
                version = Repository.stored_version(db, scope)
                from ..application.model_audit import load_model_trace
                from ..application.assessment_audits import load_audits
                load_model_trace(db, scope, version)
                load_audits(db, scope, version)
                kinds = {r['kind'] for r in db.execute('SELECT kind FROM assessments WHERE run_id=? AND version_id=?', (run['id'], version.version_context.plan_version_id))}
                if kinds != {'LOGISTICS','SAFETY'} or not db.execute("SELECT 1 FROM write_receipts WHERE run_id=? AND operation='route'", (run['id'],)).fetchone():
                    fail(ErrorCode.CONTRACT_INVALID, '新方案检查记录不完整，不能采用。')
                db.execute('UPDATE plans SET active_run_id=?,current_version_id=? WHERE id=?',
                    (run['id'], version.version_context.plan_version_id, plan_id))
            db.execute('UPDATE revision_proposals SET decision=?,revision=revision+1 WHERE id=?', (body.decision, proposal_id))
            result = {'plan_id': plan_id, 'proposal_id': proposal_id, 'decision': body.decision}
            db.execute('INSERT INTO revision_choice_commands VALUES(?,?,?,?)', (user.id, body.command_key, key, encode(result)))
            return result
