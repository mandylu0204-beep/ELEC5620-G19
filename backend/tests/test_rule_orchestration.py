"""B-03 + A real SQLite integration; explicit isolated inputs, not UI proof."""
import asyncio
from datetime import datetime, timezone

import pytest

from app.agents.rule_agent import RuleAgent
from app.auth import User
from app.contracts.dto import ConfirmedContext, Evidence, OrchestrateInput, RunResult, RunSnapshot
from app.contracts.enums import ErrorCode, RunStage
from app.contracts.errors import ContractFailure
from app.storage.database import Database
from app.storage.plan_queries import PlanQueries
from app.storage.repository import Repository
from app.storage.workflows import WorkflowService
from app.workflow import WorkflowConfiguration
from app.workflow.configuration import failure
from rule_fixtures import DEMO, call, complete_scenario, full_profile, make_agent, requirements


class CountingAgent(RuleAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    async def recommend_campsites(self, input):
        self.calls.append('recommendations')
        return await super().recommend_campsites(input)

    async def generate_or_revise_itinerary(self, input):
        self.calls.append('version')
        return await super().generate_or_revise_itinerary(input)

    async def assess_gear_and_logistics(self, input):
        self.calls.append('logistics')
        return await super().assess_gear_and_logistics(input)

    async def assess_safety(self, input):
        self.calls.append('safety')
        return await super().assess_safety(input)


class Proxy:
    def __init__(self, port):
        self.port = port

    def __getattr__(self, name):
        return getattr(self.port, name)


class FailOnce(Proxy):
    def __init__(self, port, method, *, after=True):
        super().__init__(port)
        self.method, self.after, self.used = method, after, False

    def __getattr__(self, name):
        action = getattr(self.port, name)
        if name != self.method:
            return action

        async def invoke(*args, **kwargs):
            if self.used:
                return await action(*args, **kwargs)
            self.used = True
            if self.after:
                await action(*args, **kwargs)
            raise failure(ErrorCode.PERSISTENCE_FAILURE, 'Independent injected lost response / write failure.', recoverable=True)
        return invoke


@pytest.fixture
def setup(tmp_path):
    dataset = make_agent().dataset
    db = Database(tmp_path / 'b03.sqlite3')
    db.initialize()
    user = User('b03-camper', 'b03-camper', 'B03', 'CAMPER')
    with db.transaction() as connection:
        connection.execute('INSERT INTO users VALUES(?,?,?,?,?)', (user.id, user.username, 'B03', 'CAMPER', 'test-only'))
    clock = [1000.0]
    service = WorkflowService(db, clock=lambda: clock[0], lease_seconds=60)
    return dataset, service, user, clock


def start(setup, *, req=None, profile=None, config=None, command='start', request_id='b03-request', **options):
    dataset, service, user, _ = setup
    req, profile = req or requirements(preferences=['ready-to-eat meals', 'toilets']), profile or full_profile()
    config = config or WorkflowConfiguration(dataset, scenarios=[complete_scenario(req, ['demo-moonlit-field'])])
    confirmed = ConfirmedContext(request_id=request_id, confirmed_at=datetime(2026, 10, 8, tzinfo=timezone.utc), requirements=req, profile_snapshot=profile, demo_context=DEMO, dataset_context=config.context)
    Repository(service.db).record_confirmed_request(user, 'Explicit independent B03 fixture, no automatic confirmation.', confirmed)
    scope = service.start(user, request_id, DEMO, config.context, command_key=command, **options)
    attempt = service.claim(user, scope.run_id, DEMO, config.context)
    port = service.port(user, attempt)
    input = OrchestrateInput(run_scope=scope, confirmed_context=call(port.load_confirmed_context()))
    return CountingAgent(dataset, workflow_configuration=config), input, port


def retry(setup, input, config, key='retry'):
    _, service, user, _ = setup
    with service.db.transaction(write=False) as connection:
        revision = connection.execute('SELECT revision FROM runs WHERE id=?', (input.run_scope.run_id,)).fetchone()[0]
    service.retry(user, input.run_scope.run_id, DEMO, config.context, command_key=key, expected_run_revision=revision)
    attempt = service.claim(user, input.run_scope.run_id, DEMO, config.context)
    return service.port(user, attempt)


def counts(service):
    with service.db.transaction(write=False) as connection:
        return {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('recommendations', 'versions', 'assessments', 'gear_checklists', 'write_receipts', 'final_records')}


def test_complete_rules_persist_real_ids_dependency_and_eligibility(setup):
    agent, input, port = start(setup)
    result = call(agent.orchestrate(input, port))
    assert result.run_status == 'SUCCEEDED' and result.stage == 'COMPLETED'
    assert result.route == 'ELIGIBLE_FOR_FINALISATION' and not result.blockers
    assert RunResult.model_validate_json(result.model_dump_json()) == result
    assert agent.calls == ['recommendations', 'version', 'logistics', 'safety']
    detail = PlanQueries(setup[1].db).detail(setup[2], input.run_scope.plan_id)
    assert detail['eligibility']['eligible'] and detail['finalisation_available']
    log, safe = sorted(detail['assessments'], key=lambda value: value['kind'])
    assert safe['depends_on_assessment_id'] == log['assessment_id']
    assert result.artifact_refs['version'] == detail['version']['version_context']['plan_version_id']
    assert counts(setup[1]) == dict(recommendations=1, versions=1, assessments=2, gear_checklists=1, write_receipts=5, final_records=0)


@pytest.mark.parametrize('method,remaining', [
    ('save_recommendations', ['version', 'logistics', 'safety']),
    ('append_plan_version', ['logistics', 'safety']),
    ('save_assessment', ['safety']),
    ('route_assessed_version', []),
])
def test_lost_write_response_reuses_checkpoint_without_regeneration(setup, method, remaining):
    agent, input, port = start(setup)
    failed = call(agent.orchestrate(input, FailOnce(port, method)))
    assert failed.run_status == 'FAILED' and failed.error.recoverable
    before = counts(setup[1])
    restored = retry(setup, input, agent.workflow_configuration)
    checkpoint = call(restored.load_checkpoint())
    old_version = checkpoint['version']
    old_assessments = checkpoint['assessments']
    agent.calls.clear()
    result = call(agent.orchestrate(input, restored))
    assert result.run_status == 'SUCCEEDED' and agent.calls == remaining
    assert counts(setup[1])['versions'] == 1 and counts(setup[1])['assessments'] == 2
    if old_version:
        assert result.artifact_refs['version'] == old_version.version_context.plan_version_id
    for assessment in old_assessments:
        assert result.artifact_refs[assessment.kind.value.lower()] == assessment.assessment_id
    assert before['final_records'] == counts(setup[1])['final_records'] == 0


def test_resume_with_saved_safety_does_not_recompute_it(setup):
    agent, input, port = start(setup)
    class LoseSafety(Proxy):
        async def save_assessment(self, context, kind, result, key):
            saved = await self.port.save_assessment(context, kind, result, key)
            if kind == 'SAFETY':
                raise failure(ErrorCode.PERSISTENCE_FAILURE, 'Lost safety receipt.', recoverable=True)
            return saved
    assert call(agent.orchestrate(input, LoseSafety(port))).run_status == 'FAILED'
    restored = retry(setup, input, agent.workflow_configuration)
    agent.calls.clear()
    assert call(agent.orchestrate(input, restored)).run_status == 'SUCCEEDED'
    assert not agent.calls


def test_before_write_failure_only_recomputes_the_unsaved_step(setup):
    agent, input, port = start(setup)
    assert call(agent.orchestrate(input, FailOnce(port, 'save_assessment', after=False))).run_status == 'FAILED'
    restored = retry(setup, input, agent.workflow_configuration)
    agent.calls.clear()
    assert call(agent.orchestrate(input, restored)).run_status == 'SUCCEEDED'
    assert agent.calls == ['logistics', 'safety']


def test_route_then_completion_failure_only_finishes(setup):
    agent, input, port = start(setup)
    class FailCompletion(Proxy):
        async def report_stage(self, stage, status, error):
            if status == 'SUCCEEDED':
                raise failure(ErrorCode.PERSISTENCE_FAILURE, 'Completion unavailable.', recoverable=True)
            return await self.port.report_stage(stage, status, error)
    assert call(agent.orchestrate(input, FailCompletion(port))).stage == 'ROUTING'
    restored = retry(setup, input, agent.workflow_configuration)
    agent.calls.clear()
    result = call(agent.orchestrate(input, restored))
    assert result.run_status == 'SUCCEEDED' and not agent.calls and not result.blockers


def test_no_match_is_business_success_and_recoverable_without_a_version(setup):
    agent, input, port = start(setup, req=requirements(destination='No such region'))
    failed = call(agent.orchestrate(input, FailOnce(port, 'save_recommendations')))
    assert failed.run_status == 'FAILED'
    restored = retry(setup, input, agent.workflow_configuration)
    agent.calls.clear()
    result = call(agent.orchestrate(input, restored))
    assert result.run_status == 'SUCCEEDED' and result.route is None and not agent.calls
    assert counts(setup[1])['versions'] == counts(setup[1])['assessments'] == 0


def test_unmodified_git_safety_does_not_get_fabricated_validity(setup):
    config = WorkflowConfiguration(setup[0], safety_case_ids=['safety-01'])
    agent, input, port = start(setup, config=config, req=requirements(preferences=['ready-to-eat meals'], mandatory_constraints=['toilets', 'potable_water', 'campfire']), profile=full_profile(group=2))
    result = call(agent.orchestrate(input, port))
    assert result.run_status == 'SUCCEEDED' and result.route == 'BLOCKED'
    detail = PlanQueries(setup[1].db).detail(setup[2], input.run_scope.plan_id)
    safe = next(item for item in detail['assessments'] if item['kind'] == 'SAFETY')
    assert set(safe['result']['data_quality'].values()) == {'MISSING'}
    assert not detail['eligibility']['eligible']


def test_selected_original_git_evidence_retains_unknown_intervals(setup):
    # Quiet preference selects lake-meadow; safety-08 actually references it.
    config = WorkflowConfiguration(setup[0], safety_case_ids=['safety-08'])
    agent, input, port = start(setup, config=config, req=requirements(preferences=['ready-to-eat meals', 'quiet']))
    result = call(agent.orchestrate(input, port))
    checkpoint = call(port.load_checkpoint())
    assert checkpoint['version'].content.selected_campsite_ids == ['demo-lake-meadow']
    safe = next(item for item in checkpoint['assessments'] if item.kind == 'SAFETY')
    assert any(ref.dataset_file == 'synthetic_safety_scenarios.json' for ref in safe.result.source_refs)
    assert all(item.valid_from is None and item.valid_to is None for item in safe.result.evidence)
    assert result.route == 'BLOCKED' and result.run_status == 'SUCCEEDED'


@pytest.mark.parametrize('variant,route', [('budget', 'REVISION_REQUIRED'), ('missing', 'BLOCKED'), ('closed', 'BLOCKED')])
def test_business_problem_still_completes_but_never_finalises(setup, variant, route):
    req = requirements(budget_cents=18000 if variant == 'budget' else 50000, preferences=['ready-to-eat meals', 'toilets'])
    scenario = complete_scenario(req, ['demo-moonlit-field'])
    if variant == 'missing':
        scenario = scenario.model_copy(update={'evidence': [item for item in scenario.evidence if item.kind != 'WEATHER']})
    if variant == 'closed':
        scenario = scenario.model_copy(update={'evidence': [Evidence.model_validate(item.model_dump() | {'road_state': 'CLOSED', 'summary': 'road closed'}) if item.kind == 'ROAD' else item for item in scenario.evidence]})
    config = WorkflowConfiguration(setup[0], scenarios=[scenario])
    agent, input, port = start(setup, req=req, config=config)
    result = call(agent.orchestrate(input, port))
    assert result.run_status == 'SUCCEEDED' and result.route == route and result.blockers
    assert counts(setup[1])['final_records'] == 0


def test_reassessment_reuses_content_but_has_new_run_assessments(setup):
    agent, input, port = start(setup)
    first = call(agent.orchestrate(input, port))
    config = agent.workflow_configuration
    second_agent, second_input, second_port = start(setup, config=config, command='reassess', request_id='reassess-request', plan_id=input.run_scope.plan_id, operation='REASSESS', expected_current_version_id=first.artifact_refs['version'], expected_active_run_id=input.run_scope.run_id)
    result = call(second_agent.orchestrate(second_input, second_port))
    assert result.run_status == 'SUCCEEDED' and second_agent.calls == ['logistics', 'safety']
    assert result.artifact_refs['version'] == first.artifact_refs['version']
    assert result.artifact_refs['logistics'] != first.artifact_refs['logistics']
    assert counts(setup[1])['versions'] == 1 and counts(setup[1])['assessments'] == 4


def test_revision_creates_new_immutable_version(setup):
    agent, input, port = start(setup)
    first = call(agent.orchestrate(input, port))
    previous = call(port.load_checkpoint())['version']
    config = WorkflowConfiguration(setup[0], feedback='change campsite')
    next_agent, next_input, next_port = start(setup, config=config, command='revise', request_id='revise-request', plan_id=input.run_scope.plan_id, operation='REVISE', expected_current_version_id=first.artifact_refs['version'], expected_active_run_id=input.run_scope.run_id)
    next_input = next_input.model_copy(update={'previous_version': previous})
    result = call(next_agent.orchestrate(next_input, next_port))
    assert result.run_status == 'SUCCEEDED' and result.artifact_refs['version'] != first.artifact_refs['version']
    assert counts(setup[1])['versions'] == 2
    current = call(next_port.load_checkpoint())['version']
    assert current.content.selected_campsite_ids != previous.content.selected_campsite_ids


def test_requirement_change_is_not_saved_without_confirmation(setup):
    agent, input, port = start(setup)
    first = call(agent.orchestrate(input, port))
    previous = call(port.load_checkpoint())['version']
    config = WorkflowConfiguration(setup[0], feedback='remove campfire')
    agent, next_input, port = start(setup, config=config, command='revise', request_id='revise-request', plan_id=input.run_scope.plan_id, operation='REVISE', expected_current_version_id=first.artifact_refs['version'], expected_active_run_id=input.run_scope.run_id)
    result = call(agent.orchestrate(next_input.model_copy(update={'previous_version': previous}), port))
    assert result.run_status == 'FAILED' and result.error.code == 'REQUEST_NOT_CONFIRMED'
    assert not result.error.recoverable and counts(setup[1])['versions'] == 1


@pytest.mark.parametrize('change', ['rules', 'selection', 'fixtures', 'data', 'confirmed', 'mode', 'clock'])
def test_context_mismatch_fails_before_business_writes(setup, change):
    agent, input, port = start(setup)
    if change in {'rules', 'selection', 'fixtures', 'data'}:
        field, value = {'rules': ('rules_version', 'changed'), 'selection': ('selection_config', {}), 'fixtures': ('fixture_digests', {}), 'data': ('file_digests', {})}[change]
        config = input.run_scope.dataset_context.model_copy(update={field: value})
        input = input.model_copy(update={'run_scope': input.run_scope.model_copy(update={'dataset_context': config})})
    elif change == 'confirmed':
        input = input.model_copy(update={'confirmed_context': input.confirmed_context.model_copy(update={'requirements': requirements(budget_cents=40000)})})
    else:
        demo = DEMO.model_copy(update={'mode': 'agent'} if change == 'mode' else {'demo_today': DEMO.demo_today.replace(day=9)})
        input = input.model_copy(update={'run_scope': input.run_scope.model_copy(update={'demo_context': demo})})
    result = call(agent.orchestrate(input, port))
    assert result.run_status == 'FAILED' and result.error.code == 'STALE_CONTEXT'
    assert not agent.calls and counts(setup[1])['write_receipts'] == 0


def test_missing_recovery_extension_rejected_without_writes(setup):
    agent, input, _ = start(setup)
    port = Repository(setup[1].db).bind_port(setup[2], input.run_scope.run_id)
    with pytest.raises(ContractFailure, match='RecoveryPort'):
        call(agent.orchestrate(input, port))
    assert counts(setup[1])['write_receipts'] == 0


def test_agent_configuration_change_is_not_silently_used_on_registered_run(setup):
    agent, input, port = start(setup)
    agent.workflow_configuration = WorkflowConfiguration(setup[0], safety_case_ids=['safety-01'])
    result = call(agent.orchestrate(input, port))
    assert result.error.code == 'STALE_CONTEXT' and not agent.calls
    assert counts(setup[1])['write_receipts'] == 0


@pytest.mark.parametrize('mutation', ['recommendations', 'version', 'assessments', 'route', 'run_status'])
def test_malformed_checkpoint_never_restarts_business_steps(setup, mutation):
    agent, input, port = start(setup)
    class Malformed(Proxy):
        async def load_checkpoint(self):
            saved = await self.port.load_checkpoint()
            saved[mutation] = 'invalid'
            return saved
    result = call(agent.orchestrate(input, Malformed(port)))
    assert result.error.code == 'CONTRACT_INVALID' and not agent.calls
    assert counts(setup[1])['write_receipts'] == 0


def test_recovery_across_service_and_agent_restart(setup):
    agent, input, port = start(setup)
    assert call(agent.orchestrate(input, FailOnce(port, 'append_plan_version'))).run_status == 'FAILED'
    _, service, user, clock = setup
    restarted = WorkflowService(Database(service.db.path), clock=lambda: clock[0], lease_seconds=60)
    new_setup = (setup[0], restarted, user, clock)
    restored = retry(new_setup, input, agent.workflow_configuration)
    new_agent = CountingAgent(setup[0], workflow_configuration=agent.workflow_configuration)
    assert call(new_agent.orchestrate(input, restored)).run_status == 'SUCCEEDED'
    assert new_agent.calls == ['logistics', 'safety']


def test_database_failure_not_claimed_as_durable_failed(setup):
    agent, input, port = start(setup)
    class Broken(Proxy):
        async def save_recommendations(self, *args):
            raise failure(ErrorCode.PERSISTENCE_FAILURE, 'Storage unavailable.', recoverable=True)
        async def report_stage(self, stage, status, error):
            if status == 'FAILED':
                raise failure(ErrorCode.PERSISTENCE_FAILURE, 'Failure write unavailable.', recoverable=True)
            return await self.port.report_stage(stage, status, error)
    with pytest.raises(ContractFailure) as exc:
        call(agent.orchestrate(input, Broken(port)))
    assert any('could not be confirmed' in note for note in exc.value.__notes__)
    assert call(port.load_checkpoint())['run_status'] == 'RUNNING'


def test_a_dispatcher_commits_success_after_validating_b_result(setup):
    agent, input, port = start(setup)
    class A11CompletionIntent(Proxy):
        async def report_stage(self, stage, status, error):
            if stage == 'COMPLETED' and status == 'SUCCEEDED':
                # A11 validates completion intent but leaves the run RUNNING
                # until it validates the returned RunResult.
                return RunSnapshot(run_id=input.run_scope.run_id, execution_mode=DEMO.mode,
                    run_status='RUNNING', stage='COMPLETED', revision=99)
            return await self.port.report_stage(stage, status, error)
    dispatcher_port = A11CompletionIntent(port)
    result = call(agent.orchestrate(input, dispatcher_port))
    assert result.run_status == 'SUCCEEDED' and result.stage == 'COMPLETED'
    assert all(item.code != 'RUN_NOT_SUCCEEDED' for item in result.blockers)
    assert call(port.load_checkpoint())['run_status'] == 'RUNNING'
    # Simulate A validating the B response and committing final run status.
    call(port.report_stage('COMPLETED', 'SUCCEEDED', None))
    assert call(port.load_checkpoint())['run_status'] == 'SUCCEEDED'
    assert PlanQueries(setup[1].db).detail(setup[2], input.run_scope.plan_id)['eligibility']['eligible']


def test_lease_expiry_and_old_attempt_cannot_run_business(setup):
    agent, input, port = start(setup)
    setup[3][0] += 61
    with pytest.raises(ContractFailure) as exc:
        call(agent.orchestrate(input, port))
    assert exc.value.error.code == 'STALE_CONTEXT' and not agent.calls
    setup[1].expire(setup[2], input.run_scope.run_id)
    newer = retry(setup, input, agent.workflow_configuration)
    with pytest.raises(ContractFailure):
        call(agent.orchestrate(input, port))
    assert call(agent.orchestrate(input, newer)).run_status == 'SUCCEEDED'


def test_heartbeats_during_long_async_business_call(setup):
    agent, input, port = start(setup)
    original = agent.recommend_campsites
    agent.heartbeat_interval = 0.005
    renewals = []
    class Observed(Proxy):
        async def heartbeat(self):
            renewals.append(setup[3][0])
            await self.port.heartbeat()
    async def slow(value):
        for _ in range(4):
            await asyncio.sleep(0.012)
            setup[3][0] += 20
        return await original(value)
    agent.recommend_campsites = slow
    assert call(agent.orchestrate(input, Observed(port))).run_status == 'SUCCEEDED'
    assert all(value in renewals for value in (1020.0, 1040.0, 1060.0))


def test_lost_stage_response_records_failure_without_regressing(setup):
    agent, input, port = start(setup)
    class LoseStage(Proxy):
        async def report_stage(self, stage, status, error):
            saved = await self.port.report_stage(stage, status, error)
            if stage == 'ASSESSING_SAFETY' and status == 'RUNNING':
                raise failure(ErrorCode.PERSISTENCE_FAILURE, 'Lost stage response.', recoverable=True)
            return saved
    failed = call(agent.orchestrate(input, LoseStage(port)))
    assert failed.run_status == 'FAILED' and failed.stage == 'ASSESSING_SAFETY'
    restored = retry(setup, input, agent.workflow_configuration)
    agent.calls.clear()
    assert call(agent.orchestrate(input, restored)).run_status == 'SUCCEEDED'
    assert agent.calls == ['safety']


def test_lost_completion_response_never_overwrites_durable_success(setup):
    agent, input, port = start(setup)
    class LoseCompletion(Proxy):
        async def report_stage(self, stage, status, error):
            saved = await self.port.report_stage(stage, status, error)
            if status == 'SUCCEEDED':
                raise failure(ErrorCode.PERSISTENCE_FAILURE, 'Lost completion response.', recoverable=True)
            return saved
    with pytest.raises(ContractFailure):
        call(agent.orchestrate(input, LoseCompletion(port)))
    assert call(port.load_checkpoint())['run_status'] == 'SUCCEEDED'


def test_cancellation_leaves_no_success_or_background_task(setup):
    agent, input, port = start(setup)
    async def exercise():
        entered = asyncio.Event()
        async def slow(value):
            entered.set()
            await asyncio.Event().wait()
        agent.recommend_campsites = slow
        task = asyncio.create_task(agent.orchestrate(input, port))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not [value for value in asyncio.all_tasks() if value is not asyncio.current_task() and not value.done()]
    call(exercise())
    assert call(port.load_checkpoint())['run_status'] == 'RUNNING'
    assert counts(setup[1])['versions'] == 0


def test_configuration_hashes_actual_inputs_and_detaches_mutable_lists(setup):
    scenario = complete_scenario()
    config = WorkflowConfiguration(setup[0], scenarios=[scenario])
    digest = config.context.fixture_digests
    scenario.evidence.clear()
    assert config.scenario_for(['demo-pine-camp']).evidence
    assert config.context.fixture_digests == digest
    changed = WorkflowConfiguration(setup[0], scenarios=[scenario])
    assert changed.context.fixture_digests != digest
    returned = config.context
    returned.selection_config.clear()
    assert config.context.selection_config
    assert WorkflowConfiguration(setup[0], feedback='change campsite').context != WorkflowConfiguration(setup[0]).context


@pytest.mark.parametrize('options', [{'safety_case_ids': ['safety-01', 'safety-01']}, {'feedback': ' '}, {'scenarios': [complete_scenario(), complete_scenario()]}])
def test_configuration_rejects_ambiguous_choices(setup, options):
    with pytest.raises(ContractFailure):
        WorkflowConfiguration(setup[0], **options)


def test_resume_does_not_regress_stage_even_with_missing_write(setup):
    agent, input, port = start(setup)
    call(port.report_stage('ASSESSING_SAFETY', 'RUNNING', None))
    result = call(agent.orchestrate(input, port))
    assert result.run_status == 'SUCCEEDED'
    with setup[1].db.transaction(write=False) as connection:
        stages = [list(RunStage).index(RunStage(row[0])) for row in connection.execute('SELECT stage FROM run_events WHERE run_id=? ORDER BY id', (input.run_scope.run_id,))]
    assert stages == sorted(stages)
