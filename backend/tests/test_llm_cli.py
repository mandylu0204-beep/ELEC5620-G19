import asyncio
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest

from app.llm import __main__ as cli
from app.llm.client import CampusModelClient
from app.llm.config import CampusModelSettings
from app.contracts.errors import ContractError, ContractFailure
from llm_fixtures import ROOT, completion, final_action, tool_action


def clear_env(monkeypatch):
    for field in CampusModelSettings.model_fields.values():
        monkeypatch.delenv(field.validation_alias, raising=False)


def test_standalone_plan_uses_sealed_data_and_outputs_honest_component_scope(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    path = tmp_path / 'private.env'
    path.write_text('ELEC5620_API_KEY=standalone-unit-secret\n', encoding='utf-8')
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=completion(tool_action() if len(requests) == 1 else final_action()))
    monkeypatch.setattr(cli, 'CampusModelClient', lambda config:
        CampusModelClient(config, transport=httpx.MockTransport(handler)))
    result = asyncio.run(cli.execute(SimpleNamespace(env_file=path, probe=False, plan='normal')))
    assert len(requests) == 2
    assert result['status'] == 'PLANNING_COMPONENT_VALIDATED'
    assert result['execution_mode'] == 'agent'
    assert not result['application_registered'] and not result['assessments_run'] and not result['finalisation_performed']
    assert result['itinerary']['selected_campsite_ids'] == ['demo-wattle-rest']
    assert 'standalone-unit-secret' not in json.dumps(result)


def test_probe_is_one_bounded_request_and_does_not_print_model_text(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    path = tmp_path / 'private.env'
    path.write_text('ELEC5620_API_KEY=standalone-unit-secret\n', encoding='utf-8')
    def handler(request):
        assert json.loads(request.content)['max_completion_tokens'] == 128
        return httpx.Response(200, json=completion('Synthetic school probe reply.'))
    monkeypatch.setattr(cli, 'CampusModelClient', lambda config:
        CampusModelClient(config, transport=httpx.MockTransport(handler)))
    result = asyncio.run(cli.execute(SimpleNamespace(env_file=path, probe=True, plan=None)))
    assert result['status'] == 'PROXY_RESPONSE_RECEIVED' and result['reply_received']
    assert 'Synthetic school probe reply.' not in json.dumps(result)


def test_empty_key_cli_exits_cleanly_without_live_network(tmp_path):
    path = tmp_path / 'private.env'
    path.write_text('ELEC5620_API_KEY=\n', encoding='utf-8')
    env = {key: value for key, value in os.environ.items() if not key.startswith('ELEC5620_')}
    result = subprocess.run([sys.executable, '-B', '-m', 'app.llm', '--probe', '--env-file', str(path)],
        cwd=ROOT / 'backend', env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1 and not result.stderr
    value = json.loads(result.stdout)
    assert value['status'] == 'FAILED' and value['error']['code'] == 'AGENT_FAILURE'


@pytest.mark.parametrize('encoding', ['ascii', 'cp1252', 'utf-8'])
@pytest.mark.parametrize('outcome', ['success', 'contract_failure', 'invalid_input'])
def test_main_json_roundtrips_on_strict_output_streams(monkeypatch, capsys, encoding, outcome):
    message = '离线检查：中文与符号 🏕️'
    error = ContractError(code='AGENT_FAILURE', message=message)
    expected = {'status': 'OFFLINE_SUCCESS', 'message': message, 'items': ['第二行', 'é']}
    if outcome == 'contract_failure':
        expected = {'status': 'FAILED', 'error': error.model_dump(mode='json')}
    elif outcome == 'invalid_input':
        expected = {'status': 'FAILED', 'message': '本地模型配置或演示输入无效。'}
    calls = []

    async def execute(args):
        calls.append(args)
        if outcome == 'contract_failure':
            raise ContractFailure(error)
        if outcome == 'invalid_input':
            raise ValueError('PRIVATE_SYNTHETIC_CONFIG_MUST_NOT_BE_PRINTED')
        return expected

    def forbidden_client(*args, **kwargs):
        raise AssertionError('Output tests must not construct a model client')

    monkeypatch.setattr(cli, 'execute', execute)
    monkeypatch.setattr(cli, 'CampusModelClient', forbidden_client)
    monkeypatch.setattr(sys, 'argv', ['offline-cli-output', '--probe'])
    with io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors='strict') as stream:
        with redirect_stdout(stream):
            code = cli.main()
        assert stream.encoding == encoding and stream.errors == 'strict'
        stream.flush()
        output = stream.buffer.getvalue()
    assert code == (0 if outcome == 'success' else 1)
    assert len(calls) == 1 and calls[0].probe
    assert output.isascii()
    assert json.loads(output.decode(encoding)) == expected
    assert 'PRIVATE_SYNTHETIC_CONFIG' not in output.decode(encoding)
    assert not capsys.readouterr().err
    if outcome == 'success':
        assert output.startswith(b'{\n  "status":')


@pytest.mark.parametrize('encoding', ['ascii', 'cp1252', 'utf-8'])
def test_empty_key_subprocess_json_on_non_utf8_and_utf8_streams(tmp_path, encoding):
    path = tmp_path / 'private.env'
    path.write_text('ELEC5620_API_KEY=\n', encoding='utf-8')
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('ELEC5620_')}
    env.update(PYTHONIOENCODING=encoding + ':strict', PYTHONUTF8='0',
        ELEC5620_BASE_URL='http://offline.invalid/v1')
    result = subprocess.run([sys.executable, '-B', '-m', 'app.llm', '--probe', '--env-file', str(path)],
        cwd=ROOT / 'backend', env=env, capture_output=True, timeout=10)
    assert result.returncode == 1 and not result.stderr
    assert result.stdout.isascii()
    value = json.loads(result.stdout.decode(encoding))
    assert value['status'] == 'FAILED' and value['error']['code'] == 'AGENT_FAILURE'
    assert value['error']['message']


def test_git_ignores_private_env_but_keeps_public_template():
    def ignored(name):
        return subprocess.run(['git', 'check-ignore', '--no-index', name], cwd=ROOT,
            capture_output=True, text=True).returncode == 0
    if not (ROOT / '.git').exists():
        pytest.skip('Git ignore policy is checked in repository runs, not source ZIPs.')
    assert ignored('.env.llm.local')
    assert not ignored('config/campus_llm.example')
    assert not ignored('.env.example')


def test_release_guard_rejects_private_env_even_if_force_added():
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location('llm_package_guard', ROOT / 'scripts/package.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError):
        module.safe_path('campmate_app/.env.llm.local')
    module.safe_path('campmate_app/config/campus_llm.example')
