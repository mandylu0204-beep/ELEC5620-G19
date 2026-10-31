"""Pre-planning interpretation assistance. No approvals, model calls or facts invented."""
import json
from uuid import uuid4
from pydantic import Field, StrictInt, field_validator, model_validator
from typing import Literal
from ..auth import fail, require_role
from ..contracts.base import ContractModel
from ..contracts.dto import ProfileSnapshot, TripRequirements
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractFailure
from ..application.requirement_choices import unknown_items, LABELS, CHOICES_VERSION
from .repository import encode, fingerprint, now

class HelpCreate(ContractModel):
    expected_revision: StrictInt = Field(ge=1)
    expected_profile_revision: StrictInt = Field(ge=0)
    command_key: str = Field(min_length=16,max_length=128)

class HelpMapping(ContractModel):
    field: Literal['preferences','mandatory_constraints','accessibility_requirements']
    index: StrictInt = Field(ge=0)
    original: str = Field(min_length=1,max_length=8000)
    canonical: str = Field(min_length=1,max_length=120)

class HelpDecision(ContractModel):
    expected_revision: StrictInt = Field(ge=1)
    command_key: str = Field(min_length=16,max_length=128)
    decision: Literal['PROPOSE_MAPPING','RETURN_FOR_DETAILS','UNSUPPORTED']
    feedback_version: Literal['structured-help-feedback-1']|None=None
    problem: str|None=Field(default=None,min_length=1,max_length=2000)
    next_action: str|None=Field(default=None,min_length=1,max_length=2000)
    reason: str = Field(min_length=1,max_length=4000)
    mappings: list[HelpMapping] = Field(default_factory=list,max_length=256)

    @field_validator('reason')
    @classmethod
    def meaningful(cls,value):
        if not value.strip():raise ValueError('Explain the reason for your judgement.')
        return value.strip()

    @model_validator(mode='after')
    def complete_feedback(self):
        if self.decision=='UNSUPPORTED' or self.feedback_version is not None and self.decision=='RETURN_FOR_DETAILS':
            if not self.problem or not self.problem.strip() or not self.next_action or not self.next_action.strip():
                raise ValueError('Enter the specific issue and the next action for the user.')
        return self

class HelpAdopt(HelpCreate):
    expected_task_revision: StrictInt = Field(ge=1)


def _profile(connection,owner_id):
    row=connection.execute('SELECT * FROM profiles WHERE owner_id=?',(owner_id,)).fetchone()
    return (ProfileSnapshot.model_validate_json(row['payload']),row['revision']) if row else (ProfileSnapshot(),0)


def help_state(connection,row):
    if row['status']=='CONFIRMED':return None
    profile,revision=_profile(connection,row['owner_id'])
    unknown=unknown_items(TripRequirements.model_validate_json(row['payload']),profile)
    task=connection.execute('SELECT * FROM requirement_help_tasks WHERE request_id=? AND request_revision=? AND profile_revision=?',
        (row['id'],row['revision'],revision)).fetchone()
    return {'needed':bool(unknown),'items':unknown,'profile_revision':revision,
        'task':_public(task) if task else None}


def _public(row):
    return {'task_id':row['id'],'request_id':row['request_id'],'request_revision':row['request_revision'],
        'profile_revision':row['profile_revision'],'status':row['status'],'revision':row['revision'],
        'created_at':row['created_at'],'snapshot':json.loads(row['snapshot']),
        'response':json.loads(row['response']) if row['response'] else None}

class RequirementHelp:
    def __init__(self,database):self.db=database

    @staticmethod
    def _task(connection,user,task_id):
        row=connection.execute('SELECT t.* FROM requirement_help_tasks t JOIN requests q ON q.id=t.request_id WHERE t.id=? AND NOT EXISTS(SELECT 1 FROM deleted_requests d WHERE d.request_id=q.id) AND NOT EXISTS(SELECT 1 FROM successor_requests o JOIN trip_series s ON s.id=o.series_id LEFT JOIN plans p ON p.id=o.predecessor_plan_id WHERE o.request_id=q.id AND (s.deleted_at IS NOT NULL OR p.deleted_at IS NOT NULL))',(task_id,)).fetchone()
        if not row or user.role not in {'CAMPER','FOUNDER'} or (user.role=='CAMPER' and row['owner_id']!=user.id):
            fail(ErrorCode.NOT_FOUND,'Request assistance record not found.')
        return row

    @staticmethod
    def _current(connection,task):
        row=connection.execute('SELECT * FROM requests WHERE id=?',(task['request_id'],)).fetchone()
        profile,revision=_profile(connection,task['owner_id'])
        if json.loads(task['snapshot'])['choices_version']!=CHOICES_VERSION:
            fail(ErrorCode.STALE_CONTEXT,'Available condition catalogue changed. Submit assistance again.')
        if row['status'] in {'CONFIRMED','ANALYSING'} or row['revision']!=task['request_revision'] or revision!=task['profile_revision']:
            fail(ErrorCode.STALE_CONTEXT,'Request or profile changed. Submit assistance again.')
        from .trip_series import validate_successor
        from ..auth import User
        owner=connection.execute('SELECT * FROM users WHERE id=?',(task['owner_id'],)).fetchone()
        validate_successor(connection,User(owner['id'],owner['username'],owner['display_name'],owner['role']),row['id'])
        return row,profile

    @staticmethod
    def _receipt(connection,user,key,operation,payload):
        old=connection.execute('SELECT * FROM requirement_help_commands WHERE actor_id=? AND command_key=?',(user.id,key)).fetchone()
        if old:
            if old['operation']!=operation or old['input_hash']!=fingerprint(payload):
                fail(ErrorCode.VERSION_CONFLICT,'Command key already used for different content.')
            return json.loads(old['result'])

    @staticmethod
    def _save(connection,user,key,operation,payload,task_id,result):
        connection.execute('INSERT INTO requirement_help_commands VALUES(?,?,?,?,?,?)',
            (user.id,key,operation,fingerprint(payload),task_id,encode(result)))
        connection.execute('INSERT INTO requirement_help_events(task_id,actor_id,operation,payload,created_at) VALUES(?,?,?,?,?)',
            (task_id,user.id,operation,encode(payload),now()))
        return result

    def create(self,user,request_id,body):
        require_role(user,'CAMPER')
        payload={'request_id':request_id,**body.model_dump(mode='json')}
        from .requests import RequestRepository
        with self.db.transaction() as connection:
            row=RequestRepository.own(connection,user,request_id)
            previous=self._receipt(connection,user,body.command_key,'create',payload)
            if previous:return previous
            RequestRepository.check_revision(row,body.expected_revision)
            if row['status'] in {'CONFIRMED','ANALYSING'}:fail(ErrorCode.INVALID_STATE,'Submit assistance from an unconfirmed draft.')
            profile,revision=_profile(connection,user.id)
            if revision!=body.expected_profile_revision:fail(ErrorCode.VERSION_CONFLICT,'Profile changed. Refresh.')
            from .trip_series import validate_successor
            validate_successor(connection,user,request_id)
            unknown=unknown_items(TripRequirements.model_validate_json(row['payload']),profile)
            if len(unknown)>256 or any(len(item['text'])>8000 for item in unknown):
                fail(ErrorCode.INVALID_STATE,'Too many other requirements or an item is too long. Split or simplify before submitting assistance.')
            if not unknown:fail(ErrorCode.INVALID_STATE,'Existing options cover these expressions. Human assistance is unnecessary.')
            old=connection.execute('SELECT * FROM requirement_help_tasks WHERE request_id=? AND request_revision=? AND profile_revision=?',
                (request_id,row['revision'],revision)).fetchone()
            if old:result=_public(old)
            else:
                task_id=uuid4().hex
                snapshot={'choices_version':CHOICES_VERSION,'raw_text':row['raw_text'],'explicit_fields':json.loads(row['payload']),
                    'accessibility_requirements':profile.accessibility_requirements,'items':unknown}
                connection.execute('INSERT INTO requirement_help_tasks VALUES(?,?,?,?,?,?,?,1,NULL,?)',
                    (task_id,request_id,user.id,row['revision'],revision,encode(snapshot),'PENDING',now()))
                result=_public(self._task(connection,user,task_id))
            return self._save(connection,user,body.command_key,'create',payload,result['task_id'],result)

    def queue(self,user,*,history=False):
        require_role(user,'FOUNDER')
        if history:
            with self.db.transaction(write=False) as connection:
                rows=connection.execute('''SELECT t.* FROM requirement_help_tasks t JOIN requests q ON q.id=t.request_id
                    WHERE NOT EXISTS(SELECT 1 FROM deleted_requests d WHERE d.request_id=q.id)
                    AND NOT EXISTS(SELECT 1 FROM successor_requests o JOIN trip_series s ON s.id=o.series_id
                        LEFT JOIN plans p ON p.id=o.predecessor_plan_id WHERE o.request_id=q.id
                        AND (s.deleted_at IS NOT NULL OR p.deleted_at IS NOT NULL))
                    ORDER BY t.created_at DESC,t.id DESC''').fetchall()
                result=[]
                for row in rows:
                    value=_public(row)
                    try:self._current(connection,row);value['current']=True
                    except ContractFailure:value['current']=False
                    result.append(value)
                return result
        with self.db.transaction(write=False) as connection:
            rows=connection.execute("""SELECT t.* FROM requirement_help_tasks t JOIN requests q ON q.id=t.request_id
                LEFT JOIN profiles p ON p.owner_id=t.owner_id WHERE t.status='PENDING' AND q.status NOT IN ('CONFIRMED','ANALYSING')
                AND q.revision=t.request_revision AND COALESCE(p.revision,0)=t.profile_revision
                AND NOT EXISTS(SELECT 1 FROM deleted_requests d WHERE d.request_id=q.id)
                AND NOT EXISTS(SELECT 1 FROM successor_requests o JOIN trip_series s ON s.id=o.series_id
                    LEFT JOIN plans source ON source.id=o.predecessor_plan_id
                    WHERE o.request_id=q.id AND (s.deleted_at IS NOT NULL OR source.deleted_at IS NOT NULL OR s.current_plan_id IS NOT o.predecessor_plan_id))
                ORDER BY t.created_at,t.id""").fetchall()
            return [_public(row) for row in rows]

    def get(self,user,task_id):
        with self.db.transaction(write=False) as connection:
            row=self._task(connection,user,task_id)
            value=_public(row)
            try:self._current(connection,row);value['current']=True
            except ContractFailure:value['current']=False
            return value

    def decide(self,user,task_id,body):
        require_role(user,'FOUNDER');payload={'task_id':task_id,**body.model_dump(mode='json',exclude_none=True)}
        with self.db.transaction() as connection:
            task=self._task(connection,user,task_id)
            old=self._receipt(connection,user,body.command_key,'decide',payload)
            if old:return old
            self._current(connection,task)
            if task['status']!='PENDING' or task['revision']!=body.expected_revision:fail(ErrorCode.VERSION_CONFLICT,'Assistance task processed. Refresh.')
            expected={(item['field'],item['index'],item['text']) for item in json.loads(task['snapshot'])['items']}
            actual={(item.field,item.index,item.original) for item in body.mappings}
            if body.decision=='PROPOSE_MAPPING':
                if expected!=actual or len(actual)!=len(body.mappings):fail(ErrorCode.INVALID_STATE,'Mapping must cover each original requirement exactly, without omissions or additions.')
                if any(item.canonical not in LABELS[item.field] for item in body.mappings):fail(ErrorCode.INVALID_STATE,'Only existing verifiable conditions in this category may be suggested. Other requirements cannot be directly approved.')
            elif body.mappings:fail(ErrorCode.INVALID_STATE,'A return for clarification cannot also submit mappings.')
            response={'decision':body.decision,'reason':body.reason,'mappings':[item.model_dump(mode='json') for item in body.mappings],
                'reviewer_id':user.id,'reviewed_at':now(),
                **({'feedback_version':body.feedback_version,'problem':body.problem.strip() if body.problem else None,
                    'next_action':body.next_action.strip() if body.next_action else None} if body.feedback_version or body.decision=='UNSUPPORTED' else {})}
            status='PROPOSED' if body.decision=='PROPOSE_MAPPING' else 'RETURNED'
            connection.execute('UPDATE requirement_help_tasks SET status=?,revision=revision+1,response=? WHERE id=?',(status,encode(response),task_id))
            return self._save(connection,user,body.command_key,'decide',payload,task_id,_public(self._task(connection,user,task_id)))

    def adopt(self,user,task_id,body):
        require_role(user,'CAMPER');payload={'task_id':task_id,**body.model_dump(mode='json')}
        with self.db.transaction() as connection:
            task=self._task(connection,user,task_id)
            old=self._receipt(connection,user,body.command_key,'adopt',payload)
            if old:return old
            row,profile=self._current(connection,task)
            if (body.expected_revision!=row['revision'] or body.expected_profile_revision!=task['profile_revision']
                or body.expected_task_revision!=task['revision'] or task['status']!='PROPOSED'):
                fail(ErrorCode.VERSION_CONFLICT,'Suggestion or requirements changed. Refresh and review.')
            fields=json.loads(row['payload']);access=list(profile.accessibility_requirements)
            response=json.loads(task['response'])
            for item in response['mappings']:
                values=access if item['field']=='accessibility_requirements' else fields[item['field']]
                if values[item['index']]!=item['original']:fail(ErrorCode.STALE_CONTEXT,'Original requirements changed.')
                values[item['index']]=item['canonical']
            profile_revision=task['profile_revision']
            if access!=profile.accessibility_requirements:
                profile=profile.model_copy(update={'accessibility_requirements':access})
                connection.execute('UPDATE profiles SET payload=?,revision=revision+1,updated_at=? WHERE owner_id=?',(encode(profile),now(),user.id))
                profile_revision+=1
            explicit=TripRequirements.model_validate(fields)
            connection.execute("UPDATE requests SET payload=?,status='DRAFT',revision=revision+1 WHERE id=?",(encode(explicit.model_dump(mode='json',exclude_unset=True)),row['id']))
            connection.execute('DELETE FROM request_summaries WHERE request_id=?',(row['id'],))
            connection.execute("UPDATE requirement_help_tasks SET status='APPLIED',revision=revision+1 WHERE id=?",(task_id,))
            result={'task_id':task_id,'request_id':row['id'],'request_revision':row['revision']+1,'profile_revision':profile_revision,
                'message':'Mapping adopted. Regenerate and confirm the summary. Formal planning and checks have not run.'}
            return self._save(connection,user,body.command_key,'adopt',payload,task_id,result)
