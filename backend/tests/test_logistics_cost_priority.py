"""Exact cost membership, including unpriced/deferred rows; entirely offline."""
from copy import deepcopy
import json

import httpx
import pytest

from app.application.agent_runtime import build_v2_hybrid_binding
from app.application.datasets import inspect_dataset
from app.contracts.dto import LogisticsInput
from app.contracts.errors import ContractFailure
from app.llm.logistics_agent import LOGISTICS_SYSTEM_PROMPT
from app.llm.logistics_diagnostics import cost_priority_failure
from app.llm.logistics_tools import LogisticsToolset
from app.llm.logistics_schema import parse_logistics_action
from safety_runtime_fixtures import mock_safety_runtime
from test_sydney_model_safety import safety_input, settings, profile
from test_llm_logistics_agent import agent_fixture, call, input_fixture, proposal_from_facts

PRIVATE = 'private-profile-and-key-marker-NEVER-LOG'


@pytest.fixture(autouse=True)
def no_live_http(monkeypatch):
    def forbidden(*args,**kwargs):
        pytest.fail('Real model HTTP is forbidden in cost priority regression')
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',forbidden)


@pytest.fixture
def sydney(tmp_path,monkeypatch):
    requests, _ = mock_safety_runtime(monkeypatch)
    configuration = settings(tmp_path)
    binding = build_v2_hybrid_binding(configuration,inspect_dataset(configuration))
    source, _, _ = safety_input(binding)
    input = LogisticsInput(version_context=source.version_context,saved_itinerary=source.saved_itinerary,
        confirmed_requirements=source.confirmed_requirements,profile_snapshot=profile(),
        demo_context=source.demo_context)
    return binding.agent.logistics_agent,input,requests


def test_authoritative_manifest_covers_unpriced_rows_and_does_not_alias_tool_state(sydney):
    agent, source, _ = sydney
    tools = LogisticsToolset(source,agent._facts(source))
    facts = tools.read_logistics_facts()
    ids = [line['line_id'] for line in facts['costs']]
    assert any(key.startswith('unpriced-') for key in ids)
    assert facts['required_cost_line_ids'] == ids
    assert facts['required_cost_line_count'] == len(ids)
    assert len(set(ids)) == len(ids)
    facts['required_cost_line_ids'].clear()
    assert tools.cost_priority_requirements()['required_cost_line_ids'] == ids


def test_three_turn_wire_keeps_manifest_and_all_costs_after_optional_deferral(sydney):
    agent, source, requests = sydney
    outcome = call(agent.assess_with_trace(source))
    logistics_calls = [request for request in requests if request['role']=='LOGISTICS']
    assert len(logistics_calls) == 3
    messages = logistics_calls[2]['body']['messages']
    facts = json.loads(messages[3]['content'][12:])
    feedback = json.loads(messages[-1]['content'][12:])
    ids = facts['required_cost_line_ids']
    assert feedback['required_cost_line_ids'] == ids
    assert feedback['required_cost_line_count'] == facts['required_cost_line_count'] == len(ids)
    assert set(feedback['evaluated_proposal']['cost_priority']) == set(ids)
    assert [line['line_id'] for line in feedback['plan']['budget_allocations']] == feedback['evaluated_proposal']['cost_priority']
    assert len(feedback['plan']['projected_cost_breakdown']) == len(ids)
    deferred = [row for row in outcome.plan.gear_actions if row.method=='DEFER_OPTIONAL']
    assert deferred
    allocation = {line.line_id:line for line in outcome.plan.budget_allocations}
    for row in deferred:
        if row.cost_line_id:
            assert row.cost_line_id in ids
            assert allocation[row.cost_line_id].required_cents == 0
    assert 'exact permutation' in LOGISTICS_SYSTEM_PROMPT
    assert 'NOT item_key' in LOGISTICS_SYSTEM_PROMPT


@pytest.mark.parametrize('change',['omit','duplicate','invent','item_keys','numbered_only'])
def test_bad_cost_lists_stay_rejected_without_auto_filling_or_rewriting(sydney,change):
    agent, source, _ = sydney
    tools = LogisticsToolset(source,agent._facts(source))
    facts = tools.read_logistics_facts()
    proposal = proposal_from_facts(facts)
    if change=='omit': proposal['cost_priority'].pop()
    elif change=='duplicate': proposal['cost_priority'].append(proposal['cost_priority'][0])
    elif change=='invent': proposal['cost_priority'][0] = PRIVATE
    elif change=='item_keys': proposal['cost_priority'] = [row['item_key'] for row in facts['costs']]
    else: proposal['cost_priority'] = [key for key in proposal['cost_priority'] if key.startswith('line-')]
    before = deepcopy(proposal)
    with pytest.raises(ContractFailure) as captured:
        tools.evaluate_logistics_plan(proposal)
    error = captured.value.error
    assert error.code=='CONTRACT_INVALID' and error.recoverable is False
    assert error.context['failure_stage']=='COST_PRIORITY_COVERAGE'
    detail = json.loads(error.context['cost_priority_diagnostics'])
    assert detail['expected_count']==len(facts['costs'])
    if change=='omit': assert detail['missing_count']==1
    elif change=='duplicate': assert detail['duplicate_count']==1
    elif change=='invent': assert detail['unexpected_positions']==[0] and detail['missing_count']==1
    elif change=='item_keys': assert detail['unexpected_count']==len(proposal['cost_priority'])
    else: assert detail['missing_count']==sum(key.startswith('unpriced-') for key in facts['required_cost_line_ids'])
    assert PRIVATE not in error.model_dump_json()
    assert proposal == before
    assert tools.read_logistics_facts()==facts


def test_coverage_diagnostics_are_bounded_and_do_not_echo_unknown_or_private_ids():
    expected = [f'line-{index}' for index in range(128)]
    error = cost_priority_failure(expected,[PRIVATE]*128).error
    detail = json.loads(error.context['cost_priority_diagnostics'])
    assert detail['missing_count']==128 and len(detail['missing_ids'])==16
    assert detail['unexpected_count']==128 and len(detail['unexpected_positions'])==16
    assert detail['duplicate_count']==127 and detail['details_truncated'] is True
    assert PRIVATE not in error.model_dump_json() and len(error.model_dump_json())<3000
    secret_expected = cost_priority_failure(['unpriced-'+PRIVATE],[]).error
    assert PRIVATE not in secret_expected.model_dump_json()


@pytest.mark.parametrize('field',['required_cost_line_ids','required_cost_line_count'])
def test_host_manifest_does_not_relax_proposal_output_schema(sydney,field):
    agent, source, _ = sydney
    facts = LogisticsToolset(source,agent._facts(source)).read_logistics_facts()
    proposal = proposal_from_facts(facts)
    proposal[field] = facts[field]
    with pytest.raises(ContractFailure) as captured:
        parse_logistics_action(json.dumps({'action':'tool','name':'evaluate_logistics_plan','arguments':proposal}))
    assert captured.value.error.context['failure_stage']=='SCHEMA_VALIDATION'


def test_agent_records_coverage_turn_without_logging_invented_model_value(caplog):
    dataset, source, configuration = input_fixture()
    def mutate(turn,action):
        if turn==2: action['arguments']['cost_priority'][0]=PRIVATE
        return action
    agent, requests = agent_fixture(dataset,configuration,mutate=mutate)
    with pytest.raises(ContractFailure) as captured:
        call(agent.assess_with_trace(source))
    context = captured.value.error.context
    assert len(requests)==2 and context['logistics_turn']=='2' and context['role']=='LOGISTICS'
    assert context['failure_stage']=='COST_PRIORITY_COVERAGE'
    assert 'COST_PRIORITY_COVERAGE' in caplog.text
    assert PRIVATE not in caplog.text and PRIVATE not in captured.value.error.model_dump_json()
