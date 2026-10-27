"""Minimum public-transport policy: sealed inputs, isolated SQL, no live HTTP."""
from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.agents.rule_agent import RuleAgent
from app.agents.rules import logistics
from app.agents.rules.transport import POLICY_KEY, POLICY_VERSION
from app.application.logistics_issues import project
from app.contracts.dto import DemoContext, ItineraryInput, LogisticsInput, RecommendCampsitesResult, Transport
from app.contracts.errors import ContractFailure
from app.main import create_app
from rule_fixtures import VERSION, call, equipment, full_profile, requirements
from test_planning_entry import start, wait_run
from test_requests import sign_in
from test_sydney_catalogue import PACKAGE, REGION, settings


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Real network is forbidden in minimum transport regression')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def public_profile(*, notes=True):
    profile = full_profile(mode='PUBLIC_TRANSPORT', water=30).model_copy(update={'children_count': 0})
    return profile.model_copy(update={
        'equipment': [item.model_copy(update={'unit': 'item'}) if item.item_key == 'warm_layers' else item
                      for item in profile.equipment],
        'transport': Transport(transport_type='PUBLIC_TRANSPORT',
            assumptions=['User checked outbound ferry, return service and last-mile walk.'] if notes else []),
    })


def source_input(profile=None, site='bonnie-vale'):
    dataset = SyntheticDatasetV2Adapter(PACKAGE).load()
    req = requirements(destination=REGION, start_date=date(2026, 10, 27))
    profile = profile or public_profile()
    demo = DemoContext(mode='deterministic_demo', demo_today='2026-10-26', dataset_version='2.2.0')
    rec = RecommendCampsitesResult(execution_mode='deterministic_demo', search_outcome='MATCHES',
        candidates=[{'campsite_id': site, 'rank': 1, 'reasons': ['Explicit isolated test selection.']}])
    itinerary = call(RuleAgent(dataset).generate_or_revise_itinerary(ItineraryInput(
        confirmed_requirements=req, profile_snapshot=profile, recommendations=rec, demo_context=demo)))
    return dataset, LogisticsInput(version_context=VERSION, saved_itinerary=itinerary,
        confirmed_requirements=req, profile_snapshot=profile, demo_context=demo)


def assess(dataset, input, *, policy=POLICY_VERSION):
    return logistics.assess(dataset, input, transport_policy=policy)


def test_public_trip_uses_no_private_vehicles_without_changing_unknown_inventory_or_source():
    dataset, input = source_input()
    original = input.model_dump_json()
    old = assess(dataset, input, policy=None)
    assert 'gear_rule_input.vehicle_count' in {q.field for q in old.clarifications}
    result = assess(dataset, input)
    assert result.transport_feasible is True
    assert not {'gear_rule_input.vehicle_count', 'transport.vehicle_count', 'equipment.vehicle'} & {q.field for q in result.clarifications}
    assert input.model_dump_json() == original and input.profile_snapshot.transport.vehicle_count is None
    assert next(item for item in result.gear_checklist if item.item_key == 'offline_map').required_quantity == 1
    costs = [row for row in result.cost_breakdown if row.category == 'TRANSPORT']
    assert len(costs) == 1 and costs[0].item_key == 'cost-03'
    assert costs[0].quantity == input.profile_snapshot.group_size
    assert costs[0].subtotal_cents == input.profile_snapshot.group_size * dataset.get_cost_reference('cost-03').typical_cents
    assert all(isinstance(row.subtotal_cents, int) for row in costs)
    assert any('not live timetable' in text for text in result.assumptions)
    # Legacy pure evaluation is still byte-identical after new-policy evaluation.
    assert assess(dataset, input, policy=None).model_dump_json() == old.model_dump_json()


@pytest.mark.parametrize('mutation', ['absent', 'unknown_quantity', 'zero', 'unconfirmed', 'wrong_unit', 'missing_notes'])
def test_user_connection_confirmation_and_description_are_required_not_inferred(mutation):
    profile = public_profile(notes=mutation != 'missing_notes')
    rows = []
    for row in profile.equipment:
        if row.item_key == 'transport_itinerary':
            if mutation == 'absent':
                continue
            changes = {'unknown_quantity': {'quantity': None}, 'zero': {'quantity': 0},
                       'unconfirmed': {'confirmed': False}, 'wrong_unit': {'unit': 'item'}}.get(mutation, {})
            row = row.model_copy(update=changes)
        rows.append(row)
    dataset, input = source_input(profile.model_copy(update={'equipment': rows}))
    result = assess(dataset, input)
    assert result.transport_feasible is None and result.outcome != 'PASSED'
    expected = 'transport.assumptions' if mutation == 'missing_notes' else 'equipment.transport_itinerary'
    assert expected in {q.field for q in result.clarifications}
    assert not any(q.field.endswith('vehicle_count') for q in result.clarifications)


def test_unknown_or_negative_campsite_access_and_missing_fare_never_become_verified_or_free():
    dataset, input = source_input()
    for access in (None, False):
        dataset._campsites['bonnie-vale'] = dataset.get_campsite('bonnie-vale').model_copy(update={'public_transport_access': access})
        result = assess(dataset, input)
        assert result.transport_feasible is (None if access is None else False)
        assert result.mandatory_blockers and result.outcome != 'PASSED'
        if access is None:
            assert 'transport.public_transport_access' in {q.field for q in result.clarifications}
    dataset, input = source_input()
    dataset._costs['cost-03'] = dataset.get_cost_reference('cost-03').model_copy(update={'typical_cents': None})
    result = assess(dataset, input)
    assert result.total_cents is None
    fare = next(row for row in result.cost_breakdown if row.item_key == 'cost-03')
    assert fare.subtotal_cents is None and fare.unit_price_cents is None
    assert 'cost.cost-03' in {q.field for q in result.clarifications}


def test_car_and_unspecified_mode_are_not_given_zero_private_vehicle_defaults():
    for transport in (Transport(transport_type='CAR'), Transport()):
        profile = public_profile().model_copy(update={'transport': transport})
        dataset, input = source_input(profile)
        result = assess(dataset, input)
        assert result.transport_feasible is not True
        assert 'gear_rule_input.vehicle_count' in {q.field for q in result.clarifications}


def test_connection_and_source_gap_have_distinct_editable_and_operator_targets():
    dataset, input = source_input(public_profile(notes=False))
    dataset._campsites['bonnie-vale'] = dataset.get_campsite('bonnie-vale').model_copy(update={'public_transport_access': None})
    result = assess(dataset, input)
    issues = project({'plan': {'plan_id': 'test-plan', 'request_id': 'test-request'},
        'confirmed_context': {'requirements': input.confirmed_requirements.model_dump(mode='json'),
            'profile_snapshot': input.profile_snapshot.model_dump(mode='json')},
        'assessments': [{'kind': 'LOGISTICS', 'result': result.model_dump(mode='json')}]})
    notes = next(item for item in issues if item['field'] == 'transport.assumptions')
    access = next(item for item in issues if item['field'] == 'transport.public_transport_access')
    assert notes['target'] == 'PROFILE' and 'focus=transport.assumptions' in notes['action_url']
    assert access['target'] == 'OPERATOR' and access['category'] == 'DATA_GAP' and access['action_url'] is None


def confirm_public(client, headers, profile=None):
    saved = client.put('/api/v1/profile', headers=headers,
        json={'expected_revision': 0, 'profile': (profile or public_profile()).model_dump(mode='json')})
    assert saved.status_code == 200, saved.text
    draft = client.post('/api/v1/requests', headers=headers, json={'raw_text': 'Public transport camping trip.',
        'explicit_fields': {'destination': REGION, 'start_date': '2026-10-27', 'duration_nights': 2,
            'budget_cents': 100000, 'preferences': ['ready-to-eat meals']}}).json()
    path = '/api/v1/requests/' + draft['request_id']
    summary = client.post(path + '/interpret', headers=headers, json={'expected_revision': draft['revision']})
    assert summary.status_code == 200, summary.text
    assert summary.json()['status'] == 'AWAITING_CONFIRMATION', summary.text
    confirmed = client.post(path + '/confirm', headers=headers, json={'expected_revision': summary.json()['revision'],
        'command_key': 'minimum-public-transport-confirm', 'acknowledged': True})
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def test_http_public_trip_pins_policy_and_original_profile_without_car_costs(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        assert client.get('/api/v1/request-context').json()['supported_transport_modes'] == ['CAR', 'PUBLIC_TRANSPORT']
        confirmed = confirm_public(client, headers)
        changed = public_profile().model_dump(mode='json')
        changed['transport']['assumptions'] = ['New unadopted personal profile notes.']
        assert client.put('/api/v1/profile', headers=headers, json={'expected_revision': 1, 'profile': changed}).status_code == 200
        response = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        assert response.status_code == 202, response.text
        detail = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        result = next(row['result'] for row in detail['assessments'] if row['kind'] == 'LOGISTICS')
        assert result['transport_feasible'] is True
        assert [row['item_key'] for row in result['cost_breakdown'] if row['category'] == 'TRANSPORT'] == ['cost-03']
        assert detail['confirmed_context']['profile_snapshot']['transport']['assumptions'] == public_profile().transport.assumptions
        with app.state.database.transaction(write=False) as db:
            import json
            scope = json.loads(db.execute('SELECT scope FROM runs WHERE id=?', (response.json()['run_id'],)).fetchone()[0])
        assert scope['dataset_context']['selection_config'][POLICY_KEY] == POLICY_VERSION
        assert scope['dataset_context']['rules_version'].endswith('/' + POLICY_VERSION)
        assert POLICY_KEY not in str(detail)  # Camper reads do not leak full configuration.


@pytest.mark.parametrize('mode', ['WALKING', 'OTHER', None])
def test_unsupported_or_missing_mode_is_rejected_before_interpretation_or_run(tmp_path, monkeypatch, mode):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        headers = sign_in(client)
        profile = public_profile().model_copy(update={'transport': Transport(transport_type=mode)})
        assert client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': 0, 'profile': profile.model_dump(mode='json')}).status_code == 200
        def forbidden(*args, **kwargs):
            pytest.fail('Unsupported mode must be rejected before interpreter/model call')
        monkeypatch.setattr(RuleAgent, 'interpret_request', forbidden)
        record = client.post('/api/v1/requests', headers=headers, json={'raw_text': 'Test unsupported transport.'}).json()
        response = client.post('/api/v1/requests/' + record['request_id'] + '/interpret', headers=headers,
            json={'expected_revision': record['revision']})
        assert response.status_code >= 400 and response.json()['error']['code'] == 'INPUT_INVALID'
        with app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0


def test_runtime_reconstructs_absent_legacy_policy_and_rejects_unknown_versions(tmp_path):
    app = create_app(settings(tmp_path))
    runtime = app.state.runtime
    current = runtime.resolve()
    assert current.dataset.selection_config[POLICY_KEY] == POLICY_VERSION
    legacy = runtime.resolve(transport_policy=None)
    assert POLICY_KEY not in legacy.dataset.selection_config
    scope = SimpleNamespace(dataset_context=legacy.dataset, demo_context=legacy.demo)
    assert runtime.for_scope(scope).dataset == legacy.dataset
    assert runtime.resolve().dataset == current.dataset
    with pytest.raises(ContractFailure):
        runtime.resolve(transport_policy='unknown-transport-policy')


@pytest.mark.parametrize('protocol', ['standard', 'compact'])
def test_model_logistics_public_trip_persists_and_lost_receipt_reuses_saved_artifacts(tmp_path, monkeypatch, protocol):
    from safety_runtime_fixtures import mock_safety_runtime, role_counts
    from test_model_logistics_wiring import wrap_port
    from test_planning_entry import retry
    from test_rule_orchestration import FailOnce
    from test_sydney_model_safety import settings as model_settings
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'bonnie-vale'
    used = []
    def once(port):
        if used:
            return port
        used.append(True)
        return FailOnce(port, 'save_model_logistics_assessment', after=True)
    wrap_port(monkeypatch, once)
    cfg = model_settings(tmp_path, daily=True, safety_protocol=protocol)
    with TestClient(create_app(cfg)) as client:
        headers = sign_in(client)
        confirmed = confirm_public(client, headers)
        response = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        assert response.status_code == 202, response.text
        failed = wait_run(client, response.json()['run_id'], 'FAILED')
        assert failed['retry_available']
        saved_logistics = next(item for item in failed['assessments'] if item['kind'] == 'LOGISTICS')
        assert saved_logistics['result']['transport_feasible'] is True
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3, 'SAFETY': 0}
        changed = public_profile().model_dump(mode='json')
        changed['transport']['assumptions'] = ['Latest profile must not replace the pinned run.']
        assert client.put('/api/v1/profile', headers=headers, json={'expected_revision': 1, 'profile': changed}).status_code == 200
    with TestClient(create_app(cfg)) as client:
        headers = sign_in(client)
        response = retry(client, headers, failed)
        assert response.status_code == 202, response.text
        done = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3, 'SAFETY': 3}
        assert done['version']['version_context'] == failed['version']['version_context']
        assert done['version']['content'] == failed['version']['content']
        assert next(item for item in done['assessments'] if item['kind'] == 'LOGISTICS') == saved_logistics
        assert done['confirmed_context']['profile_snapshot']['transport']['assumptions'] == public_profile().transport.assumptions
        assert POLICY_KEY not in str(done)
        with client.app.state.database.transaction(write=False) as db:
            assert db.execute('SELECT COUNT(*) FROM model_logistics_audits').fetchone()[0] == 1
            assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 1
