"""Local-only registration/provider checks; no production orchestration claim."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.application.agent_runtime import build_v2_hybrid_binding
from app.application.datasets import inspect_dataset
from app.application.dispatcher import PlanningDispatcher
from app.application.logistics_audit import canonical, decode, digest
from app.contracts.errors import ContractFailure
from app.agents.hybrid_planning_agent import HybridPlanningAgent
from app.workflow.orchestration import Orchestrator
from campus_http_fixtures import mock_campus
from llm_fixtures import ROOT
from safety_fixtures import safety_fixture


def settings(tmp_path,**changes):
    return Settings(_env_file=None,execution_mode='agent',dataset_path=ROOT/'data/synthetic_demo_v2_1',
        clock_mode='fixed',demo_today='2026-11-05',synthetic_evidence_mode='sealed',
        database_path=tmp_path/'runtime.sqlite3',planning_enabled=True,**changes)


def enable_registration_test_double(monkeypatch):
    # Explicitly tests A registration, NOT B's future Hybrid/Orchestrator wiring.
    class RegistrationOnlyHybrid(HybridPlanningAgent):
        safety_audit_contract='1.0'
        def __init__(self,*args,safety_agent=None,**kwargs):
            self.safety_agent=safety_agent
            super().__init__(*args,**kwargs)
        async def assess_safety_with_trace(self,*args):
            raise AssertionError('Registration tests must not perform inference')
    import app.agents.hybrid_planning_agent as module
    monkeypatch.setattr(module,'HybridPlanningAgent',RegistrationOnlyHybrid)
    monkeypatch.setattr(Orchestrator,'safety_audit_contract','1.0',raising=False)


@pytest.mark.parametrize('logistics_mode,safety_mode',[
    ('rules','rules'),('model','rules'),('rules','model'),('model','model')])
def test_factory_collects_all_seeds_before_one_final_context(tmp_path,monkeypatch,logistics_mode,safety_mode):
    calls,_=mock_campus(monkeypatch)
    enable_registration_test_double(monkeypatch)
    config=settings(tmp_path,logistics_execution=logistics_mode,safety_execution=safety_mode)
    binding=build_v2_hybrid_binding(config,inspect_dataset(config))
    context=binding.context.model_dump(mode='json')
    for role,mode in (('logistics',logistics_mode),('safety',safety_mode)):
        choices=binding.context.selection_config
        assert (f'a_{role}_identity_seed' in choices)==(mode=='model')
        if mode=='model':
            seed=decode(choices[f'a_{role}_identity_seed'])
            component=getattr(binding.agent,f'{role}_agent')
            assert component.identity['workflow_context']==context
            assert component.identity['configuration_fingerprint']==digest(canonical({**seed,'workflow_context':context}))
            assert seed['kernel_version']=='b02-v1-rules-2/a-meal-clarification-v1/a-profile-essentials-v1'
            assert seed['dataset_rules_version']=='b02-v2-rules-2/a-meal-clarification-v1/a-profile-essentials-v1/trip-evidence-selection-1'
            assert not {'workflow_context','configuration_fingerprint','api_key'} & seed.keys()
    assert calls==[]


def test_unwired_production_safety_flag_fails_closed_without_network(tmp_path,monkeypatch):
    calls,_=mock_campus(monkeypatch)
    config=settings(tmp_path,safety_execution='model')
    app=create_app(config)
    with TestClient(app) as client:
        assert client.get('/api/v1/health/ready').status_code==503
        meta=client.get('/api/v1/meta').json()
        assert meta['features']['planning'] is False
        assert meta['features']['model_safety'] is False
        assert meta['planning_stages']['safety']=='rules'
        assert meta['agent_configuration_error'] is not None
        assert app.state.workflows.safety_facts_provider is not None
    assert calls==[]


@pytest.mark.parametrize('mode',['stub','deterministic_demo'])
def test_safety_model_is_rejected_outside_agent_mode(tmp_path,mode):
    app=create_app(Settings(_env_file=None,execution_mode=mode,safety_execution='model',
        database_path=tmp_path/'wrong-mode.sqlite3'))
    with TestClient(app) as client:
        meta=client.get('/api/v1/meta').json()
        assert not meta['features']['planning'] and not meta['features']['model_safety']


def test_rules_mode_cannot_inherit_safety_model_markers(tmp_path,monkeypatch):
    calls,_=mock_campus(monkeypatch)
    config=settings(tmp_path,dataset_selection={'a_safety_mode':'model'})
    with pytest.raises(ContractFailure):build_v2_hybrid_binding(config,inspect_dataset(config))
    assert calls==[]


@pytest.fixture(scope='module')
def facts():return safety_fixture()


def test_authoritative_provider_uses_pinned_runtime_selection(facts):
    dataset,input,configuration,baseline,selection=facts
    scope=SimpleNamespace(dataset_context=configuration.context,demo_context=input.demo_context)
    snapshot=SimpleNamespace(dataset=configuration.context,demo=input.demo_context,
        agent=SimpleNamespace(dataset=dataset,workflow_configuration=configuration))
    dispatcher=PlanningDispatcher.__new__(PlanningDispatcher)
    dispatcher.state=SimpleNamespace(runtime=SimpleNamespace(for_scope=lambda pinned:snapshot))
    confirmed=SimpleNamespace(requirements=input.confirmed_requirements)
    version=SimpleNamespace(version_context=input.version_context,content=input.saved_itinerary)
    rebuilt,result,selected=dispatcher.safety_facts(scope,confirmed,version,input.saved_logistics_assessment)
    assert rebuilt==input and result==baseline and selected==selection
    snapshot.dataset=configuration.context.model_copy(update={'rules_version':'changed'})
    with pytest.raises(ContractFailure) as exc:dispatcher.safety_facts(scope,confirmed,version,input.saved_logistics_assessment)
    assert exc.value.error.code=='STALE_CONTEXT'


def test_safety_flag_default_and_invalid_values():
    from pydantic import ValidationError
    assert Settings(_env_file=None).safety_execution=='rules'
    with pytest.raises(ValidationError):Settings(_env_file=None,safety_execution='auto')


def test_safety_registration_preserves_revision_feedback(tmp_path,monkeypatch):
    from dataclasses import replace
    calls,_=mock_campus(monkeypatch)
    enable_registration_test_double(monkeypatch)
    config=settings(tmp_path,logistics_execution='model',safety_execution='model')
    descriptor=inspect_dataset(config)
    context=descriptor.context.model_copy(update={'selection_config':{
        **descriptor.context.selection_config,'a_revision_feedback':'Choose a quieter campsite.'}})
    binding=build_v2_hybrid_binding(config,replace(descriptor,context=context))
    assert binding.context.selection_config['revision_feedback']=='Choose a quieter campsite.'
    for role in ('logistics','safety'):
        component=getattr(binding.agent,role+'_agent')
        assert component.identity['workflow_context']==binding.context.model_dump(mode='json')
    assert calls==[]


def test_safety_model_rejects_v2_without_trip_selector(tmp_path,monkeypatch):
    calls,_=mock_campus(monkeypatch)
    enable_registration_test_double(monkeypatch)
    config=Settings(_env_file=None,execution_mode='agent',safety_execution='model',
        dataset_path=ROOT/'data/synthetic_demo_v2',database_path=tmp_path/'unsupported.sqlite3')
    with pytest.raises(ContractFailure):build_v2_hybrid_binding(config,inspect_dataset(config))
    assert calls==[]
