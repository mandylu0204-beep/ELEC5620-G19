"""Independent storage fixtures, not demo dataset repairs or B Agent outputs."""
import asyncio
from datetime import date, datetime, timezone

import pytest

from app.auth import AuthService, User
from app.contracts.dto import (
    ConfirmedContext, ConfirmedRequirements, DatasetContext, DemoContext, ItineraryResult,
    LogisticsResult, ProfileSnapshot, SafetyResult,
)
from app.contracts.enums import AssessmentKind, ErrorCode, PlanVersionStatus
from app.contracts.errors import ContractFailure
from app.contracts.ports import PersistencePort
from app.storage.database import Database
from app.storage.repository import Repository, encode


def call(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def stored(tmp_path):
    db = Database(tmp_path / 'storage.sqlite3')
    db.initialize()
    AuthService(db, 8).seed_demo_accounts()
    user = User('camper-a', 'camper.a', 'Camper A', 'CAMPER')
    repo = Repository(db)
    demo = DemoContext(mode='deterministic_demo', demo_today=date(2026, 10, 8))
    dataset = DatasetContext(dataset_version='independent-storage-test', file_digests={'test-fixture': 'a' * 64}, rules_version='test-only')
    confirmed = ConfirmedContext(request_id='request-test', confirmed_at=datetime.now(timezone.utc), requirements=ConfirmedRequirements(destination='Test Region', start_date='2026-10-08', duration_nights=2, duration_days=3, end_date='2026-10-10', budget_cents=1000), profile_snapshot=ProfileSnapshot(group_size=2), demo_context=demo, dataset_context=dataset)
    repo.record_confirmed_request(user, 'Explicit storage test input', confirmed)
    scope = repo.begin_run(user, confirmed.request_id, demo, dataset)
    port = repo.bind_port(user, scope.run_id)
    assert isinstance(port, PersistencePort)
    itinerary = ItineraryResult(execution_mode='deterministic_demo', itinerary_entries=[{'entry_kind': 'CAMP', 'start_at': '2026-10-08T12:00:00+11:00', 'end_at': '2026-10-10T12:00:00+11:00', 'campsite_id': 'camp-test', 'description': 'Independent storage fixture'}], selected_campsite_ids=['camp-test'], revision_reason='Initial fixture')
    version = call(port.append_plan_version(None, itinerary, confirmed.request_id, 'Test', scope.write_keys['version']))
    return db, repo, user, scope, port, version, itinerary


def logistics(context):
    return LogisticsResult(execution_mode='deterministic_demo', version_context=context,
        gear_checklist=[{'item_key': 'tent', 'required_quantity': '2', 'available_quantity': '2', 'missing_quantity': '0', 'unit': 'persons', 'arrangement_status': 'OWNED', 'essential': True}],
        transport_feasible=True, cost_breakdown=[{'category': kind, 'item_key': kind, 'quantity': '1', 'unit': 'test', 'unit_price_cents': 100, 'subtotal_cents': 100, 'source_ref': None} for kind in ('CAMPSITE','TRANSPORT','FOOD','WATER','ADDITIONAL_GEAR')],
        total_cents=500, known_subtotal_cents=500, budget_difference_cents=-500, outcome='PASSED')


def safety(context, dependency, *, closed=False):
    return SafetyResult(execution_mode='deterministic_demo', version_context=context, depends_on_assessment_id=dependency,
        risk_level='LOW', confidence='HIGH', data_quality={kind: 'AVAILABLE' for kind in ('WEATHER','FIRE','ROAD','RESTRICTION')},
        evidence=[{'kind': kind, 'summary': 'Independent fixture evidence', 'source_date': '2026-10-07', 'status': 'AVAILABLE', 'valid_from': '2026-10-08', 'valid_to': '2026-10-10', 'road_state': ('CLOSED' if closed else 'OPEN') if kind == 'ROAD' else None, 'source_refs': [{'dataset_file': 'test-only.json', 'record_id': 'camp-test'}]} for kind in ('WEATHER','FIRE','ROAD','RESTRICTION')],
        hazards=[], mandatory_blockers=[], recommended_actions=[], outcome='PASSED', requires_human_review=False)


def test_version_idempotency_atomic_failure_and_retry(stored):
    db, repo, user, scope, port, version, itinerary = stored
    again = call(port.append_plan_version(None, itinerary, scope.request_id, 'Test', scope.write_keys['version']))
    assert again == version
    with pytest.raises(ContractFailure) as conflict:
        call(port.append_plan_version(None, itinerary, scope.request_id, 'Different reason', scope.write_keys['version']))
    assert conflict.value.error.code == ErrorCode.IDEMPOTENCY_CONFLICT
    with db.transaction() as connection:
        connection.execute("CREATE TRIGGER fail_checklist BEFORE INSERT ON gear_checklists BEGIN SELECT RAISE(ABORT,'Injected storage failure'); END")
    result = logistics(version.version_context)
    with pytest.raises(ContractFailure) as failure:
        call(port.save_assessment(version.version_context, AssessmentKind.LOGISTICS, result, scope.write_keys['logistics']))
    assert failure.value.error.code == ErrorCode.PERSISTENCE_FAILURE
    with db.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM assessments').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM gear_checklists').fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM write_receipts WHERE operation='logistics'").fetchone()[0] == 0
        connection.execute('DROP TRIGGER fail_checklist')
    saved = call(port.save_assessment(version.version_context, AssessmentKind.LOGISTICS, result, scope.write_keys['logistics']))
    assert saved.gear_checklist_id
    assert call(port.save_assessment(version.version_context, AssessmentKind.LOGISTICS, result, scope.write_keys['logistics'])) == saved


def test_snapshots_restart_history_and_stale_tasks(stored):
    db, repo, user, scope, port, version, itinerary = stored
    profile = repo.save_profile(user, ProfileSnapshot(group_size=2), 0)
    repo.save_profile(user, ProfileSnapshot(group_size=8), profile['revision'])
    assert call(port.load_confirmed_context()).profile_snapshot.group_size == 2
    new_scope = repo.begin_run(user, scope.request_id, scope.demo_context, scope.dataset_context, plan_id=scope.plan_id, operation='REVISE', expected_current_version_id=version.version_context.plan_version_id)
    new_port = repo.bind_port(user, new_scope.run_id)
    new_content = itinerary.model_copy(update={'revision_reason': 'Second immutable version'})
    new_version = call(new_port.append_plan_version(version.version_context.plan_version_id, new_content, scope.request_id, 'Revision', new_scope.write_keys['version']))
    assert new_version.version_number == 2
    with pytest.raises(ContractFailure) as stale:
        call(port.save_assessment(version.version_context, AssessmentKind.LOGISTICS, logistics(version.version_context), scope.write_keys['logistics']))
    assert stale.value.error.code == ErrorCode.STALE_CONTEXT
    restarted_db = Database(db.path)
    restarted_db.initialize()
    restarted = Repository(restarted_db)
    history = restarted.history(user, scope.plan_id)
    assert len(history) == 2
    assert history[0]['content']['revision_reason'] == itinerary.revision_reason
    assert history[1]['content']['revision_reason'] == 'Second immutable version'
    for other in (User('camper-b','camper.b','Camper B','CAMPER'),):
        with pytest.raises(ContractFailure) as denied:
            restarted.history(other, scope.plan_id)
        assert denied.value.error.code == ErrorCode.NOT_FOUND
    with pytest.raises(ContractFailure):
        with db.transaction() as connection:
            connection.execute("UPDATE versions SET content='{}' WHERE id=?", (version.version_context.plan_version_id,))


def test_run_context_fingerprint_and_old_approval_are_not_reused(stored):
    db, repo, user, scope, port, version, itinerary = stored
    first = call(port.save_assessment(version.version_context, AssessmentKind.LOGISTICS, logistics(version.version_context), scope.write_keys['logistics']))
    second = call(port.save_assessment(version.version_context, AssessmentKind.SAFETY, safety(version.version_context, first.assessment_id), scope.write_keys['safety']))
    review = {'review_id':'review-test', 'version_context':version.version_context.model_dump(mode='json'), 'assessment_ids':[first.assessment_id, second.assessment_id], 'reviewer_user_id':'founder', 'decision':'APPROVE', 'reason':'Independent test approval'}
    with db.transaction() as connection:
        connection.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?)', ('review-test', scope.run_id, version.version_context.plan_version_id, 'founder', encode(review), '2026-10-09T00:00:00Z'))
    assert call(port.load_review_result(version.version_context, review['assessment_ids'])) is not None
    changed = scope.dataset_context.model_copy(update={'file_digests': {'test-fixture': 'b' * 64}})
    new_scope = repo.begin_run(user, scope.request_id, scope.demo_context, changed, plan_id=scope.plan_id, operation='REASSESS', expected_current_version_id=version.version_context.plan_version_id)
    new_port = repo.bind_port(user, new_scope.run_id)
    with db.transaction(write=False) as connection:
        new_version = Repository.stored_version(connection, new_scope)
    assert new_version.version_context.input_fingerprint != version.version_context.input_fingerprint
    assert new_version.content == version.content
    assert call(new_port.load_review_result(new_version.version_context, review['assessment_ids'])) is None
    assert call(new_port.evaluate_eligibility(new_version.version_context)).eligible is False


@pytest.mark.parametrize('closed', [False, True])
def test_route_guards_road_closure_and_never_finalises(stored, closed):
    db, repo, user, scope, port, version, itinerary = stored
    context = version.version_context
    call(port.report_stage('ASSESSING_LOGISTICS', 'RUNNING', None))
    first = call(port.save_assessment(context, AssessmentKind.LOGISTICS, logistics(context), scope.write_keys['logistics']))
    call(port.report_stage('ASSESSING_SAFETY', 'RUNNING', None))
    call(port.save_assessment(context, AssessmentKind.SAFETY, safety(context, first.assessment_id, closed=closed), scope.write_keys['safety']))
    with pytest.raises(ContractFailure):
        call(port.route_assessed_version(context, 'FINALISED', 'Forbidden', scope.write_keys['route']))
    routed = call(port.route_assessed_version(context, 'ELIGIBLE_FOR_FINALISATION', 'Test', scope.write_keys['route']))
    assert routed.status == (PlanVersionStatus.BLOCKED if closed else PlanVersionStatus.ELIGIBLE_FOR_FINALISATION)
    assert not routed.eligibility.eligible  # Run has not yet ended.
    call(port.report_stage('COMPLETED', 'SUCCEEDED', None))
    eligible = call(port.evaluate_eligibility(context))
    assert eligible.eligible is not closed
    with pytest.raises(ContractFailure):
        call(port.report_stage('GENERATING', 'RUNNING', None))
    with db.transaction(write=False) as connection:
        assert connection.execute('SELECT COUNT(*) FROM final_records').fetchone()[0] == 0
        assert connection.execute('SELECT final_version_id FROM plans').fetchone()[0] is None


def test_plan_pointers_cannot_reference_another_plan(stored):
    db, repo, user, scope, port, version, itinerary = stored
    other = repo.begin_run(user, scope.request_id, scope.demo_context, scope.dataset_context)
    other_port = repo.bind_port(user, other.run_id)
    other_version = call(other_port.append_plan_version(None, itinerary, scope.request_id, 'Test', other.write_keys['version']))
    with pytest.raises(ContractFailure) as failure:
        with db.transaction() as connection:
            connection.execute('UPDATE plans SET current_version_id=? WHERE id=?', (other_version.version_context.plan_version_id, scope.plan_id))
    assert failure.value.error.code == ErrorCode.PERSISTENCE_FAILURE
    with pytest.raises(ContractFailure):
        with db.transaction() as connection:
            connection.execute('UPDATE run_versions SET version_id=? WHERE run_id=?', (other_version.version_context.plan_version_id, scope.run_id))


@pytest.mark.parametrize('proposed', ['BLOCKED','REVISION_REQUIRED','ESCALATED'])
def test_stricter_agent_route_stays_ineligible(stored, proposed):
    db, repo, user, scope, port, version, itinerary = stored
    context = version.version_context
    first = call(port.save_assessment(context, AssessmentKind.LOGISTICS, logistics(context), scope.write_keys['logistics']))
    call(port.save_assessment(context, AssessmentKind.SAFETY, safety(context, first.assessment_id), scope.write_keys['safety']))
    call(port.route_assessed_version(context, proposed, 'Stricter B route', scope.write_keys['route']))
    call(port.report_stage('COMPLETED', 'SUCCEEDED', None))
    assert call(port.evaluate_eligibility(context)).eligible is False


def test_missing_evidence_cannot_be_overridden_by_approval(stored):
    db, repo, user, scope, port, version, itinerary = stored
    context = version.version_context
    first = call(port.save_assessment(context, AssessmentKind.LOGISTICS, logistics(context), scope.write_keys['logistics']))
    original = safety(context, first.assessment_id)
    missing = SafetyResult.model_validate(original.model_dump(mode='json') | {'data_quality': {'WEATHER':'MISSING'}, 'evidence':[], 'outcome':'REVIEW', 'requires_human_review':True})
    second = call(port.save_assessment(context, AssessmentKind.SAFETY, missing, scope.write_keys['safety']))
    review = {'review_id':'forced-approval-test', 'version_context':context.model_dump(mode='json'), 'assessment_ids':[first.assessment_id, second.assessment_id], 'reviewer_user_id':'founder', 'decision':'APPROVE', 'reason':'Injection test; no real approval endpoint'}
    with db.transaction() as connection:
        connection.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?)', ('forced-approval-test', scope.run_id, context.plan_version_id, 'founder', encode(review), '2026-10-09T00:00:00Z'))
    routed = call(port.route_assessed_version(context, 'ELIGIBLE_FOR_FINALISATION', 'Injected approval cannot override', scope.write_keys['route']))
    assert routed.status == PlanVersionStatus.BLOCKED
    call(port.report_stage('COMPLETED', 'SUCCEEDED', None))
    assert not call(port.evaluate_eligibility(context)).eligible
