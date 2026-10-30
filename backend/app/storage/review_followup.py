"""Bind camper-initiated revision feedback to an immutable reviewed result."""
import json
from ..auth import fail
from ..contracts.enums import ErrorCode
from .repository import Repository
from .trip_series import require_current


def revision_feedback(database,user,plan_id,body):
    with database.transaction(write=False) as connection:
        plan=Repository.own_plan(connection,user,plan_id)
        require_current(connection,plan)
        receipt=connection.execute('SELECT operation FROM workflow_commands WHERE owner_id=? AND command_key=?',(user.id,body.command_key)).fetchone()
        # A receipt permits reconstructing the original input only. begin_run still
        # verifies the complete command hash before returning the saved scope.
        if not receipt and (plan['active_run_id']!=body.expected_active_run_id or plan['current_version_id']!=body.expected_current_version_id):
            fail(ErrorCode.STALE_CONTEXT,'审核所针对的方案已变化，请刷新后重新核对。')
        row=connection.execute('SELECT h.payload FROM reviews h JOIN runs r ON r.id=h.run_id WHERE h.id=? AND h.run_id=? AND h.version_id=? AND r.plan_id=?',
            (body.source_review_id,body.expected_active_run_id,body.expected_current_version_id,plan_id)).fetchone()
        if not row:fail(ErrorCode.STALE_CONTEXT,'审核意见不属于本次当前版本。')
        review=json.loads(row['payload'])
        actual=sorted(row['id'] for row in connection.execute('SELECT id FROM assessments WHERE run_id=? AND version_id=?',
            (body.expected_active_run_id,body.expected_current_version_id)))
        if review['decision'] not in {'REQUEST_REVISION','REJECT'} or sorted(review['assessment_ids'])!=actual or len(actual)!=2:
            fail(ErrorCode.INVALID_STATE,'这条审核记录不能用作修订意见。')
        # Persisted in the existing revision_feedback scope and reused on recovery.
        # No approval or confirmed requirement is forwarded as a new permission.
        from ..contracts.revision_feedback import linked_feedback,model_feedback_text
        feedback=linked_feedback(review,body.feedback)
        if len(model_feedback_text(feedback))>4000:
            fail(ErrorCode.INPUT_INVALID,'审核意见与补充指令合计超过4000字符，请精简补充说明；原审核意见不会截断。')
        return feedback
