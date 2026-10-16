"""Actual B SafetyAgent/pure replay plus A SQLite; all campus HTTP is mocked."""
import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth import User
from app.config import Settings
from app.main import create_app
from app.agents.rules import logistics, safety
from app.application.logistics_audit import canonical, identity_seed
from app.contracts.dto import ConfirmedContext, LogisticsInput, SafetyInput
from app.contracts.errors import ContractFailure
from app.llm.logistics_agent import LogisticsAgent
from app.workflow import WorkflowConfiguration
from safety_fixtures import safety_fixture, safety_agent_fixture
from test_llm_logistics_agent import agent_fixture
from llm_fixtures import model_input

call=asyncio.run


@pytest.fixture(scope='module')
def base():
    return safety_fixture()


@pytest.fixture(params=[False,True],ids=['rules-logistics','model-logistics'])
def integrated(tmp_path,base,request):
    dataset,original,initial,_,_=base
    prototype,_=safety_agent_fixture(dataset,initial)
    markers=dict(initial.context.selection_config)
    markers.update(a_safety_mode='model',a_safety_audit_required='1',a_safety_audit_contract='1.0',
        a_safety_identity_seed=canonical(prototype.identity_seed))
    suffix=''
    if request.param:
        proto_log=LogisticsAgent(dataset,prototype.client,workflow_configuration=initial)
        markers.update(a_logistics_mode='model',a_logistics_audit_required='1',a_logistics_audit_contract='1.0',
            a_logistics_identity_seed=canonical(identity_seed(proto_log)))
        suffix='/a-model-logistics-audit-v1'
    registered=dataset.context.model_copy(update={'selection_config':markers,
        'rules_version':dataset.context.rules_version+suffix+'/a-model-safety-audit-v1'})
    config=WorkflowConfiguration(dataset,registered_context=registered)
    app=create_app(Settings(_env_file=None,database_path=tmp_path/'combined.sqlite3'))
    with TestClient(app) as client:
        user=User('camper-a','camper.a','Camper A','CAMPER')
        wf=app.state.workflows;wf.context_provider=None
        confirmed=ConfirmedContext(request_id='combined-safety-request',confirmed_at=datetime.now(timezone.utc),
            requirements=original.confirmed_requirements,profile_snapshot=model_input()[1].profile_snapshot,
            demo_context=original.demo_context,dataset_context=config.context)
        app.state.repository.record_confirmed_request(user,'Offline combined safety fixture',confirmed)
        scope=wf.start(user,confirmed.request_id,confirmed.demo_context,config.context,command_key='combined-safety-start')
        attempt=wf.claim(user,scope.run_id,scope.demo_context,scope.dataset_context);port=wf.port(user,attempt)
        call(port.save_recommendations(model_input()[1].recommendations,scope.write_keys['recommendations']))
        version=call(port.append_plan_version(None,original.saved_itinerary,scope.request_id,'Offline fixture',scope.write_keys['version']))
        log_input=LogisticsInput(version_context=version.version_context,saved_itinerary=version.content,
            confirmed_requirements=confirmed.requirements,profile_snapshot=confirmed.profile_snapshot,demo_context=scope.demo_context)
        ids=json.loads(config.context.selection_config['safety_case_ids'])
        wf.logistics_facts_provider=lambda scope,input:logistics.assess(dataset,input,expected_mode='agent',safety_case_ids=ids)
        log_requests=[]
        if request.param:
            log_agent,log_requests=agent_fixture(dataset,config)
            outcome=call(log_agent.assess_with_trace(log_input))
            log=call(port.save_model_logistics_assessment(version.version_context,outcome.assessment,
                outcome.plan.model_dump(mode='json'),outcome.trace.model_dump(mode='json'),scope.write_keys['logistics']))
        else:
            log=call(port.save_assessment(version.version_context,'LOGISTICS',wf.logistics_facts_provider(scope,log_input),scope.write_keys['logistics']))
        selection=config.resolve_trip_evidence(confirmed.requirements,version.content.selected_campsite_ids,scope.demo_context)
        input=SafetyInput(version_context=version.version_context,saved_itinerary=version.content,
            confirmed_requirements=confirmed.requirements,saved_logistics_assessment=log,
            scenario_context=selection.scenario_context,demo_context=scope.demo_context)
        baseline=safety.assess(dataset,input,expected_mode='agent')
        wf.safety_facts_provider=lambda *args:(input,baseline,selection)
        agent,requests=safety_agent_fixture(dataset,config)
        outcome=call(agent.assess_safety_with_trace(input))
        yield SimpleNamespace(app=app,user=user,wf=wf,port=port,scope=scope,attempt=attempt,
            version=version,outcome=outcome,baseline=baseline,log=log,requests=requests,log_requests=log_requests,
            expected_keys={'SAFETY','LOGISTICS'} if request.param else {'SAFETY'})


def save(f):
    return call(f.port.save_model_safety_assessment(f.version.version_context,f.outcome.assessment,
        f.outcome.plan.model_dump(mode='json'),f.outcome.trace.model_dump(mode='json'),f.scope.write_keys['safety']))


def test_actual_component_save_replay_dependency_and_checkpoint(integrated):
    f=integrated;stored=save(f)
    assert save(f)==stored and len(f.requests)==3
    checkpoint=call(f.port.load_checkpoint())
    assert set(checkpoint['model_assessment_audits'])==f.expected_keys
    audit=checkpoint['model_assessment_audits']['SAFETY']
    assert audit['plan']==f.outcome.plan.model_dump(mode='json')
    assert audit['trace']==f.outcome.trace.model_dump(mode='json')
    assert stored.result==f.baseline and stored.depends_on_assessment_id==f.log.assessment_id
    assert audit['attempt_id']==f.attempt.attempt_id
    f.wf.safety_facts_provider=None
    assert save(f)==stored and len(f.requests)==3


def test_actual_validator_rejects_modified_advice_without_writes(integrated):
    f=integrated
    plan=f.outcome.plan.model_dump(mode='json');plan['decision_summary_unverified']='See www.example.com for guidance.'
    with pytest.raises(ContractFailure) as exc:
        call(f.port.save_model_safety_assessment(f.version.version_context,f.outcome.assessment,plan,
            f.outcome.trace.model_dump(mode='json'),f.scope.write_keys['safety']))
    assert exc.value.error.code=='CONTRACT_INVALID'
    with f.app.state.database.transaction(write=False) as db:
        assert db.execute('SELECT COUNT(*) FROM model_safety_audits').fetchone()[0]==0


def test_actual_saved_trace_corruption_blocks_recovery(integrated):
    f=integrated;save(f)
    with f.app.state.database.transaction() as db:
        db.execute('DROP TRIGGER immutable_safety_audit')
        db.execute("UPDATE model_safety_audits SET configuration_fingerprint=?",('f'*64,))
    with pytest.raises(ContractFailure) as exc:call(f.port.load_checkpoint())
    assert exc.value.error.code=='PERSISTENCE_FAILURE' and not exc.value.error.recoverable
    assert len(f.requests)==3
