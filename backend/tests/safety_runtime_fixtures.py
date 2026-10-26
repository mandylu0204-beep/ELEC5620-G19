"""Three actual role components + production factory; mocked campus HTTP only."""
from datetime import date, timedelta
from copy import deepcopy
import json
import time

import httpx
import pytest

from app.config import Settings
from app.llm.client import CampusModelClient
from app.main import create_app
from llm_fixtures import ROOT, completion, model_settings, tool_action, final_action
from safety_fixtures import proposal_from_safety_facts
from test_llm_logistics_agent import proposal_from_facts
from test_v2_http_demo import CASES, INPUTS
from request_semantics_fixtures import interpretation_proposal


def mock_safety_runtime(monkeypatch, *, settings=None):
    from app.llm import client, config
    requests, control = [], {}
    async def respond(request):
        body = json.loads(request.content)
        messages = body['messages']
        system = messages[0]['content']
        first_input = json.loads(messages[1]['content']) if messages[1]['content'].startswith('{') else {}
        if first_input.get('operation') == 'INTERPRET_REQUEST':
            requests.append({'role':'INTERPRETATION', 'body':body})
            # Summary calls are a separate capability, never a safety/logistics
            # gate, action mutation or workflow-role failure injection.
            return httpx.Response(200, json=completion(interpretation_proposal(first_input),
                model='offline-request-interpretation'))
        role = 'SAFETY' if 'SafetyAgent' in system else 'LOGISTICS' if 'LogisticsAgent' in system else 'PLANNING'
        requests.append({'role':role, 'body':body})
        if control.get('on_request'):
            await control['on_request'](role)
        if role == 'SAFETY' and control.get('unavailable'):
            return httpx.Response(503, json={'error':'offline safety provider unavailable'})
        tools = [json.loads(item['content'][12:]) for item in messages if item['content'].startswith('TOOL_RESULT=')]
        if role in {'LOGISTICS','SAFETY'}:
            name = role.lower()
            if not tools:
                action = {'action':'tool','name':f'read_{name}_facts','arguments':{}}
            else:
                if role == 'SAFETY' and tools[0].get('codec') == 'safety-lossless-facts-1':
                    facts = tools[0]
                    proposal = {'facts_sha256':facts['facts_sha256'],
                        'findings':[{'id':item['id'],'action':item['actions'][0],
                            'advice':'Review this recorded issue before departure.'}
                            for item in facts['findings']],
                        'priority':[item['id'] for item in facts['findings']],
                        'summary':'Resolve recorded issues before departure.'}
                else:
                    proposal = proposal_from_safety_facts(tools[0]) if role == 'SAFETY' else proposal_from_facts(tools[0])
                action = {'action':'tool','name':f'evaluate_{name}_plan','arguments':proposal} if len(tools) == 1 else {
                    'action':'final','proposal':proposal}
            if role == 'SAFETY' and control.get('invalid'):
                action = {'action':'final','proposal':{}}
        else:
            input = json.loads(messages[1]['content'])
            if not tools:
                action = tool_action()
            else:
                site = control.get('site') or ('demo-moonlit-field' if input.get('revision_feedback') == 'cheaper campsite' else 'demo-wattle-rest')
                first = date.fromisoformat(input['confirmed_requirements']['start_date'])
                action = final_action(campsite_id=site,nights=[(first+timedelta(days=i)).isoformat()
                    for i in range(input['confirmed_requirements']['duration_nights'])])
        if control.get('mutate_action'):
            action = control['mutate_action'](role,len(tools),action)
        return httpx.Response(200,json=completion(action,model='offline-safety-runtime'))
    class ActiveClient(CampusModelClient):
        async def complete(self,messages):
            control['active_client'] = self
            return await super().complete(messages)
    values = settings or model_settings()
    monkeypatch.setattr(config,'CampusModelSettings',lambda:values)
    monkeypatch.setattr(client,'CampusModelClient',lambda config:ActiveClient(config,transport=httpx.MockTransport(respond)))
    return requests,control


def application(tmp_path,case='normal',*,logistics='model',safety='model',**changes):
    values = {**CASES[case]['settings'],'execution_mode':'agent','logistics_execution':logistics,
        'safety_execution':safety,'dataset_path':'data/synthetic_demo_v2_1',
        'workflow_safety_case_ids':[],'dataset_scenario_files':[],**changes}
    values['dataset_path'] = ROOT/values['dataset_path']
    return create_app(Settings(_env_file=None,database_path=tmp_path/'safety-runtime.sqlite3',**values))


def role_counts(requests):
    # Formal workflow roles only; interpretation is retained as a separate row.
    return {role:sum(row['role'] == role for row in requests) for role in ('PLANNING','LOGISTICS','SAFETY')}


def db_counts(app):
    with app.state.database.transaction(write=False) as db:
        return {name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
            ('versions','assessments','gear_checklists','model_planning_traces','model_logistics_audits','model_safety_audits')}


def wait_run(client,run_id,status):
    # The real 2.1 factory/provider and repeated archive reads cost more than
    # the old v2 scenario fixture. This is an offline test deadline, NOT a model
    # timeout/retry/token setting or a reason to skip audit verification.
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        response = client.get('/api/v1/runs/'+run_id)
        assert response.status_code == 200,response.text
        data = response.json()
        actual = data['run']['status']
        if actual == status:
            return data
        if actual in {'FAILED','SUCCEEDED'}:
            pytest.fail(f"Unexpected terminal {actual}, wanted {status}: {data['run'].get('error')}")
        time.sleep(.01)
    pytest.fail(f"Run deadline: wanted {status}, got {data['run']['status']}/{data['run']['stage']}")


def confirmed_request(client,headers,case='normal',*,start=None,unknown_tent=False):
    from test_extended_demo import confirm_saved
    profile = deepcopy(INPUTS['profile'])
    if unknown_tent:
        next(item for item in profile['equipment'] if item['item_key']=='tent')['quantity'] = None
    response = client.put('/api/v1/profile',headers=headers,json={'expected_revision':0,'profile':profile})
    assert response.status_code == 200,response.text
    payload = deepcopy(CASES[case]['request'])
    if start:
        old = payload['explicit_fields']['start_date']
        payload['explicit_fields']['start_date'] = start
        payload['raw_text'] = payload['raw_text'].replace(old,start)
    saved = client.post('/api/v1/requests',headers=headers,json=payload)
    assert saved.status_code == 201,saved.text
    return confirm_saved(client,headers,saved.json(),'safety-runtime-confirmed')


def launch(client,headers,case,**options):
    from test_planning_entry import start
    confirmed = confirmed_request(client,headers,case,**options)
    begun = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
    assert begun.status_code == 202,begun.text
    return wait_run(client,begun.json()['run_id'],'SUCCEEDED')
