"""SQLite storage tests with an explicitly synthetic replay boundary, no inference.

B's current identity is incompatible with A31 (R-S01). These tests do not claim
combined real-component acceptance; actual rule facts and persisted contexts are
used, while advisory validation is a test double until the agreed B revision.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth import User
from app.config import Settings
from app.main import create_app
from app.agents.rules import logistics, safety
from app.agents.rules.trip_evidence import TripEvidenceSelection
from app.application import safety_audit
from app.application.assessment_audits import load_audits
from app.application.logistics_audit import canonical, digest
from app.contracts.dto import ConfirmedContext, LogisticsInput, SafetyInput
from app.contracts.errors import ContractFailure
from app.workflow import WorkflowConfiguration
from app.storage.repository import Repository
from llm_fixtures import model_input
from test_llm_logistics_agent import input_fixture

call = asyncio.run


class Artifact:
    def __init__(self, body): self.body = body
    def model_dump(self, **_): return deepcopy(self.body)
    def __getattr__(self, key): return self.body[key]


@pytest.fixture
def stored(tmp_path, monkeypatch):
    dataset, original, _ = input_fixture()
    seed = dict(agent_version='campus-safety-advisory-agent-2',tool_version='safety-read-only-tools-2',
        validation_version='safety-advisory-validation-2',kernel_version='b02-v1-rules-2/a-meal-clarification-v1',
        dataset_rules_version=dataset.rules_version,prompt_sha256='a'*64,
        model_client={'model':'offline-test-double'})
    markers = {'a_safety_mode':'model','a_safety_audit_required':'1','a_safety_audit_contract':'1.0',
        'a_safety_identity_seed':canonical(seed)}
    context = dataset.context.model_copy(update={'selection_config':markers})
    config = WorkflowConfiguration(dataset,safety_case_ids=['safety-15'],registered_context=context)
    app = create_app(Settings(_env_file=None,database_path=tmp_path/'safety.sqlite3'))
    with TestClient(app) as client:
        user = User('camper-a','camper.a','Camper A','CAMPER')
        wf = app.state.workflows
        wf.context_provider = None
        confirmed = ConfirmedContext(request_id='safety-storage-request',confirmed_at=datetime.now(timezone.utc),
            requirements=original.confirmed_requirements,profile_snapshot=original.profile_snapshot,
            demo_context=original.demo_context,dataset_context=config.context)
        app.state.repository.record_confirmed_request(user,'Independent storage fixture',confirmed)
        scope = wf.start(user,confirmed.request_id,confirmed.demo_context,config.context,command_key='safety-storage-start')
        attempt = wf.claim(user,scope.run_id,scope.demo_context,scope.dataset_context)
        port = wf.port(user,attempt)
        call(port.save_recommendations(model_input()[1].recommendations,scope.write_keys['recommendations']))
        version = call(port.append_plan_version(None,original.saved_itinerary,scope.request_id,'Offline fixture',scope.write_keys['version']))
        log_input = LogisticsInput(version_context=version.version_context,saved_itinerary=version.content,
            confirmed_requirements=confirmed.requirements,profile_snapshot=confirmed.profile_snapshot,demo_context=scope.demo_context)
        log = call(port.save_assessment(version.version_context,'LOGISTICS',
            logistics.assess(dataset,log_input,expected_mode='agent',safety_case_ids=['safety-15']),scope.write_keys['logistics']))
        scenario = config.scenario_for(version.content.selected_campsite_ids)
        selection = TripEvidenceSelection(selected_case_ids=['safety-15'],scenario_context=scenario,
            weather_facts_by_campsite={},coverage_issues=[],selection_digest='a'*64)
        input = SafetyInput(version_context=version.version_context,saved_itinerary=version.content,
            confirmed_requirements=confirmed.requirements,saved_logistics_assessment=log,scenario_context=scenario,demo_context=scope.demo_context)
        baseline = safety.assess(dataset,input,expected_mode='agent')
        wf.safety_facts_provider = lambda *args: (input,baseline,selection)
        plan = {'test_only_advice':'Independent SQLite fixture, not model advice.'}
        identity = safety_audit.registered_identity(scope,new_write=True)
        trace = {'configuration_fingerprint':identity['configuration_fingerprint'],
            'input_sha256':digest(input.model_dump_json()),'rule_facts_sha256':digest(baseline.model_dump_json())}
        replay_calls = []
        def replay(scope_arg, input_arg, baseline_arg, result, raw_plan, raw_trace, selected, **kwargs):
            replay_calls.append(kwargs)
            assert safety_audit.registered_identity(scope_arg,**kwargs) == identity
            if (input_arg != input or baseline_arg != baseline or result != baseline
                    or raw_plan != plan or raw_trace != trace or selected != selection):
                raise ValueError('Test replay mismatch')
            return Artifact(plan), Artifact(trace)
        monkeypatch.setattr(safety_audit,'replay',replay)
        yield SimpleNamespace(app=app,user=user,wf=wf,port=port,scope=scope,attempt=attempt,
            version=version,input=input,baseline=baseline,selection=selection,plan=plan,trace=trace,
            replay_calls=replay_calls,log=log)


def save(f, **changes):
    return call(f.port.save_model_safety_assessment(f.version.version_context,
        changes.get('result',f.baseline),changes.get('plan',f.plan),changes.get('trace',f.trace),
        changes.get('key',f.scope.write_keys['safety'])))


def counts(f):
    with f.app.state.database.transaction(write=False) as db:
        return [db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
            for table in ('assessments','gear_checklists','model_safety_audits')]


def test_atomic_receipt_checkpoint_and_restart(stored):
    f=stored
    first=save(f)
    assert save(f)==first and counts(f)==[2,1,1]
    audit=call(f.port.load_checkpoint())['model_assessment_audits']['SAFETY']
    assert audit['assessment_id']==first.assessment_id
    assert audit['depends_on_assessment_id']==f.log.assessment_id
    assert audit['attempt_id']==f.attempt.attempt_id
    assert not {'input_json','rule_facts_json','selection_json','owner_id'} & audit.keys()
    f.app.state.database.initialize()
    assert f.app.state.database.ready()
    with f.app.state.database.transaction(write=False) as db:
        assert load_audits(db,f.scope,f.version)['SAFETY']==audit


@pytest.mark.parametrize('table',['assessments','model_safety_audits','write_receipts'])
def test_each_write_failure_rolls_back(stored,table):
    f=stored
    with f.app.state.database.transaction() as db:
        db.execute(f"CREATE TRIGGER injected BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(ContractFailure): save(f)
    assert counts(f)==[1,1,0]


def test_changed_receipt_payload_conflicts(stored):
    save(stored)
    with pytest.raises(ContractFailure) as exc: save(stored,trace={**stored.trace,'extra':True})
    assert exc.value.error.code=='IDEMPOTENCY_CONFLICT'
    assert counts(stored)==[2,1,1]


@pytest.mark.parametrize('change',['baseline','plan','trace','key'])
def test_wrong_artifacts_never_save(stored,change):
    f=stored
    changed = {'baseline':{'result':f.baseline.model_copy(update={'hazards':['Invented hazard']})},
        'plan':{'plan':{}},'trace':{'trace':{}},'key':{'key':f.scope.write_keys['logistics']}}[change]
    with pytest.raises(ContractFailure):save(f,**changed)
    assert counts(f)==[1,1,0]


@pytest.mark.parametrize('corruption',['missing','payload','receipt','dependency','attempt','changed_attempt'])
def test_corruption_fails_nonrecoverably_at_checkpoint(stored,corruption):
    f=stored;save(f)
    with f.app.state.database.transaction() as db:
        db.execute('DROP TRIGGER immutable_safety_audit');db.execute('DROP TRIGGER no_delete_safety_audit')
        if corruption=='missing':db.execute('DELETE FROM model_safety_audits')
        elif corruption=='payload':db.execute("UPDATE model_safety_audits SET payload='{}'")
        elif corruption=='receipt':db.execute("DELETE FROM write_receipts WHERE operation='safety'")
        elif corruption=='dependency':db.execute("UPDATE model_safety_audits SET depends_on_assessment_id=assessment_id")
        elif corruption=='changed_attempt':db.execute("UPDATE model_safety_audits SET attempt_id='another-attempt'")
        else:db.execute("UPDATE model_safety_audits SET attempt_id=''")
    with pytest.raises(ContractFailure) as exc:call(f.port.load_checkpoint())
    assert exc.value.error.code=='PERSISTENCE_FAILURE' and not exc.value.error.recoverable
    assert 'RETRY' not in exc.value.error.allowed_actions


def test_plain_safety_port_cannot_bypass_audit(stored):
    f=stored
    with pytest.raises(ContractFailure):call(f.port.save_assessment(f.version.version_context,'SAFETY',f.baseline,f.scope.write_keys['safety']))
    assert counts(f)==[1,1,0]


def test_missing_provider_or_incompatible_component_fail_closed(stored,monkeypatch):
    f=stored;provider=f.wf.safety_facts_provider
    f.wf.safety_facts_provider=None
    with pytest.raises(ContractFailure):save(f)
    f.wf.safety_facts_provider=provider
    monkeypatch.undo()
    with pytest.raises(ContractFailure):save(f)
    assert counts(f)==[1,1,0]


def test_late_attempt_cannot_write(stored):
    f=stored
    with f.app.state.database.transaction() as db:
        db.execute('UPDATE run_leases SET expires_at=0 WHERE run_id=?',(f.scope.run_id,))
    with pytest.raises(ContractFailure) as exc:save(f)
    assert exc.value.error.code=='STALE_CONTEXT' and counts(f)==[1,1,0]


def test_triggers_preserve_audit_immutability(stored):
    f=stored;save(f)
    for query in ('UPDATE model_safety_audits SET payload=payload','DELETE FROM model_safety_audits'):
        with pytest.raises(ContractFailure):
            with f.app.state.database.transaction() as db:db.execute(query)


def test_no_saved_safety_allows_empty_audit_but_completion_requires_it(stored):
    f=stored
    with f.app.state.database.transaction(write=False) as db:
        assert load_audits(db,f.scope,f.version)=={}
        with pytest.raises(ContractFailure):load_audits(db,f.scope,f.version,must_exist=True)


def test_audit_missing_blocks_route_and_final_guards(stored):
    f=stored;save(f)
    with f.app.state.database.transaction() as db:
        db.execute('DROP TRIGGER no_delete_safety_audit');db.execute('DELETE FROM model_safety_audits')
    for operation in (
        lambda:call(f.port.route_assessed_version(f.version.version_context,'BLOCKED','offline',f.scope.write_keys['route'])),
        lambda:call(f.port.evaluate_eligibility(f.version.version_context)),
        lambda:f.app.state.plan_queries.detail(f.user,f.scope.plan_id),
    ):
        with pytest.raises(ContractFailure) as exc:operation()
        assert exc.value.error.code=='PERSISTENCE_FAILURE' and not exc.value.error.recoverable


def test_foreign_owner_cannot_read_safety_advice(stored):
    f=stored;save(f)
    other=User('camper-b','camper.b','Camper B','CAMPER')
    with pytest.raises(ContractFailure) as exc:f.app.state.plan_queries.detail(other,f.scope.plan_id)
    assert exc.value.error.code=='NOT_FOUND'


def test_saved_audit_read_needs_no_current_facts_provider(stored):
    f=stored;save(f);f.wf.safety_facts_provider=None
    assert call(f.port.load_checkpoint())['model_assessment_audits']['SAFETY']['assessment_id']


@pytest.mark.parametrize('version',['safety-advisory-validation-1','unknown-validator'])
def test_new_registration_rejects_legacy_or_unknown_validator(stored,version):
    scope=stored.scope
    choices=dict(scope.dataset_context.selection_config)
    seed=safety_audit.decode(choices['a_safety_identity_seed'])
    seed.update(validation_version=version,agent_version='campus-safety-advisory-agent-1',tool_version='safety-read-only-tools-1')
    choices['a_safety_identity_seed']=canonical(seed)
    changed=scope.model_copy(update={'dataset_context':scope.dataset_context.model_copy(update={'selection_config':choices})})
    with pytest.raises(ValueError):safety_audit.registered_identity(changed,new_write=True)
    if version=='safety-advisory-validation-1':
        assert safety_audit.registered_identity(changed)['validation_version']==version


def test_old_kernel_is_read_only_not_a_new_write_registration(stored):
    scope=stored.scope
    choices=dict(scope.dataset_context.selection_config)
    seed=safety_audit.decode(choices['a_safety_identity_seed'])
    seed.update(kernel_version='b02-v1-rules-2',dataset_rules_version='b02-v2-rules-2/trip-evidence-selection-1')
    choices['a_safety_identity_seed']=canonical(seed)
    historical=scope.model_copy(update={'dataset_context':scope.dataset_context.model_copy(update={'selection_config':choices})})
    assert safety_audit.registered_identity(historical)['kernel_version']=='b02-v1-rules-2'
    with pytest.raises(ValueError):safety_audit.registered_identity(historical,new_write=True)


def test_migration_from_nine_keeps_existing_user(tmp_path):
    from app.storage.database import Database, execute_migration
    from app.storage import database as module
    db=Database(tmp_path/'schema-nine.sqlite3')
    with db.transaction() as connection:
        for number in range(1,8):
            execute_migration(connection,getattr(module,'MIGRATION_'+str(number)))
            connection.execute('INSERT INTO schema_migrations VALUES(?,?)',(number,'historical'))
        connection.execute('ALTER TABLE plans ADD COLUMN deleted_at TEXT')
        connection.execute('CREATE TABLE deleted_requests(request_id TEXT PRIMARY KEY REFERENCES requests(id), deleted_at TEXT NOT NULL)')
        connection.execute("INSERT INTO schema_migrations VALUES(8,'historical'),(9,'historical')")
        connection.execute("INSERT INTO users VALUES('old-owner','old.user','Old Camper','CAMPER','old-hash')")
    db.initialize();db.initialize()
    assert db.ready()
    with db.transaction(write=False) as connection:
        assert connection.execute('SELECT username FROM users').fetchone()[0]=='old.user'
        assert connection.execute('SELECT COUNT(*) FROM model_safety_audits').fetchone()[0]==0
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_final_snapshot_binds_safety_audit_and_rechecks_it_on_read(stored):
    from app.storage.finalisation import FinaliseInput
    from test_finalisation import command
    f=stored;save(f)
    call(f.port.route_assessed_version(f.version.version_context,'ELIGIBLE_FOR_FINALISATION',
        'Independent storage fixture',f.scope.write_keys['route']))
    call(f.port.report_stage('COMPLETED','SUCCEEDED',None))
    f.app.state.finalisation.context_guard=None
    detail=f.app.state.plan_queries.detail(f.user,f.scope.plan_id)
    result=f.app.state.finalisation.submit(f.user,f.scope.plan_id,FinaliseInput.model_validate(command(detail)))
    final=f.app.state.finalisation.detail(f.user,f.scope.plan_id,result['final_id'])
    assert final['final_record']['model_assessment_audits']['SAFETY']['depends_on_assessment_id']==f.log.assessment_id
    with f.app.state.database.transaction() as db:
        db.execute('DROP TRIGGER no_delete_safety_audit');db.execute('DELETE FROM model_safety_audits')
    with pytest.raises(ContractFailure) as exc:f.app.state.finalisation.detail(f.user,f.scope.plan_id,result['final_id'])
    assert not exc.value.error.recoverable
