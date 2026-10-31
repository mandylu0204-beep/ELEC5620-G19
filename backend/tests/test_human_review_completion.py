"""Human follow-up, history and static PDF; isolated SQLite and no model IO."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pypdf import PdfReader
import pytest

from app.auth import User
from app.contracts.errors import ContractFailure
from app.storage.database import Database
from app.storage.review_assistance import AssistanceInput, ReviewAssistance
from app.storage.review_followup import revision_feedback
from app.application.final_pdf import render_final_pdf
from plan_fixtures import create,call
from test_agent_runtime import dataset
from test_reviews import review_client,command as review_command
from test_finalisation import final_client,command as final_command,finish_new_run
from test_requests import sign_in
from test_requirement_help import web,create as create_help,decision as help_decision


def assistance(detail,**patch):
    return review_command(detail)|{'decision':'WAITING_EVIDENCE','problem':'Weather information does not cover trip dates.',
        'reason':'Use only the registered date range.','next_action':'Wait for information updates, then explicitly start formal checks.',
        'recheck_on':'2026-10-21','command_key':'assistance-command-0001'}|patch


def test_assistance_is_append_only_bound_and_never_changes_eligibility(review_client):
    client,app,camper,headers=review_client
    scope,_=create(app.state.repository,camper,'help-evidence','missing')
    path='/api/v1/review/'+scope.plan_id
    before=client.get(path).json();assert before['assistance_available'] and not before['review_available']
    original=deepcopy(before)
    body=assistance(before)
    reply=client.post(path+'/assistance',headers=headers,json=body)
    assert reply.status_code==200,reply.text
    note=reply.json();assert note['is_approval'] is False
    assert client.post(path+'/assistance',headers=headers,json=body).json()==note
    assert client.post(path+'/assistance',headers=headers,json=body|{'reason':'Different reason'}).status_code==409
    after=client.get(path).json()
    assert after['review_assistance_notes']==[note]
    queued=client.get('/api/v1/assistance-queue').json()['plans'][0]
    assert queued['last_assistance']['decision']=='WAITING_EVIDENCE'
    for key in ['assessments','eligibility','route','version','reviews']:assert after[key]==original[key]
    assert not after['eligibility']['eligible'] and not after['review_available']
    own=sign_in(client)
    visible=client.get('/api/v1/plans/'+scope.plan_id).json()
    assert visible['review_assistance_notes']==[note]
    assert 'model_diagnostics' not in visible
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==0
    for sql in ['UPDATE review_assistance_notes SET payload=payload','DELETE FROM review_assistance_notes',
        'UPDATE review_assistance_commands SET result=result','DELETE FROM review_assistance_commands']:
        with pytest.raises(ContractFailure),app.state.database.transaction() as db:db.execute(sql)


@pytest.mark.parametrize('change',[{'problem':' '},{'reason':' '},{'next_action':' '},{'recheck_on':'2026-01-01'},
    {'expected_run_revision':999},{'assessment_ids':['wrong','wrong']}])
def test_assistance_rejects_incomplete_or_stale_commands(review_client,change):
    client,app,camper,headers=review_client
    scope,_=create(app.state.repository,camper,'invalid-note','missing')
    path='/api/v1/review/'+scope.plan_id
    detail=client.get(path).json()
    assert client.post(path+'/assistance',headers=headers,json=assistance(detail,**change)).status_code in {409,422}
    assert not client.get(path).json().get('review_assistance_notes')


def test_assistance_roles_risk_tasks_and_transaction_failure(review_client):
    client,app,camper,headers=review_client
    risk,_=create(app.state.repository,camper,'risk-no-notes','review')
    path='/api/v1/review/'+risk.plan_id
    assert not client.get(path).json()['assistance_available']
    assert client.post(path+'/assistance',headers=headers,json=assistance(client.get(path).json())).status_code==409
    scope,_=create(app.state.repository,camper,'rollback-note','missing')
    path='/api/v1/review/'+scope.plan_id;body=assistance(client.get(path).json())
    assert client.post(path+'/assistance',json=body).status_code==403
    with app.state.database.transaction() as db:
        db.execute("CREATE TRIGGER fail_note_receipt BEFORE INSERT ON review_assistance_commands BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
    assert client.post(path+'/assistance',headers=headers,json=body).status_code>=400
    with app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM review_assistance_notes').fetchone()[0]==0
    other=sign_in(client,'camper.b','CampMate-B-2026!')
    assert client.get('/api/v1/plans/'+scope.plan_id).status_code==404
    assert client.post(path+'/assistance',headers=other,json=body).status_code==403


def test_assistance_duplicate_threads_and_stale_result_are_guarded(review_client):
    client,app,camper,headers=review_client
    scope,version=create(app.state.repository,camper,'concurrent-note','missing')
    detail=client.get('/api/v1/review/'+scope.plan_id).json();body=AssistanceInput.model_validate(assistance(detail))
    founder=User('founder','founder','Founder','FOUNDER');service=ReviewAssistance(app.state.database)
    with ThreadPoolExecutor(2) as pool:
        replies=list(pool.map(lambda _:service.submit(founder,scope.plan_id,body),range(2)))
    assert replies[0]==replies[1]
    app.state.repository.begin_run(camper,scope.request_id,scope.demo_context,scope.dataset_context,
        plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=version.version_context.plan_version_id)
    with pytest.raises(ContractFailure):service.submit(founder,scope.plan_id,body)


def test_revision_uses_authoritative_review_reason_and_rejects_unrelated_or_old_sources(review_client):
    client,app,camper,headers=review_client
    scope,version=create(app.state.repository,camper,'review-revision','review')
    path='/api/v1/review/'+scope.plan_id
    detail=client.get(path).json()
    reply=client.post(path,headers=headers,json=review_command(detail,'REQUEST_REVISION')).json()['review']
    body=SimpleNamespace(expected_active_run_id=scope.run_id,expected_current_version_id=version.version_context.plan_version_id,
        source_review_id=reply['review_id'],feedback='Keep the confirmed budget and revise using this feedback.',command_key='review-helper-command-0001')
    before=client.get(path).json()
    value=revision_feedback(app.state.database,camper,scope.plan_id,body)
    assert reply['review_id'] in value and reply['reason'] in value and body.feedback in value
    assert client.get(path).json()==before
    with pytest.raises(ContractFailure):revision_feedback(app.state.database,camper,scope.plan_id,SimpleNamespace(**(vars(body)|{'feedback':'x'*4000})))
    with pytest.raises(ContractFailure):revision_feedback(app.state.database,camper,scope.plan_id,SimpleNamespace(**(vars(body)|{'source_review_id':'not-this-review'})))
    with pytest.raises(ContractFailure):revision_feedback(app.state.database,User('camper-b','camper.b','B','CAMPER'),scope.plan_id,body)
    app.state.repository.begin_run(camper,scope.request_id,scope.demo_context,scope.dataset_context,
        plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=version.version_context.plan_version_id)
    with pytest.raises(ContractFailure):revision_feedback(app.state.database,camper,scope.plan_id,body)


def test_review_history_is_paginated_and_old_results_are_read_only(review_client):
    client,app,camper,headers=review_client
    scope,version=create(app.state.repository,camper,'history-reviewed','review')
    path='/api/v1/review/'+scope.plan_id
    reply=client.post(path,headers=headers,json=review_command(client.get(path).json(),'APPROVE'))
    assert reply.status_code==200
    history=client.get('/api/v1/review-history?decision=APPROVE&limit=1').json()
    assert history['total']==1 and len(history['reviews'])==1
    assert history['reviews'][0]['is_current_result']
    old=client.get('/api/v1/plans/'+scope.plan_id)  # Founder is not the owner.
    assert old.status_code==403
    original=app.state.plan_queries.detail(camper,scope.plan_id)
    newer=app.state.repository.begin_run(camper,scope.request_id,scope.demo_context,scope.dataset_context,
        plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=version.version_context.plan_version_id)
    finish_new_run(app,camper,newer,original)
    history=client.get('/api/v1/review-history').json()
    assert not history['reviews'][0]['is_current_result']
    past=client.get(path+'?run_id='+scope.run_id)
    assert past.status_code==200,past.text
    assert past.json()['review_scope']=='HISTORY' and not past.json()['review_available'] and not past.json()['assistance_available']
    assert client.get('/api/v1/review-history?offset=1&limit=1').json()['reviews']==[]
    sign_in(client)
    assert client.get('/api/v1/review-history').status_code==403


def test_unsupported_help_has_specific_next_action_and_can_never_be_adopted(web):
    app,client,headers=web
    row,task,_=create_help(client,headers)
    founder=sign_in(client,'founder','CampMate-Founder-2026!')
    body=help_decision(task,decision='UNSUPPORTED',mappings=[],feedback_version='structured-help-feedback-1',
        problem='Existing data cannot verify this qualifier.',next_action='Choose an existing condition or keep a draft.')
    assert client.post('/api/v1/requirement-help/'+task['task_id']+'/decision',headers=founder,json=body|{'next_action':' '}).status_code==422
    result=client.post('/api/v1/requirement-help/'+task['task_id']+'/decision',headers=founder,json=body)
    assert result.status_code==200,result.text
    assert result.json()['status']=='RETURNED' and result.json()['response']['decision']=='UNSUPPORTED'
    assert client.get('/api/v1/requirement-help?history=true').json()['tasks'][0]['response']['next_action']==body['next_action']
    own=sign_in(client)
    adopt={'expected_revision':row['revision'],'expected_profile_revision':task['profile_revision'],
        'expected_task_revision':result.json()['revision'],'command_key':'unsupported-adopt-command'}
    assert client.post('/api/v1/requirement-help/'+task['task_id']+'/adopt',headers=own,json=adopt).status_code==409
    assert client.post('/api/v1/requests/'+row['request_id']+'/interpret',headers=own,json={'expected_revision':row['revision']}).status_code==409


def test_pdf_only_exports_authorised_saved_final_without_diagnostics_or_mutation(final_client,tmp_path,monkeypatch):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'pdf-final','complete')
    path='/api/v1/plans/'+scope.plan_id
    detail=client.get(path).json()
    final=client.post(path+'/finalise',headers=headers,json=final_command(detail)).json()
    final_path=path+'/finals/'+final['final_id']
    original=client.get(final_path).json()
    response=client.get(final_path+'/pdf')
    assert response.status_code==200 and response.headers['content-type']=='application/pdf'
    assert response.content.startswith(b'%PDF-') and 'attachment' in response.headers['content-disposition']
    assert client.get(final_path).json()==original
    reader=PdfReader(BytesIO(response.content))
    fonts=[font.get_object() for page in reader.pages for font in page['/Resources']['/Font'].values()]
    assert any('/FontDescriptor' in font and '/FontFile2' in font['/FontDescriptor'] for font in fonts)
    text='\n'.join(page.extract_text() for page in reader.pages)
    for expected in ['Saved final plan','Version ID','Costs and budget','Equipment checklist','Saved safety assessments','Source date',final['final_id']]:assert expected in text
    private=deepcopy(original['final_record']);private['model_diagnostics']={'requested_model':'DO_NOT_EXPORT_PRIVATE_MODEL','usage':{'private_token_usage':777}}
    private['confirmed_context']['dataset_context']['selection_config']={'secret_fingerprint':'DO_NOT_EXPORT_FINGERPRINT'}
    pdf=render_final_pdf(private,is_current=False)
    extracted='\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    assert 'Historical final record' in extracted
    assert 'DO_NOT_EXPORT' not in extracted and 'private_token_usage' not in extracted
    (tmp_path/'final.pdf').write_bytes(response.content)
    from app.application import final_pdf
    monkeypatch.setattr(final_pdf,'render_final_pdf',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('private failure')))
    failure=client.get(final_path+'/pdf')
    assert failure.status_code>=400 and 'private failure' not in failure.text
    assert client.get(final_path).json()==original
    other=sign_in(client,'camper.b','CampMate-B-2026!')
    assert client.get(final_path+'/pdf').status_code==404
    sign_in(client,'founder','CampMate-Founder-2026!')
    assert client.get(final_path+'/pdf').status_code==403


def test_draft_and_rejected_versions_have_no_final_pdf(final_client):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'not-final','review')
    assert client.get('/api/v1/plans/'+scope.plan_id+'/finals/not-final/pdf').status_code==404
    founder=sign_in(client,'founder','CampMate-Founder-2026!')
    path='/api/v1/review/'+scope.plan_id
    assert client.post(path,headers=founder,json=review_command(client.get(path).json(),'REJECT')).status_code==200
    sign_in(client)
    assert client.get('/api/v1/plans/'+scope.plan_id+'/finals/not-final/pdf').status_code==404


def test_migration_fourteen_preserves_schema_thirteen_and_saved_records(tmp_path):
    database=Database(tmp_path/'upgrade.sqlite3');database.initialize()
    with database.transaction() as db:
        db.execute('DROP TABLE review_assistance_commands');db.execute('DROP TABLE review_assistance_notes')
        db.execute('DELETE FROM schema_migrations WHERE version=14')
        before=[tuple(row) for row in db.execute('SELECT * FROM schema_migrations')]
    assert not database.ready()
    database.initialize();database.initialize()
    assert database.ready()
    with database.transaction(write=False) as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM schema_migrations WHERE version<=13')]==before
        assert db.execute('SELECT COUNT(*) FROM review_assistance_notes').fetchone()[0]==0


def test_public_review_linked_revision_keeps_known_goals_and_feedback_pinned(dataset,tmp_path):
    from test_agent_runtime import settings
    from test_plan_changes import start_complete,change_fact,command
    from test_planning_entry import wait_run
    from app.main import create_app
    from app.contracts.revision_feedback import PREFIX,revision_goal
    change_fact(dataset,'WEATHER',summary='Strong wind in this synthetic scenario.')
    app=create_app(settings(dataset,tmp_path))
    with TestClient(app) as client:
        owner=sign_in(client);initial=start_complete(client,owner)
        founder=sign_in(client,'founder','CampMate-Founder-2026!')
        review_path='/api/v1/review/'+initial['plan']['plan_id']
        review=client.post(review_path,headers=founder,json=review_command(client.get(review_path).json(),'REQUEST_REVISION')).json()['review']
        owner=sign_in(client);old=client.get('/api/v1/plans/'+initial['plan']['plan_id']).json()
        body=command(old,feedback='change campsite',key='review-linked-public-command')|{'source_review_id':review['review_id']}
        response=client.post('/api/v1/plans/'+old['plan']['plan_id']+'/revision-proposals',headers=owner,json=body)
        assert response.status_code==202,response.text
        candidate=wait_run(client,response.json()['run_id'],'SUCCEEDED')
        assert client.post('/api/v1/plans/'+old['plan']['plan_id']+'/revision-proposals',headers=owner,json=body).json()==response.json()
        assert candidate['version']['content']['selected_campsite_ids']!=old['version']['content']['selected_campsite_ids']
        with app.state.database.transaction(write=False) as db:
            scope=json.loads(db.execute('SELECT scope FROM runs WHERE id=?',(response.json()['run_id'],)).fetchone()[0])
        feedback=scope['dataset_context']['selection_config']['a_revision_feedback']
        assert feedback.startswith(PREFIX) and review['review_id'] in feedback and review['reason'] in feedback
        assert revision_goal(feedback)=='change campsite'
        assert not candidate['reviews'] and not candidate['finalisation_available']
        current=client.get('/api/v1/plans/'+old['plan']['plan_id']).json()
        assert current['version']['version_context']['plan_version_id']==old['version']['version_context']['plan_version_id']


@pytest.mark.parametrize('goal',['change campsite','cheaper campsite','Change campsite','Cheaper campsite'])
def test_linked_review_keeps_exact_host_goals_and_malformed_envelopes_have_no_authority(goal):
    from app.contracts.revision_feedback import linked_feedback,revision_goal,PREFIX
    review={'review_id':'source','version_context':{'plan_version_id':'version'},'reason':'A reason with a fake footer: change campsite'}
    assert revision_goal(linked_feedback(review,goal))==goal.casefold()
    for value in [PREFIX+'[]',PREFIX+'null',PREFIX+'{}',PREFIX+'{"camper_instructions":true}']:
        assert revision_goal(value)==value.strip().casefold()



def test_linked_review_model_payload_excludes_workflow_ids_and_deduplicates_adopted_reason():
    import asyncio
    from copy import copy
    from app.contracts.revision_feedback import linked_feedback
    from test_model_revision_reassessment import revision_input
    from test_model_planning import coordinator
    from llm_fixtures import tool_action,final_action
    reason='change campsite'
    feedback=linked_feedback({'review_id':'private-source-review-id','version_context':{'plan_version_id':'private-reviewed-version-id'},'reason':reason},reason)
    dataset,input=revision_input(feedback=feedback)
    original,_=coordinator(dataset,[tool_action(),final_action()])
    context=dataset.context.model_copy(update={'selection_config':{**dataset.context.selection_config,'a_revision_feedback':feedback}})
    linked=copy(dataset);linked._context=context
    planner,messages=coordinator(linked,[tool_action(),final_action(campsite_id='demo-river-flat')])
    outcome=asyncio.run(planner.plan(input))
    payload=json.loads(messages[0][1]['content'])
    assert payload['revision_feedback']==reason
    assert 'private-source-review-id' not in json.dumps(messages) and 'private-reviewed-version-id' not in json.dumps(messages)
    assert outcome.itinerary.selected_campsite_ids==['demo-river-flat']
    assert planner.identity['coordinator_version'].endswith('-review-feedback-1')
    assert planner.identity['validation_version'].endswith('-review-feedback-1')
    assert planner.identity['configuration_fingerprint']!=original.identity['configuration_fingerprint']
    assert not original.identity['coordinator_version'].endswith('-review-feedback-1')


def test_pdf_long_text_escapes_markup_and_preserves_unicode_and_page_flow(final_client,tmp_path):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'pdf-long','complete')
    path='/api/v1/plans/'+scope.plan_id
    final=client.post(path+'/finalise',headers=headers,json=final_command(client.get(path).json())).json()
    saved=client.get(path+'/finals/'+final['final_id']).json()['final_record']
    saved=deepcopy(saved)
    saved['content']['itinerary_entries'][0]['description']=('Chinese itinerary <tag> & Original text.🏕\n'*150)+'End of long text'
    payload=render_final_pdf(saved,is_current=False)
    reader=PdfReader(BytesIO(payload));text='\n'.join(page.extract_text() for page in reader.pages)
    assert len(reader.pages)>=5
    assert '<tag> & Original text' in text and 'End of long text' in text and '[U+1F3D5]' in text
    assert 'Characters unavailable in the font' in text and 'Human review record' in text
    (tmp_path/'long-final.pdf').write_bytes(payload)



def test_historical_assistance_stays_readable_after_same_version_passes_and_deleted_plan_is_hidden(review_client):
    client,app,camper,headers=review_client
    scope,version=create(app.state.repository,camper,'past-assistance','missing')
    path='/api/v1/review/'+scope.plan_id
    note=client.post(path+'/assistance',headers=headers,json=assistance(client.get(path).json())).json()
    original=app.state.plan_queries.detail(camper,scope.plan_id)
    newer=app.state.repository.begin_run(camper,scope.request_id,scope.demo_context,scope.dataset_context,
        plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=version.version_context.plan_version_id)
    # Route is now eligible after the new evidence is supplied. This fixture's
    # new assessments are separate records; no old assessment/notice is edited.
    _,_=create(app.state.repository,camper,'complete-evidence-source','complete')
    with app.state.database.transaction(write=False) as db:
        ready_id=db.execute("SELECT id FROM plans WHERE request_id<>? ORDER BY rowid DESC LIMIT 1",(scope.request_id,)).fetchone()[0]
    ready=app.state.plan_queries.detail(camper,ready_id)
    finish_new_run(app,camper,newer,ready)
    current=app.state.plan_queries.detail(camper,scope.plan_id)
    assert current['finalisation_available'] and not current['review_assistance_notes']
    past=client.get(path+'?run_id='+scope.run_id)
    assert past.status_code==200,past.text
    assert past.json()['review_assistance_notes']==[note]
    assert not past.json()['review_available'] and not past.json()['assistance_available']
    owner=sign_in(client)
    assert client.delete('/api/v1/plans/'+scope.plan_id,headers=owner).status_code==204
    sign_in(client,'founder','CampMate-Founder-2026!')
    assert client.get(path+'?run_id='+scope.run_id).status_code==404
