import asyncio
import json

import httpx
from pydantic import ValidationError
import pytest

from app.contracts.errors import ContractFailure
from app.llm.client import CampusModelClient, MAX_RESPONSE_BYTES
from app.llm.config import CampusModelSettings
from llm_fixtures import completion, model_settings

MESSAGES = [{'role': 'user', 'content': 'Independent synthetic unit request.'}]


def call(client):
    return asyncio.run(client.complete(MESSAGES))


def test_proxy_request_matches_school_guide_and_uses_no_native_tool_assumptions():
    requests = []
    def handler(request):
        requests.append(request)
        assert request.url == 'http://10.167.60.148:8000/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer unit-only-school-secret'
        body = json.loads(request.content)
        assert body == {'model': 'campus-qwen', 'messages': MESSAGES,
            'max_completion_tokens': 2048, 'stream': False}
        assert 'unit-only-school-secret' not in str(body)
        return httpx.Response(200, json=completion('answer'))
    config = model_settings()
    result = call(CampusModelClient(config, transport=httpx.MockTransport(handler)))
    assert result.content == 'answer' and result.attempts == 1
    assert result.usage['total_tokens'] == 160
    assert 'unit-only-school-secret' not in repr(config)
    assert 'unit-only-school-secret' not in json.dumps(config.public_identity())
    assert len(requests) == 1


@pytest.mark.parametrize('key', ['', 'oaipxy_k_REPLACE_WITH_YOUR_KEY', 'bad\nkey', '非ASCII'])
def test_missing_or_unsafe_key_never_sends_request(key):
    def forbidden(request):
        pytest.fail('Invalid key must never leave the process')
    with pytest.raises(ContractFailure) as error:
        call(CampusModelClient(model_settings(api_key=key), transport=httpx.MockTransport(forbidden)))
    assert not error.value.error.recoverable
    assert key not in str(error.value) if key else True


def test_optional_low_effort_is_sent_and_registered_without_secret_or_template_options():
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body['reasoning_effort'] == 'low'
        assert 'chat_template_kwargs' not in body
        return httpx.Response(200, json=completion('answer'))
    original = model_settings()
    settings = model_settings(reasoning_effort='low')
    assert 'reasoning_effort' not in original.public_identity()
    assert settings.public_identity() == original.public_identity() | {'reasoning_effort': 'low'}
    call(CampusModelClient(settings, transport=httpx.MockTransport(handler)))
    assert len(requests) == 1 and 'unit-only-school-secret' not in str(requests)


@pytest.mark.parametrize('value', ['high', 'auto', '', True, {'enable_thinking': False}])
def test_reasoning_override_is_explicit_and_bounded(value):
    with pytest.raises(ValidationError):
        model_settings(reasoning_effort=value)


@pytest.mark.parametrize('status', [301, 302, 307, 400, 401, 403, 404])
def test_rejected_or_redirected_response_is_not_followed_retried_or_echoed(status):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={'Location': 'https://not-the-school.invalid'},
            text='unit-only-school-secret private proxy body')
    with pytest.raises(ContractFailure) as error:
        call(CampusModelClient(model_settings(max_attempts=3), transport=httpx.MockTransport(handler)))
    assert len(requests) == 1
    assert str(status) == error.value.error.context['http_status']
    assert 'unit-only-school-secret' not in str(error.value)
    assert 'private proxy body' not in str(error.value)


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_transient_response_has_bounded_retry(status):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status if len(requests) == 1 else 200, json=completion('answer'))
    result = call(CampusModelClient(model_settings(max_attempts=2), transport=httpx.MockTransport(handler)))
    assert result.attempts == len(requests) == 2


def test_exhausted_timeout_is_recoverable_and_sanitized():
    requests = []
    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout('unit-only-school-secret private details', request=request)
    with pytest.raises(ContractFailure) as error:
        call(CampusModelClient(model_settings(max_attempts=2), transport=httpx.MockTransport(handler)))
    assert len(requests) == 2 and error.value.error.recoverable
    assert 'unit-only-school-secret' not in str(error.value)


@pytest.mark.parametrize('body', [
    {}, {'choices': []}, {'choices': [{'message': {'content': None}}]},
    {'choices': [{'message': {'content': 'answer'}, 'finish_reason': 'length'}]},
    {'choices': [{'message': {'content': 'answer', 'tool_calls': [{'function': 'unknown'}]}}]},
    completion('answer', usage={'total_tokens': True}),
])
def test_malformed_or_truncated_reply_is_rejected(body):
    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=body)))
    with pytest.raises(ContractFailure) as error:
        call(client)
    assert error.value.error.code == 'CONTRACT_INVALID'


def test_upstream_model_identity_may_differ_from_proxy_alias():
    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=completion('answer', model='upstream-qwen-label'))))
    result = call(client)
    assert result.model == 'campus-qwen' and result.served_model == 'upstream-qwen-label'


@pytest.mark.parametrize('body', [b'not JSON', b'{"choices":[],"choices":[]}',
    b'x' * (MAX_RESPONSE_BYTES + 1)], ids=['invalid-json','duplicate-key','oversized-body'])
def test_invalid_duplicate_or_oversized_body_is_not_accepted(body):
    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=body)))
    with pytest.raises(ContractFailure) as error:
        call(client)
    assert error.value.error.code == 'CONTRACT_INVALID'


def test_cancellation_during_network_wait_is_not_swallowed_or_retried():
    async def run():
        started = asyncio.Event()
        requests = []
        async def handler(request):
            requests.append(request)
            started.set()
            await asyncio.sleep(10)
            return httpx.Response(200, json=completion('answer'))
        client = CampusModelClient(model_settings(max_attempts=3), transport=httpx.MockTransport(handler))
        task = asyncio.create_task(client.complete(MESSAGES))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(requests) == 1
    asyncio.run(run())


@pytest.mark.parametrize('changes', [
    {'base_url': 'http://user:secret@10.167.60.148:8000/v1'},
    {'base_url': 'http://10.167.60.148:8000/v1?api_key=secret'},
    {'base_url': 'http://10.167.60.148:8000/v1/chat/completions'},
    {'base_url': 'file:///v1'}, {'model': 'different-model'},
    {'max_attempts': 0}, {'max_turns': 100}, {'max_completion_tokens': 9000},
    {'timeout_seconds': float('nan')}, {'max_attempts': True},
])
def test_configuration_rejects_unsafe_endpoints_models_and_unbounded_limits(changes):
    with pytest.raises(ValidationError):
        model_settings(**changes)


def test_local_dotenv_file_is_opt_in_and_process_environment_takes_precedence(tmp_path, monkeypatch):
    for field in CampusModelSettings.model_fields.values():
        monkeypatch.delenv(field.validation_alias, raising=False)
    path = tmp_path / 'private.env'
    path.write_text('ELEC5620_API_KEY=local-unit-secret\nELEC5620_MAX_ATTEMPTS=2\n', encoding='utf-8')
    config = CampusModelSettings(_env_file=path)
    assert config.api_key.get_secret_value() == 'local-unit-secret' and config.max_attempts == 2
    monkeypatch.setenv('ELEC5620_API_KEY', 'process-unit-secret')
    assert CampusModelSettings(_env_file=path).api_key.get_secret_value() == 'process-unit-secret'


@pytest.mark.parametrize('changes', [
    {'content': 'unit-only-school-secret'},
    {'served_model': 'echo-unit-only-school-secret'},
])
def test_proxy_cannot_echo_credential_into_successful_trace(changes):
    body = completion(changes.get('content', 'answer'),
        model=changes.get('served_model', 'campus-qwen'))
    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=body)))
    with pytest.raises(ContractFailure) as error:
        call(client)
    assert error.value.error.code == 'CONTRACT_INVALID'
    assert 'unit-only-school-secret' not in str(error.value)


def test_oversized_request_is_rejected_before_network():
    def forbidden(request):
        pytest.fail('Oversized input must not leave the process')
    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(forbidden))
    with pytest.raises(ContractFailure):
        asyncio.run(client.complete([{'role': 'user', 'content': 'x' * 131073}]))


def test_offline_configuration_check_is_safe_for_a_ready_endpoint():
    def forbidden(request):
        pytest.fail('Readiness must not call a billable model endpoint')
    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(forbidden))
    assert client.validate_configuration() is None
    with pytest.raises(ContractFailure):
        CampusModelClient(model_settings(api_key='')).validate_configuration()


def test_credential_accidentally_added_to_model_context_is_blocked_before_network():
    def forbidden(request):
        pytest.fail('A credential must not be sent as model context')
    client = CampusModelClient(model_settings(), transport=httpx.MockTransport(forbidden))
    with pytest.raises(ContractFailure) as error:
        asyncio.run(client.complete([{'role': 'user', 'content': 'key=unit-only-school-secret'}]))
    assert error.value.error.code == 'CONTRACT_INVALID'
    assert 'unit-only-school-secret' not in str(error.value)
