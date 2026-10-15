"""Read-only A coverage projection on B's actual 2.1 rules and source index."""
import hashlib
import json
import shutil

from fastapi.testclient import TestClient

from app.contracts.dto import ConfirmedContext
from test_plan_changes import change
from test_requests import sign_in
from test_trip_evidence_http import PACKAGE, app, launch, wait_run


def counts(application):
    with application.state.database.transaction(write=False) as connection:
        return [connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
            for table in ('runs','versions','assessments','final_records')]


def test_current_coverage_follows_revised_campsite_and_same_version_recheck(tmp_path):
    application = app(tmp_path, 'budget_revision')
    with TestClient(application) as client:
        headers = sign_in(client)
        original = wait_run(client, launch(client, headers, 'budget_revision'), 'SUCCEEDED')
        coverage = original['trip_evidence_coverage']
        assert coverage['dataset_version'] == '2.1.0' and not coverage['issues']
        assert coverage['checked_on'] == '2026-10-26'
        marker = 'Trip evidence selection digest: '+coverage['selection_digest']+'.'
        assert all(marker in value['result']['assumptions'] for value in original['assessments'])
        response = change(client, headers, original, 'revise', feedback='cheaper campsite')
        revised = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert revised['version']['content']['selected_campsite_ids'] == ['demo-moonlit-field']
        assert revised['trip_evidence_coverage']['selection_digest'] != coverage['selection_digest']
        assert not revised['trip_evidence_coverage']['issues']
        response = change(client, headers, revised, key='projection-recheck-123456')
        checked = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert checked['check_feedback']['comparison'] == 'UNCHANGED'
        assert checked['trip_evidence_coverage'] == revised['trip_evidence_coverage']
        before = counts(application)
        path = '/api/v1/plans/'+original['plan']['plan_id']
        assert client.get(path).json()['trip_evidence_coverage'] == checked['trip_evidence_coverage']
        assert client.get('/api/v1/runs/'+original['run']['run_id']).json()['trip_evidence_coverage'] is None
        sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert client.get(path).status_code == 404
        assert counts(application) == before


def test_boundary_gaps_remain_visible_without_fabricated_alternatives_or_approval(tmp_path):
    with TestClient(app(tmp_path, today='2026-11-29')) as client:
        headers = sign_in(client)
        detail = wait_run(client, launch(client, headers, start='2026-11-30'), 'SUCCEEDED')
        coverage = detail['trip_evidence_coverage']
        weather = next(item for item in coverage['issues'] if item['kind'] == 'WEATHER')
        assert weather['requested_range'] == {'start':'2026-11-30','end':'2026-12-02'}
        assert weather['uncovered_ranges'][-1]['end'] == '2026-12-02'
        assert not coverage['alternative_dates'] and not coverage['alternative_campsites']
        assert not detail['finalisation_available']


def test_optional_dates_are_individually_queried_and_never_saved_as_user_requirements(tmp_path):
    application = app(tmp_path)
    with TestClient(application) as client:
        headers = sign_in(client)
        detail = wait_run(client, launch(client, headers, start='2026-11-20'), 'SUCCEEDED')
        coverage = detail['trip_evidence_coverage']
        assert any(item['code'] == 'NOT_YET_OBSERVED' for item in coverage['issues'])
        assert 0 < len(coverage['alternative_dates']) <= 3
        confirmed = ConfirmedContext.model_validate(detail['confirmed_context'])
        snapshot = application.state.runtime.resolve()
        for candidate in coverage['alternative_dates']:
            raw = confirmed.requirements.model_dump()
            raw.update(candidate)
            proposed = type(confirmed.requirements).model_validate(raw)
            assert proposed.start_date >= snapshot.demo.demo_today
            assert proposed.duration_nights == confirmed.requirements.duration_nights
            selected = snapshot.agent.workflow_configuration.resolve_trip_evidence(proposed,
                detail['version']['content']['selected_campsite_ids'], snapshot.demo)
            assert not selected.coverage_issues
        reread = client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()
        assert reread['confirmed_context'] == detail['confirmed_context']
        assert reread['version']['content'] == detail['version']['content']
        assert not reread['finalisation_available']


def test_alternative_campsites_are_verified_without_switching_current_plan(tmp_path):
    package = tmp_path/'package'
    shutil.copytree(PACKAGE, package)
    manifest_path = package/'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    rows = json.loads((package/'data/runtime_safety_evidence.json').read_bytes())
    rows = [row for row in rows if not (row['campsite_id']=='demo-wattle-rest' and row['active_kinds']==['WEATHER'])]
    payload = (json.dumps(rows, sort_keys=True)+'\n').encode()
    for name in ('runtime_safety_evidence.json','synthetic_safety_scenarios.json'):
        (package/'data'/name).write_bytes(payload)
        manifest['files_sha256']['data/'+name] = hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    application = app(tmp_path, package=package)
    with TestClient(application) as client:
        headers = sign_in(client)
        detail = wait_run(client, launch(client, headers), 'SUCCEEDED')
        assert detail['version']['content']['selected_campsite_ids'] == ['demo-wattle-rest']
        alternatives = detail['trip_evidence_coverage']['alternative_campsites']
        assert 0 < len(alternatives) <= 3 and not detail['finalisation_available']
        confirmed = ConfirmedContext.model_validate(detail['confirmed_context'])
        snapshot = application.state.runtime.resolve()
        for candidate in alternatives:
            assert candidate['campsite_id'] != 'demo-wattle-rest'
            selection = snapshot.agent.workflow_configuration.resolve_trip_evidence(
                confirmed.requirements, [candidate['campsite_id']], snapshot.demo)
            assert not selection.coverage_issues
            assert not any(item.road_state=='CLOSED' for item in selection.scenario_context.evidence)
        before = counts(application)
        assert client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()['version'] == detail['version']
        assert counts(application) == before
    # Changing the source identity cannot enrich the old run with new facts.
    manifest['revision_date'] = '2026-10-16'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with TestClient(app(tmp_path, package=package)) as client:
        sign_in(client)
        read = client.get('/api/v1/plans/'+detail['plan']['plan_id']).json()
        assert read['current_inputs_state'] == 'CHANGED'
        assert read['trip_evidence_coverage'] is None


def test_complete_source_coverage_does_not_clear_known_road_closure(tmp_path):
    with TestClient(app(tmp_path, 'road_closure')) as client:
        detail = wait_run(client, launch(client, sign_in(client), 'road_closure'), 'SUCCEEDED')
        assert not detail['trip_evidence_coverage']['issues']
        assert not detail['trip_evidence_coverage']['alternative_campsites']
        safety = next(item['result'] for item in detail['assessments'] if item['kind']=='SAFETY')
        assert safety['outcome'] == 'BLOCKED'
        assert any(item['code']=='ROAD_CLOSED' for item in safety['mandatory_blockers'])
        assert not detail['finalisation_available']
