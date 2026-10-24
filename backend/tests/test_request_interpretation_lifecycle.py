"""Summary-only model observations preserve ownership and immutable run context.

These tests use a local deterministic double. No campus transport is created.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import shutil
from threading import Event
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from app.agents.stub import StubAgent
from app.config import Settings
from app.contracts.dto import InterpretRequestInput, InterpretRequestResult, TripRequirements
from app.contracts.enums import ErrorCode
from app.contracts.errors import ContractError, ContractFailure
from app.main import BUSINESS_FILES, create_app
from app.storage.requests import request_input_fingerprint
from test_requests import FIELDS, confirm_body, sign_in


IDENTITY = {
    'component_version': 'request-interpreter-1', 'schema_version': '1.0',
    'prompt_sha256': '1' * 64, 'configuration_fingerprint': '2' * 64,
    'requested_model': 'campus-qwen',
}
RAW_TEXT = '准备和男朋友一起去，想找个安静的地方。'
EXPLICIT = FIELDS | {'preferences': ['希望安静', 'ready-to-eat meals'],
    'mandatory_constraints': ['需要洗澡']}


class ObservedAgent:
    model_request_terms = True

    def __init__(self):
        self.identity = deepcopy(IDENTITY)
        self.calls = []
        self.failure = None
        self.observation_edit = None
        self.after_observation = None
        self.entered = self.release = None

    @property
    def request_interpretation_identity(self):
        return deepcopy(self.identity)

    async def interpret_request(self, input):
        raise AssertionError('Observed model interpretation must not silently fall back.')

    async def interpret_request_with_observation(self, input):
        self.calls.append(input.model_copy(deep=True))
        if self.entered is not None:
            self.entered.set()
            while not self.release.is_set():
                await asyncio.sleep(.01)
        if self.failure:
            raise self.failure
        result = InterpretRequestResult(execution_mode='agent',
            extracted_requirements=input.explicit_fields.model_copy(update={
                'preferences': ['quiet', 'ready-to-eat meals'],
                'mandatory_constraints': ['showers'],
            }))
        observation = {'identity': self.request_interpretation_identity,
            'usage': {'prompt_tokens': len(input.raw_text), 'completion_tokens': 12},
            'attempts': 1}
        if self.observation_edit:
            self.observation_edit(observation)
        if self.after_observation:
            self.after_observation()
        return SimpleNamespace(result=result, observation=observation)


@pytest.fixture
def observed_web(tmp_path):
    source = Settings(_env_file=None).dataset_path
    dataset = tmp_path / 'dataset'
    (dataset / 'data').mkdir(parents=True)
    for filename in BUSINESS_FILES:
        shutil.copyfile(source / 'data' / filename, dataset / 'data' / filename)
    # No agent factory exists for this isolated v1 copy in model mode. The
    # explicit test double below supplies the capability without an LLM client.
    settings = Settings(_env_file=None, dataset_path=dataset,
        database_path=tmp_path / 'requests.sqlite3', execution_mode='agent',
        clock_mode='fixed', demo_today='2026-10-08', planning_enabled=False)
    app = create_app(settings)
    agent = ObservedAgent()
    app.state.agent = agent
    with TestClient(app) as client:
        headers = sign_in(client)
        assert client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': 0, 'profile': {'group_size': 2}}).status_code == 200
        yield app, client, headers, agent


def draft(client, headers, raw_text=RAW_TEXT, explicit=None):
    response = client.post('/api/v1/requests', headers=headers,
        json={'raw_text': raw_text, 'explicit_fields': EXPLICIT if explicit is None else explicit})
    assert response.status_code == 201, response.text
    return response.json()


def interpret(client, headers, record):
    return client.post(f"/api/v1/requests/{record['request_id']}/interpret",
        headers=headers, json={'expected_revision': record['revision']})


def analysed(client, headers, record):
    response = interpret(client, headers, record)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'AWAITING_CONFIRMATION', response.text
    return response.json()


def saved_summary(app, request_id):
    with app.state.database.transaction(write=False) as connection:
        row = connection.execute('SELECT * FROM request_summaries WHERE request_id=?',
            (request_id,)).fetchone()
        return dict(row), json.loads(row['result']) if row['result'] else None


def test_model_summary_is_private_restartable_and_confirmation_does_not_call_model(observed_web):
    app, client, headers, agent = observed_web
    record = analysed(client, headers, draft(client, headers))
    endpoint = f"/api/v1/requests/{record['request_id']}"
    assert record['explicit_fields'] == EXPLICIT
    assert record['summary']['extracted_requirements']['mandatory_constraints'] == ['showers']
    assert record['summary']['extracted_requirements']['preferences'] == ['quiet', 'ready-to-eat meals']
    assert 'interpretation_metadata' not in record['summary']
    row, stored = saved_summary(app, record['request_id'])
    metadata = stored['interpretation_metadata']
    assert metadata['identity'] == IDENTITY
    assert metadata['input_sha256'] == request_input_fingerprint(agent.calls[0])
    assert metadata['analysis_revision'] == row['analysis_revision'] == 2
    assert metadata['usage']['prompt_tokens'] == len(RAW_TEXT)
    assert 'base_url' not in json.dumps(metadata) and 'raw_text' not in json.dumps(metadata)
    body = confirm_body(record)
    confirmed = client.post(endpoint + '/confirm', headers=headers, json=body)
    assert confirmed.status_code == 200, confirmed.text
    value = confirmed.json()
    assert value['confirmed_context']['requirements']['mandatory_constraints'] == ['showers']
    assert not any('interpretation' in key for key in value['confirmed_context']['dataset_context'])
    # An acknowledged snapshot and its receipt remain valid when a later
    # interpreter version is installed; retrying confirmation never re-parses.
    agent.identity['configuration_fingerprint'] = '3' * 64
    assert client.post(endpoint + '/confirm', headers=headers, json=body).json() == value
    assert len(agent.calls) == 1
    with TestClient(create_app(app.state.settings)) as restarted:
        sign_in(restarted)
        assert restarted.get(endpoint).json() == value
    with app.state.database.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM plans').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM request_confirmations').fetchone()[0] == 1


@pytest.mark.parametrize('change', ['identity', 'capability', 'profile'])
def test_pending_model_summary_requires_same_interpreter_and_profile(observed_web, change):
    app, client, headers, agent = observed_web
    record = analysed(client, headers, draft(client, headers))
    if change == 'identity':
        agent.identity['prompt_sha256'] = '4' * 64
    elif change == 'capability':
        agent.model_request_terms = False
    else:
        assert client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': 1, 'profile': {'group_size': 3}}).status_code == 200
    response = client.post(f"/api/v1/requests/{record['request_id']}/confirm",
        headers=headers, json=confirm_body(record))
    assert response.status_code == 409
    assert response.json()['error']['code'] == ('VERSION_CONFLICT' if change == 'profile' else 'STALE_CONTEXT')
    assert len(agent.calls) == 1


@pytest.mark.parametrize('field,value', [
    ('input_sha256', '0' * 64), ('analysis_revision', 999),
    ('usage', {'prompt_tokens': True}),
])
def test_corrupt_or_misbound_model_observation_cannot_be_confirmed(observed_web, field, value):
    app, client, headers, agent = observed_web
    record = analysed(client, headers, draft(client, headers))
    _, stored = saved_summary(app, record['request_id'])
    stored['interpretation_metadata'][field] = value
    with app.state.database.transaction() as connection:
        connection.execute('UPDATE request_summaries SET result=? WHERE request_id=?',
            (json.dumps(stored), record['request_id']))
    response = client.post(f"/api/v1/requests/{record['request_id']}/confirm",
        headers=headers, json=confirm_body(record))
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'STALE_CONTEXT'
    assert len(agent.calls) == 1


@pytest.mark.parametrize('corruption', ['extra', 'usage', 'attempts', 'identity'])
def test_invalid_model_observation_keeps_draft_without_fallback(observed_web, corruption):
    app, client, headers, agent = observed_web
    def corrupt(value):
        if corruption == 'extra':
            value['base_url'] = 'not-public'
        elif corruption == 'usage':
            value['usage']['provider_private_field'] = 1
        elif corruption == 'attempts':
            value['attempts'] = True
        else:
            value['identity']['configuration_fingerprint'] = '0' * 64
    agent.observation_edit = corrupt
    record = draft(client, headers)
    response = interpret(client, headers, record)
    assert response.status_code in {409, 502}, response.text
    current = client.get(f"/api/v1/requests/{record['request_id']}").json()
    assert current['status'] == 'DRAFT' and current['summary'] is None
    assert len(agent.calls) == 1
    assert saved_summary(app, record['request_id'])[1] is None


def test_identity_changed_during_model_wait_is_not_persisted(observed_web):
    app, client, headers, agent = observed_web
    agent.after_observation = lambda: agent.identity.update(prompt_sha256='5' * 64)
    record = draft(client, headers)
    response = interpret(client, headers, record)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'STALE_CONTEXT'
    assert saved_summary(app, record['request_id'])[1] is None


def test_model_failure_keeps_draft_and_does_not_fall_back(observed_web):
    app, client, headers, agent = observed_web
    agent.failure = ContractFailure(ContractError(code=ErrorCode.AGENT_FAILURE,
        message='Offline simulated model failure.'))
    record = draft(client, headers)
    response = interpret(client, headers, record)
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'AGENT_FAILURE'
    current = client.get(f"/api/v1/requests/{record['request_id']}").json()
    assert current['status'] == 'DRAFT' and current['summary'] is None
    assert len(agent.calls) == 1


def test_edit_while_model_waits_rejects_old_summary_and_duplicate_analysis(observed_web):
    app, client, headers, agent = observed_web
    agent.entered, agent.release = Event(), Event()
    record = draft(client, headers)
    endpoint = f"/api/v1/requests/{record['request_id']}"
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(interpret, client, headers, record)
        try:
            assert agent.entered.wait(timeout=5)
            analysing = client.get(endpoint).json()
            duplicate = interpret(client, headers, analysing)
            assert duplicate.status_code == 409
            edited = client.patch(endpoint, headers=headers, json={
                'expected_revision': analysing['revision'], 'raw_text': 'Updated requirements',
                'explicit_fields': EXPLICIT | {'budget_cents': 99900}})
            assert edited.status_code == 200, edited.text
        finally:
            agent.release.set()
        assert future.result(timeout=5).json()['error']['code'] == 'STALE_CONTEXT'
    current = client.get(endpoint).json()
    assert current['summary'] is None and current['status'] == 'DRAFT'
    assert current['explicit_fields']['budget_cents'] == 99900
    assert len(agent.calls) == 1


def test_other_user_cannot_trigger_model_or_read_observation(observed_web):
    app, client, headers, agent = observed_web
    record = draft(client, headers)
    other = sign_in(client, 'camper.b', 'CampMate-B-2026!')
    endpoint = f"/api/v1/requests/{record['request_id']}"
    assert client.get(endpoint).status_code == 404
    assert interpret(client, other, record).status_code == 404
    assert client.post(endpoint + '/confirm', headers=other, json=confirm_body(record)).status_code == 404
    assert not agent.calls


def test_concurrent_user_observations_remain_bound_to_each_request(observed_web):
    app, client, headers, agent = observed_web
    first = draft(client, headers)
    other_app = create_app(app.state.settings)
    other_app.state.agent = agent
    with TestClient(other_app) as other_client:
        other_headers = sign_in(other_client, 'camper.b', 'CampMate-B-2026!')
        assert other_client.put('/api/v1/profile', headers=other_headers,
            json={'expected_revision': 0, 'profile': {'group_size': 3}}).status_code == 200
        second = draft(other_client, other_headers, raw_text='A longer independent camping request.',
            explicit=EXPLICIT | {'budget_cents': 60000})
        agent.entered, agent.release = Event(), Event()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(interpret, client, headers, first),
                executor.submit(interpret, other_client, other_headers, second)]
            try:
                assert agent.entered.wait(timeout=5)
            finally:
                agent.release.set()
            assert all(future.result(timeout=10).status_code == 200 for future in futures)
    for record in (first, second):
        _, stored = saved_summary(app, record['request_id'])
        original = next(value for value in agent.calls if value.raw_text == record['raw_text'])
        assert stored['interpretation_metadata']['input_sha256'] == request_input_fingerprint(original)
        assert stored['interpretation_metadata']['usage']['prompt_tokens'] == len(record['raw_text'])
        assert stored['extracted_requirements']['budget_cents'] == record['explicit_fields']['budget_cents']
    assert len(agent.calls) == 2


def test_legacy_summary_without_model_observation_still_confirms(observed_web):
    app, client, headers, agent = observed_web
    class LegacyAgent:
        async def interpret_request(self, input):
            result = await StubAgent().interpret_request(input)
            return result.model_copy(update={'execution_mode': 'agent'})
    app.state.agent = LegacyAgent()
    record = analysed(client, headers, draft(client, headers,
        explicit=FIELDS | {'preferences': ['quiet', 'ready-to-eat meals'], 'mandatory_constraints': ['showers']}))
    assert 'interpretation_metadata' not in saved_summary(app, record['request_id'])[1]
    app.state.agent = agent
    response = client.post(f"/api/v1/requests/{record['request_id']}/confirm",
        headers=headers, json=confirm_body(record))
    assert response.status_code == 200, response.text
    assert not agent.calls


def test_request_input_digest_preserves_explicit_field_presence():
    base = dict(raw_text='Need a quiet campground.',
        demo_context={'mode': 'agent', 'demo_today': '2026-10-08'})
    omitted = InterpretRequestInput(**base, explicit_fields=TripRequirements())
    empty = InterpretRequestInput(**base, explicit_fields=TripRequirements(preferences=[]))
    null = InterpretRequestInput(**base, explicit_fields=TripRequirements(start_date=None))
    assert len({request_input_fingerprint(value) for value in (omitted, empty, null)}) == 3


def test_production_hybrid_request_chain_with_mock_transport_preserves_canonical_snapshot(tmp_path, monkeypatch):
    from app.config import APP_ROOT
    from app.llm import client as client_module, config as config_module
    from llm_fixtures import completion, model_settings

    requests = []
    client_class = client_module.CampusModelClient
    public_settings = model_settings()

    def respond(request):
        body = json.loads(request.content)
        payload = json.loads(body['messages'][-1]['content'])
        requests.append(payload)
        assert payload['operation'] == 'INTERPRET_REQUEST'
        clauses = []
        for source in payload['sources']:
            text = source['text']
            if source['source'] == 'raw_text':
                quote, canonical, strength = '想找个安静的地方', 'quiet', 'soft'
            elif source['source'] == 'preferences':
                quote, canonical, strength = text, 'ready-to-eat meals', 'soft'
            else:
                quote, canonical, strength = text, 'showers', 'hard'
            clauses.append({'source': source['source'], 'index': source['index'],
                'quote': text, 'unresolved': False, 'mentions': [{
                    'quote': quote, 'canonical': canonical, 'polarity': 'positive',
                    'strength': strength, 'ambiguous': False}]})
        return httpx.Response(200, json=completion({'clauses': clauses}))

    monkeypatch.setattr(config_module, 'CampusModelSettings', lambda: public_settings)
    monkeypatch.setattr(client_module, 'CampusModelClient',
        lambda settings: client_class(settings, transport=httpx.MockTransport(respond)))
    settings = Settings(_env_file=None, execution_mode='agent', planning_enabled=False,
        dataset_path=APP_ROOT / 'data/sydney_surrounds_v2_2', database_path=tmp_path / 'hybrid.sqlite3',
        demo_today='2026-10-24', clock_mode='fixed', synthetic_evidence_mode='sealed')
    app = create_app(settings)
    with TestClient(app) as client:
        headers = sign_in(client)
        assert client.put('/api/v1/profile', headers=headers,
            json={'expected_revision': 0, 'profile': {'group_size': 2}}).status_code == 200
        snapshot = app.state.runtime.resolve()
        before = snapshot.dataset.model_dump(mode='json')
        assert snapshot.agent.model_request_terms is True
        region = snapshot.descriptor.regions[0]
        explicit = FIELDS | {'destination': region, 'start_date': '2026-10-25',
            'preferences': ['ready-to-eat meals'], 'mandatory_constraints': ['需要洗澡']}
        record = analysed(client, headers, draft(client, headers, explicit=explicit))
        assert record['summary']['extracted_requirements']['preferences'] == ['quiet', 'ready-to-eat meals']
        assert record['summary']['extracted_requirements']['mandatory_constraints'] == ['showers']
        response = client.post(f"/api/v1/requests/{record['request_id']}/confirm",
            headers=headers, json=confirm_body(record))
        assert response.status_code == 200, response.text
        assert response.json()['confirmed_context']['requirements']['mandatory_constraints'] == ['showers']
        assert app.state.runtime.resolve().dataset.model_dump(mode='json') == before
        stored, result = saved_summary(app, record['request_id'])
        assert result['interpretation_metadata']['identity'] == snapshot.agent.request_interpretation_identity
        with app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0
    assert len(requests) == 1


def test_managed_factory_rejects_an_unbound_request_interpreter(tmp_path, monkeypatch):
    from app.agents import hybrid_planning_agent
    from app.application.agent_runtime import build_v2_hybrid_binding
    from app.application.datasets import inspect_dataset
    from app.llm import config as config_module
    from llm_fixtures import ROOT, model_settings

    original = hybrid_planning_agent.HybridPlanningAgent

    class MissingInterpreter(original):
        @property
        def model_request_terms(self):
            return False

    monkeypatch.setattr(hybrid_planning_agent, 'HybridPlanningAgent', MissingInterpreter)
    monkeypatch.setattr(config_module, 'CampusModelSettings', model_settings)
    settings = Settings(_env_file=None, execution_mode='agent',
        dataset_path=ROOT / 'data/sydney_surrounds_v2_2',
        database_path=tmp_path / 'unbound.sqlite3',
        demo_today='2026-10-24', clock_mode='fixed', synthetic_evidence_mode='sealed')
    with pytest.raises(ContractFailure) as caught:
        build_v2_hybrid_binding(settings, inspect_dataset(settings))
    assert caught.value.error.code == 'AGENT_FAILURE'
