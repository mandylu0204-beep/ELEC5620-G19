import asyncio
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
