"""Progress is owner-scoped persisted state, never business eligibility."""
import pytest
from fastapi.testclient import TestClient
from app.auth import User
from app.config import Settings
from app.main import create_app
from plan_fixtures import create
from test_accounts import login

@pytest.fixture
def progress_client():
    app=create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        session=login(client)
        yield app,client,User('camper-a','camper.a','Camper A','CAMPER'),session


def test_progress_does_not_resolve_runtime_or_read_full_artifacts(progress_client,monkeypatch):
    app,client,user,_=progress_client
    scope,_=create(app.state.repository,user,'progress-active')
    def forbidden(*a,**kw):raise AssertionError('Progress must not resolve datasets or artifacts')
    monkeypatch.setattr(app.state.runtime,'resolve',forbidden)
    monkeypatch.setattr(app.state.plan_queries,'detail',forbidden)
    response=client.get('/api/v1/runs/'+scope.run_id+'/progress')
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    data=response.json()
    assert set(data)=={'plan_id','active_run_id','revision_proposal_id','run'}
    assert data['revision_proposal_id'] is None
    assert set(data['run'])=={'run_id','status','stage','revision','is_active'}
    assert data['run']['status']=='RUNNING' and data['run']['is_active']
    assert data['plan_id']==scope.plan_id


@pytest.mark.parametrize('account,expected', [('camper.b',404),('founder',403)])
def test_progress_keeps_owner_and_role_boundary(progress_client,account,expected):
    app,client,user,_=progress_client
    scope,_=create(app.state.repository,user,'progress-owner')
    login(client,account,'CampMate-B-2026!' if account=='camper.b' else 'CampMate-Founder-2026!')
    assert client.get('/api/v1/runs/'+scope.run_id+'/progress').status_code==expected


def test_progress_requires_session_and_hides_deleted_plan(progress_client):
    app,client,user,session=progress_client
    scope,_=create(app.state.repository,user,'progress-deleted','complete')
    assert client.get('/api/v1/runs/'+scope.run_id+'/progress').json()['run']['status']=='SUCCEEDED'
    headers={'X-CampMate-Client':'1','X-CSRF-Token':session['csrf_token']}
    assert client.delete('/api/v1/plans/'+scope.plan_id,headers=headers).status_code==204
    assert client.get('/api/v1/runs/'+scope.run_id+'/progress').status_code==404
    client.cookies.clear()
    assert client.get('/api/v1/runs/'+scope.run_id+'/progress').status_code==401


@pytest.mark.parametrize('expired',[False,True])
def test_progress_preserves_live_lease_and_expires_only_expired_worker(progress_client,expired):
    app,client,user,_=progress_client
    scope,_=create(app.state.repository,user,'progress-lease')
    with app.state.database.transaction() as db:
        db.execute('INSERT INTO run_leases VALUES(?,?,?,?)',(scope.run_id,'progress-test',1,0 if expired else app.state.workflows.clock()+120))
    data=client.get('/api/v1/runs/'+scope.run_id+'/progress').json()
    assert data['run']['status']==('FAILED' if expired else 'RUNNING')
    with app.state.database.transaction(write=False) as db:
        run=db.execute('SELECT status,error FROM runs WHERE id=?',(scope.run_id,)).fetchone()
        assert run['status']==data['run']['status']
        assert bool(run['error'])==expired


def test_progress_marks_superseded_run_without_expiring_it(progress_client):
    app,client,user,_=progress_client
    scope,_=create(app.state.repository,user,'progress-history')
    with app.state.database.transaction() as db:
        db.execute('UPDATE plans SET active_run_id=NULL WHERE id=?',(scope.plan_id,))
        db.execute('INSERT INTO run_leases VALUES(?,?,?,?)',(scope.run_id,'old-attempt',1,0))
    data=client.get('/api/v1/runs/'+scope.run_id+'/progress').json()
    assert data['run']['status']=='RUNNING' and not data['run']['is_active']


def test_real_workflow_progress_then_full_detail_keeps_terminal_guards(tmp_path):
    import time
    from test_trip_evidence_http import app, launch
    from test_requests import sign_in
    application=app(tmp_path)
    with TestClient(application) as client:
        headers=sign_in(client)
        run_id=launch(client,headers)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            progress=client.get('/api/v1/runs/'+run_id+'/progress')
            assert progress.status_code==200
            if progress.json()['run']['status'] not in {'PENDING','RUNNING'}:
                break
            time.sleep(.02)
        assert progress.json()['run']['status']=='SUCCEEDED'
        detail=client.get('/api/v1/runs/'+run_id).json()
        assert detail['run']['status']=='SUCCEEDED'
        assert len(detail['assessments'])==2 and detail['trip_evidence_coverage']
        # Complete detail still checks current identity after a date change.
        from datetime import date
        application.state.settings.demo_today=date(2026,10,27)
        changed=client.get('/api/v1/runs/'+run_id).json()
        assert changed['current_inputs_state']=='CHANGED'
        assert not changed['finalisation_available']
