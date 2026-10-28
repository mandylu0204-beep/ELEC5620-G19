"""System-owned preparation. Synthetic files, isolated SQLite, no live HTTP."""
from copy import deepcopy
from decimal import Decimal
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.adapters import transport_reference as ref
from app.agents.rules import logistics
from app.agents.rules.transport import POLICY_KEY, POLICY_VERSION, MINIMAL_POLICY_VERSION
from app.application.presentation import plan_response
from app.application.trip_preparation import summary
from app.contracts.errors import ContractFailure
from app.main import create_app
from rule_fixtures import equipment, full_profile
from test_minimal_transport import source_input, public_profile, confirm_public
from test_sydney_catalogue import settings
from test_requests import sign_in
from test_planning_entry import start, wait_run


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    def forbidden(*args, **kwargs):
        pytest.fail('Real HTTP forbidden in system preparation tests')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def public_without_plans():
    profile = public_profile(notes=False)
    return profile.model_copy(update={'equipment': [row for row in profile.equipment
        if row.item_key not in {'transport_itinerary', 'fire_free_meal_plan'}]})


def test_public_matching_no_longer_requires_a_user_authored_route_or_virtual_inventory():
    dataset, input = source_input(public_without_plans())
    before = input.model_dump_json()
    result = logistics.assess(dataset, input, transport_policy=POLICY_VERSION)
    assert result.transport_feasible is True
    assert not {'transport_itinerary', 'fire_free_meal_plan'} & {row.item_key for row in result.gear_checklist}
    assert not any('transport_itinerary' in q.field or q.field == 'transport.assumptions' for q in result.clarifications)
    assert next(row for row in result.cost_breakdown if row.item_key == 'cost-03').subtotal_cents > 0
    assert input.model_dump_json() == before
    old = logistics.assess(dataset, input, transport_policy=MINIMAL_POLICY_VERSION)
    assert old.transport_feasible is None


@pytest.mark.parametrize('vehicles', [1, 2])
def test_car_distance_is_selected_trip_reference_times_confirmed_fleet_not_profile_mileage(vehicles):
    profile = full_profile(vehicles=vehicles, kilometres='999').model_copy(update={'children_count': 0})
    dataset, input = source_input(profile)
    dataset.transport_reference, _ = ref.read_reference()
    before = input.model_dump_json()
    result = logistics.assess(dataset, input, transport_policy=POLICY_VERSION)
    line = next(row for row in result.cost_breakdown if row.item_key == 'cost-02')
    assert result.transport_feasible is True and line.quantity == Decimal(100 * vehicles)
    assert line.subtotal_cents == 100 * vehicles * dataset.get_cost_reference('cost-02').typical_cents
    assert any(row.dataset_file == ref.REFERENCE_KEY and row.record_id == 'bonnie-vale' for row in result.source_refs)
    assert input.model_dump_json() == before
    old = logistics.assess(dataset, input, transport_policy=MINIMAL_POLICY_VERSION)
    assert next(row for row in old.cost_breakdown if row.item_key == 'cost-02').quantity == 999


@pytest.mark.parametrize('mutation', ['no_reference', 'unconfirmed', 'unknown_count', 'unknown_capacity', 'wrong_unit'])
def test_unknown_transport_inputs_cannot_be_inferred_from_a_distance_table(mutation):
    profile = full_profile().model_copy(update={'children_count': 0})
    rows = list(profile.equipment)
    if mutation in {'unconfirmed', 'unknown_count', 'unknown_capacity', 'wrong_unit'}:
        values = {'unconfirmed': {'confirmed': False}, 'unknown_count': {'quantity': None},
            'unknown_capacity': {'capacity_persons': None}, 'wrong_unit': {'unit': 'item'}}[mutation]
        rows = [row.model_copy(update=values) if row.item_key == 'vehicle' else row for row in rows]
        profile = profile.model_copy(update={'equipment': rows})
    dataset, input = source_input(profile)
    if mutation != 'no_reference':
        dataset.transport_reference, _ = ref.read_reference()
    result = logistics.assess(dataset, input, transport_policy=POLICY_VERSION)
    if mutation != 'unknown_capacity':
        assert next(row for row in result.cost_breakdown if row.item_key == 'cost-02').subtotal_cents is None
        assert result.total_cents is None
    if mutation != 'no_reference':
        assert result.transport_feasible is not True
    assert result.outcome != 'PASSED'


def test_virtual_plan_cannot_replace_real_cooking_equipment_or_change_fire_constraints():
    profile = public_without_plans()
    profile = profile.model_copy(update={'equipment': [*profile.equipment,
        equipment('fire_free_meal_plan', 1, 'plan')]})
    dataset, input = source_input(profile)
    input = input.model_copy(update={'confirmed_requirements': input.confirmed_requirements.model_copy(
        update={'preferences': ['self-catered meals']})})
    result = logistics.assess(dataset, input, transport_policy=POLICY_VERSION)
    stove = next(row for row in result.gear_checklist if row.item_key == 'camping_stove')
    assert stove.missing_quantity > 0 and result.outcome != 'PASSED'
    assert not any(row.item_key == 'fire_free_meal_plan' for row in result.gear_checklist)
    assert 'cooking_method' not in {q.field for q in result.clarifications}


def test_mode_filter_excludes_unknown_access_and_no_match_does_not_change_the_request():
    from app.agents.rules.planning import recommend
    from app.contracts.dto import RecommendCampsitesInput
    dataset, input = source_input(public_without_plans())
    request = RecommendCampsitesInput(confirmed_requirements=input.confirmed_requirements,
        profile_snapshot=input.profile_snapshot, demo_context=input.demo_context)
    before = request.model_dump_json()
    result = recommend(dataset, request)
    assert result.candidates
    assert all(dataset.get_campsite(row.campsite_id).public_transport_access is True for row in result.candidates)
    # Independent fixture mutation: no source files or production records change.
    for camp in dataset.campsites:
        dataset._campsites[camp.campsite_id] = camp.model_copy(update={'public_transport_access': None})
    unavailable = recommend(dataset, request)
    assert unavailable.search_outcome == 'NO_MATCH' and not unavailable.candidates
    assert all('Public transport access is unavailable or unknown.' in row.reasons for row in unavailable.excluded_candidates)
    assert request.model_dump_json() == before


def test_single_route_reference_cannot_invent_multi_camp_legs_or_missing_routes():
    dataset, input = source_input(full_profile())
    dataset.transport_reference, _ = ref.read_reference()
    camps = [dataset.get_campsite('bonnie-vale'), dataset.get_campsite('euroka')]
    assert ref.estimate_vehicle_km(dataset, input.profile_snapshot, camps) == (None, None)
    assert ref.estimate_vehicle_km(dataset, input.profile_snapshot, [dataset.get_campsite('cockatoo-island')]) == (None, None)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate_key', 'duplicate_site', 'negative', 'float', 'not_synthetic'])
def test_reference_rejects_invalid_bytes(tmp_path, monkeypatch, mutation):
    value = json.loads(ref.REFERENCE_PATH.read_text())
    if mutation == 'duplicate_site':
        value['routes'][-1] = value['routes'][0]
    if mutation in {'negative', 'float'}:
        value['routes'][0]['round_trip_km_per_vehicle'] = -1 if mutation == 'negative' else 1.5
    if mutation == 'not_synthetic':
        value['provenance']['demo_only'] = False
    path = tmp_path / 'reference.json'
    if mutation != 'missing':
        path.write_text('{"version":"duplicate",' + json.dumps(value)[1:] if mutation == 'duplicate_key' else json.dumps(value))
    monkeypatch.setattr(ref, 'REFERENCE_PATH', path)
    with pytest.raises(ContractFailure):
        ref.read_reference()


def test_reference_hash_pinned_in_runtime_recovery_and_cached_loading(tmp_path, monkeypatch):
    path = tmp_path / 'distances.json'
    path.write_bytes(ref.REFERENCE_PATH.read_bytes())
    monkeypatch.setattr(ref, 'REFERENCE_PATH', path)
    runtime = create_app(settings(tmp_path)).state.runtime
    binding = runtime.resolve()
    context = binding.dataset
    assert context.file_digests[ref.REFERENCE_KEY] == context.selection_config['b_transport_reference_sha256']
    scope = SimpleNamespace(dataset_context=context, demo_context=binding.demo)
    assert runtime.for_scope(scope).dataset == context
    path.write_bytes(path.read_bytes() + b'\n')  # Same values, different consumed bytes.
    with pytest.raises(ContractFailure):
        runtime.for_scope(scope)
    current = runtime.resolve()
    assert current.dataset.file_digests[ref.REFERENCE_KEY] != context.file_digests[ref.REFERENCE_KEY]
    for policy in (MINIMAL_POLICY_VERSION, None):
        old = runtime.resolve(transport_policy=policy)
        assert ref.REFERENCE_KEY not in old.dataset.file_digests
        assert runtime.for_scope(SimpleNamespace(dataset_context=old.dataset, demo_context=old.demo)).dataset == old.dataset


def test_http_public_trip_uses_system_preparation_and_cropped_saved_projection(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        headers = sign_in(client)
        capability = client.get('/api/v1/request-context', headers=headers).json()
        assert capability['system_preparation'] is True
        assert capability['planning_origin']['id'] == ref.ORIGIN_ID
        confirmed = confirm_public(client, headers, public_without_plans())
        response = start(client, headers, request_id=confirmed['request_id'], revision=confirmed['revision'])
        assert response.status_code == 202, response.text
        done = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        preparation = done['preparation_summary']
        assert preparation['transport_type'] == 'PUBLIC_TRANSPORT' and preparation['access_and_capacity'] is True
        assert preparation['estimated_transport_cents'] > 0 and preparation['meal_mode'] == 'READY_TO_EAT'
        assert not {'transport_itinerary', 'fire_free_meal_plan'} & {row['item_key'] for row in
            next(row['result'] for row in done['assessments'] if row['kind'] == 'LOGISTICS')['gear_checklist']}
        assert 'b_transport_reference_sha256' not in str(done)
        assert 'model_diagnostics' not in done
        assert client.get('/api/v1/plans/' + done['plan']['plan_id'], headers=headers).json()['preparation_summary'] == preparation


def test_saved_summary_never_reads_current_profile_or_reference_and_final_view_keeps_it():
    dataset, input = source_input(public_without_plans())
    result = logistics.assess(dataset, input, transport_policy=POLICY_VERSION)
    confirmed = {'request_id': 'saved-request', 'dataset_context': {'dataset_version': '2.2.0', 'selection_config': {POLICY_KEY: POLICY_VERSION}},
        'profile_snapshot': input.profile_snapshot.model_dump(mode='json'),
        'requirements': input.confirmed_requirements.model_dump(mode='json')}
    saved = {'confirmed_context': confirmed, 'assessments': [{'kind': 'LOGISTICS', 'result': result.model_dump(mode='json')}],
        'version_context': {'plan_id': 'saved'}, 'status': 'FINALISED'}
    before = deepcopy(saved)
    # Exercise both projection entrances with exactly the stored snapshot.
    user = SimpleNamespace(role='CAMPER')
    public = plan_response(saved, user)
    final = plan_response({'final_record': saved}, user)['final_record']
    assert public['preparation_summary'] == final['preparation_summary'] == summary(confirmed, result.model_dump(mode='json'))
    assert saved == before
    assert public['confirmed_context']['dataset_context'] == {'dataset_version': '2.2.0'}
    old = deepcopy(saved)
    old['confirmed_context']['dataset_context']['selection_config'][POLICY_KEY] = MINIMAL_POLICY_VERSION
    assert plan_response(old, user)['preparation_summary'] is None
