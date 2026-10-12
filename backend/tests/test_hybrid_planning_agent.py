"""Offline real-client + shared-orchestrator + A SQLite integration, not live HTTP."""
import asyncio
from datetime import date, datetime, timedelta, timezone
import json

import httpx
import pytest

from app.agents.hybrid_planning_agent import HybridPlanningAgent, build_hybrid_configuration
from app.agents.rule_agent import RuleAgent
from app.auth import User
from app.contracts.dto import (
    ConfirmedContext, ConfirmedRequirements, DemoContext, InterpretRequestInput,
    ItineraryInput, LogisticsInput, OrchestrateInput, ProfileSnapshot,
    RecommendCampsitesInput, VersionContext,
)
from app.contracts.errors import ContractFailure
from app.contracts.enums import ExecutionMode
from app.contracts.ports import AgentPort
from app.llm.client import CampusModelClient
from app.llm.coordinator import PlanningCoordinator
from app.storage.database import Database
from app.storage.plan_queries import PlanQueries
from app.storage.repository import Repository
from app.storage.workflows import WorkflowService
from app.workflow import WorkflowConfiguration
from llm_fixtures import ROOT, completion, final_action, model_input, model_settings, tool_action
from test_rule_orchestration import FailOnce, Proxy, counts

call = asyncio.run
INPUTS = json.loads((ROOT / 'docs/demo/v2_inputs.json').read_text())


def components(case_id='normal', *, handler=None, settings=None, interval=20):
    dataset, _ = model_input()
    case = next(item for item in INPUTS['cases'] if item['id'] == case_id)
    fields = dict(case['request']['explicit_fields'])
    start_date = date.fromisoformat(fields['start_date'])
    fields.update(end_date=start_date + timedelta(days=fields['duration_nights']),
                  duration_days=fields['duration_nights'] + 1)
    req = ConfirmedRequirements.model_validate(fields)
    demo = DemoContext(mode='agent', dataset_version='2.0.0', demo_today=case['settings']['demo_today'])
    sites = {'normal': 'demo-wattle-rest', 'budget_revision': 'demo-wattle-rest',
             'missing_evidence': 'demo-river-flat', 'road_closure': 'demo-moonlit-field'}
    actions = [tool_action(), final_action(campsite_id=sites[case_id],
        nights=[(start_date + timedelta(days=i)).isoformat() for i in range(req.duration_nights)])]
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        if handler:
            return handler(request)
        return httpx.Response(200, json=completion(actions[(len(requests) - 1) % 2]))
    client = CampusModelClient(settings or model_settings(), transport=httpx.MockTransport(respond))
    coordinator = PlanningCoordinator(dataset, client)
    config = build_hybrid_configuration(dataset, coordinator,
        safety_case_ids=case['settings']['workflow_safety_case_ids'])
    agent = HybridPlanningAgent(dataset, coordinator, workflow_configuration=config, heartbeat_interval=interval)
    recommend = RecommendCampsitesInput(confirmed_requirements=req,
        profile_snapshot=ProfileSnapshot.model_validate(INPUTS['profile']), demo_context=demo)
    return agent, recommend, requests


def start(tmp_path, agent, input):
    db = Database(tmp_path / 'hybrid.sqlite3')
    db.initialize()
    user = User('hybrid-camper', 'hybrid-camper', 'Hybrid', 'CAMPER')
    with db.transaction() as connection:
        connection.execute('INSERT INTO users VALUES(?,?,?,?,?)', (user.id, user.username, 'Hybrid', 'CAMPER', 'test-only'))
    clock = [1000.0]
    service = WorkflowService(db, clock=lambda: clock[0], lease_seconds=60)
    confirmed = ConfirmedContext(request_id='hybrid-request', confirmed_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
        requirements=input.confirmed_requirements, profile_snapshot=input.profile_snapshot,
        demo_context=input.demo_context, dataset_context=agent.workflow_configuration.context)
    Repository(db).record_confirmed_request(user, 'Explicit isolated agent fixture; not HTTP confirmation evidence.', confirmed)
    scope = service.start(user, confirmed.request_id, input.demo_context, confirmed.dataset_context, command_key='hybrid-start')
    attempt = service.claim(user, scope.run_id, input.demo_context, confirmed.dataset_context)
    return service, user, clock, OrchestrateInput(run_scope=scope, confirmed_context=confirmed), service.port(user, attempt)


def retry(service, user, input, agent):
    with service.db.transaction(write=False) as connection:
        revision = connection.execute('SELECT revision FROM runs WHERE id=?', (input.run_scope.run_id,)).fetchone()[0]
    service.retry(user, input.run_scope.run_id, input.run_scope.demo_context, agent.workflow_configuration.context,
        command_key='hybrid-retry', expected_run_revision=revision)
    attempt = service.claim(user, input.run_scope.run_id, input.run_scope.demo_context, agent.workflow_configuration.context)
    return service.port(user, attempt)


def itinerary_input(agent, input):
    return ItineraryInput(**input.model_dump(), recommendations=call(agent.recommend_campsites(input)))


def test_agent_port_rules_do_not_call_model_and_do_not_relabel_inputs():
    agent, input, requests = components()
    assert isinstance(agent, AgentPort)
    interpreted = call(agent.interpret_request(InterpretRequestInput(raw_text=INPUTS['cases'][0]['request']['raw_text'],
        explicit_fields=INPUTS['cases'][0]['request']['explicit_fields'], profile_snapshot=input.profile_snapshot,
        demo_context=input.demo_context)))
    recommendations = call(agent.recommend_campsites(input))
    assert interpreted.execution_mode == recommendations.execution_mode == input.demo_context.mode == 'agent'
    assert 'deterministic rules, not an LLM' in ' '.join(interpreted.assumptions + recommendations.assumptions)
    assert interpreted.extracted_requirements.budget_cents == 32000
    assert not requests
    with pytest.raises(ContractFailure):
        call(RuleAgent(agent.dataset).recommend_campsites(input))


@pytest.mark.parametrize('case_id,total,safety_outcome,eligible', [
    ('normal', 25100, 'PASSED', True), ('budget_revision', 25100, 'PASSED', False),
    ('missing_evidence', 24100, 'REVIEW', False), ('road_closure', 23100, 'BLOCKED', False),
])
def test_four_agent_scenarios_use_model_plan_and_real_a_persistence(tmp_path, case_id, total, safety_outcome, eligible):
    agent, input, requests = components(case_id)
    service, user, _, run_input, port = start(tmp_path, agent, input)
    result = call(agent.orchestrate(run_input, port))
    assert result.run_status == 'SUCCEEDED', result.error
    assert result.execution_mode == 'agent'
    assert len(requests) == 2 and requests[0]['model'] == 'campus-qwen'
    assert 'TOOL_RESULT=' in requests[1]['messages'][-1]['content']
    detail = PlanQueries(service.db).detail(user, run_input.run_scope.plan_id)
    assert detail['version']['content']['execution_mode'] == 'agent'
    assessments = {item['kind']: item for item in detail['assessments']}
    assert assessments['LOGISTICS']['result']['total_cents'] == total
    assert assessments['SAFETY']['result']['outcome'] == safety_outcome
    assert assessments['SAFETY']['depends_on_assessment_id'] == assessments['LOGISTICS']['assessment_id']
    assert all(item['result']['execution_mode'] == 'agent' for item in assessments.values())
    assert all('deterministic rules, not an LLM' in ' '.join(item['result']['assumptions']) for item in assessments.values())
    assert detail['finalisation_available'] is eligible
    assert counts(service) == dict(recommendations=1, versions=1, assessments=2, gear_checklists=1, write_receipts=5, final_records=0)
    assert input.demo_context.mode == 'agent'


@pytest.mark.parametrize('method,expected_model_calls', [
    ('save_recommendations', 2), ('append_plan_version', 2), ('save_assessment', 2), ('route_assessed_version', 2),
])
def test_lost_write_receipts_resume_without_regenerating_saved_model_version(tmp_path, method, expected_model_calls):
    agent, input, requests = components()
    service, user, _, run_input, port = start(tmp_path, agent, input)
    assert call(agent.orchestrate(run_input, FailOnce(port, method))).run_status == 'FAILED'
    restored = retry(service, user, run_input, agent)
    checkpoint = call(restored.load_checkpoint())
    # Process restart: a new wrapper uses the same bound snapshot/identity.
    restarted = HybridPlanningAgent(agent.dataset, agent.coordinator, workflow_configuration=agent.workflow_configuration)
    result = call(restarted.orchestrate(run_input, restored))
    assert result.run_status == 'SUCCEEDED'
    assert len(requests) == expected_model_calls
    after = PlanQueries(service.db).detail(user, run_input.run_scope.plan_id)
    if checkpoint['version']:
        assert after['version']['content'] == checkpoint['version'].content.model_dump(mode='json')
        assert result.artifact_refs['version'] == checkpoint['version'].version_context.plan_version_id
    assert counts(service)['versions'] == 1 and counts(service)['assessments'] == 2


def test_failure_before_version_write_may_plan_again_but_never_rewrites_saved_content(tmp_path):
    agent, input, requests = components()
    service, user, _, run_input, port = start(tmp_path, agent, input)
    assert call(agent.orchestrate(run_input, FailOnce(port, 'append_plan_version', after=False))).run_status == 'FAILED'
    assert counts(service)['versions'] == 0
    assert call(agent.orchestrate(run_input, retry(service, user, run_input, agent))).run_status == 'SUCCEEDED'
    assert len(requests) == 4 and counts(service)['versions'] == 1


@pytest.mark.parametrize('handler,settings,expected_calls', [
    (lambda request: httpx.Response(503, json={'error': 'not retained'}), None, 1),
    (lambda request: httpx.Response(200, json=completion(final_action())), None, 1),
    (None, model_settings(api_key=''), 0),
    (lambda request: httpx.Response(200, json=completion(final_action(campsite_id='invented'))), None, 1),
])
def test_model_failure_never_falls_back_or_saves_fake_agent_version(tmp_path, handler, settings, expected_calls):
    agent, input, requests = components(handler=handler, settings=settings)
    service, _, _, run_input, port = start(tmp_path, agent, input)
    result = call(agent.orchestrate(run_input, port))
    assert result.run_status == 'FAILED' and result.stage == 'GENERATING'
    assert result.execution_mode == 'agent' and len(requests) == expected_calls
    assert counts(service)['versions'] == counts(service)['assessments'] == 0


@pytest.mark.parametrize('mode', ['stub', 'deterministic_demo'])
def test_hybrid_rejects_other_modes_before_business_writes(tmp_path, mode):
    agent, input, requests = components()
    changed = input.model_copy(update={'demo_context': input.demo_context.model_copy(update={'mode': ExecutionMode(mode)})})
    with pytest.raises(ContractFailure):
        call(agent.recommend_campsites(changed))
    service, _, _, run_input, port = start(tmp_path, agent, changed)
    assert call(agent.orchestrate(run_input, port)).run_status == 'FAILED'
    assert counts(service)['recommendations'] == 0 and not requests


@pytest.mark.parametrize('operation', ['REVISE', 'REASSESS'])
def test_unsupported_operation_is_explicit_and_does_not_touch_port(tmp_path, operation):
    agent, input, requests = components()
    _, _, _, run_input, _ = start(tmp_path, agent, input)
    run_input = run_input.model_copy(update={'run_scope': run_input.run_scope.model_copy(update={'operation': operation})})
    with pytest.raises(ContractFailure) as error:
        call(agent.orchestrate(run_input, object()))
    assert error.value.error.code == 'INPUT_INVALID' and not requests


def test_registered_context_preserves_all_a_identity_and_guards_drift(tmp_path):
    agent, input, requests = components()
    base = agent.dataset.context.model_copy(deep=True)
    base.file_digests['a-extra.json'] = 'a' * 64
    base.fixture_digests['a-fixture.json'] = 'b' * 64
    base.selection_config['a_runtime_bound'] = '1'
    base = base.model_copy(update={'rules_version': base.rules_version + '/a-runtime-bindings-v2'})
    config = build_hybrid_configuration(agent.dataset, agent.coordinator, safety_case_ids=['safety-15'], registered_context=base)
    assert config.context.file_digests == base.file_digests
    assert config.context.fixture_digests == base.fixture_digests
    assert config.context.selection_config['a_runtime_bound'] == '1'
    assert config.context.rules_version.startswith(base.rules_version + '/')
    assert 'unit-only-school-secret' not in config.context.model_dump_json()
    agent = HybridPlanningAgent(agent.dataset, agent.coordinator, workflow_configuration=config)
    service, _, _, run_input, port = start(tmp_path, agent, input)
    agent.coordinator.client.settings = model_settings(max_completion_tokens=1024)
    result = call(agent.orchestrate(run_input, port))
    assert result.error.code == 'STALE_CONTEXT'
    assert counts(service)['recommendations'] == 0 and not requests


def test_drift_while_model_is_waiting_rejects_outcome_before_save(tmp_path):
    agent, input, requests = components()
    original = agent.coordinator.plan
    async def drift(value):
        outcome = await original(value)
        agent.coordinator.client.settings = model_settings(max_completion_tokens=1024)
        return outcome
    agent.coordinator.plan = drift
    service, _, _, run_input, port = start(tmp_path, agent, input)
    result = call(agent.orchestrate(run_input, port))
    assert result.error.code == 'STALE_CONTEXT' and len(requests) == 2
    assert counts(service)['versions'] == 0


def test_configuration_requires_same_snapshot_and_registered_hybrid_identity():
    agent, _, _ = components()
    other, _ = model_input()
    with pytest.raises(ContractFailure):
        HybridPlanningAgent(other, agent.coordinator)
    with pytest.raises(ContractFailure):
        HybridPlanningAgent(agent.dataset, agent.coordinator, workflow_configuration=WorkflowConfiguration(agent.dataset))
    base = agent.dataset.context.model_copy(deep=True)
    base.selection_config['hybrid_planning_fingerprint'] = 'wrong'
    with pytest.raises(ContractFailure):
        build_hybrid_configuration(agent.dataset, agent.coordinator, registered_context=base)


def test_transient_trace_is_caller_owned_and_no_global_last_result_cache():
    agent, input, requests = components()
    value = itinerary_input(agent, input)
    outcome = call(agent.plan_with_trace(value))
    assert outcome.itinerary.execution_mode == 'agent' and outcome.trace.validation_passed
    assert outcome.trace.configuration_fingerprint == agent.workflow_configuration.context.selection_config['hybrid_planning_fingerprint']
    assert len(requests) == 2
    assert not hasattr(agent, 'last_trace') and not hasattr(agent.coordinator, 'last_trace')


def test_agent_assessments_reject_deterministic_saved_itinerary():
    agent, input, _ = components()
    content = call(agent.generate_or_revise_itinerary(itinerary_input(agent, input)))
    context = VersionContext(plan_id='plan', plan_version_id='version', run_id='run', input_fingerprint='a' * 64)
    value = LogisticsInput(version_context=context, saved_itinerary=content.model_copy(update={'execution_mode': ExecutionMode.DETERMINISTIC_DEMO}),
        confirmed_requirements=input.confirmed_requirements, profile_snapshot=input.profile_snapshot, demo_context=input.demo_context)
    with pytest.raises(ContractFailure):
        call(agent.assess_gear_and_logistics(value))


def test_heartbeat_renews_during_async_client_wait(tmp_path):
    agent, input, requests = components(interval=.005)
    original = agent.coordinator.client.transport
    async def slow(request):
        await asyncio.sleep(.035)
        return await original.handle_async_request(request)
    agent.coordinator.client.transport = httpx.MockTransport(slow)
    service, _, _, run_input, port = start(tmp_path, agent, input)
    class CountingPort(Proxy):
        beats = 0
        async def heartbeat(self):
            self.beats += 1
            return await self.port.heartbeat()
    tracked = CountingPort(port)
    result = call(agent.orchestrate(run_input, tracked))
    assert result.run_status == 'SUCCEEDED' and tracked.beats > 25 and len(requests) == 2


def test_lost_lease_cancels_model_without_saving_then_retries(tmp_path):
    agent, input, requests = components(interval=.005)
    original = agent.coordinator.client.transport
    cancelled = []
    clock_ref = []
    async def expired(request):
        clock_ref[0][0] += 61
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return await original.handle_async_request(request)
    agent.coordinator.client.transport = httpx.MockTransport(expired)
    service, user, clock, run_input, port = start(tmp_path, agent, input)
    clock_ref.append(clock)
    with pytest.raises(ContractFailure):
        call(agent.orchestrate(run_input, port))
    assert cancelled == [True] and counts(service)['versions'] == 0
    service.expire(user, run_input.run_scope.run_id)
    agent.coordinator.client.transport = original
    assert call(agent.orchestrate(run_input, retry(service, user, run_input, agent))).run_status == 'SUCCEEDED'
    assert len(requests) == 2
