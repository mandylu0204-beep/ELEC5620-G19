"""Offline campus logistics role: actual client, sealed facts and host arithmetic."""
import asyncio
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path

import httpx
import pytest

from app.agents.hybrid_planning_agent import HybridPlanningAgent, build_hybrid_configuration
from app.agents.rules import logistics
from app.contracts.dto import GearItem, LogisticsInput, VersionContext
from app.contracts.enums import ExecutionMode
from app.contracts.errors import ContractFailure
from app.llm.client import CampusModelClient
from app.llm.coordinator import PlanningCoordinator
from app.llm.logistics_agent import LogisticsAgent
from app.llm.logistics_schema import LogisticsProposal, parse_logistics_action
from app.llm.logistics_tools import LogisticsToolset
from app.llm.planning_schema import validated_itinerary
from app.workflow import WorkflowConfiguration
from llm_fixtures import completion, final_action, model_input, model_settings

call = asyncio.run


def input_fixture(*, missing=(), unknown=(), group_size=None, km=None, budget=None):
    dataset, planning = model_input()
    content = validated_itinerary(dataset, planning, final_action()['proposal'],
        [item.campsite_id for item in planning.recommendations.candidates])
    profile = planning.profile_snapshot.model_dump(mode='json')
    profile['equipment'] = [item for item in profile['equipment'] if item['item_key'] not in missing]
    for item in profile['equipment']:
        if item['item_key'] in unknown:
            item['confirmed'] = False
    if group_size is not None:
        profile['group_size'] = group_size
    if km is not None:
        profile['transport']['estimated_km'] = str(km)
    requirements = planning.confirmed_requirements.model_dump(mode='json')
    if budget is not None:
        requirements['budget_cents'] = budget
    input = LogisticsInput(version_context=VersionContext(plan_id='independent-plan', plan_version_id='independent-version',
        run_id='independent-run', input_fingerprint='a' * 64), saved_itinerary=content,
        confirmed_requirements=requirements, profile_snapshot=profile, demo_context=planning.demo_context)
    config = WorkflowConfiguration(dataset, safety_case_ids=['safety-15'])
    return dataset, input, config


def proposal_from_facts(facts, *, methods=None, reverse=False):
    methods = methods or {}
    return {
        'gear_choices': [{'item_key': item['item_key'], 'method': methods.get(item['item_key'], item['allowed_methods'][0]),
            'reason': 'Use the allowed arrangement, subject to independent confirmation.'} for item in facts['gear']],
        'cost_priority': [item['line_id'] for item in (reversed(facts['costs']) if reverse else facts['costs'])],
        'decision_summary': 'Prioritize the recorded needs and verify supply arrangements before departure.',
    }


def agent_fixture(dataset, config, *, methods=None, reverse=False, mutate=None, settings=None, on_request=None):
    requests = []
    async def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if on_request:
            await on_request(request)
        messages = payload['messages']
        tool_results = [json.loads(message['content'][12:]) for message in messages if message['content'].startswith('TOOL_RESULT=')]
        if not tool_results:
            value = {'action': 'tool', 'name': 'read_logistics_facts', 'arguments': {}}
        else:
            # Independent model surrogate uses only the facts actually exposed.
            proposal = proposal_from_facts(tool_results[0], methods=methods, reverse=reverse)
            value = {'action': 'tool', 'name': 'evaluate_logistics_plan', 'arguments': proposal} if len(tool_results) == 1 else {
                'action': 'final', 'proposal': proposal}
        if mutate:
            value = mutate(len(requests), value)
        return httpx.Response(200, json=completion(value, model='offline-test-only'))
    client = CampusModelClient(settings or model_settings(), transport=httpx.MockTransport(respond))
    return LogisticsAgent(dataset, client, workflow_configuration=config), requests


def baseline(dataset, input, config):
    return logistics.assess(dataset, input, expected_mode=ExecutionMode.AGENT,
        safety_case_ids=json.loads(config.context.selection_config['safety_case_ids']))


def test_model_reads_facts_evaluates_structured_plan_and_returns_shared_agent_result():
    dataset, input, config = input_fixture()
    agent, requests = agent_fixture(dataset, config)
    outcome = call(agent.assess_with_trace(input))
    original = baseline(dataset, input, config)
    assert len(requests) == outcome.trace.turns == outcome.trace.http_attempts == 3
    assert outcome.trace.tool_calls == ['read_logistics_facts', 'evaluate_logistics_plan']
    assert outcome.trace.role == 'LOGISTICS' and outcome.trace.served_models == ['offline-test-only']
    assert outcome.trace.usage['total_tokens'] == 480 and outcome.trace.validation_passed
    assert outcome.assessment.execution_mode == 'agent' and outcome.assessment.version_context == input.version_context
    assert outcome.assessment.total_cents == original.total_cents == 25100
    assert outcome.assessment.gear_checklist == original.gear_checklist
    assert outcome.assessment.mandatory_blockers == original.mandatory_blockers
    assert outcome.assessment.clarifications == original.clarifications
    assert set(item.fact.item_key for item in outcome.plan.gear_actions) == set(item.item_key for item in original.gear_checklist)
    assert input.profile_snapshot == input_fixture()[1].profile_snapshot
    for private in ['independent-plan', 'independent-version', 'independent-run', 'unit-only-school-secret', 'expected_outcome', 'write_keys']:
        assert private not in json.dumps(requests)
        assert private not in outcome.trace.model_dump_json()


def test_evaluation_feedback_keeps_computed_values_and_exact_proposal_without_repeated_facts():
    dataset, input, config = input_fixture(missing=['sleeping_bag'])
    agent, requests = agent_fixture(dataset, config)
    outcome = call(agent.assess_with_trace(input))
    messages = requests[2]['messages']
    action = json.loads(messages[-2]['content'])
    feedback = json.loads(messages[-1]['content'][12:])
    assert feedback['evaluated_proposal'] == action['arguments']
    assert feedback['confirmation_is_not_granted'] is True
    wire = feedback['plan']
    saved = outcome.plan.model_dump(mode='json')
    for field in ('budget_allocations', 'projected_cost_breakdown', 'projected_total_cents',
                  'known_subtotal_cents', 'budget_difference_cents', 'budget_feasible',
                  'unallocated_known_budget_cents', 'requires_user_confirmation'):
        assert wire[field] == saved[field]
    assert 'source_refs' not in wire and saved['source_refs']
    for thin, full in zip(wire['gear_actions'], saved['gear_actions']):
        assert thin == {key: value for key, value in full.items() if key not in {'fact', 'price_source'}} | {
            'item_key': full['fact']['item_key']}
    original = {'tool': 'evaluate_logistics_plan', 'read_only': True, 'plan': saved,
                'rule_outcome': feedback['rule_outcome'], 'confirmation_is_not_granted': True}
    assert len(json.dumps(feedback).encode()) < len(json.dumps(original).encode())
    # The earlier read is unchanged: each original source, blocker and quote is
    # still available to the model; the persisted plan remains the full object.
    facts = json.loads(messages[3]['content'][12:])
    tools = LogisticsToolset(input, baseline(dataset, input, config))
    assert facts == tools.read_logistics_facts()


def test_prompt_changes_alter_registered_identity_without_changing_persistence_validation(monkeypatch):
    from app.llm import logistics_agent
    dataset, _, config = input_fixture()
    agent, _ = agent_fixture(dataset, config)
    before = agent.identity
    monkeypatch.setattr(logistics_agent, 'LOGISTICS_SYSTEM_PROMPT', logistics_agent.LOGISTICS_SYSTEM_PROMPT + '\nShorter wire instructions.')
    after = agent.identity
    assert before['prompt_sha256'] != after['prompt_sha256']
    assert before['configuration_fingerprint'] != after['configuration_fingerprint']
    for key in ('agent_version', 'tool_version', 'validation_version', 'kernel_version'):
        assert before[key] == after[key]


def test_model_choices_change_supply_strategy_and_computed_costs_not_only_summary():
    dataset, input, config = input_fixture(missing=['sleeping_bag'])
    hire, _ = agent_fixture(dataset, config)
    borrow, _ = agent_fixture(dataset, config, methods={'sleeping_bag': 'PROPOSE_BORROW'})
    rented = call(hire.assess_with_trace(input))
    borrowed = call(borrow.assess_with_trace(input))
    hire_item = next(item for item in rented.plan.gear_actions if item.fact.item_key == 'sleeping_bag')
    borrow_item = next(item for item in borrowed.plan.gear_actions if item.fact.item_key == 'sleeping_bag')
    assert hire_item.method == 'PROPOSE_RENTAL' and hire_item.procurement_quantity == Decimal(2)
    assert hire_item.estimated_cost_cents == 4400 and hire_item.price_source.record_id == 'cost-07'
    assert borrow_item.method == 'PROPOSE_BORROW' and borrow_item.estimated_cost_cents is None
    assert rented.plan.projected_total_cents == 29500 and borrowed.plan.projected_total_cents is None
    assert borrowed.assessment.total_cents is None and borrowed.assessment.budget_difference_cents is None
    assert borrowed.plan.budget_feasible is None
    assert rented.assessment.outcome == borrowed.assessment.outcome == 'REVISION'
    assert rented.assessment.gear_checklist == borrowed.assessment.gear_checklist
    assert all(item.confirmation_required for item in [hire_item, borrow_item])
    assert hire_item.fact.arrangement_status == borrow_item.fact.arrangement_status == 'MISSING'
    assert any(item.code == 'ESSENTIAL_GEAR_MISSING' for item in rented.assessment.mandatory_blockers)


def test_tent_capacity_and_trip_hire_price_are_host_computed_without_extra_nights():
    dataset, input, config = input_fixture(group_size=5)
    agent, _ = agent_fixture(dataset, config)
    outcome = call(agent.assess_with_trace(input))
    tent = next(item for item in outcome.plan.gear_actions if item.fact.item_key == 'tent')
    assert tent.fact.required_quantity == 5 and tent.fact.available_quantity == 2 and tent.fact.missing_quantity == 3
    assert tent.fact.capacity_requirement == 5
    assert tent.procurement_quantity == 2 and tent.procurement_unit == 'per_item'
    assert tent.estimated_cost_cents == 9000  # ceil(3 spaces / 2) * 4500, NOT * nights.
    assert tent.confirmation_required and tent.fact.arrangement_status == 'MISSING'
    assert outcome.assessment.outcome == 'REVISION'


def test_decimal_rounding_and_allocation_are_host_computed():
    dataset, input, config = input_fixture(km=Decimal('3.5'), budget=10000)
    normal, _ = agent_fixture(dataset, config)
    reversed_agent, _ = agent_fixture(dataset, config, reverse=True)
    first = call(normal.assess_with_trace(input))
    other = call(reversed_agent.assess_with_trace(input))
    car = next(item for item in first.assessment.cost_breakdown if item.item_key == 'cost-02')
    assert car.quantity == Decimal('3.5') and car.unit_price_cents == 35 and car.subtotal_cents == 123
    assert first.assessment.total_cents == other.assessment.total_cents == 21723
    assert first.plan.budget_feasible is False and first.assessment.outcome == 'REVISION'
    assert first.plan.budget_allocations != other.plan.budget_allocations
    assert sum(item.allocated_cents or 0 for item in first.plan.budget_allocations) == 10000
    assert sum(item.unfunded_cents or 0 for item in first.plan.budget_allocations) == 11723
    assert first.plan.unallocated_known_budget_cents == 0
    assert input.confirmed_requirements.budget_cents == 10000


def test_unknown_stock_is_not_zero_or_confirmed_and_weather_clarifications_survive():
    dataset, input, config = input_fixture(unknown=['sleeping_bag'])
    agent, _ = agent_fixture(dataset, config)
    outcome = call(agent.assess_with_trace(input))
    item = next(item for item in outcome.plan.gear_actions if item.fact.item_key == 'sleeping_bag')
    assert item.method == 'ASK_USER' and item.procurement_quantity is None and item.estimated_cost_cents is None
    assert item.fact.available_quantity is None and item.fact.missing_quantity is None
    assert item.fact.arrangement_status == 'UNCONFIRMED'
    assert outcome.assessment.total_cents is None and outcome.assessment.outcome == 'REVISION'
    assert any(item.field == 'equipment.sleeping_bag' for item in outcome.assessment.clarifications)
    empty_config = WorkflowConfiguration(dataset)  # Weather was not silently inferred from unselected fixtures.
    unknown_weather, _ = agent_fixture(dataset, empty_config)
    result = call(unknown_weather.assess_with_trace(input))
    assert any('gear_rule_input' in item.field for item in result.assessment.clarifications)
    assert result.assessment.outcome == 'REVISION'


def test_unpriced_optional_supply_cannot_be_omitted_from_projected_cost():
    dataset, input, config = input_fixture()
    original = baseline(dataset, input, config)
    # Explicit isolated tool fact, not a change to sealed data or a live record.
    optional = GearItem(item_key='optional_cover', required_quantity='1', available_quantity='0',
        missing_quantity='1', unit='item', arrangement_status='MISSING', essential=False)
    tools = LogisticsToolset(input, original.model_copy(update={'gear_checklist': [*original.gear_checklist, optional]}))
    proposal = LogisticsProposal.model_validate(proposal_from_facts(tools.read_logistics_facts(),
        methods={'optional_cover': 'PROPOSE_BORROW'}))
    plan = tools.evaluate_logistics_plan(proposal)
    assert plan.projected_total_cents is None and plan.budget_feasible is None
    assert any(item.line_id == 'unpriced-optional_cover' and item.required_cents is None for item in plan.budget_allocations)
    assert tools.result(plan).outcome == 'REVISION'
    deferred = tools.evaluate_logistics_plan(LogisticsProposal.model_validate(proposal_from_facts(tools.read_logistics_facts(),
        methods={'optional_cover': 'DEFER_OPTIONAL'})))
    assert deferred.projected_total_cents == original.total_cents
    assert deferred.gear_actions[-1].fact.arrangement_status == 'MISSING'
    assert deferred.gear_actions[-1].procurement_quantity == 0 and not deferred.gear_actions[-1].confirmation_required


def test_missing_reference_rate_is_not_zero_or_a_priced_purchase():
    dataset, input, config = input_fixture(missing=['sleeping_bag'])
    old = dataset.get_cost_reference('cost-07')
    dataset._costs['cost-07'] = old.model_copy(update={'typical_cents': None})
    agent, _ = agent_fixture(dataset, config)
    outcome = call(agent.assess_with_trace(input))
    assert outcome.assessment.total_cents is None
    assert next(item for item in outcome.plan.gear_actions if item.fact.item_key == 'sleeping_bag').estimated_cost_cents is None
    agent, _ = agent_fixture(dataset, config, methods={'sleeping_bag': 'PROPOSE_RENTAL'})
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(input))


@pytest.mark.parametrize('method', ['KEEP_CONFIRMED', 'CONFIRMED_RENTAL', 'OWNED', 'PURCHASE_NOW', 'DEFER_OPTIONAL'])
def test_model_cannot_invent_stock_or_confirm_procurement(method):
    dataset, input, config = input_fixture(missing=['sleeping_bag'])
    agent, requests = agent_fixture(dataset, config, methods={'sleeping_bag': method})
    with pytest.raises(ContractFailure) as error:
        call(agent.assess_with_trace(input))
    assert error.value.error.code == 'CONTRACT_INVALID' and len(requests) == 2


@pytest.mark.parametrize('field,value', [
    ('quantity', '1'), ('available_quantity', '99'), ('capacity_persons', 99),
    ('unit_price_cents', 1), ('subtotal_cents', 0), ('confirmed', True), ('source_ref', {}),
])
def test_model_cannot_supply_numeric_or_confirmation_fields(field, value):
    dataset, input, config = input_fixture()
    def mutate(turn, action):
        if turn == 2:
            action['arguments']['gear_choices'][0][field] = value
        return action
    agent, requests = agent_fixture(dataset, config, mutate=mutate)
    with pytest.raises(ContractFailure) as error:
        call(agent.assess_with_trace(input))
    assert error.value.error.code == 'CONTRACT_INVALID' and len(requests) == 2


@pytest.mark.parametrize('field,value', [
    ('budget_cents', 999999), ('total_cents', 0), ('outcome', 'PASSED'),
    ('mandatory_blockers', []), ('source_refs', []), ('confirmed_requirements', {}),
])
def test_model_cannot_override_confirmed_budget_or_rule_verdict(field, value):
    dataset, input, config = input_fixture()
    def mutate(turn, action):
        if turn == 2:
            action['arguments'][field] = value
        return action
    agent, _ = agent_fixture(dataset, config, mutate=mutate)
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(input))


@pytest.mark.parametrize('change', ['omit-gear', 'duplicate-gear', 'invent-gear', 'omit-cost', 'duplicate-cost', 'invent-cost'])
def test_proposals_must_cover_all_facts_without_omitting_essential_items_or_costs(change):
    dataset, input, config = input_fixture()
    def mutate(turn, action):
        if turn == 2:
            proposal = action['arguments']
            if change == 'omit-gear': proposal['gear_choices'].pop()
            elif change == 'duplicate-gear': proposal['gear_choices'].append(proposal['gear_choices'][0])
            elif change == 'invent-gear': proposal['gear_choices'][0]['item_key'] = 'invented'
            elif change == 'omit-cost': proposal['cost_priority'].pop()
            elif change == 'duplicate-cost': proposal['cost_priority'].append(proposal['cost_priority'][0])
            else: proposal['cost_priority'][0] = 'read_sql'
        return action
    agent, _ = agent_fixture(dataset, config, mutate=mutate)
    with pytest.raises(ContractFailure) as error:
        call(agent.assess_with_trace(input))
    assert error.value.error.code == 'CONTRACT_INVALID'


@pytest.mark.parametrize('body', [
    'not json', '{"action":"tool","action":"final"}',
    '{"action":"tool","name":"read_file","arguments":{"path":"tests/oracle.json"}}',
    '{"action":"tool","name":"read_logistics_facts","arguments":{"budget_cents":1}}',
    '{"action":"tool","name":"purchase","arguments":{}}',
    '<think>private reasoning</think>{"action":"tool","name":"read_logistics_facts","arguments":{}}',
], ids=['invalid-json', 'duplicate-key', 'unknown-file-tool', 'overridden-budget', 'purchase-tool', 'private-reasoning'])
def test_protocol_rejects_uncontrolled_tools_extra_fields_and_non_json(body):
    with pytest.raises(ContractFailure):
        parse_logistics_action(body)


def test_final_must_match_a_previously_evaluated_plan():
    dataset, input, config = input_fixture()
    def mutate(turn, action):
        if turn == 3:
            action['proposal']['cost_priority'].reverse()
        return action
    agent, requests = agent_fixture(dataset, config, mutate=mutate)
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(input))
    assert len(requests) == 3
    def skip(turn, action):
        if turn == 2:
            return {'action': 'final', 'proposal': action['arguments']}
        return action
    agent, requests = agent_fixture(dataset, config, mutate=skip)
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(input))
    assert len(requests) == 2


def test_loop_is_bounded_and_missing_credentials_never_return_rule_fallback():
    dataset, input, config = input_fixture()
    agent, requests = agent_fixture(dataset, config, mutate=lambda turn, action:
        {'action': 'tool', 'name': 'read_logistics_facts', 'arguments': {}})
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(input))
    assert len(requests) == 4
    agent, requests = agent_fixture(dataset, config, settings=model_settings(api_key=''))
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(input))
    assert not requests
    agent, requests = agent_fixture(dataset, config, settings=model_settings(max_turns=2))
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(input))
    assert not requests


@pytest.mark.parametrize('problem', ['mode', 'saved-mode', 'dataset', 'past', 'invalid-dto'])
def test_invalid_input_is_rejected_before_model_call(problem):
    dataset, input, config = input_fixture()
    agent, requests = agent_fixture(dataset, config)
    if problem == 'mode': input = input.model_copy(update={'demo_context': input.demo_context.model_copy(update={'mode': ExecutionMode.DETERMINISTIC_DEMO})})
    elif problem == 'saved-mode': input = input.model_copy(update={'saved_itinerary': input.saved_itinerary.model_copy(update={'execution_mode': ExecutionMode.DETERMINISTIC_DEMO})})
    elif problem == 'dataset': input = input.model_copy(update={'demo_context': input.demo_context.model_copy(update={'dataset_version': 'different'})})
    elif problem == 'past': input = input.model_copy(update={'demo_context': input.demo_context.model_copy(update={'demo_today': input.confirmed_requirements.start_date + timedelta(days=1)})})
    else: input = {}
    with pytest.raises(ContractFailure):
        call(agent.assess_with_trace(input))
    assert not requests


@pytest.mark.parametrize('change', ['price', 'model-config', 'selected-safety', 'reasoning-effort'])
def test_identity_and_fact_changes_during_model_wait_reject_outcome(change):
    dataset, input, config = input_fixture()
    agent_ref = []
    async def on_request(request):
        if change == 'price':
            old = dataset.get_cost_reference('cost-02')
            dataset._costs['cost-02'] = old.model_copy(update={'typical_cents': 99})
        elif change == 'model-config':
            agent_ref[0].client.settings = model_settings(timeout_seconds=6)
        elif change == 'reasoning-effort':
            agent_ref[0].client.settings = model_settings(reasoning_effort='low')
        else:
            config._context.selection_config['safety_case_ids'] = '[]'
    agent, requests = agent_fixture(dataset, config, on_request=on_request)
    agent_ref.append(agent)
    with pytest.raises(ContractFailure) as error:
        call(agent.assess_with_trace(input))
    assert error.value.error.code == 'STALE_CONTEXT' and len(requests) == 1


def test_second_round_proxy_failure_has_bounded_sanitized_operational_metadata():
    dataset, input, config = input_fixture()
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(200, json=completion({
                'action': 'tool', 'name': 'read_logistics_facts', 'arguments': {}}))
        return httpx.Response(502, text='unit-only-school-secret private upstream response')
    agent = LogisticsAgent(dataset, CampusModelClient(model_settings(), transport=httpx.MockTransport(respond)),
                           workflow_configuration=config)
    with pytest.raises(ContractFailure) as error:
        call(agent.assess_with_trace(input))
    metadata = error.value.error.context
    assert len(requests) == 2 and error.value.error.recoverable
    assert metadata['http_status'] == '502' and metadata['role'] == 'LOGISTICS'
    assert metadata['logistics_turn'] == '2' and int(metadata['elapsed_ms']) >= 0
    assert int(metadata['request_message_bytes']) == sum(len(m['content'].encode()) for m in requests[1]['messages'])
    assert 'unit-only-school-secret' not in str(metadata) and 'private upstream response' not in str(metadata)


def test_tools_are_detached_and_do_not_read_files_or_oracles_after_loading(monkeypatch):
    dataset, input, config = input_fixture()
    original = baseline(dataset, input, config)
    tools = LogisticsToolset(input, original)
    facts = tools.read_logistics_facts()
    facts['gear'][0]['available_quantity'] = '999'
    assert tools.read_logistics_facts()['gear'][0]['available_quantity'] != '999'
    def denied(*args, **kwargs):
        raise AssertionError('Logistics tools must use the loaded business snapshot.')
    monkeypatch.setattr(Path, 'read_bytes', denied)
    monkeypatch.setattr(Path, 'read_text', denied)
    agent, _ = agent_fixture(dataset, config)
    assert call(agent.assess_with_trace(input)).trace.validation_passed


def test_logistics_component_does_not_silently_replace_registered_hybrid_rule_step():
    dataset, input, config = input_fixture()
    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(lambda request:
        (_ for _ in ()).throw(AssertionError('Existing Hybrid logistics must remain rules until audit integration.'))))
    planner = PlanningCoordinator(dataset, client)
    hybrid_config = build_hybrid_configuration(dataset, planner, safety_case_ids=['safety-15'])
    hybrid = HybridPlanningAgent(dataset, planner, workflow_configuration=hybrid_config)
    result = call(hybrid.assess_gear_and_logistics(input))
    assert result.total_cents == 25100 and 'uses deterministic rules' in ' '.join(result.assumptions)


def test_trace_and_outcomes_are_per_call_and_settings_identity_excludes_secret():
    dataset, input, config = input_fixture()
    agent, requests = agent_fixture(dataset, config)
    assert 'unit-only-school-secret' not in canonical_identity(agent.identity)
    rotated = LogisticsAgent(dataset, CampusModelClient(model_settings(api_key='different-fake-secret')), workflow_configuration=config)
    assert rotated.identity == agent.identity
    async def concurrent():
        return await asyncio.gather(agent.assess_with_trace(input), agent.assess_with_trace(input))
    first, second = call(concurrent())
    assert first.trace is not second.trace
    assert first.trace.input_sha256 == second.trace.input_sha256 and first.trace.proposal_sha256 == second.trace.proposal_sha256
    assert first.assessment == second.assessment and len(requests) == 6
    first.plan.gear_actions.clear()
    assert second.plan.gear_actions
    assert not hasattr(agent, 'last_trace')


def canonical_identity(identity):
    return json.dumps(identity, sort_keys=True)


@pytest.mark.parametrize('field', ['stock', 'capacity', 'quantity', 'price', 'funding', 'sources'])
def test_typed_tool_result_cannot_bypass_host_recalculation(field):
    dataset, input, config = input_fixture(missing=['sleeping_bag'])
    tools = LogisticsToolset(input, baseline(dataset, input, config))
    proposal = LogisticsProposal.model_validate(proposal_from_facts(tools.read_logistics_facts()))
    plan = tools.evaluate_logistics_plan(proposal).model_copy(deep=True)
    if field == 'stock':
        first = plan.gear_actions[0]
        plan.gear_actions[0] = first.model_copy(update={'fact': first.fact.model_copy(update={'available_quantity': Decimal(999)})})
    elif field == 'capacity':
        first = plan.gear_actions[0]
        plan.gear_actions[0] = first.model_copy(update={'fact': first.fact.model_copy(update={'capacity_requirement': 999})})
    elif field == 'quantity':
        plan.gear_actions[0] = plan.gear_actions[0].model_copy(update={'procurement_quantity': Decimal(999)})
    elif field == 'price':
        plan.projected_cost_breakdown[0] = plan.projected_cost_breakdown[0].model_copy(update={'unit_price_cents': 0, 'subtotal_cents': 0})
    elif field == 'funding':
        plan.budget_allocations[0] = plan.budget_allocations[0].model_copy(update={'allocated_cents': 999999})
    else:
        plan.source_refs.clear()
    with pytest.raises(ContractFailure):
        tools.result(plan)


def test_upstream_failure_and_cancellation_never_return_successful_assessment():
    dataset, input, config = input_fixture()
    failed = LogisticsAgent(dataset, CampusModelClient(model_settings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(503, json={'error': 'independent-failure'}))), workflow_configuration=config)
    with pytest.raises(ContractFailure) as error:
        call(failed.assess_with_trace(input))
    assert error.value.error.recoverable and error.value.error.code == 'AGENT_FAILURE'
    async def cancel_during_wait():
        entered, cancelled = asyncio.Event(), []
        async def waiting(request):
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
        agent = LogisticsAgent(dataset, CampusModelClient(model_settings(), transport=httpx.MockTransport(waiting)),
            workflow_configuration=config)
        task = asyncio.create_task(agent.assess_with_trace(input))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled == [True]
    call(cancel_during_wait())


def test_model_may_evaluate_multiple_strategies_before_selecting_one():
    dataset, input, config = input_fixture(missing=['sleeping_bag'])
    requests = []
    async def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        messages = payload['messages']
        results = [json.loads(item['content'][12:]) for item in messages if item['content'].startswith('TOOL_RESULT=')]
        if not results:
            action = {'action': 'tool', 'name': 'read_logistics_facts', 'arguments': {}}
        else:
            proposal = proposal_from_facts(results[0], methods={'sleeping_bag': 'PROPOSE_RENTAL' if len(results) == 1 else 'PROPOSE_BORROW'})
            action = {'action': 'final', 'proposal': proposal} if len(results) == 3 else {
                'action': 'tool', 'name': 'evaluate_logistics_plan', 'arguments': proposal}
        return httpx.Response(200, json=completion(action))
    agent = LogisticsAgent(dataset, CampusModelClient(model_settings(), transport=httpx.MockTransport(respond)), workflow_configuration=config)
    result = call(agent.assess_with_trace(input))
    assert len(requests) == 4 and result.assessment.total_cents is None
    assert result.trace.tool_calls == ['read_logistics_facts', 'evaluate_logistics_plan', 'evaluate_logistics_plan']
    assert next(item for item in result.plan.gear_actions if item.fact.item_key == 'sleeping_bag').method == 'PROPOSE_BORROW'
