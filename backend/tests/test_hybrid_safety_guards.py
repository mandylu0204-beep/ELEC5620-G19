"""Local-only B capability checks with real A38 factory composition."""
import asyncio
from copy import copy

import pytest

from app.agents.hybrid_planning_agent import HybridPlanningAgent
from app.application.agent_runtime import build_v2_hybrid_binding
from app.application.datasets import inspect_dataset
from app.contracts.errors import ContractFailure
from app.workflow.orchestration import Orchestrator
from safety_runtime_fixtures import mock_safety_runtime
from safety_fixtures import safety_fixture
from test_safety_runtime_registration import settings


@pytest.mark.parametrize('mutation',[
    'missing','other_component','other_context','missing_marker','wrong_contract',
    'seed','unregistered','missing_replay'])
def test_hybrid_rejects_safety_binding_and_registration_mismatch_before_inference(tmp_path,monkeypatch,mutation):
    requests,_ = mock_safety_runtime(monkeypatch)
    config = settings(tmp_path,safety_execution='model',logistics_execution='model')
    binding = build_v2_hybrid_binding(config,inspect_dataset(config))
    agent = binding.agent
    choices = dict(binding.context.selection_config)
    if mutation == 'missing': agent.safety_agent = None
    elif mutation == 'other_component': agent.safety_agent = agent.logistics_agent
    elif mutation == 'other_context':
        role = agent.safety_agent
        other = copy(role.configuration)
        other._context = binding.context.model_copy(update={'rules_version':'other-context'})
        monkeypatch.setattr(role,'configuration',other)
    elif mutation == 'missing_marker': del choices['a_safety_audit_required']
    elif mutation == 'wrong_contract': choices['a_safety_audit_contract'] = 'unrecognised'
    elif mutation == 'seed': choices['a_safety_identity_seed'] = '{}'
    elif mutation == 'unregistered': choices = {key:value for key,value in choices.items() if not key.startswith('a_safety_')}
    else: monkeypatch.setattr(agent.safety_agent,'validate_safety_artifacts',None)
    # Both role checks see the same tampered context; none may silently rebind.
    if mutation in {'missing_marker','wrong_contract','seed','unregistered'}:
        monkeypatch.setattr(agent.workflow_configuration,'_context',binding.context.model_copy(update={'selection_config':choices}))
    with pytest.raises(ContractFailure) as exc: agent._check_configuration()
    assert exc.value.error.code == 'STALE_CONTEXT' and not requests


def test_rule_safety_does_not_offer_a_trace_or_accept_an_unregistered_component(tmp_path,monkeypatch):
    requests,_ = mock_safety_runtime(monkeypatch)
    config = settings(tmp_path)
    binding = build_v2_hybrid_binding(config,inspect_dataset(config))
    input = safety_fixture()[1]
    with pytest.raises(ContractFailure) as exc:
        asyncio.run(binding.agent.assess_safety_with_trace(input))
    assert exc.value.error.code == 'CONTRACT_INVALID'
    with pytest.raises(ContractFailure):
        HybridPlanningAgent(binding.agent.dataset,binding.agent.coordinator,
            workflow_configuration=binding.agent.workflow_configuration,safety_agent=object())
    assert not requests


@pytest.mark.parametrize('target,attribute',[
    ('hybrid','safety_audit_contract'),('hybrid','assess_safety_with_trace'),
    ('orchestrator','safety_audit_contract')])
def test_factory_readiness_refuses_incomplete_wiring_without_paid_probe(tmp_path,monkeypatch,target,attribute):
    requests,_ = mock_safety_runtime(monkeypatch)
    monkeypatch.setattr(HybridPlanningAgent if target=='hybrid' else Orchestrator,attribute,None)
    config = settings(tmp_path,safety_execution='model')
    with pytest.raises(ContractFailure):build_v2_hybrid_binding(config,inspect_dataset(config))
    assert not requests
