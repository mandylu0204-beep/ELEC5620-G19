"""2.2/v3 actual components, HTTP/SQLite and recovery; MockTransport only."""
import asyncio
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.agents.rules import logistics, safety
from app.application.agent_runtime import build_v2_hybrid_binding
from app.application.daily_snapshot import effective_settings
from app.application.datasets import inspect_dataset
from app.application.safety_audit import registered_identity
from app.config import Settings
from app.contracts.dto import (DemoContext, ItineraryInput, LogisticsInput,
    RecommendCampsitesInput, SafetyInput)
from app.contracts.errors import ContractFailure
from app.llm.planning_schema import validated_itinerary
from app.llm.safety_validation import safety_validator_for
from app.llm.safety_v3 import (SafetyAgent, SafetyToolset, SafetyIdentitySeed, PROMPT_SHA256,
    compose_safety_identity, safety_contract_document)
from app.llm.tools import recommend_for_model
from app.main import create_app
from app.workflow import WorkflowConfiguration
from audit_test_reads import internal_audit_reads, json_with_internal_audits, CAMPER
from llm_fixtures import model_settings
from rule_fixtures import full_profile, requirements, stored_logistics, VERSION
from safety_runtime_fixtures import mock_safety_runtime, role_counts, wait_run as public_wait
from test_extended_demo import confirm_saved
from test_finalisation import command as final_command
from test_model_logistics_wiring import wrap_port
from test_plan_changes import change
from test_planning_entry import start, retry
from test_requests import sign_in
from test_rule_orchestration import FailOnce

ROOT = Path(__file__).resolve().parents[2]
wait_run = internal_audit_reads(public_wait)


def profile():
    # Explicit test confirmation, not a production inference from has_children.
    return full_profile(water=30, kilometres='100').model_copy(update={'children_count': 0})


@pytest.fixture(autouse=True)
def no_live_http(monkeypatch):
    # TestClient uses ASGITransport; campus responses must use MockTransport.
    def forbidden(*args, **kwargs):
        pytest.fail('No real HTTP transport is allowed in offline v3 regression')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def settings(tmp_path, *, daily=False, **changes):
    return Settings(_env_file=None, **{
        'dataset_path': ROOT / 'data/sydney_surrounds_v2_2', 'execution_mode': 'agent',
        'planning_enabled': True, 'logistics_execution': 'model', 'safety_execution': 'model',
        'workflow_safety_case_ids': [], 'dataset_scenario_files': [], 'dataset_selection': {},
        'clock_mode': 'fixed', 'demo_today': '2026-10-26',
        'synthetic_evidence_mode': 'rolling' if daily else 'sealed',
        'snapshot_cache_path': tmp_path / 'snapshots', 'database_path': tmp_path / 'runtime.sqlite3',
        **changes})


def safety_input(binding, *, start_day='2026-10-27'):
    data = binding.agent.dataset
    demo = DemoContext(mode='agent', demo_today='2026-10-26', dataset_version='2.2.0')
    req = requirements(destination='Sydney & Surrounds', start_date=date.fromisoformat(start_day),
        budget_cents=100000)
    saved_profile = profile()
    recs = recommend_for_model(data, RecommendCampsitesInput(confirmed_requirements=req,
        profile_snapshot=saved_profile, demo_context=demo))
    planning = ItineraryInput(confirmed_requirements=req, profile_snapshot=saved_profile,
        recommendations=recs, demo_context=demo)
    content = validated_itinerary(data, planning, {'campsite_id': 'little-beach',
        'nights': [(req.start_date + timedelta(days=i)).isoformat() for i in range(2)],
        'decision_summary': 'Explicit offline fixture selection.'}, [item.campsite_id for item in recs.candidates])
    log = logistics.assess(data, LogisticsInput(version_context=VERSION, saved_itinerary=content,
        confirmed_requirements=req, profile_snapshot=saved_profile, demo_context=demo), expected_mode='agent')
    selection = binding.agent.workflow_configuration.resolve_trip_evidence(req, ['little-beach'], demo)
    input = SafetyInput(version_context=VERSION, confirmed_requirements=req, saved_itinerary=content,
        saved_logistics_assessment=stored_logistics(log), scenario_context=selection.scenario_context, demo_context=demo)
    return input, safety.assess(data, input, expected_mode='agent'), selection


@pytest.fixture
def component(tmp_path, monkeypatch):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    config = settings(tmp_path)
    binding = build_v2_hybrid_binding(config, inspect_dataset(config))
    input, baseline, selection = safety_input(binding)
    return binding, input, baseline, selection, requests, control


def test_component_calls_model_and_replays_complete_v3_without_changing_rules(component):
    binding, input, baseline, selection, requests, _ = component
    role = binding.agent.safety_agent
    assert type(role) is SafetyAgent and not requests
    outcome = asyncio.run(role.assess_safety_with_trace(input))
    assert outcome.assessment == baseline
    assert role_counts(requests) == {'PLANNING': 0, 'LOGISTICS': 0, 'SAFETY': 3}
    assert outcome.trace.tool_version == 'safety-read-only-tools-3'
    assert role.identity_seed['validation_version'] == 'safety-advisory-validation-3'
    assert outcome.trace.prompt_sha256 == PROMPT_SHA256
    facts = json.loads(requests[1]['body']['messages'][-1]['content'][12:])
    provenance = facts['source_provenance']
    assert provenance['dynamic_conditions'] == 'SIMULATED_NOT_LIVE'
    assert provenance['official_clearance'] is False
    assert provenance['source_catalogue_sha256'] == binding.context.file_digests['source_catalogue.json']
    assert 'source_catalogue.json' not in facts  # No full catalogue in prompt.
    plan, trace = safety_validator_for('safety-advisory-validation-3')(input, baseline, baseline,
        outcome.plan.model_dump(mode='json'), outcome.trace.model_dump(mode='json'),
        identity=role.identity, selection=selection)
    assert plan == outcome.plan and trace == outcome.trace


@pytest.mark.parametrize('field', ['dataset_version', 'catalogue', 'daily', 'fingerprint', 'prompt', 'kernel', 'tool'])
def test_identity_or_dataset_downgrade_is_rejected(component, field):
    binding, _, _, _, _, _ = component
    role = binding.agent.safety_agent
    seed = deepcopy(role.identity_seed)
    context = binding.context.model_dump(mode='json')
    if field == 'dataset_version': context['dataset_version'] = '2.1.0'
    elif field == 'catalogue': del context['file_digests']['source_catalogue.json']
    elif field == 'daily': context['selection_config']['a_daily_snapshot'] = 'unknown'
    elif field == 'fingerprint': seed['validation_version'] = 'safety-advisory-validation-2'
    elif field == 'prompt': seed['prompt_sha256'] = 'a' * 64
    elif field == 'kernel': seed['kernel_version'] += '/unknown'
    else: seed['tool_version'] = 'safety-read-only-tools-2'
    with pytest.raises((ValueError, KeyError)):
        compose_safety_identity(seed, context)


@pytest.mark.parametrize('change', ['result', 'trace', 'source', 'priority', 'advice', 'context'])
def test_v3_artifact_tampering_never_replays(component, change):
    binding, input, baseline, selection, _, _ = component
    role = binding.agent.safety_agent
    outcome = asyncio.run(role.assess_safety_with_trace(input))
    plan, trace, identity = outcome.plan.model_dump(mode='json'), outcome.trace.model_dump(mode='json'), role.identity
    result = baseline
    if change == 'result': result = baseline.model_copy(update={'outcome': 'BLOCKED'})
    elif change == 'trace': trace['input_sha256'] = '0' * 64
    elif change == 'source': plan['source_refs'] = []
    elif change == 'priority': plan['action_priority'] = []
    elif change == 'advice': plan['findings'][0]['action_unverified'] = 'Visit https://invalid.example'
    else: identity['workflow_context']['file_digests']['source_catalogue.json'] = '0' * 64
    with pytest.raises(ContractFailure):
        safety_validator_for('safety-advisory-validation-3')(input, baseline, result, plan, trace,
            identity=identity, selection=selection)


def test_v2_cannot_replay_or_new_write_v3(component):
    binding, input, baseline, selection, _, _ = component
    role = binding.agent.safety_agent
    outcome = asyncio.run(role.assess_safety_with_trace(input))
    with pytest.raises(ContractFailure):
        safety_validator_for('safety-advisory-validation-2')(input, baseline, baseline,
            outcome.plan.model_dump(mode='json'), outcome.trace.model_dump(mode='json'),
            identity=role.identity, selection=selection)
    context = binding.context.model_copy(deep=True)
    seed = deepcopy(role.identity_seed)
    seed.update(agent_version='campus-safety-advisory-agent-2',
        tool_version='safety-read-only-tools-2', validation_version='safety-advisory-validation-2')
    context.selection_config['a_safety_identity_seed'] = json.dumps(seed)
    with pytest.raises(ValueError):
        registered_identity(SimpleNamespace(dataset_context=context, demo_context=input.demo_context), new_write=True)


def test_concurrent_v3_calls_and_returned_fact_views_stay_isolated(component):
    binding, first, baseline, selection, requests, _ = component
    second, second_baseline, _ = safety_input(binding, start_day='2026-10-28')
    role = binding.agent.safety_agent
    async def run():
        return await asyncio.gather(role.assess_safety_with_trace(first), role.assess_safety_with_trace(second))
    before = deepcopy(first)
    a, b = asyncio.run(run())
    assert a.assessment == baseline and b.assessment == second_baseline
    assert a.trace.input_sha256 != b.trace.input_sha256 and first == before
    assert role_counts(requests)['SAFETY'] == 6
    tools = SafetyToolset(first, baseline, selection=selection, workflow_context=role.identity['workflow_context'])
    facts = tools.read_safety_facts()
    facts['source_provenance']['official_clearance'] = True
    facts['findings'].clear()
    assert tools.read_safety_facts()['source_provenance']['official_clearance'] is False
    assert tools.read_safety_facts()['findings']


def begin(client, headers, *, day='2026-10-27'):
    saved_profile = client.put('/api/v1/profile', headers=headers, json={
        'expected_revision': 0, 'profile': profile().model_dump(mode='json')})
    assert saved_profile.status_code == 200, saved_profile.text
    saved = client.post('/api/v1/requests', headers=headers, json={
        'raw_text': 'Explicit offline Sydney trip; ready-to-eat meals.',
        'explicit_fields': {'destination': 'Sydney & Surrounds', 'start_date': day,
            'duration_nights': 2, 'budget_cents': 100000, 'preferences': ['ready-to-eat meals']}})
    assert saved.status_code == 201, saved.text
    confirmed = confirm_saved(client, headers, saved.json(), 'v3-confirm-command-123456')
    response = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
    assert response.status_code == 202, response.text
    return response.json()['run_id']


def assert_audit(detail):
    audit = detail['model_assessment_audits']['SAFETY']
    assert audit['trace']['tool_version'] == 'safety-read-only-tools-3'
    assert audit['assessment_id'] == next(x['assessment_id'] for x in detail['assessments'] if x['kind'] == 'SAFETY')
    assert audit['configuration_fingerprint'] == audit['trace']['configuration_fingerprint']
    assert audit['run_id'] == detail['run']['run_id']
    return audit


@pytest.mark.parametrize('daily', [False, True])
@pytest.mark.parametrize('logistics_mode', ['rules', 'model'])
def test_http_plan_revision_reassessment_final_and_restart(tmp_path, monkeypatch, daily, logistics_mode):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    config = settings(tmp_path, daily=daily, logistics_execution=logistics_mode)
    with TestClient(create_app(config)) as client:
        headers = sign_in(client)
        old = wait_run(client, begin(client, headers), 'SUCCEEDED')
        old_audit = assert_audit(old)
        assert old['finalisation_available']
        # The offline model must actually select a different, permitted campsite.
        control['site'] = 'euroka'
        response = change(client, headers, old, 'revise', feedback='change campsite', key='v3-revise-command-123456')
        assert response.status_code == 202, response.text
        revised = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        revised_audit = assert_audit(revised)
        assert revised_audit['audit_id'] != old_audit['audit_id']
        assert revised['version']['content']['selected_campsite_ids'] == ['euroka']
        assert revised['finalisation_available']
        saved = client.post('/api/v1/plans/'+revised['plan']['plan_id']+'/finalise',
            headers=headers, json=final_command(revised))
        assert saved.status_code == 200, saved.text
        final_path = '/api/v1/plans/'+revised['plan']['plan_id']+'/finals/'+saved.json()['final_id']
        snapshot = json_with_internal_audits(client, client.get(final_path))
        current = json_with_internal_audits(client, client.get('/api/v1/plans/'+old['plan']['plan_id']))
        response = change(client, headers, current, key='v3-reassess-command-123456')
        assert response.status_code == 202, response.text
        reassessed = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        audit = assert_audit(reassessed)
        assert audit['run_id'] != revised_audit['run_id']
        assert audit['plan_version_id'] == revised_audit['plan_version_id']
        assert reassessed['model_planning_trace'] == revised['model_planning_trace']
        assert role_counts(requests) == {'PLANNING': 4, 'LOGISTICS': 9 if logistics_mode == 'model' else 0, 'SAFETY': 9}
        assert sum(item['role'] == 'INTERPRETATION' for item in requests) == 1
    before = len(requests)
    with TestClient(create_app(config)) as client:
        sign_in(client)
        assert json_with_internal_audits(client, client.get(final_path)) == {**snapshot, 'is_current': False}
        assert_audit(wait_run(client, reassessed['run']['run_id'], 'SUCCEEDED'))
        assert len(requests) == before
        sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get(final_path).status_code == 404


@pytest.mark.parametrize('after,expected_safety_calls', [(False, 6), (True, 3)])
def test_failed_safety_save_recovers_without_replanning_or_redoing_logistics(tmp_path, monkeypatch, after, expected_safety_calls):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    used = []
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port, 'save_model_safety_assessment', after=after)
        return port
    wrap_port(monkeypatch, once)
    config = settings(tmp_path, daily=True)
    with TestClient(create_app(config)) as client:
        headers = sign_in(client)
        failed = wait_run(client, begin(client, headers), 'FAILED')
        old_logistics = deepcopy(failed['model_assessment_audits']['LOGISTICS'])
        old_content, old_trace = failed['version']['content'], failed['model_planning_trace']
        saved_safety = deepcopy(failed['model_assessment_audits'].get('SAFETY'))
        assert failed['retry_available']
    with TestClient(create_app(config)) as client:
        headers = sign_in(client)
        failed = json_with_internal_audits(client, client.get('/api/v1/runs/'+failed['run']['run_id']))
        assert retry(client, headers, failed).status_code == 202
        recovered = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        assert_audit(recovered)
        assert recovered['model_assessment_audits']['LOGISTICS'] == old_logistics
        assert recovered['version']['content'] == old_content and recovered['model_planning_trace'] == old_trace
        if saved_safety:
            assert recovered['model_assessment_audits']['SAFETY'] == saved_safety
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3, 'SAFETY': expected_safety_calls}


def test_future_daily_weather_remains_missing_and_model_failure_never_becomes_rules_success(tmp_path, monkeypatch):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    with TestClient(create_app(settings(tmp_path, daily=True))) as client:
        headers = sign_in(client)
        detail = wait_run(client, begin(client, headers, day='2026-11-10'), 'SUCCEEDED')
        safe = next(x['result'] for x in detail['assessments'] if x['kind'] == 'SAFETY')
        assert_audit(detail)
        assert safe['data_quality']['WEATHER'] == 'MISSING' and not detail['finalisation_available']
        response = client.post('/api/v1/plans/'+detail['plan']['plan_id']+'/finalise', headers=headers, json=final_command(detail))
        assert response.status_code == 409
        control['invalid'] = True
        response = change(client, headers, detail, key='v3-invalid-reassess')
        assert response.status_code == 202
        failed = wait_run(client, response.json()['run_id'], 'FAILED')
        assert 'SAFETY' not in failed['model_assessment_audits']
        assert failed['version']['content'] == detail['version']['content']
        assert failed['model_planning_trace'] == detail['model_planning_trace']


def test_committed_v3_contract_matches_component():
    path = ROOT / 'docs/contracts/safety_advisory_v3.schema.json'
    assert json.loads(path.read_text(encoding='utf-8')) == safety_contract_document()


@pytest.mark.parametrize('args,expected', [
    (['--mode', 'agent', '--safety', 'model'], 'model'),
    (['--mode', 'agent'], 'rules'), ([], 'rules')])
def test_launcher_explicit_opt_in_only(monkeypatch, args, expected):
    spec = importlib.util.spec_from_file_location('sydney_v3_launcher', ROOT / 'scripts/sydney.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = []
    def capture(command, *, cwd, env):
        captured.append(env['CAMPMATE_SAFETY_EXECUTION'])
        return 0
    monkeypatch.setattr(module.sys, 'argv', ['sydney.py', *args])
    monkeypatch.setattr(module.subprocess, 'call', capture)
    assert module.main() == 0 and captured == [expected]


def test_launcher_rejects_model_safety_without_agent_mode(monkeypatch):
    spec = importlib.util.spec_from_file_location('sydney_v3_invalid_launcher', ROOT / 'scripts/sydney.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, 'argv', ['sydney.py', '--safety', 'model'])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
