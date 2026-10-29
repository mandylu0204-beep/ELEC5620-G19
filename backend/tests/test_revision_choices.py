"""Candidate choice uses real storage/roles with offline model transports only."""
from fastapi.testclient import TestClient
import pytest

from app.storage.database import Database
from test_model_logistics_wiring import application, mock_roles, launch, finalise, wait_run
from test_plan_changes import command
from test_requests import sign_in
from test_finalisation import command as final_command
from test_v2_http_demo import CASES


def choose_body(value, decision, key='choose-revision-command-123456'):
    return {'decision': decision, 'command_key': key, 'expected_proposal_revision': value['revision'],
        'expected_candidate_run_revision': value['after']['run']['revision']}


@pytest.mark.parametrize('decision', ['KEEP','ADOPT'])
def test_candidate_keeps_original_selected_until_explicit_choice_and_preserves_audits(tmp_path, monkeypatch, decision):
    requests, control = mock_roles(monkeypatch)
    # This input must allow saving the original, independently of the sealed
    # over-budget scenario used by the older revision tests.
    monkeypatch.setitem(CASES['budget_revision']['request']['explicit_fields'], 'budget_cents', 50000)
    app = application(tmp_path, 'budget_revision')
    with TestClient(app) as client:
        headers = sign_in(client)
        original = launch(client, headers, 'budget_revision')
        final_path, _ = finalise(client, headers, original)
        old_final = client.get(final_path).json()
        path = '/api/v1/plans/'+original['plan']['plan_id']
        original = client.get(path).json()
        old_pointer = original['plan'].copy()
        body = command(original, feedback='cheaper campsite')
        enqueue = app.state.dispatcher.enqueue
        monkeypatch.setattr(app.state.dispatcher, 'enqueue', lambda *_: None)
        response = client.post(path+'/revision-proposals', headers=headers, json=body)
        assert response.status_code == 202, response.text
        candidate_id = response.json()['run_id']
        waiting = client.get(path).json()
        assert waiting['plan'] == old_pointer
        assert waiting['version'] == original['version']
        assert waiting['last_final']['is_current']
        assert not waiting['finalisation_available'] and not waiting['revision_available']
        proposal = waiting['revision_comparison']
        assert proposal['status'] == 'GENERATING' and not proposal['can_keep']
        choice_path = path+'/revision-proposals/'+proposal['proposal_id']+'/decision'
        assert client.post(choice_path, headers=headers, json=choose_body(proposal,'KEEP')).status_code == 409
        assert client.post(path+'/finalise', headers=headers, json=final_command(original)).status_code == 409
        assert client.post(path+'/reassess', headers=headers, json=command(original,key='concurrent-reassessment')).status_code == 409
        progress = client.get('/api/v1/runs/'+candidate_id+'/progress').json()
        assert progress['active_run_id'] == original['run']['run_id']
        assert progress['revision_proposal_id'] == proposal['proposal_id']

        # Replaying the lost start receipt enqueues the same durable candidate.
        monkeypatch.setattr(app.state.dispatcher, 'enqueue', enqueue)
        assert client.post(path+'/revision-proposals', headers=headers, json=body).json()['run_id'] == candidate_id
        candidate = wait_run(client, candidate_id, 'SUCCEEDED')
        current = client.get(path).json()
        proposal = current['revision_comparison']
        assert current['plan'] == old_pointer and current['version'] == original['version']
        assert proposal['status'] == 'READY' and proposal['can_adopt'] and proposal['can_keep']
        assert proposal['before']['campsite_ids'] == ['demo-wattle-rest']
        assert proposal['after']['campsite_ids'] == ['demo-moonlit-field']
        assert proposal['before']['nightly_fee_cents'] == 3000
        assert proposal['after']['nightly_fee_cents'] == 2000
        assert proposal['camp_saving_cents'] == 2000
        assert proposal['total_saving_cents'] == proposal['before']['total_cents']-proposal['after']['total_cents']
        request_count = len(requests)
        choice = choose_body(proposal, decision)
        assert client.post(choice_path,headers=headers,json={**choice,'expected_proposal_revision':99}).status_code == 409
        selected = client.post(choice_path, headers=headers, json=choice)
        assert selected.status_code == 200, selected.text
        assert client.post(choice_path, headers=headers, json=choice).json() == selected.json()
        opposite = choose_body(proposal,'ADOPT' if decision=='KEEP' else 'KEEP',key='opposite-selection-key')
        assert client.post(choice_path, headers=headers, json=opposite).status_code == 409
        current = client.get(path).json()
        assert current['run']['run_id'] == (original['run']['run_id'] if decision=='KEEP' else candidate_id)
        assert current['version']['content'] == (original['version']['content'] if decision=='KEEP' else candidate['version']['content'])
        assert current['revision_comparison']['decision'] == decision
        assert client.get(final_path).json()['final_record'] == old_final['final_record']
        assert len(requests) == request_count  # Selection never calls any model.
        with app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 2
            assert db.execute('SELECT COUNT(*) FROM model_planning_traces').fetchone()[0] == 2
            assert db.execute('SELECT COUNT(*) FROM model_logistics_audits').fetchone()[0] == 2
        if decision=='KEEP':
            assert current['last_final']['is_current']
        else:
            assert not current['last_final']['is_current']
            assert current['finalisation_available']
        other = sign_in(client,'camper.b','CampMate-B-2026!')
        assert client.post(choice_path,headers=other,json=choice).status_code == 404


def test_migration_preserves_existing_schema_12_history(tmp_path):
    database = Database(tmp_path/'migration.sqlite3')
    database.initialize()
    with database.transaction() as db:
        db.execute('DROP TABLE revision_choice_commands')
        db.execute('DROP TABLE revision_proposals')
        db.execute('DELETE FROM schema_migrations WHERE version=13')
        before = [tuple(row) for row in db.execute('SELECT * FROM schema_migrations')]
    database.initialize()
    assert database.ready()
    with database.transaction(write=False) as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM schema_migrations WHERE version<13')] == before
        assert db.execute('SELECT COUNT(*) FROM revision_proposals').fetchone()[0] == 0


def test_pending_candidate_recovers_after_restart_without_replanning_original(tmp_path, monkeypatch):
    requests, _ = mock_roles(monkeypatch)
    monkeypatch.setitem(CASES['budget_revision']['request']['explicit_fields'], 'budget_cents', 50000)
    app = application(tmp_path, 'budget_revision')
    with TestClient(app) as client:
        headers = sign_in(client)
        original = launch(client, headers, 'budget_revision')
        path = '/api/v1/plans/'+original['plan']['plan_id']
        monkeypatch.setattr(app.state.dispatcher, 'enqueue', lambda *_: None)
        response = client.post(path+'/revision-proposals',headers=headers,json=command(original,feedback='cheaper campsite'))
        assert response.status_code == 202
        candidate_id = response.json()['run_id']
        before = len([r for r in requests if r['role']=='PLANNING'])
    with TestClient(application(tmp_path,'budget_revision')) as client:
        headers = sign_in(client)
        wait_run(client,candidate_id,'SUCCEEDED')
        current=client.get(path).json()
        assert current['run']['run_id']==original['run']['run_id']
        assert current['revision_comparison']['status']=='READY'
        assert len([r for r in requests if r['role']=='PLANNING'])==before+2
        proposal=current['revision_comparison']
        response=client.post(path+'/revision-proposals/'+proposal['proposal_id']+'/decision',
            headers=headers,json=choose_body(proposal,'KEEP'))
        assert response.status_code==200,response.text
        assert client.get(path).json()['version']['content']==original['version']['content']


@pytest.mark.parametrize('recover', [False,True])
def test_failed_candidate_can_only_be_kept_and_does_not_damage_the_original(tmp_path, monkeypatch, recover):
    requests, control = mock_roles(monkeypatch)
    monkeypatch.setitem(CASES['budget_revision']['request']['explicit_fields'], 'budget_cents', 50000)
    with TestClient(application(tmp_path,'budget_revision')) as client:
        headers=sign_in(client);original=launch(client,headers,'budget_revision')
        path='/api/v1/plans/'+original['plan']['plan_id']
        control['unavailable']=True
        response=client.post(path+'/revision-proposals',headers=headers,json=command(original,feedback='cheaper campsite'))
        assert response.status_code==202,response.text
        failed=wait_run(client,response.json()['run_id'],'FAILED')
        current=client.get(path).json();proposal=current['revision_comparison']
        assert current['plan']==original['plan'] and current['version']==original['version']
        assert proposal['status']=='FAILED' and not proposal['can_adopt'] and proposal['can_keep']
        assert proposal['total_saving_cents'] is None
        endpoint=path+'/revision-proposals/'+proposal['proposal_id']+'/decision'
        assert client.post(endpoint,headers=headers,json=choose_body(proposal,'ADOPT')).status_code==409
        if recover:
            from test_planning_entry import retry
            planning_count=len([item for item in requests if item['role']=='PLANNING'])
            control['unavailable']=False
            assert retry(client,headers,failed).status_code==202
            resumed=wait_run(client,failed['run']['run_id'],'SUCCEEDED')
            assert resumed['version']['version_context']['plan_version_id']==failed['version']['version_context']['plan_version_id']
            assert len([item for item in requests if item['role']=='PLANNING'])==planning_count
            proposal=client.get(path).json()['revision_comparison']
        count=len(requests)
        assert client.post(endpoint,headers=headers,json=choose_body(proposal,'KEEP')).status_code==200
        assert client.get(path).json()['version']==original['version']
        assert len(requests)==count


def test_adoption_uses_its_own_three_role_audits_and_finalisation_guards(tmp_path, monkeypatch):
    from test_model_safety_wiring import mock_safety_runtime, application as safety_application, launch as safety_launch, wait_run as safety_wait
    requests,_=mock_safety_runtime(monkeypatch)
    monkeypatch.setitem(CASES['budget_revision']['request']['explicit_fields'], 'budget_cents', 50000)
    with TestClient(safety_application(tmp_path,'budget_revision',logistics='model')) as client:
        headers=sign_in(client);original=safety_launch(client,headers,'budget_revision')
        path='/api/v1/plans/'+original['plan']['plan_id']
        response=client.post(path+'/revision-proposals',headers=headers,json=command(original,feedback='cheaper campsite'))
        assert response.status_code==202,response.text
        candidate=safety_wait(client,response.json()['run_id'],'SUCCEEDED')
        proposal=client.get(path).json()['revision_comparison']
        count=len(requests)
        endpoint=path+'/revision-proposals/'+proposal['proposal_id']+'/decision'
        choice=choose_body(proposal,'ADOPT')
        assert client.post(endpoint,json=choice).status_code==403
        adopted=client.post(endpoint,headers=headers,json=choice)
        assert adopted.status_code==200,adopted.text
        current=client.get(path).json()
        assert current['run']['run_id']==candidate['run']['run_id']
        assert current['model_assessment_audits']['SAFETY']['audit_id']!=original['model_assessment_audits']['SAFETY']['audit_id']
        assert current['model_assessment_audits']['LOGISTICS']['audit_id']!=original['model_assessment_audits']['LOGISTICS']['audit_id']
        assert not current['reviews']
        assert current['finalisation_available']
        finalise(client,headers,current)
        assert len(requests)==count


def test_previous_revisions_gain_read_only_comparison_without_retroactive_choices(tmp_path, monkeypatch):
    from test_plan_changes import change
    requests,_=mock_roles(monkeypatch)
    with TestClient(application(tmp_path,'budget_revision')) as client:
        headers=sign_in(client);original=launch(client,headers,'budget_revision')
        response=change(client,headers,original,'revise',feedback='cheaper campsite')
        assert response.status_code==202,response.text
        revised=wait_run(client,response.json()['run_id'],'SUCCEEDED')
        comparison=client.get('/api/v1/plans/'+original['plan']['plan_id']).json()['revision_comparison']
        assert comparison['legacy'] and comparison['decision']=='ADOPT'
        assert not comparison['can_adopt'] and not comparison['can_keep']
        assert comparison['before']['campsite_ids']==original['version']['content']['selected_campsite_ids']
        assert comparison['after']['campsite_ids']==revised['version']['content']['selected_campsite_ids']
        assert comparison['camp_saving_cents']==2000
        with client.app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM revision_proposals').fetchone()[0]==0
