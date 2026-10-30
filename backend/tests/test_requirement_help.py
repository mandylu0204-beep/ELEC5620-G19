"""HTTP/SQLite assistance lifecycle, isolated DB, no model transport."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.contracts.errors import ContractFailure
from app.storage.requirement_help import RequirementHelp,HelpCreate
from test_requests import web,draft,sign_in,FIELDS,confirm_body

def create(client,headers,**fields):
    row=draft(client,headers,FIELDS|{'preferences':['ready-to-eat meals'],'mandatory_constraints':['想要方便洗澡的设施']}|fields)
    state=row['requirement_help']
    body={'expected_revision':row['revision'],'expected_profile_revision':state['profile_revision'],'command_key':'help-create-command-0001'}
    reply=client.post('/api/v1/requests/'+row['request_id']+'/requirement-help',headers=headers,json=body)
    assert reply.status_code==201,reply.text
    return row,reply.json(),body

def decision(task,**patch):
    return {'expected_revision':task['revision'],'command_key':'help-review-command-0001','decision':'PROPOSE_MAPPING',
        'reason':'建议对应已有条件，请用户确认；不代表营地满足。','mappings':[{'field':item['field'],'index':item['index'],'original':item['text'],
        'canonical':{'preferences':'quiet','mandatory_constraints':'showers','accessibility_requirements':'step-free path'}[item['field']]}
        for item in task['snapshot']['items']]}|patch

def decide(client,task):
    founder=sign_in(client,'founder','CampMate-Founder-2026!')
    reply=client.post('/api/v1/requirement-help/'+task['task_id']+'/decision',headers=founder,json=decision(task))
    assert reply.status_code==200,reply.text
    repeat=client.post('/api/v1/requirement-help/'+task['task_id']+'/decision',headers=founder,json=decision(task))
    assert repeat.json()==reply.json()
    return reply.json()

def adopt(task):
    return {'expected_revision':task['request_revision'],'expected_profile_revision':task['profile_revision'],
        'expected_task_revision':task['revision'],'command_key':'help-adopt-command-0001'}

def test_known_other_aliases_need_no_assistance_and_catalogue_is_host_owned(web):
    app,client,headers=web
    catalogue=client.get('/api/v1/requirement-choices').json()
    assert catalogue==client.get('/api/v1/request-context').json()['requirement_choices']
    row=draft(client,headers,FIELDS|{'preferences':['希望安静','ready-to-eat meals'],'mandatory_constraints':['需要洗澡']})
    assert row['requirement_help']['needed'] is False
    reply=client.post('/api/v1/requests/'+row['request_id']+'/requirement-help',headers=headers,
        json={'expected_revision':1,'expected_profile_revision':1,'command_key':'known-help-command-0001'})
    assert reply.status_code==409
    reply=client.put('/api/v1/profile',headers=headers,json={'expected_revision':1,'profile':{'group_size':2,
        'accessibility_requirements':['需要无台阶通道','需要私人热水淋浴']}})
    assert reply.status_code==200,reply.text
    assert reply.json()['profile']['accessibility_requirements']==['step-free path','需要私人热水淋浴']

def test_unknown_is_blocked_before_runtime_or_paid_model_resolution(web,monkeypatch):
    app,client,headers=web;row,task,body=create(client,headers)
    monkeypatch.setattr(app.state.runtime,'resolve',lambda:pytest.fail('must not resolve runtime'))
    reply=client.post('/api/v1/requests/'+row['request_id']+'/interpret',headers=headers,json={'expected_revision':1})
    assert reply.status_code==409,reply.text
    assert '未调用模型' in reply.json()['error']['message']
    current=client.get('/api/v1/requests/'+row['request_id']).json()
    assert current['status']=='DRAFT' and current['summary'] is None and current['revision']==1

def test_duplicate_create_and_new_key_share_task_and_never_start_planning(web):
    app,client,headers=web;row,task,body=create(client,headers)
    path='/api/v1/requests/'+row['request_id']+'/requirement-help'
    assert client.post(path,headers=headers,json=body).json()==task
    assert client.post(path,headers=headers,json=body|{'command_key':'another-create-command-0001'}).json()==task
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM requirement_help_tasks').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM plans').fetchone()[0]==0

def test_ownership_roles_and_csrf_cannot_be_bypassed(web):
    app,client,headers=web;row,task,body=create(client,headers)
    path='/api/v1/requirement-help/'+task['task_id']
    assert client.post(path+'/decision',headers=headers,json=decision(task)).status_code==403
    other=sign_in(client,'camper.b','CampMate-B-2026!')
    assert client.get(path).status_code==404
    assert client.get('/api/v1/requirement-help').status_code==403
    assert client.post(path+'/adopt',headers=other,json=adopt(task)).status_code==404
    assert client.post('/api/v1/requests/'+row['request_id']+'/requirement-help',headers=other,json=body).status_code==404
    sign_in(client,'founder','CampMate-Founder-2026!')
    assert client.post(path+'/decision',json=decision(task)).status_code==403

def test_mapping_is_complete_exact_category_bounded_and_cannot_approve(web):
    app,client,headers=web;row,task,body=create(client,headers)
    founder=sign_in(client,'founder','CampMate-Founder-2026!')
    original=decision(task)['mappings'][0]
    for index,patch in enumerate([{'mappings':[]},{'mappings':[original|{'canonical':'quiet'}]},
        {'mappings':[original|{'original':'不同原文'}]},{'mappings':[original,original]},
        {'decision':'APPROVE'},{'reason':' '}]):
        reply=client.post('/api/v1/requirement-help/'+task['task_id']+'/decision',headers=founder,
            json=decision(task,**patch)|{'command_key':f'invalid-command-key-{index:04d}'})
        assert reply.status_code in {409,422},reply.text
    assert client.get('/api/v1/requirement-help/'+task['task_id']).json()['status']=='PENDING'

def test_suggestion_requires_owner_adoption_then_reanalysis_and_preserves_original_audit(web):
    app,client,headers=web
    assert client.put('/api/v1/profile',headers=headers,json={'expected_revision':1,'profile':{'group_size':2,
        'accessibility_requirements':['婴儿车方便通行']}}).status_code==200
    original=client.get('/api/v1/profile').json()
    row,task,body=create(client,headers,preferences=['ready-to-eat meals','尽量少喧闹'])
    proposed=decide(client,task);owner=sign_in(client)
    assert client.get('/api/v1/profile').json()==original
    assert client.get('/api/v1/requests/'+row['request_id']).json()['explicit_fields']==row['explicit_fields']
    path='/api/v1/requirement-help/'+task['task_id']+'/adopt';payload=adopt(proposed)
    first=client.post(path,headers=owner,json=payload)
    assert first.status_code==200,first.text
    assert client.post(path,headers=owner,json=payload).json()==first.json()
    current=client.get('/api/v1/requests/'+row['request_id']).json()
    assert current['status']=='DRAFT' and current['summary'] is None and current['confirmed_context'] is None
    assert current['explicit_fields']['mandatory_constraints']==['showers']
    assert current['explicit_fields']['preferences']==['ready-to-eat meals','quiet']
    profile=client.get('/api/v1/profile').json()
    assert profile['revision']==original['revision']+1
    assert profile['profile']['accessibility_requirements']==['step-free path']
    assert current['requirement_help']['needed'] is False
    assert client.post('/api/v1/requests/'+row['request_id']+'/confirm',headers=owner,json=confirm_body(current)).status_code==409
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM requirement_help_events').fetchone()[0]==3
        assert db.execute('SELECT COUNT(*) FROM plans').fetchone()[0]==0
    old=client.get('/api/v1/requirement-help/'+task['task_id']).json()
    assert old['snapshot']['items']==task['snapshot']['items']

@pytest.mark.parametrize('change',['request','profile','delete'])
def test_stale_profile_request_and_deleted_data_reject_late_adoption(web,change):
    app,client,headers=web;row,task,body=create(client,headers);proposed=decide(client,task);owner=sign_in(client)
    if change=='request':assert client.patch('/api/v1/requests/'+row['request_id'],headers=owner,
        json={'expected_revision':1,'raw_text':'changed','explicit_fields':row['explicit_fields']}).status_code==200
    elif change=='profile':assert client.put('/api/v1/profile',headers=owner,json={'expected_revision':1,'profile':{'group_size':3}}).status_code==200
    else:assert client.delete('/api/v1/requests/'+row['request_id'],headers=owner).status_code==204
    assert client.post('/api/v1/requirement-help/'+task['task_id']+'/adopt',headers=owner,json=adopt(proposed)).status_code in {404,409}
    sign_in(client,'founder','CampMate-Founder-2026!')
    assert client.get('/api/v1/requirement-help').json()['tasks']==[]
    if change=='delete':assert client.get('/api/v1/requirement-help/'+task['task_id']).status_code==404

def test_returned_requirement_has_no_adopt_or_approval_action(web):
    app,client,headers=web;row,task,body=create(client,headers)
    founder=sign_in(client,'founder','CampMate-Founder-2026!')
    reply=client.post('/api/v1/requirement-help/'+task['task_id']+'/decision',headers=founder,
        json=decision(task,decision='RETURN_FOR_DETAILS',mappings=[]))
    assert reply.status_code==200
    owner=sign_in(client)
    assert client.post('/api/v1/requirement-help/'+task['task_id']+'/adopt',headers=owner,json=adopt(reply.json())).status_code==409

def test_concurrent_create_is_deduplicated_and_changed_payload_cannot_reuse_key(web):
    app,client,headers=web
    row=draft(client,headers,FIELDS|{'mandatory_constraints':['其他特殊要求']})
    user=app.state.auth.authenticate(client.cookies.get('campmate_session'));service=RequirementHelp(app.state.database)
    def command(number):return service.create(user,row['request_id'],HelpCreate(expected_revision=1,
        expected_profile_revision=1,command_key=f'concurrent-help-command-{number:04d}'))
    with ThreadPoolExecutor(max_workers=2) as workers:one,two=list(workers.map(command,[1,2]))
    assert one['task_id']==two['task_id']
    with pytest.raises(ContractFailure):service.create(user,row['request_id'],HelpCreate(expected_revision=2,
        expected_profile_revision=1,command_key='concurrent-help-command-0001'))


def test_profile_change_between_preflight_and_analysis_is_checked_under_the_snapshot_transaction(web,monkeypatch):
    app,client,headers=web;row=draft(client,headers,FIELDS)
    original=app.state.runtime.resolve
    def changed():
        with app.state.database.transaction() as db:
            import json
            saved=db.execute("SELECT payload FROM profiles WHERE owner_id='camper-a'").fetchone()
            profile=json.loads(saved['payload']);profile['accessibility_requirements']=['尚未明确的无障碍要求']
            db.execute("UPDATE profiles SET payload=?,revision=revision+1 WHERE owner_id='camper-a'",(json.dumps(profile),))
        return original()
    monkeypatch.setattr(app.state.runtime,'resolve',changed)
    reply=client.post('/api/v1/requests/'+row['request_id']+'/interpret',headers=headers,json={'expected_revision':1})
    assert reply.status_code==409,reply.text
    current=client.get('/api/v1/requests/'+row['request_id']).json()
    assert current['status']=='DRAFT' and current['summary'] is None


def test_upgrade_from_eleven_preserves_profile_payload_revision_and_is_repeatable(web):
    app,client,headers=web;database=app.state.database
    with database.transaction() as db:
        before=[tuple(row) for row in db.execute('SELECT * FROM profiles')]
        for table in ['review_assistance_commands','review_assistance_notes','revision_choice_commands','revision_proposals','requirement_help_events','requirement_help_commands','requirement_help_tasks']:
            db.execute('DROP TABLE '+table)
        db.execute('DELETE FROM schema_migrations WHERE version>=12')
    database.initialize();database.initialize()
    with database.transaction(write=False) as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM profiles')]==before
        assert [row[0] for row in db.execute('SELECT version FROM schema_migrations ORDER BY version')]==list(range(1,15))
    assert database.ready()


def test_original_help_snapshot_events_and_command_receipts_are_immutable(web):
    app,client,headers=web;row,task,body=create(client,headers)
    for sql in ["UPDATE requirement_help_tasks SET snapshot='{}'",
        "UPDATE requirement_help_events SET payload='{}'","DELETE FROM requirement_help_events",
        "UPDATE requirement_help_commands SET result='{}'","DELETE FROM requirement_help_commands"]:
        with pytest.raises(ContractFailure):
            with app.state.database.transaction() as db:db.execute(sql)
    assert client.get('/api/v1/requirement-help/'+task['task_id']).json()['snapshot']==task['snapshot']
