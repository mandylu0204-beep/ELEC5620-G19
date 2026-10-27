"""Offline structural diagnostics: rejected model values never escape."""
from copy import deepcopy
import json
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.application.presentation import plan_response
from app.auth import User
from app.contracts.errors import ContractFailure
from app.llm.logistics_schema import parse_logistics_action
from test_llm_logistics_agent import agent_fixture, call, input_fixture
from llm_fixtures import completion, model_settings


PRIVATE = 'private-profile-and-key-marker-UNTRUSTED'


def evaluation():
    return {'action': 'tool', 'name': 'evaluate_logistics_plan', 'arguments': {
        'gear_choices': [{'item_key': 'tent', 'method': 'ASK_USER', 'reason': 'Verify stock'}],
        'cost_priority': ['example-cost'], 'decision_summary': 'Verify arrangements'}}


def diagnostic(value):
    with pytest.raises(ContractFailure) as captured:
        parse_logistics_action(value if isinstance(value, str) else json.dumps(value))
    error = captured.value.error
    assert error.code == 'CONTRACT_INVALID' and error.recoverable is False
    assert error.field_errors == []
    assert PRIVATE not in error.model_dump_json()
    assert len(error.model_dump_json()) < 4000
    return error.context, json.loads(error.context['validation_errors'])


@pytest.mark.parametrize('change,path,kind', [
    ('missing', '$.arguments.cost_priority', 'missing'),
    ('enum', '$.arguments.gear_choices[0].method', 'literal_error'),
    ('long-reason', '$.arguments.gear_choices[0].reason', 'string_too_long'),
    ('extra', '$.arguments.<extra_field>', 'extra_forbidden'),
    ('blank', '$.arguments.decision_summary', 'blank_explanation'),
])
def test_exact_field_and_type_are_reported_without_input_messages_or_unknown_keys(change,path,kind):
    value = evaluation()
    if change == 'missing': value['arguments'].pop('cost_priority')
    elif change == 'enum': value['arguments']['gear_choices'][0]['method'] = PRIVATE
    elif change == 'long-reason': value['arguments']['gear_choices'][0]['reason'] = PRIVATE * 20
    elif change == 'extra': value['arguments'][PRIVATE] = PRIVATE
    else: value['arguments']['decision_summary'] = '   '
    context, errors = diagnostic(value)
    assert errors == [{'path': path, 'type': kind}]
    assert context['failure_stage'] == ('EXPLANATION_VALIDATION' if change == 'blank' else 'SCHEMA_VALIDATION')


@pytest.mark.parametrize('value,kind', [
    ('{"secret":"'+PRIVATE+'",\n', 'json_invalid'),
    ('{"'+PRIVATE+'":1,"'+PRIVATE+'":2}', 'duplicate_key'),
    ('{"secret":NaN}', 'nonfinite_json'),
    ('<think>'+PRIVATE+'</think>{}', 'json_invalid'),
])
def test_json_errors_have_safe_categories_not_source_snippets(value,kind):
    context, errors = diagnostic(value)
    assert context['failure_stage'] == 'JSON_PARSE'
    assert errors == [{'path': '$', 'type': kind}]
    if kind == 'json_invalid':
        assert int(context['json_line']) >= 1 and int(context['json_column']) >= 1


def test_many_unknown_keys_are_bounded_and_forged_names_are_redacted():
    value = evaluation()
    value['arguments'].update({PRIVATE+str(index): PRIVATE for index in range(100)})
    _, errors = diagnostic(value)
    assert len(errors) == 8
    assert all(error == {'path': '$.arguments.<extra_field>', 'type': 'extra_forbidden'} for error in errors)


def test_agent_adds_exact_turn_and_logs_only_sanitised_structure(caplog):
    dataset, source, config = input_fixture()
    def mutate(turn, action):
        if turn == 2:
            action['arguments']['gear_choices'][0]['method'] = PRIVATE
        return action
    agent, requests = agent_fixture(dataset, config, mutate=mutate)
    with pytest.raises(ContractFailure) as captured:
        call(agent.assess_with_trace(source))
    context = captured.value.error.context
    assert len(requests) == 2 and context['logistics_turn'] == '2'
    assert context['role'] == 'LOGISTICS' and context['http_attempts'] == '2'
    assert int(context['response_bytes']) > 0
    assert PRIVATE not in caplog.text
    assert '$.arguments.gear_choices[0].method' in caplog.text
    assert 'literal_error' in caplog.text
    assert 'confirmed_requirements' not in caplog.text


def test_camper_projection_hides_diagnostics_but_internal_and_reviewer_error_retain_them():
    value = evaluation(); value['arguments']['gear_choices'][0]['method'] = PRIVATE
    with pytest.raises(ContractFailure) as captured:
        parse_logistics_action(json.dumps(value))
    error = captured.value.error.model_dump(mode='json')
    raw = {'run': {'status': 'FAILED', 'error': error}, 'events': [{'error': deepcopy(error)}],
        'assessments': [], 'confirmed_context': None}
    before = deepcopy(raw)
    public = plan_response(raw, User('a','a','a','CAMPER'))
    assert public['run']['error']['context'] == {} and public['events'][0]['error']['context'] == {}
    assert 'validation_errors' not in json.dumps(public)
    reviewer = plan_response(raw, User('reviewer','reviewer','reviewer','FOUNDER'))
    assert reviewer['run']['error']['context']['validation_errors'] == error['context']['validation_errors']
    assert raw == before


@pytest.mark.parametrize('failure_kind',['schema','coverage'])
def test_failed_http_run_persists_safe_diagnostics_without_exposing_them_or_losing_saved_itinerary(tmp_path,monkeypatch,failure_kind):
    from test_model_logistics_wiring import application, mock_roles
    from test_campus_http import confirmed_request
    from test_planning_entry import start, wait_run
    from test_requests import sign_in
    _, control = mock_roles(monkeypatch)
    control['invalid'] = failure_kind == 'schema'
    control['omit_cost'] = failure_kind == 'coverage'
    instance = application(tmp_path)
    with TestClient(instance) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client,headers)
        response = start(client,headers,request_id=confirmed['request_id'],revision=confirmed['revision'])
        run_id = response.json()['run_id']
        wait_run(client,run_id,'FAILED')
        public_response = client.get('/api/v1/runs/'+run_id)
        assert public_response.status_code == 200
        public = public_response.json()
        assert public['run']['stage'] == 'ASSESSING_LOGISTICS' and public['version']
        assert public['run']['error']['code'] == 'CONTRACT_INVALID'
        assert 'validation_errors' not in public_response.text
        assert 'logistics_turn' not in public_response.text
        assert 'cost_priority_diagnostics' not in public_response.text
        progress = client.get('/api/v1/runs/'+run_id+'/progress')
        assert progress.status_code == 200
        assert 'validation_errors' not in progress.text and 'logistics_turn' not in progress.text
        assert 'cost_priority_diagnostics' not in progress.text
        with instance.state.database.transaction(write=False) as db:
            error = json.loads(db.execute('SELECT error FROM runs WHERE id=?',(run_id,)).fetchone()[0])
            if failure_kind == 'schema':
                assert error['context']['logistics_turn'] == '1'
                assert error['context']['failure_stage'] == 'SCHEMA_VALIDATION'
                issues = json.loads(error['context']['validation_errors'])
                assert {entry['path'] for entry in issues} == {'$.proposal.gear_choices','$.proposal.cost_priority','$.proposal.decision_summary'}
            else:
                assert error['context']['logistics_turn'] == '2'
                assert error['context']['failure_stage'] == 'COST_PRIORITY_COVERAGE'
                detail = json.loads(error['context']['cost_priority_diagnostics'])
                assert detail['missing_count'] == 1
                assert detail['provided_count'] == detail['expected_count']-1
            assert db.execute('SELECT COUNT(*) FROM model_planning_traces WHERE run_id=?',(run_id,)).fetchone()[0] == 1
            assert db.execute('SELECT COUNT(*) FROM model_logistics_audits WHERE run_id=?',(run_id,)).fetchone()[0] == 0


def probe_module():
    spec = importlib.util.spec_from_file_location('offline_logistics_probe',Path(__file__).resolve().parents[2]/'scripts/logistics_protocol_probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostic_client_rejects_http_retries_and_stops_after_three_offline_requests():
    import httpx
    module = probe_module()
    with pytest.raises(ValueError):
        module.BoundedClient(model_settings())
    client = module.BoundedClient(model_settings().model_copy(update={'max_attempts':1,'max_turns':3}))
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json=completion({'action':'tool','name':'read_logistics_facts','arguments':{}}))
    client.transport = httpx.MockTransport(respond)
    async def exercise():
        for _ in range(3):
            await client.complete([{'role':'user','content':'Offline test'}])
        with pytest.raises(RuntimeError):
            await client.complete([{'role':'user','content':'Must not be sent'}])
    call(exercise())
    assert len(requests) == client.calls == 3


def test_probe_without_allow_model_performs_no_completion(monkeypatch,capsys):
    module = probe_module()
    class ForbiddenClient:
        async def complete(self,*args):
            pytest.fail('Default diagnostic CLI must not send a request')
    monkeypatch.setattr(module,'prepare',lambda *args:(None,ForbiddenClient(),None,{}))
    monkeypatch.setattr(module.sys,'argv',['probe','--database','unused','--run-id','unused','--snapshot','unused'])
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out) == {'status':'OFFLINE_PREFLIGHT','http_requests':0}


def test_probe_report_preserves_sanitised_cost_diff_without_model_or_private_values():
    from app.llm.logistics_diagnostics import cost_priority_failure
    module = probe_module()
    class RejectedAgent:
        async def assess_with_trace(self,source):
            raise cost_priority_failure(['line-0'],[PRIVATE])
    class NoCallClient:
        calls = 0
        usage = {}
    report = call(module.probe(RejectedAgent(),NoCallClient(),None,{}))
    assert report['status']=='REJECTED' and report['http_requests']==0
    assert json.loads(report['diagnostics']['cost_priority_diagnostics'])['missing_ids']==['line-0']
    assert PRIVATE not in json.dumps(report)
