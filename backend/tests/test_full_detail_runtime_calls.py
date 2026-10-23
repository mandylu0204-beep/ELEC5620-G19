"""A non-actionable full read must not rebuild runtime for unused operations."""
from threading import Event
import sys
from test_planning_entry import web, TestOnlyAgent, start, wait_run

def test_full_detail_only_resolves_operations_when_actions_can_be_offered(web,monkeypatch):
    app,client,headers=web
    gate=Event();agent=app.state.agent=TestOnlyAgent(gate=gate)
    calls=[];original=app.state.runtime.resolve
    def counted(*args,**kwargs):
        calls.append(sys._getframe(1).f_code.co_name)
        return original(*args,**kwargs)
    monkeypatch.setattr(app.state.runtime,'resolve',counted)
    try:
        started=start(client,headers);assert started.status_code==202
        assert agent.saved.wait(3)
        calls.clear()
        pending=client.get('/api/v1/runs/'+started.json()['run_id']).json()
        assert pending['run']['status']=='RUNNING'
        assert not pending['revision_available'] and not pending['reassessment_available'] and not pending['finalisation_available']
        assert 'available' in calls
        assert 'retry_fields' not in calls
        gate.set();wait_run(client,started.json()['run_id'],'SUCCEEDED')
        calls.clear();complete=client.get('/api/v1/runs/'+started.json()['run_id']).json()
        assert complete['run']['status']=='SUCCEEDED'
        assert calls.count('retry_fields')==1
    finally:
        gate.set()
