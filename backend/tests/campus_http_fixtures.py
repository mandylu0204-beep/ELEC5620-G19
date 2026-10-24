"""Actual campus client/Coordinator with offline HTTP responses, never live keys."""
import json

import httpx

from app.llm.client import CampusModelClient
from app.config import Settings
from app.main import create_app
from test_v2_http_demo import CASES, ROOT
from llm_fixtures import model_settings, completion, tool_action, final_action
from request_semantics_fixtures import interpretation_proposal, model_operation


def mock_campus(monkeypatch, *, site='demo-wattle-rest'):
    from app.llm import config, client
    requests = []
    async def respond(request):
        body = json.loads(request.content)
        role = 'INTERPRETATION' if model_operation(body) == 'INTERPRET_REQUEST' else 'PLANNING'
        requests.append({'role': role, 'body': body})
        if role == 'INTERPRETATION':
            value = interpretation_proposal(json.loads(body['messages'][1]['content']))
        else:
            tool_result = body['messages'][-1]['content'].startswith('TOOL_RESULT=')
            value = final_action(campsite_id=site) if tool_result else tool_action()
        return httpx.Response(200, json=completion(value, model='offline-test-only'))
    settings = model_settings()
    monkeypatch.setattr(config, 'CampusModelSettings', lambda: settings)
    monkeypatch.setattr(client, 'CampusModelClient', lambda values: CampusModelClient(values, transport=httpx.MockTransport(respond)))
    return requests, settings


def application(tmp_path, case='normal'):
    values = {**CASES[case]['settings'], 'execution_mode':'agent'}
    values['dataset_path'] = ROOT / values['dataset_path']
    return create_app(Settings(_env_file=None, database_path=tmp_path/'campus-http.sqlite3', **values))
