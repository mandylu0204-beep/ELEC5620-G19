"""Independent A recovery tests. No B Agent, LLM or business demo validation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app.auth import User
from app.contracts.dto import ConfirmedContext, ConfirmedRequirements, DatasetContext, DemoContext, ProfileSnapshot, ItineraryResult, RecommendCampsitesResult
from app.contracts.errors import ContractError, ContractFailure
from app.contracts.enums import ExecutionMode
from app.storage.database import Database, execute_migration, MIGRATION_1, MIGRATION_2, MIGRATION_3, MIGRATION_4
from app.storage.repository import Repository
from app.storage.workflows import WorkflowService, Attempt
from app.storage.plan_queries import PlanQueries
from test_storage import call, logistics, safety


@pytest.fixture
def workflow(tmp_path):
    db = Database(tmp_path / 'workflow.sqlite3'); db.initialize()
    user = User('camper-a', 'camper.a', 'Camper A', 'CAMPER')
    with db.transaction() as connection:
        for identity, role in [('camper-a','CAMPER'),('camper-b','CAMPER'),('founder','FOUNDER')]:
            connection.execute('INSERT INTO users VALUES(?,?,?,?,?)', (identity, identity, identity, role, 'test-only-no-login'))
    demo = DemoContext(mode='deterministic_demo', demo_today='2026-10-08')
    dataset = DatasetContext(dataset_version='independent-a09-tests', file_digests={'test-only':'a'*64}, rules_version='test-only')
    confirmed = ConfirmedContext(request_id='request-a09', confirmed_at=datetime.now(timezone.utc), requirements=ConfirmedRequirements(destination='Independent test area', start_date='2026-10-08', end_date='2026-10-10', duration_nights=2, duration_days=3, budget_cents=1000), profile_snapshot=ProfileSnapshot(group_size=2), demo_context=demo, dataset_context=dataset)
    Repository(db).record_confirmed_request(user, 'A-09 independent test fixture', confirmed)
    clock = [1000.0]
    service = WorkflowService(db, clock=lambda:clock[0], lease_seconds=60)
    return service, user, demo, dataset, clock


def start(fixture, key='start'):
    service, user, demo, dataset, _ = fixture
    return service.start(user, 'request-a09', demo, dataset, command_key=key)


def claim(fixture, scope):
    service, user, demo, dataset, _ = fixture
    attempt = service.claim(user, scope.run_id, demo, dataset)
    return attempt, service.port(user, attempt)


def revision(service, scope):
    with service.db.transaction(write=False) as connection:
        return connection.execute('SELECT revision FROM runs WHERE id=?', (scope.run_id,)).fetchone()[0]


def failure(port, stage='SAVING_VERSION', recoverable=True):
    return call(port.report_stage(stage, 'FAILED', ContractError(code='AGENT_FAILURE', message='Independent injected failure', recoverable=recoverable, allowed_actions=['RETRY'] if recoverable else [])))


def itinerary():
    return ItineraryResult(execution_mode='deterministic_demo', itinerary_entries=[{'entry_kind':'CAMP','start_at':'2026-10-08T12:00:00+11:00','end_at':'2026-10-10T12:00:00+11:00','campsite_id':'camp-test','description':'Independent A-09 fixture'}], selected_campsite_ids=['camp-test'], revision_reason='Test')


def append(port):
    return call(port.append_plan_version(port.scope.expected_current_version_id, itinerary(), port.scope.request_id, 'Test', port.scope.write_keys['version']))


def assert_error(code, action):
    with pytest.raises(ContractFailure) as error:
        action()
    assert error.value.error.code == code


def test_concurrent_start_is_one_plan_and_key_conflict(workflow):
    service, user, demo, dataset, _ = workflow
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:start(workflow), range(2)))
    assert results[0] == results[1]
    changed = dataset.model_copy(update={'rules_version':'changed'})
    assert_error('IDEMPOTENCY_CONFLICT', lambda:service.start(user,'request-a09',demo,changed,command_key='start'))
    with service.db.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM plans').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 1


def test_start_receipt_failure_rolls_back_everything(workflow):
    service, *_ = workflow
    with service.db.transaction() as connection:
        connection.execute("CREATE TRIGGER fail_command BEFORE INSERT ON workflow_commands BEGIN SELECT RAISE(ABORT,'test'); END")
    assert_error('PERSISTENCE_FAILURE', lambda:start(workflow))
    with service.db.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM plans').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0
        connection.execute('DROP TRIGGER fail_command')
    assert start(workflow).run_id


def test_two_workers_cannot_claim_same_run(workflow):
    scope = start(workflow)
    def try_claim(_):
        try:
            return claim(workflow,scope)[0]
        except ContractFailure as error:
            return error.error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(try_claim, range(2)))
    assert sum(isinstance(result,Attempt) for result in results) == 1
    assert 'INVALID_STATE' in results


def test_retry_reuses_version_and_checkpoints_across_restart(workflow):
    service, user, demo, dataset, clock = workflow
    scope = start(workflow); attempt, old = claim(workflow,scope)
    saved = append(old)
    assessment = call(old.save_assessment(saved.version_context,'LOGISTICS',logistics(saved.version_context),scope.write_keys['logistics']))
    failure(old,'ASSESSING_SAFETY')
    old_revision = revision(service,scope)
    again = service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=old_revision)
    assert again == scope
    assert service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=old_revision) == scope
    assert_error('IDEMPOTENCY_CONFLICT', lambda:service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=old_revision+1))
    assert_error('STALE_CONTEXT', lambda:call(old.load_confirmed_context()))
    assert_error('STALE_CONTEXT', lambda:failure(old,'ASSESSING_SAFETY'))
    restarted = WorkflowService(Database(service.db.path),clock=lambda:clock[0],lease_seconds=60)
    newer = restarted.claim(user,scope.run_id,demo,dataset)
    current = restarted.port(user,newer)
    checkpoint = call(current.load_checkpoint())
    assert checkpoint['version'].version_context == saved.version_context
    assert checkpoint['assessments'] == [assessment]
    assert checkpoint['stage'] == 'ASSESSING_SAFETY' and newer.generation > attempt.generation
    assert_error('STALE_CONTEXT', lambda:append(old))
    # Saved versions are read from checkpoint; identical resubmission returns its receipt.
    assert append(current) == saved
    call(current.save_assessment(saved.version_context,'SAFETY',safety(saved.version_context,assessment.assessment_id),scope.write_keys['safety']))
    call(current.report_stage('ROUTING','RUNNING',None))
    call(current.route_assessed_version(saved.version_context,'ELIGIBLE_FOR_FINALISATION','Test',scope.write_keys['route']))
    call(current.report_stage('COMPLETED','SUCCEEDED',None))
    assert PlanQueries(service.db).detail(user,scope.plan_id)['eligibility']['eligible']
    with service.db.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM assessments').fetchone()[0] == 2
        assert connection.execute('SELECT COUNT(*) FROM gear_checklists').fetchone()[0] == 1


def test_resume_after_route_needs_no_recomputed_outputs(workflow):
    service, user, demo, dataset, _ = workflow
    scope=start(workflow); _,port=claim(workflow,scope); saved=append(port)
    stored=call(port.save_assessment(saved.version_context,'LOGISTICS',logistics(saved.version_context),scope.write_keys['logistics']))
    call(port.save_assessment(saved.version_context,'SAFETY',safety(saved.version_context,stored.assessment_id),scope.write_keys['safety']))
    call(port.report_stage('ROUTING','RUNNING',None))
    route=call(port.route_assessed_version(saved.version_context,'ELIGIBLE_FOR_FINALISATION','Test',scope.write_keys['route']))
    failure(port,'ROUTING')
    service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=revision(service,scope))
    _, resumed=claim(workflow,scope)
    assert call(resumed.load_checkpoint())['route'] == route
    call(resumed.report_stage('COMPLETED','SUCCEEDED',None))
    assert PlanQueries(service.db).detail(user,scope.plan_id)['finalisation_available']


@pytest.mark.parametrize('change',['data','rules','clock','mode'])
def test_changed_evidence_or_execution_cannot_retry(workflow,change):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); _,port=claim(workflow,scope); failure(port)
    next_demo=demo.model_copy(update={'demo_today':demo.demo_today.replace(day=9)}) if change=='clock' else demo.model_copy(update={'mode':ExecutionMode.AGENT}) if change=='mode' else demo
    next_dataset=dataset.model_copy(update={'file_digests':{'test-only':'b'*64}}) if change=='data' else dataset.model_copy(update={'rules_version':'new-rule'}) if change=='rules' else dataset
    assert_error('STALE_CONTEXT',lambda:service.retry(user,scope.run_id,next_demo,next_dataset,command_key='retry',expected_run_revision=revision(service,scope)))
    with service.db.transaction(write=False) as connection:
        assert connection.execute('SELECT status FROM runs WHERE id=?',(scope.run_id,)).fetchone()[0]=='FAILED'


def test_expired_lease_cannot_write_and_explicit_recovery(workflow):
    service,user,demo,dataset,clock=workflow
    scope=start(workflow); attempt,port=claim(workflow,scope)
    assert_error('INVALID_STATE',lambda:service.expire(user,scope.run_id))
    clock[0]+=30; call(port.heartbeat()); clock[0]+=31
    saved=append(port)
    clock[0]+=30
    assert_error('STALE_CONTEXT',lambda:append(port))
    assert_error('STALE_CONTEXT',lambda:call(port.heartbeat()))
    assert_error('STALE_CONTEXT',lambda:failure(port))
    restarted=WorkflowService(Database(service.db.path),clock=lambda:clock[0],lease_seconds=60)
    restarted.expire(user,scope.run_id)
    restarted.retry(user,scope.run_id,demo,dataset,command_key='restart',expected_run_revision=revision(service,scope))
    next_attempt=restarted.claim(user,scope.run_id,demo,dataset)
    assert next_attempt.attempt_id != attempt.attempt_id
    assert restarted.checkpoint(user,next_attempt)['version'].version_context == saved.version_context


def test_retry_receipt_failure_restores_old_status_and_lease(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); attempt,port=claim(workflow,scope); failure(port)
    expected=revision(service,scope)
    with service.db.transaction() as connection:
        before=dict(connection.execute('SELECT * FROM run_leases').fetchone())
        event_count=connection.execute('SELECT COUNT(*) FROM run_events').fetchone()[0]
        connection.execute("CREATE TRIGGER fail_retry BEFORE INSERT ON workflow_commands WHEN NEW.operation='RETRY' BEGIN SELECT RAISE(ABORT,'test'); END")
    assert_error('PERSISTENCE_FAILURE',lambda:service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=expected))
    with service.db.transaction() as connection:
        assert dict(connection.execute('SELECT * FROM run_leases').fetchone())==before
        assert connection.execute('SELECT COUNT(*) FROM run_events').fetchone()[0]==event_count
        assert connection.execute('SELECT status,revision FROM runs').fetchone()[:]==('FAILED',expected)
        connection.execute('DROP TRIGGER fail_retry')
    service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=expected)
    assert_error('STALE_CONTEXT',lambda:service.checkpoint(user,attempt))


def test_save_failure_does_not_leave_partial_artifacts(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); _,port=claim(workflow,scope); saved=append(port)
    with service.db.transaction() as connection:
        connection.execute("CREATE TRIGGER fail_gear BEFORE INSERT ON gear_checklists BEGIN SELECT RAISE(ABORT,'test'); END")
    result=logistics(saved.version_context)
    assert_error('PERSISTENCE_FAILURE',lambda:call(port.save_assessment(saved.version_context,'LOGISTICS',result,scope.write_keys['logistics'])))
    with service.db.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM assessments').fetchone()[0]==0
        assert connection.execute("SELECT COUNT(*) FROM write_receipts WHERE operation='logistics'").fetchone()[0]==0
        connection.execute('DROP TRIGGER fail_gear')
    call(port.report_stage('ASSESSING_LOGISTICS','FAILED',ContractError(code='PERSISTENCE_FAILURE',message='Injected save failure',recoverable=True,allowed_actions=['RETRY'])))
    service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=revision(service,scope))
    _,current=claim(workflow,scope)
    assert call(current.load_checkpoint())['assessments']==[]
    assert call(current.save_assessment(saved.version_context,'LOGISTICS',result,scope.write_keys['logistics'])).assessment_id


def test_new_run_cas_fences_competing_reassessments(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); attempt,old=claim(workflow,scope); saved=append(old)
    changed=dataset.model_copy(update={'file_digests':{'test-only':'b'*64}})
    args=dict(plan_id=scope.plan_id,operation='REASSESS',expected_current_version_id=saved.version_context.plan_version_id,expected_active_run_id=scope.run_id)
    newer=service.start(user,scope.request_id,demo,changed,command_key='reassess',**args)
    assert newer.run_id!=scope.run_id
    assert service.start(user,scope.request_id,demo,changed,command_key='reassess',**args)==newer
    assert_error('STALE_CONTEXT',lambda:service.start(user,scope.request_id,demo,changed,command_key='competing',**args))
    assert_error('STALE_CONTEXT',lambda:call(old.report_stage('ASSESSING_LOGISTICS','RUNNING',None)))
    assert_error('STALE_CONTEXT',lambda:service.checkpoint(user,attempt))
    new_attempt=service.claim(user,newer.run_id,demo,changed)
    checkpoint=service.checkpoint(user,new_attempt)
    assert checkpoint['version'].version_context.input_fingerprint!=saved.version_context.input_fingerprint
    assert checkpoint['assessments']==[] and checkpoint['route'] is None


@pytest.mark.parametrize('other',[User('camper-b','b','B','CAMPER'),User('founder','f','F','FOUNDER')])
def test_execution_commands_and_checkpoint_do_not_cross_users(workflow,other):
    service,_,demo,dataset,_=workflow
    scope=start(workflow); attempt,_=claim(workflow,scope)
    expected='FORBIDDEN' if other.role=='FOUNDER' else 'NOT_FOUND'
    assert_error(expected,lambda:service.claim(other,scope.run_id,demo,dataset))
    assert_error(expected,lambda:service.retry(other,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=0))
    assert_error(expected,lambda:service.checkpoint(other,attempt))


def test_legacy_failure_is_fenced_before_new_claim(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); legacy=Repository(service.db).bind_port(user,scope.run_id)
    failure(legacy)
    service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=revision(service,scope))
    assert_error('STALE_CONTEXT',lambda:append(legacy))
    _,current=claim(workflow,scope)
    assert append(current).version_number==1


def test_unrecoverable_failure_and_wrong_revision_cannot_retry(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); _,port=claim(workflow,scope); failure(port,recoverable=False)
    expected=revision(service,scope)
    assert_error('VERSION_CONFLICT',lambda:service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=expected-1))
    assert_error('INVALID_STATE',lambda:service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=expected))
    assert_error('INPUT_INVALID',lambda:service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=True))


def test_pending_no_match_checkpoint_can_finish_after_retry(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); _,port=claim(workflow,scope)
    result=RecommendCampsitesResult(execution_mode='deterministic_demo',search_outcome='NO_MATCH',candidates=[],excluded_candidates=[],assumptions=['Independent A-09 fixture'],source_refs=[])
    stored=call(port.save_recommendations(result,scope.write_keys['recommendations']))
    failure(port,'RECOMMENDING')
    service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=revision(service,scope))
    _,resumed=claim(workflow,scope)
    checkpoint=call(resumed.load_checkpoint())
    assert checkpoint['recommendations']==stored and checkpoint['version'] is None
    call(resumed.report_stage('COMPLETED','SUCCEEDED',None))
    assert not PlanQueries(service.db).detail(user,scope.plan_id)['finalisation_available']


def test_upgrade_four_preserves_saved_input_and_initializes_recovery_tables(tmp_path):
    db=Database(tmp_path/'old-four.sqlite3')
    with db.transaction() as connection:
        for number,script in enumerate((MIGRATION_1,MIGRATION_2,MIGRATION_3,MIGRATION_4),1):
            execute_migration(connection,script)
            connection.execute('INSERT INTO schema_migrations VALUES(?,?)',(number,'test'))
        connection.execute("INSERT INTO users VALUES('camper-a','a','A','CAMPER','test-no-login')")
        connection.execute("INSERT INTO profiles VALUES('camper-a','profile-old','{}',1,'test')")
    db.initialize(); db.initialize()
    assert db.ready()
    with db.transaction(write=False) as connection:
        assert connection.execute('SELECT payload FROM profiles').fetchone()[0]=='{}'
        assert connection.execute('SELECT COUNT(*) FROM workflow_commands').fetchone()[0]==0
        assert connection.execute('SELECT COUNT(*) FROM run_leases').fetchone()[0]==0


def test_concurrent_retries_cannot_schedule_twice(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); _,port=claim(workflow,scope); failure(port)
    expected=revision(service,scope)
    def retry(key):
        try:
            return service.retry(user,scope.run_id,demo,dataset,command_key=key,expected_run_revision=expected)
        except ContractFailure as error:
            return error.error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(retry,['retry-a','retry-b']))
    assert sum(hasattr(result,'run_id') for result in results)==1
    assert 'VERSION_CONFLICT' in results
    with service.db.transaction(write=False) as connection:
        assert connection.execute("SELECT COUNT(*) FROM run_events WHERE status='PENDING'").fetchone()[0]==1


def test_claim_failure_rolls_back_lease_status_and_events(workflow):
    service,*_=workflow; scope=start(workflow)
    with service.db.transaction() as connection:
        connection.execute("CREATE TRIGGER fail_claim BEFORE UPDATE ON runs WHEN NEW.status='RUNNING' BEGIN SELECT RAISE(ABORT,'test'); END")
    assert_error('PERSISTENCE_FAILURE',lambda:claim(workflow,scope))
    with service.db.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM run_leases').fetchone()[0]==0
        assert connection.execute('SELECT COUNT(*) FROM run_events').fetchone()[0]==0
        assert connection.execute('SELECT status,revision FROM runs').fetchone()[:]==('PENDING',0)
        connection.execute('DROP TRIGGER fail_claim')
    assert claim(workflow,scope)[0].generation==1


def test_retry_rejects_corrupted_version_fingerprint(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); _,port=claim(workflow,scope); append(port); failure(port)
    with service.db.transaction() as connection:
        connection.execute('DROP TRIGGER immutable_run_binding')
        connection.execute("UPDATE run_versions SET fingerprint=?",('b'*64,))
    assert_error('STALE_CONTEXT',lambda:service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=revision(service,scope)))


def test_resumed_step_cannot_replace_saved_content_with_new_output(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); _,port=claim(workflow,scope); saved=append(port); failure(port)
    expected=revision(service,scope)
    service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=expected)
    _,resumed=claim(workflow,scope)
    altered=itinerary().model_copy(update={'revision_reason':'Different generated output'})
    assert_error('IDEMPOTENCY_CONFLICT',lambda:call(resumed.append_plan_version(None,altered,scope.request_id,'Test',scope.write_keys['version'])))
    assert call(resumed.load_checkpoint())['version'].version_context==saved.version_context
    failure(resumed)
    # A replay of the first retry receipt cannot silently reset a second failure.
    assert service.retry(user,scope.run_id,demo,dataset,command_key='retry',expected_run_revision=expected)==scope
    with service.db.transaction(write=False) as connection:
        assert connection.execute('SELECT status FROM runs').fetchone()[0]=='FAILED'


def test_changed_data_before_first_version_starts_new_run_in_same_plan(workflow):
    service,user,demo,dataset,_=workflow
    scope=start(workflow); _,old=claim(workflow,scope); failure(old,'GENERATING')
    changed=dataset.model_copy(update={'file_digests':{'test-only':'b'*64}})
    newer=service.start(user,scope.request_id,demo,changed,command_key='new-evidence',plan_id=scope.plan_id,expected_active_run_id=scope.run_id)
    assert newer.plan_id==scope.plan_id and newer.run_id!=scope.run_id
    assert_error('STALE_CONTEXT',lambda:service.retry(user,scope.run_id,demo,dataset,command_key='late-retry',expected_run_revision=revision(service,scope)))
    assert_error('STALE_CONTEXT',lambda:call(old.load_confirmed_context()))
    attempt=service.claim(user,newer.run_id,demo,changed)
    checkpoint=service.checkpoint(user,attempt)
    assert checkpoint['version'] is None and checkpoint['recommendations'] is None
    assert checkpoint['confirmed_context'].dataset_context==changed
    with service.db.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM plans').fetchone()[0]==1
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==2
