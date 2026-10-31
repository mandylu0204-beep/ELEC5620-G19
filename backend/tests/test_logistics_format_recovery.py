"""Offline regression for one rejected envelope, including audit/restart reuse."""
from copy import deepcopy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.contracts.errors import ContractFailure
from app.llm.client import CampusModelClient
from app.llm.coordinator import canonical, digest
from app.llm.logistics_agent import (
    LOGISTICS_AGENT_VERSION, LEGACY_LOGISTICS_AGENT_VERSION, LogisticsAgent,
    LogisticsTraceV1,
)
from app.llm.logistics_format import (
    READ_ENVELOPE, EVALUATE_ENVELOPE, FINAL_ENVELOPE, misplaced_evaluation_name,
)
from app.llm.logistics_validation import validate_logistics_payload
from llm_fixtures import completion, model_settings
from test_llm_logistics_agent import input_fixture, baseline, proposal_from_facts, call


PRIVATE = 'rejected-private-model-text-marker'


def misplaced(action):
    action = deepcopy(action)
    action['arguments']['name'] = action.pop('name')
    return action


def fixture(*, mutate=None, max_turns=4, max_attempts=1, on_request=None):
    dataset, source, config = input_fixture(missing=['sleeping_bag'])
    requests, replies = [], []
    async def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if on_request:
            await on_request(len(requests))
        tools = [json.loads(m['content'][12:]) for m in body['messages'] if m['content'].startswith('TOOL_RESULT=')]
        if not tools:
            action = deepcopy(READ_ENVELOPE)
        elif len(tools) == 1:
            action = {'action': 'tool', 'name': 'evaluate_logistics_plan',
                'arguments': proposal_from_facts(tools[0])}
        else:
            action = {'action': 'final', 'proposal': tools[-1]['evaluated_proposal']}
        if mutate:
            action = mutate(len(requests), action)
        if isinstance(action, httpx.Response):
            return action
        wire = json.dumps(action) if not isinstance(action, str) else action
        replies.append(wire)
        return httpx.Response(200, json=completion(wire, model='offline-format-correction'))
    client = CampusModelClient(model_settings(max_turns=max_turns, max_attempts=max_attempts),
        transport=httpx.MockTransport(respond))
    agent = LogisticsAgent(dataset, client, workflow_configuration=config)
    return agent, source, requests, replies, baseline(dataset, source, config)


def test_new_identity_and_phase_templates_without_extra_calls():
    agent, source, requests, _, facts = fixture()
    result = call(agent.assess_with_trace(source))
    assert agent.identity['agent_version'] == LOGISTICS_AGENT_VERSION == 'campus-logistics-agent-2'
    assert len(requests) == 3 and result.trace.format_correction_turns == []
    assert json.loads(requests[0]['messages'][1]['content'])['next_action'] == READ_ENVELOPE
    assert json.loads(requests[1]['messages'][-1]['content'][12:])['next_action'] == EVALUATE_ENVELOPE
    assert json.loads(requests[2]['messages'][-1]['content'][12:])['next_action'] == FINAL_ENVELOPE
    validate_logistics_payload(source, facts, result.assessment, result.plan.model_dump(mode='json'),
        result.trace.model_dump(mode='json'), identity=agent.identity)


@pytest.mark.parametrize('wrapper', ['plain', 'whitespace', 'fenced'])
def test_one_fresh_model_correction_counts_every_reply_and_preserves_rule_gaps(caplog, wrapper):
    def mutate(turn, action):
        if turn == 2:
            action['arguments']['decision_summary'] = PRIVATE
            value = misplaced(action)
            if wrapper == 'whitespace': return ' \n'+json.dumps(value)+'\n '
            if wrapper == 'fenced': return '```json\n'+json.dumps(value)+'\n```'
            return value
        return action
    agent, source, requests, replies, facts = fixture(mutate=mutate)
    result = call(agent.assess_with_trace(source))
    trace = result.trace
    assert len(requests) == trace.turns == trace.http_attempts == 4
    assert trace.format_correction_turns == [2]
    assert trace.tool_calls == ['read_logistics_facts', 'evaluate_logistics_plan']
    assert trace.response_sha256 == [digest(reply) for reply in replies]
    assert trace.usage == {'prompt_tokens': 400, 'completion_tokens': 240, 'total_tokens': 640}
    correction = json.loads(requests[2]['messages'][-1]['content'])
    assert correction['kind'] == 'LOGISTICS_FORMAT_CORRECTION'
    assert correction['errors'] == [{'path': '$.name', 'type': 'missing'},
        {'path': '$.arguments.name', 'type': 'extra_forbidden'}]
    assert PRIVATE not in json.dumps(requests) + caplog.text + trace.model_dump_json()
    assert result.plan.decision_summary_unverified != PRIVATE
    assert result.assessment.mandatory_blockers == facts.mandatory_blockers
    assert result.assessment.clarifications == facts.clarifications
    assert result.assessment.gear_checklist == facts.gear_checklist
    assert result.assessment.outcome == facts.outcome == 'REVISION'
    validate_logistics_payload(source, facts, result.assessment, result.plan.model_dump(mode='json'),
        trace.model_dump(mode='json'), identity=agent.identity)


@pytest.mark.parametrize('limit', [4, 6])
def test_second_bad_envelope_stops_even_when_more_turns_are_available(limit):
    agent, source, requests, _, _ = fixture(max_turns=limit,
        mutate=lambda turn, action: misplaced(action) if turn >= 2 else action)
    with pytest.raises(ContractFailure) as caught:
        call(agent.assess_with_trace(source))
    assert len(requests) == 3
    assert caught.value.error.code == 'CONTRACT_INVALID' and not caught.value.error.recoverable
    assert caught.value.error.context['logistics_turn'] == '3'


def test_three_turn_budget_does_not_start_correction_without_room_for_final():
    agent, source, requests, _, _ = fixture(max_turns=3,
        mutate=lambda turn, action: misplaced(action) if turn == 2 else action)
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(source))
    assert len(requests) == 2


@pytest.mark.parametrize('problem', ['quantity', 'enum', 'missing-field', 'unknown-name',
    'unknown-field', 'json', 'duplicate-json-key', 'coverage', 'method', 'early-final', 'changed-final'])
def test_other_protocol_business_and_final_errors_are_not_format_retries(problem):
    def mutate(turn, action):
        if problem == 'changed-final' and turn == 3:
            action['proposal']['decision_summary'] = 'Not evaluated'
        if turn != 2:
            return action
        if problem == 'json': return '{'
        if problem == 'duplicate-json-key': return '{"action":"tool","action":"tool"}'
        if problem == 'early-final': return {'action': 'final', 'proposal': action['arguments']}
        proposal = action['arguments']
        if problem == 'quantity': proposal['gear_choices'][0]['quantity'] = '999'
        if problem == 'enum': proposal['gear_choices'][0]['method'] = 'CONFIRMED_PURCHASE'
        if problem == 'missing-field': proposal.pop('cost_priority')
        if problem == 'unknown-name': action['name'] = PRIVATE
        if problem == 'unknown-field': proposal[PRIVATE] = PRIVATE
        if problem == 'coverage': proposal['cost_priority'].pop()
        if problem == 'method':
            next(item for item in proposal['gear_choices'] if item['item_key'] == 'sleeping_bag')['method'] = 'KEEP_CONFIRMED'
        return action
    agent, source, requests, _, _ = fixture(mutate=mutate)
    with pytest.raises(ContractFailure) as caught:
        call(agent.assess_with_trace(source))
    assert len(requests) == (3 if problem == 'changed-final' else 2)
    assert caught.value.error.code == 'CONTRACT_INVALID'
    assert not any(message['role'] == 'user' and message['content'].startswith('{')
        and json.loads(message['content']).get('kind') == 'LOGISTICS_FORMAT_CORRECTION'
        for body in requests for message in body['messages'])


@pytest.mark.parametrize('problem', ['business', 'final', 'facts', 'network'])
def test_correction_response_still_passes_all_original_gates(problem):
    def mutate(turn, action):
        if turn == 2: return misplaced(action)
        if turn == 3:
            if problem == 'business': action['arguments']['cost_priority'].pop()
            elif problem == 'final': return {'action': 'final', 'proposal': action['arguments']}
            elif problem == 'facts': return deepcopy(READ_ENVELOPE)
            else: return httpx.Response(502, text=PRIVATE)
        return action
    agent, source, requests, _, _ = fixture(mutate=mutate)
    with pytest.raises(ContractFailure) as caught:
        call(agent.assess_with_trace(source))
    assert len(requests) == 3
    assert PRIVATE not in caught.value.error.model_dump_json()


def test_identity_change_during_correction_rejects_before_accepting_new_reply():
    reference = []
    async def on_request(turn):
        if turn == 3:
            reference[0].client.settings = model_settings(timeout_seconds=6)
    agent, source, requests, _, _ = fixture(on_request=on_request,
        mutate=lambda turn, action: misplaced(action) if turn == 2 else action)
    reference.append(agent)
    with pytest.raises(ContractFailure) as caught:
        call(agent.assess_with_trace(source))
    assert len(requests) == 3 and caught.value.error.code == 'STALE_CONTEXT'


@pytest.mark.parametrize('value', [None, [True], ['2'], [1], [3], [2, 2], []])
def test_corrected_trace_cannot_omit_or_forge_correction_accounting(value):
    agent, source, _, _, facts = fixture(mutate=lambda turn, action: misplaced(action) if turn == 2 else action)
    result = call(agent.assess_with_trace(source))
    raw = result.trace.model_dump(mode='json')
    if value is None: raw.pop('format_correction_turns')
    else: raw['format_correction_turns'] = value
    with pytest.raises(ContractFailure):
        validate_logistics_payload(source, facts, result.assessment, result.plan.model_dump(mode='json'), raw, identity=agent.identity)


def test_archived_v1_shape_replays_without_accepting_v2_corrections_or_unknown_versions():
    agent, source, _, _, facts = fixture()
    result = call(agent.assess_with_trace(source))
    raw = result.trace.model_dump(mode='json')
    old = deepcopy(raw); old.pop('format_correction_turns')
    identity = agent.identity | {'agent_version': LEGACY_LOGISTICS_AGENT_VERSION}
    # An archived seed's fingerprint is derived from that seed, not today's one.
    seed = {key: value for key, value in identity.items() if key != 'configuration_fingerprint'}
    identity['configuration_fingerprint'] = digest(canonical(seed))
    old['configuration_fingerprint'] = identity['configuration_fingerprint']
    assert LogisticsTraceV1.model_validate(old).model_dump(mode='json') == old
    validate_logistics_payload(source, facts, result.assessment, result.plan.model_dump(mode='json'), old, identity=identity)
    for broken, registered in [(old, agent.identity), (raw, identity), (raw, agent.identity | {'agent_version': 'unknown'})]:
        with pytest.raises(ContractFailure):
            validate_logistics_payload(source, facts, result.assessment, result.plan.model_dump(mode='json'), broken, identity=registered)


def test_classifier_never_normalizes_invalid_or_unknown_content():
    assert not misplaced_evaluation_name('{')
    assert not misplaced_evaluation_name(json.dumps({'action': 'tool', 'arguments': {'name': PRIVATE}}))
    # A boolean or unknown field cannot become a valid proposal via the classifier.
    assert not misplaced_evaluation_name(json.dumps({'action': 'tool', 'arguments': True}))


@pytest.mark.parametrize('lost_receipt', [False, True])
def test_corrected_audit_saved_atomically_and_reused_after_restart(tmp_path, monkeypatch, lost_receipt):
    from test_model_logistics_wiring import application, mock_roles, wrap_port, db_counts, role_counts
    from test_campus_http import confirmed_request
    from test_planning_entry import start, wait_run, retry
    from test_requests import sign_in
    from test_rule_orchestration import FailOnce
    from audit_test_reads import json_with_internal_audits

    requests, _ = mock_roles(monkeypatch)
    original = CampusModelClient.complete
    altered = []
    async def one_misplaced_reply(client, messages):
        response = await original(client, messages)
        if 'LogisticsAgent' in messages[0]['content']:
            action = json.loads(response.content)
            if action.get('name') == 'evaluate_logistics_plan' and not altered:
                altered.append(True)
                from dataclasses import replace
                return replace(response, content=json.dumps(misplaced(action)))
        return response
    monkeypatch.setattr(CampusModelClient, 'complete', one_misplaced_reply)
    if lost_receipt:
        used = []
        def once(port):
            if not used:
                used.append(True)
                return FailOnce(port, 'save_model_logistics_assessment', after=True)
            return port
        wrap_port(monkeypatch, once)
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        confirmed = confirmed_request(client, headers)
        started = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        rid = started.json()['run_id']
        detail = wait_run(client, rid, 'FAILED' if lost_receipt else 'SUCCEEDED')
        detail = json_with_internal_audits(client, client.get('/api/v1/runs/'+rid))
        audit = detail['model_assessment_audits']['LOGISTICS']
        assert audit['trace']['format_correction_turns'] == [2]
        assert audit['trace']['turns'] == audit['trace']['http_attempts'] == 4
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 4}
        assert db_counts(client.app)['model_logistics_audits'] == 1
        content, origin = detail['version']['content'], detail['model_planning_trace']
    with TestClient(application(tmp_path)) as client:
        headers = sign_in(client)
        read = json_with_internal_audits(client, client.get('/api/v1/runs/'+rid))
        assert read['model_assessment_audits']['LOGISTICS'] == audit
        if lost_receipt:
            assert retry(client, headers, read).status_code == 202
            wait_run(client, rid, 'SUCCEEDED')
        result = json_with_internal_audits(client, client.get('/api/v1/runs/'+rid))
        assert result['model_assessment_audits']['LOGISTICS'] == audit
        assert result['version']['content'] == content and result['model_planning_trace'] == origin
        assert db_counts(client.app)['model_logistics_audits'] == 1
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 4}
