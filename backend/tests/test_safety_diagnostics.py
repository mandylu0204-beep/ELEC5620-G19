"""Offline rejection/correction, exact diagnosis and raw HTTP privacy."""
from copy import deepcopy
import json
from types import SimpleNamespace
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.application.presentation import plan_response
from app.contracts.errors import ContractFailure
from app.llm.safety_diagnostics import VERSION, proposal_failure
from app.llm.safety_feedback import POLICY_KEY, POLICY_VERSION, correction_result
from app.llm.safety_schema import ActionCode
from app.llm.safety_tools import SafetyToolset
from app.main import create_app
from safety_fixtures import safety_fixture, proposal_from_safety_facts
from test_safety_compact import case as compact_case, tools as compact_tools, proposal as compact_proposal
from safety_runtime_fixtures import mock_safety_runtime, role_counts
from test_sydney_model_safety import settings, begin, wait_run
from test_requests import sign_in

PRIVATE = 'Private profile material must never appear in diagnostics.'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    def forbidden(*args, **kwargs):
        pytest.fail('Real HTTP is forbidden in safety diagnosis regression')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def component(compact_case, compact):
    if compact:
        tool = compact_tools(compact_case)
        return tool, compact_proposal(tool.read_safety_facts()), tool.evaluate_compact_plan
    _, source, _, baseline, selection = safety_fixture()
    tool = SafetyToolset(source, baseline, selection=selection)
    return tool, proposal_from_safety_facts(tool.read_safety_facts()), tool.evaluate_safety_plan


@pytest.mark.parametrize('compact', [False, True])
def test_wrong_per_finding_action_is_identified_without_advice_or_profile_text(compact_case, compact):
    tool, proposal, evaluate = component(compact_case, compact)
    before = tool.baseline.model_dump_json()
    expected = tool._definitions[0]
    wrong = next(code for code in get_args(ActionCode) if code not in expected.allowed_actions)
    proposal['findings'][0]['action' if compact else 'action_code'] = wrong
    proposal['findings'][0]['advice' if compact else 'interpretation_unverified'] = PRIVATE
    with pytest.raises(ContractFailure) as captured:
        evaluate(proposal)
    error = captured.value.error
    assert error.code == 'CONTRACT_INVALID' and error.recoverable is False
    assert error.context['failure_stage'] == 'ACTION_NOT_ALLOWED'
    detail = json.loads(error.context['safety_validation_diagnostics'])
    assert detail['finding_id'] == expected.finding_key
    assert detail['actual_action'] == wrong and detail['allowed_actions'] == expected.allowed_actions
    assert detail.get('compact_id') == ('f0' if compact else None)
    assert PRIVATE not in error.model_dump_json() and len(error.model_dump_json()) < 3000
    assert tool.baseline.model_dump_json() == before


@pytest.mark.parametrize('compact', [False, True])
def test_coverage_errors_are_separate_and_report_only_registered_ids(compact_case, compact):
    tool, proposal, evaluate = component(compact_case, compact)
    proposal['findings'].pop()
    proposal['priority' if compact else 'action_priority'].pop()
    with pytest.raises(ContractFailure) as captured:
        evaluate(proposal)
    context = captured.value.error.context
    assert context['failure_stage'] == 'FINDING_COVERAGE'
    detail = json.loads(context['safety_validation_diagnostics'])
    assert detail['missing_count'] == 1 and detail['unexpected_count'] == 0
    assert detail['missing_ids'] == [tool._definitions[-1].finding_key]


def test_schema_and_host_fact_errors_cannot_be_misreported_as_model_action_errors(compact_case):
    tool, proposal, evaluate = component(compact_case, False)
    bad = deepcopy(proposal);bad[PRIVATE] = PRIVATE
    with pytest.raises(ContractFailure) as captured:
        evaluate(bad)
    assert captured.value.error.context['failure_stage'] == 'PROPOSAL_SCHEMA'
    assert PRIVATE not in captured.value.error.model_dump_json()
    first = tool._definitions[0]
    tool._definitions = (first.model_copy(update={'fact_refs': [first.fact_refs[0]] * 2}), *tool._definitions[1:])
    with pytest.raises(ContractFailure) as captured:
        evaluate(proposal)
    assert captured.value.error.context['failure_stage'] == 'FACT_BINDING'


def test_compact_digest_failure_and_bounded_unknown_values_are_redacted(compact_case):
    tool, proposal, evaluate = component(compact_case, True)
    proposal['facts_sha256'] = '0' * 64
    with pytest.raises(ContractFailure) as captured:
        evaluate(proposal)
    assert captured.value.error.context['failure_stage'] == 'FACT_IDENTITY'
    failure = proposal_failure('FINDING_COVERAGE', expected=['finding-' + f'{i:064x}' for i in range(64)], provided=[PRIVATE])
    detail = json.loads(failure.error.context['safety_validation_diagnostics'])
    assert len(detail['missing_ids']) == 16 and detail['details_truncated']
    assert PRIVATE not in failure.error.model_dump_json()
    wrong = proposal_failure('ACTION_NOT_ALLOWED', finding=PRIVATE, actual=PRIVATE, allowed=['CHANGE_TRIP'])
    assert PRIVATE not in wrong.error.model_dump_json()


@pytest.mark.parametrize('condition', ['legacy', 'used', 'no_final_turn', 'coverage', 'unknown_policy'])
def test_feedback_never_relaxes_validation_or_exceeds_the_existing_budget(compact_case, condition):
    tool = compact_tools(compact_case)
    error = proposal_failure('ACTION_NOT_ALLOWED').error
    args = dict(compact=True, policy=POLICY_VERSION, turn=2, max_turns=4, already_used=False)
    if condition == 'legacy': args['policy'] = None
    if condition == 'used': args['already_used'] = True
    if condition == 'no_final_turn': args['max_turns'] = 3
    if condition == 'coverage': error = proposal_failure('FINDING_COVERAGE').error
    if condition == 'unknown_policy':
        args['policy'] = 'unknown'
        with pytest.raises(ContractFailure): correction_result(error, tool, **args)
    else:
        assert correction_result(error, tool, **args) is None


@pytest.mark.parametrize('protocol', ['standard', 'compact'])
@pytest.mark.parametrize('behaviour', ['correct', 'stubborn', 'coverage', 'premature_final'])
def test_http_action_correction_is_model_authored_bounded_and_private(tmp_path, monkeypatch, caplog, protocol, behaviour):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    def mutate(role, count, action):
        if role != 'SAFETY' or count == 0:
            return action
        compact = protocol == 'compact'
        if count == 1:
            proposal = action['arguments']
            if behaviour == 'coverage':
                proposal['findings'].pop();proposal['priority' if compact else 'action_priority'].pop()
            else:
                proposal['findings'][0]['action' if compact else 'action_code'] = 'CHANGE_TRIP'
                proposal['findings'][0]['advice' if compact else 'interpretation_unverified'] = PRIVATE
        elif count == 2 and behaviour != 'premature_final':
            # A second MockTransport response authors a corrected complete
            # proposal; production code never chooses/replaces model actions.
            proposal = action['proposal']
            if behaviour == 'stubborn':
                proposal['findings'][0]['action' if compact else 'action_code'] = 'CHANGE_TRIP'
            action = {'action':'tool', 'name':'evaluate_safety_plan', 'arguments':proposal}
        return action
    control['mutate_action'] = mutate
    app = create_app(settings(tmp_path, daily=True, safety_protocol=protocol))
    with TestClient(app) as client:
        headers = sign_in(client)
        run_id = begin(client, headers)
        done = wait_run(client, run_id, 'SUCCEEDED' if behaviour == 'correct' else 'FAILED')
        expected_calls = 4 if behaviour == 'correct' else 2 if behaviour == 'coverage' else 3
        assert role_counts(requests)['SAFETY'] == expected_calls
        assert role_counts(requests)['PLANNING'] == 2 and role_counts(requests)['LOGISTICS'] == 3
        assert done['version'] and any(a['kind'] == 'LOGISTICS' for a in done['assessments'])
        for path in ['/runs/' + run_id, '/runs/' + run_id + '/progress', '/plans/' + done['plan']['plan_id']]:
            response = client.get('/api/v1' + path)
            assert response.status_code == 200
            assert 'safety_validation_diagnostics' not in response.text and 'safety_turn' not in response.text
            assert 'b_safety_action_feedback' not in response.text
        with app.state.database.transaction(write=False) as db:
            row = db.execute('SELECT scope,error FROM runs WHERE id=?', (run_id,)).fetchone()
            scope = json.loads(row['scope'])
            assert scope['dataset_context']['selection_config'][POLICY_KEY] == POLICY_VERSION
            assert POLICY_VERSION in scope['dataset_context']['rules_version']
            audits = db.execute('SELECT payload FROM model_safety_audits WHERE run_id=?', (run_id,)).fetchall()
            assert len(audits) == (1 if behaviour == 'correct' else 0)
            if behaviour == 'correct':
                payload = json.loads(audits[0]['payload'])
                assert payload['trace']['turns'] == 4
                assert PRIVATE not in json.dumps(payload)
            elif behaviour != 'premature_final':
                error = json.loads(row['error'])
                assert error['context']['failure_stage'] == ('FINDING_COVERAGE' if behaviour == 'coverage' else 'ACTION_NOT_ALLOWED')
                assert error['context']['safety_turn'] == ('2' if behaviour == 'coverage' else '3')
                assert PRIVATE not in row['error']
        if behaviour != 'coverage':
            assert 'actual_action' in caplog.text
            assert 'compact_id' in caplog.text if protocol == 'compact' else 'finding_id' in caplog.text
        assert PRIVATE not in caplog.text


def test_legacy_and_current_runtime_policy_are_distinct_and_reconstructed(tmp_path, monkeypatch):
    mock_safety_runtime(monkeypatch)
    runtime = create_app(settings(tmp_path, daily=True, safety_protocol='compact')).state.runtime
    new = runtime.resolve()
    old = runtime.resolve(safety_feedback_policy=None)
    assert POLICY_KEY not in old.dataset.selection_config
    assert new.dataset != old.dataset
    for binding in (old, new):
        recovered = runtime.for_scope(SimpleNamespace(dataset_context=binding.dataset, demo_context=binding.demo))
        assert recovered.dataset == binding.dataset


def test_corrected_safety_receipt_loss_recovers_without_regenerating_any_role(tmp_path, monkeypatch):
    from test_model_logistics_wiring import wrap_port
    from test_rule_orchestration import FailOnce
    from test_planning_entry import retry
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    def mutate(role, count, action):
        if role == 'SAFETY' and count == 1:
            action['arguments']['findings'][0]['action'] = 'CHANGE_TRIP'
        if role == 'SAFETY' and count == 2:
            return {'action':'tool', 'name':'evaluate_safety_plan', 'arguments':action['proposal']}
        return action
    control['mutate_action'] = mutate
    used = []
    def once(port):
        if used: return port
        used.append(True)
        return FailOnce(port, 'save_model_safety_assessment', after=True)
    wrap_port(monkeypatch, once)
    cfg = settings(tmp_path, daily=True, safety_protocol='compact')
    with TestClient(create_app(cfg)) as client:
        headers = sign_in(client)
        failed = wait_run(client, begin(client, headers), 'FAILED')
        assert role_counts(requests) == {'PLANNING':2, 'LOGISTICS':3, 'SAFETY':4}
        saved = failed['model_assessment_audits']['SAFETY']
        assert saved['trace']['turns'] == 4
    with TestClient(create_app(cfg)) as client:
        headers = sign_in(client)
        response = retry(client, headers, failed)
        assert response.status_code == 202, response.text
        recovered = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        assert role_counts(requests) == {'PLANNING':2, 'LOGISTICS':3, 'SAFETY':4}
        assert recovered['model_assessment_audits']['SAFETY'] == saved
        assert recovered['version']['content'] == failed['version']['content']


def test_founder_retains_safe_diagnostics_while_camper_projection_does_not():
    error = proposal_failure('ACTION_NOT_ALLOWED', finding='finding-'+'a'*64,
        actual='CHANGE_TRIP', allowed=['ACKNOWLEDGE_INFORMATION']).error.model_dump(mode='json')
    source = {'run': {'status':'FAILED', 'error':error}, 'events':[{'error':deepcopy(error)}], 'assessments':[]}
    before = deepcopy(source)
    assert 'safety_validation_diagnostics' not in json.dumps(plan_response(source, SimpleNamespace(role='CAMPER')))
    reviewer = plan_response(source, SimpleNamespace(role='FOUNDER'))
    assert reviewer['run']['error']['context']['diagnostic_version'] == VERSION
    assert source == before
