"""Append-only assistance notes, independent of assessments and approval."""
import json
from datetime import date
from typing import Literal
from uuid import uuid4
from pydantic import Field, field_validator
from ..auth import fail, require_role
from ..contracts.dto import RunScope
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractFailure
from .reviews import ReviewInput
from .repository import encode,fingerprint,now
from .port import SqlitePersistencePort
from .trip_series import require_current
from .revision_choices import require_decided
from ..application.review_policy import approval_required


class AssistanceInput(ReviewInput):
    decision: Literal['WAITING_EVIDENCE','NEEDS_CAMPER_INPUT','UNSUPPORTED']
    problem: str=Field(min_length=1,max_length=2000)
    next_action: str=Field(min_length=1,max_length=2000)
    recheck_on: date|None=None

    @field_validator('problem','next_action')
    @classmethod
    def meaningful(cls,value):
        if not value.strip():raise ValueError('请填写具体问题和下一步动作。')
        return value.strip()


def saved_notes(connection,plan_id,run_id,version_id):
    return [json.loads(row['payload']) for row in connection.execute(
        'SELECT payload FROM review_assistance_notes WHERE plan_id=? AND run_id=? AND version_id=? ORDER BY rowid',
        (plan_id,run_id,version_id))]


class ReviewAssistance:
    def __init__(self,database,*,context_guard=None):self.db,self.context_guard=database,context_guard

    def submit(self,user,plan_id,body:AssistanceInput):
        require_role(user,'FOUNDER')
        with self.db.transaction() as connection:
            plan=connection.execute('SELECT * FROM plans WHERE id=? AND deleted_at IS NULL',(plan_id,)).fetchone()
            if not plan:fail(ErrorCode.NOT_FOUND,'方案不存在。')
            require_current(connection,plan);require_decided(connection,plan_id)
            run=connection.execute('SELECT * FROM runs WHERE id=?',(plan['active_run_id'],)).fetchone()
            if not run or body.version_context.plan_id!=plan_id:fail(ErrorCode.STALE_CONTEXT,'处理依据已变化，请刷新。')
            scope=RunScope.model_validate_json(run['scope'])
            port=SqlitePersistencePort(self.db,plan['owner_id'],scope)
            _,_,version=port.context(connection,body.version_context)
            assessments=port.assessments(connection,body.version_context)
            actual=sorted(item.assessment_id for item in assessments)
            if len(set(body.assessment_ids))!=2 or sorted(body.assessment_ids)!=actual:
                fail(ErrorCode.STALE_CONTEXT,'处理记录必须绑定当前两份评估。')
            key=fingerprint({'plan_id':plan_id,**body.model_dump(mode='json')})
            receipt=connection.execute('SELECT * FROM review_assistance_commands WHERE actor_id=? AND command_key=?',(user.id,body.command_key)).fetchone()
            if receipt:
                if receipt['input_hash']!=key:fail(ErrorCode.IDEMPOTENCY_CONFLICT,'同一命令不能用于不同处理内容。')
                return json.loads(receipt['result'])
            if run['revision']!=body.expected_run_revision or version.revision!=body.expected_version_revision:
                fail(ErrorCode.VERSION_CONFLICT,'方案或运行已变化，请刷新。')
            if run['status']!='SUCCEEDED' or version.status not in {'ESCALATED','BLOCKED','REVISION_REQUIRED'} or port.review(connection,body.version_context,actual):
                fail(ErrorCode.INVALID_STATE,'本次结果不再接受修正协助，请刷新。')
            unavailable=False
            if self.context_guard:
                try:self.context_guard(scope)
                except ContractFailure:unavailable=True
            eligibility=port.decision(connection,body.version_context)[1].model_dump(mode='json')
            if not unavailable and approval_required([item.model_dump(mode='json') for item in assessments],eligibility):
                fail(ErrorCode.INVALID_STATE,'这是风险审批任务，请使用正式审核决定。')
            if body.recheck_on and body.recheck_on<scope.demo_context.demo_today:
                fail(ErrorCode.INPUT_INVALID,'建议重查日期不能早于本次检查日期。')
            result={'note_id':uuid4().hex,'plan_id':plan_id,'run_id':run['id'],'plan_version_id':body.version_context.plan_version_id,
                'assessment_ids':actual,'reviewer_user_id':user.id,'decision':body.decision,'problem':body.problem,
                'reason':body.reason,'next_action':body.next_action,'recheck_on':body.recheck_on.isoformat() if body.recheck_on else None,
                'created_at':now(),'is_approval':False}
            connection.execute('INSERT INTO review_assistance_notes VALUES(?,?,?,?,?,?,?)',
                (result['note_id'],plan_id,run['id'],result['plan_version_id'],user.id,encode(result),result['created_at']))
            connection.execute('INSERT INTO review_assistance_commands VALUES(?,?,?,?,?)',
                (user.id,body.command_key,key,result['note_id'],encode(result)))
            return result
