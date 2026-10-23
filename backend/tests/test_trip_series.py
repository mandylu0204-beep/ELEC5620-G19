"""Real rules/HTTP in isolated SQLite. Raw responses for every permission check."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import time

from fastapi.testclient import TestClient
import pytest

from app.auth import User
from app.contracts.errors import ContractFailure
from app.main import create_app
from app.storage.trip_series import SuccessorInput, TripSeriesService
from test_agent_runtime import dataset, settings, confirmed
from test_finalisation import command as final_command
from test_plan_changes import change
from test_requests import sign_in
from test_reviews import command as review_command
from plan_fixtures import create


def wait(client, run_id):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        response=client.get('/api/v1/runs/'+run_id)
        assert response.status_code==200,response.text
        value=response.json()
        if value['run']['status'] in {'FAILED','SUCCEEDED'}:
            assert value['run']['status']=='SUCCEEDED',value['run']['error']
            return value
        time.sleep(.005)
    pytest.fail('offline run timed out')


def start(client, headers, record, key):
    result=client.post('/api/v1/requests/'+record['request_id']+'/plan',headers=headers,
        json={'expected_request_revision':record['revision'],'command_key':key})
    assert result.status_code==202,result.text
    return result.json()


@pytest.fixture
def web(dataset,tmp_path):
    app=create_app(settings(dataset,tmp_path))
    with TestClient(app) as client:
        headers=sign_in(client)
        record=confirmed(client,headers)
        original=wait(client,start(client,headers,record,'series-original-plan-key')['run_id'])
        yield app,client,headers,original


def origin(detail,key='series-successor-command'):
    return {'command_key':key,'expected_series_revision':(detail.get('trip_series') or {}).get('series_revision',0),
        'expected_current_version_id':detail['plan']['current_version_id'],
        'expected_version_revision':detail['current_version_revision'],
        'expected_active_run_id':detail['run']['run_id'],'expected_run_revision':detail['run']['revision']}


def successor(client,headers,detail,key='series-successor-command'):
    response=client.post('/api/v1/plans/'+detail['plan']['plan_id']+'/successor-requests',headers=headers,json=origin(detail,key))
    assert response.status_code==201,response.text
    return response.json()


def preview(client,headers,record):
    response=client.post('/api/v1/requests/'+record['request_id']+'/interpret',headers=headers,json={'expected_revision':record['revision']})
    assert response.status_code==200,response.text
    return response.json()


def confirm(client,headers,record,key='series-confirm-command'):
    response=client.post('/api/v1/requests/'+record['request_id']+'/confirm',headers=headers,
        json={'expected_revision':record['revision'],'command_key':key,'acknowledged':True})
    assert response.status_code==200,response.text
    return response.json()


def update_profile(client,headers,**changes):
    saved=client.get('/api/v1/profile').json()
    profile={**saved['profile'],**changes};profile.pop('profile_id',None)
    response=client.put('/api/v1/profile',headers=headers,json={'expected_revision':saved['revision'],'profile':profile})
    assert response.status_code==200,response.text
    return response.json()


def assert_public(value):
    forbidden={'trace','usage','http_attempts','configuration_fingerprint','configuration_summary','selection_config','file_digests','model_planning_trace','prompt_sha256','requested_model'}
    if isinstance(value,dict):
        assert not value.keys()&forbidden,value.keys()&forbidden
        for child in value.values():assert_public(child)
    elif isinstance(value,list):
        for child in value:assert_public(child)


def test_adopt_revision_same_series_preserves_final_snapshot_and_receipts(web):
    app,client,headers,old=web
    saved=client.post('/api/v1/plans/'+old['plan']['plan_id']+'/finalise',headers=headers,json=final_command(old))
    assert saved.status_code==200,saved.text
    final_path='/api/v1/plans/'+old['plan']['plan_id']+'/finals/'+saved.json()['final_id']
    snapshot=client.get(final_path).json()['final_record']
    old=client.get('/api/v1/plans/'+old['plan']['plan_id']).json()
    raw_before={}
    with app.state.database.transaction(write=False) as db:
        for table,column in [('versions','content'),('assessments','payload'),('final_records','payload')]:
            raw_before[table]=[tuple(row) for row in db.execute(f'SELECT id,{column} FROM {table} ORDER BY id')]
    updated=update_profile(client,headers,experience_level='EXPERIENCED')
    draft=successor(client,headers,old)
    assert successor(client,headers,old)==draft
    record=preview(client,headers,draft)
    assert record['profile_revision']==updated['revision']
    assert record['profile_snapshot']['experience_level']=='EXPERIENCED'
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM plans').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==1
    request=confirm(client,headers,record)
    update_profile(client,headers,experience_level='ADVANCED')
    ids=start(client,headers,request,'series-new-plan-command')
    assert start(client,headers,request,'series-new-plan-command')==ids
    new=wait(client,ids['run_id'])
    assert new['confirmed_context']['profile_snapshot']['experience_level']=='EXPERIENCED'
    assert new['trip_series']['trip_series_id']==old['trip_series']['trip_series_id']
    series=client.get('/api/v1/trip-series').json()
    assert len(series['trip_series'])==1 and series['independent_plans']==[]
    card=series['trip_series'][0]
    assert card['current_plan']['plan_id']==ids['plan_id']
    assert [row['plan_id'] for row in card['history']]==[old['plan']['plan_id']]
    assert card['last_final']['plan_id']==old['plan']['plan_id'] and not card['last_final']['is_current']
    assert client.get(final_path).json()['final_record']==snapshot
    assert not client.get(final_path).json()['is_current']
    historical=client.get('/api/v1/plans/'+old['plan']['plan_id']).json()
    assert not historical['finalisation_available'] and not historical['reassessment_available']
    assert change(client,headers,historical).status_code==409
    assert client.post('/api/v1/plans/'+old['plan']['plan_id']+'/finalise',headers=headers,json=final_command(old)).status_code==409
    assert_public(series);assert_public(new);assert_public(client.get(final_path).json())
    # Replaying a successor-create receipt after confirmation must ALSO project
    # its now-confirmed request; never leak internal dataset configuration.
    repeated=client.post('/api/v1/plans/'+old['plan']['plan_id']+'/successor-requests',headers=headers,json=origin(old))
    assert repeated.status_code==201;assert_public(repeated.json())
    with app.state.database.transaction(write=False) as db:
        for table,column in [('versions','content'),('assessments','payload'),('final_records','payload')]:
            actual={row['id']:row[column] for row in db.execute(f'SELECT id,{column} FROM {table}')}
            assert all(actual[key]==value for key,value in raw_before[table])


def test_profile_revision_conflict_cancel_and_duplicate_confirmation(web):
    app,client,headers,old=web
    record=preview(client,headers,successor(client,headers,old))
    update_profile(client,headers,experience_level='EXPERIENCED')
    path='/api/v1/requests/'+record['request_id']
    body={'expected_revision':record['revision'],'command_key':'series-stale-confirm-key','acknowledged':True}
    assert client.post(path+'/confirm',headers=headers,json=body).json()['error']['code']=='VERSION_CONFLICT'
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==1
        assert db.execute('SELECT status FROM requests WHERE id=?',(record['request_id'],)).fetchone()[0]=='AWAITING_CONFIRMATION'
    record=preview(client,headers,record)
    confirmed=confirm(client,headers,record)
    assert confirm(client,headers,record)==confirmed
    assert confirmed['profile_revision']==2


def test_repeated_meal_summary_edits_keep_one_update_request_and_one_trip(web):
    app,client,headers,old=web
    before=deepcopy(old['confirmed_context'])
    draft=successor(client,headers,old,'meal-update-create-command')
    assert draft['source_profile_snapshot']==before['profile_snapshot']
    assert draft['source_requirements']==before['requirements']
    assert_public(draft)
    request_id=draft['request_id'];path='/api/v1/requests/'+request_id
    for meal in ('self-catered meals','ready-to-eat meals','self-catered meals'):
        fields={**before['requirements'],'preferences':[meal,'quiet']}
        response=client.patch(path,headers=headers,json={'raw_text':draft['raw_text'],'explicit_fields':fields,'expected_revision':draft['revision']})
        assert response.status_code==200,response.text
        draft=preview(client,headers,response.json())
        assert draft['request_id']==request_id
        assert draft['source_requirements']==before['requirements']
        assert_public(draft)
        with app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]==2
            assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==1
    rows=client.get('/api/v1/requests').json()['requests']
    updates=[row for row in rows if row['is_trip_update']]
    assert len(updates)==1 and updates[0]['trip_series_id']==old['trip_series']['trip_series_id']
    confirmed_record=confirm(client,headers,draft,'meal-update-confirm-command')
    ids=start(client,headers,confirmed_record,'meal-update-plan-command')
    new=wait(client,ids['run_id'])
    assert new['trip_series']['predecessor_plan_id']==old['plan']['plan_id']
    series=client.get('/api/v1/trip-series').json()
    assert len(series['trip_series'])==1 and not series['independent_plans']
    assert len(series['trip_series'][0]['history'])==1
    assert client.get('/api/v1/plans/'+old['plan']['plan_id']).json()['confirmed_context']==before
    stale_edit=client.patch(path,headers=headers,json={'raw_text':'late edit','explicit_fields':fields,'expected_revision':confirmed_record['revision']})
    assert stale_edit.status_code==409


def test_saved_profile_does_not_rewrite_update_origin_or_start_a_run(web):
    app,client,headers,old=web
    draft=successor(client,headers,old,'profile-update-preview-command')
    original_profile=deepcopy(draft['source_profile_snapshot'])
    update_profile(client,headers,experience_level='EXPERIENCED')
    first=preview(client,headers,draft)
    assert first['source_profile_snapshot']==original_profile
    assert first['profile_snapshot']['experience_level']=='EXPERIENCED'
    assert first['profile_revision']==2
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==1
    update_profile(client,headers,experience_level='ADVANCED')
    failed=client.post('/api/v1/requests/'+draft['request_id']+'/confirm',headers=headers,
        json={'expected_revision':first['revision'],'command_key':'profile-update-conflict-command','acknowledged':True})
    assert failed.status_code==409 and failed.json()['error']['code']=='VERSION_CONFLICT'
    assert_public(client.get('/api/v1/requests/'+draft['request_id']).json())


def test_deleted_source_cannot_be_edited_or_expose_original_profile(web):
    _,client,headers,old=web
    draft=successor(client,headers,old,'deleted-source-update-command')
    assert client.delete('/api/v1/plans/'+old['plan']['plan_id'],headers=headers).status_code==204
    read=client.get('/api/v1/requests/'+draft['request_id']).json()
    assert read['predecessor_plan_id'] is None and 'source_profile_snapshot' not in read
    edit=client.patch('/api/v1/requests/'+draft['request_id'],headers=headers,
        json={'raw_text':'cannot revive','explicit_fields':old['confirmed_context']['requirements'],'expected_revision':draft['revision']})
    assert edit.status_code==404


def test_competing_successors_and_start_receipt_are_atomic(web):
    app,client,headers,old=web
    records=[confirm(client,headers,preview(client,headers,successor(client,headers,old,'create-successor-'+str(i)*16)),'confirm-successor-'+str(i)*16) for i in range(2)]
    user=User('camper-a','camper.a','Camper A','CAMPER')
    runtime=app.state.runtime.resolve()
    def begin(record):
        try:return app.state.repository.begin_run(user,record['request_id'],runtime.demo,runtime.dataset,
            command_key='plan-'+record['request_id'],expected_request_revision=record['revision'],single_plan=True)
        except ContractFailure as exc:return exc.error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(begin,records))
    assert sum(not isinstance(row,str) for row in results)==1
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM plans').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM series_replacements').fetchone()[0]==1


def test_successor_command_concurrency_ownership_deletion_and_independent_trip(web):
    app,client,headers,old=web
    user=User('camper-a','camper.a','Camper A','CAMPER');service=TripSeriesService(app.state.database)
    body=SuccessorInput.model_validate(origin(old))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:service.create_successor(user,old['plan']['plan_id'],body),range(2)))
    assert results[0]['request_id']==results[1]['request_id']
    other=sign_in(client,'camper.b','CampMate-B-2026!')
    assert client.post('/api/v1/plans/'+old['plan']['plan_id']+'/successor-requests',headers=other,json=origin(old)).status_code==404
    assert client.get('/api/v1/trip-series/'+old['trip_series']['trip_series_id']).status_code==404
    headers=sign_in(client)
    original_request=client.get('/api/v1/requests/'+old['plan']['request_id']).json()
    independent=client.post('/api/v1/requests',headers=headers,json={'raw_text':original_request['raw_text'],'explicit_fields':original_request['confirmed_context']['requirements']}).json()
    independent=confirm(client,headers,preview(client,headers,independent),'independent-confirm-key')
    wait(client,start(client,headers,independent,'independent-plan-command')['run_id'])
    assert len(client.get('/api/v1/trip-series').json()['trip_series'])==2
    assert client.delete('/api/v1/plans/'+old['plan']['plan_id'],headers=headers).status_code==204
    assert client.post('/api/v1/plans/'+old['plan']['plan_id']+'/successor-requests',headers=headers,json=origin(old)).status_code==404
    card=client.get('/api/v1/trip-series/'+old['trip_series']['trip_series_id']).json()
    assert card['current_plan'] is None and card['history']==[]


def test_delete_history_current_and_whole_series_never_resurrects_old_records(web):
    app,client,headers,old=web
    new=wait(client,start(client,headers,confirm(client,headers,preview(client,headers,successor(client,headers,old))),'delete-series-plan-command')['run_id'])
    series_id=new['trip_series']['trip_series_id']
    assert client.delete('/api/v1/plans/'+old['plan']['plan_id'],headers=headers).status_code==204
    value=client.get('/api/v1/trip-series/'+series_id).json()
    assert value['history']==[] and value['current_plan']['plan_id']==new['plan']['plan_id']
    assert client.get('/api/v1/runs/'+old['run']['run_id']).status_code==404
    assert client.delete('/api/v1/plans/'+new['plan']['plan_id'],headers=headers).status_code==204
    value=client.get('/api/v1/trip-series/'+series_id).json()
    assert value['current_plan'] is None and value['history']==[]
    command={'command_key':'delete-whole-trip-series','expected_series_revision':value['revision']}
    path='/api/v1/trip-series/'+series_id+'/delete'
    assert client.post(path,headers=headers,json=command).status_code==204
    assert client.post(path,headers=headers,json=command).status_code==204
    assert client.get('/api/v1/trip-series/'+series_id).status_code==404
    assert client.get('/api/v1/requests/'+new['plan']['request_id']).status_code==404
    assert client.get('/api/v1/trip-series').json()=={'trip_series':[],'independent_plans':[]}


def test_replaced_review_task_rejects_late_decisions_and_does_not_inherit_approval(web):
    app,client,headers,_=web
    camper=User('camper-a','camper.a','Camper A','CAMPER')
    scope,_=create(app.state.repository,camper,'series-risk-review','review')
    founder=sign_in(client,'founder','CampMate-Founder-2026!')
    old_review=client.get('/api/v1/review/'+scope.plan_id).json()
    body=review_command(old_review)
    assert old_review['review_available']
    # A new independent request is not a waiver; actual new results decide its
    # approval requirement. For lineage guard testing, start the successor from
    # its already-confirmed immutable request without executing the fixture data.
    headers=sign_in(client)
    old=client.get('/api/v1/plans/'+scope.plan_id).json()
    draft=successor(client,headers,old,'replace-review-command')
    from app.storage.repository import encode
    with app.state.database.transaction() as db:
        original=db.execute('SELECT confirmed_context FROM requests WHERE id=?',(scope.request_id,)).fetchone()[0]
        context=__import__('json').loads(original);context['request_id']=draft['request_id']
        db.execute("UPDATE requests SET status='CONFIRMED',confirmed_context=?,revision=2 WHERE id=?",(encode(context),draft['request_id']))
    new_scope=app.state.repository.begin_run(camper,draft['request_id'],scope.demo_context,scope.dataset_context,command_key='replace-review-plan-command',single_plan=True)
    founder=sign_in(client,'founder','CampMate-Founder-2026!')
    assert all(row['plan_id']!=scope.plan_id for row in client.get('/api/v1/review-queue').json()['reviews'])
    assert client.post('/api/v1/review/'+scope.plan_id,headers=founder,json=body).status_code==409
    assert not client.get('/api/v1/review/'+scope.plan_id).json()['review_available']
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM reviews WHERE run_id=?',(new_scope.run_id,)).fetchone()[0]==0


def test_successor_recovery_reuses_saved_version_and_pinned_profile_after_personal_edit(dataset,tmp_path,monkeypatch):
    from dataclasses import replace
    from app.application.agent_runtime import DATASET_AGENT_FACTORIES
    from test_agent_runtime import KEY
    from test_rule_orchestration import FailOnce
    from test_planning_entry import retry,wait_run
    factory=DATASET_AGENT_FACTORIES[KEY];control={'fail_next':False}
    class Wrapper:
        def __init__(self,agent):self.agent=agent
        def __getattr__(self,name):return getattr(self.agent,name)
        async def orchestrate(self,input,port):
            if control['fail_next']:
                control['fail_next']=False;port=FailOnce(port,'append_plan_version',after=True)
            return await self.agent.orchestrate(input,port)
    def binding(config,descriptor):
        result=factory(config,descriptor)
        return replace(result,agent=Wrapper(result.agent))
    monkeypatch.setitem(DATASET_AGENT_FACTORIES,KEY,binding)
    app=create_app(settings(dataset,tmp_path))
    with TestClient(app) as client:
        headers=sign_in(client);old=wait(client,start(client,headers,confirmed(client,headers),'recovery-old-plan-command')['run_id'])
        request=confirm(client,headers,preview(client,headers,successor(client,headers,old)))
        control['fail_next']=True
        ids=start(client,headers,request,'recovery-successor-plan-key')
        failed=wait_run(client,ids['run_id'],'FAILED')
        version=failed['version']['version_context']['plan_version_id']
        content=failed['version']['content'];pinned=failed['confirmed_context']['profile_snapshot']
        update_profile(client,headers,group_size=9)
        assert retry(client,headers,failed).status_code==202
        completed=wait(client,ids['run_id'])
        assert completed['version']['version_context']['plan_version_id']==version
        assert completed['version']['content']==content
        assert completed['confirmed_context']['profile_snapshot']==pinned
        assert pinned['group_size']==2
        with app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0]==2


def test_active_run_and_changed_source_reject_successor_and_whole_delete(web):
    app,client,headers,old=web
    body=origin(old)
    # Stale exact evidence is rejected before any successor draft is created.
    assert client.post('/api/v1/plans/'+old['plan']['plan_id']+'/successor-requests',headers=headers,
        json={**body,'expected_run_revision':body['expected_run_revision']+1}).status_code==409
    assert client.post('/api/v1/plans/'+old['plan']['plan_id']+'/successor-requests',headers=headers,
        json={**body,'expected_series_revision':99}).status_code==409
    with app.state.database.transaction() as db:
        db.execute("UPDATE runs SET status='RUNNING',revision=revision+1 WHERE id=?",(old['run']['run_id'],))
    assert client.post('/api/v1/plans/'+old['plan']['plan_id']+'/successor-requests',headers=headers,
        json={**body,'expected_run_revision':body['expected_run_revision']+1}).status_code==409
    assert client.post('/api/v1/trip-series/'+old['trip_series']['trip_series_id']+'/delete',headers=headers,
        json={'command_key':'active-delete-series-key','expected_series_revision':old['trip_series']['series_revision']}).status_code==409
