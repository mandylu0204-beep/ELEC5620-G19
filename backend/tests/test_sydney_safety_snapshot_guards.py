"""Additional 2.2 source/date guards, isolated fixtures and mocked model only."""
from datetime import date, timedelta
import hashlib
import json
import shutil

from fastapi.testclient import TestClient

from app.main import create_app
from audit_test_reads import json_with_internal_audits
from safety_runtime_fixtures import mock_safety_runtime, role_counts
from test_finalisation import command as final_command
from test_model_logistics_wiring import wrap_port
from test_plan_changes import change
from test_planning_entry import retry
from test_requests import sign_in
from test_rule_orchestration import FailOnce
from test_sydney_model_safety import ROOT, settings, begin, wait_run, assert_audit


def test_v22_closed_road_is_a_blocker_not_model_approval(tmp_path, monkeypatch):
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    package = tmp_path / 'explicit-offline-closure'
    shutil.copytree(ROOT / 'data/sydney_surrounds_v2_2', package)
    path = package / 'data/runtime_safety_evidence.json'
    rows = json.loads(path.read_bytes())
    changed = 0
    for row in rows:
        if row['campsite_id'] == 'little-beach' and 'ROAD' in row.get('active_kinds', []):
            row['road_access']['status'] = 'CLOSED'
            row['road_access']['summary'] = 'Explicit isolated offline road closure fixture, not a live finding.'
            changed += 1
    assert changed
    # Only this temporary test package is resealed, never shared data.
    payload = (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode()
    path.write_bytes(payload)
    manifest_path = package / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest['files_sha256']['data/runtime_safety_evidence.json'] = hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with TestClient(create_app(settings(tmp_path, dataset_path=package))) as client:
        headers = sign_in(client)
        detail = wait_run(client, begin(client, headers), 'SUCCEEDED')
        audit = assert_audit(detail)
        safe = next(x['result'] for x in detail['assessments'] if x['kind'] == 'SAFETY')
        assert safe['outcome'] == 'BLOCKED' and not detail['finalisation_available']
        assert any(x['code'] == 'ROAD_CLOSED' for x in safe['mandatory_blockers'])
        assert any(x['action_code'] == 'CHANGE_TRIP' for x in audit['plan']['findings'])
        response = client.post('/api/v1/plans/'+detail['plan']['plan_id']+'/finalise',
            headers=headers, json=final_command(detail))
        assert response.status_code == 409
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 3, 'SAFETY': 3}


def test_v3_midnight_recovery_pins_old_snapshot_then_reassessment_uses_new_one(tmp_path, monkeypatch):
    day = [date(2026, 10, 26)]
    monkeypatch.setattr('app.config.sydney_today', lambda: day[0])
    requests, control = mock_safety_runtime(monkeypatch)
    control['site'] = 'little-beach'
    used = []
    def once(port):
        if not used:
            used.append(True)
            return FailOnce(port, 'save_model_safety_assessment', after=True)
        return port
    wrap_port(monkeypatch, once)
    config = settings(tmp_path, daily=True, clock_mode='current')
    with TestClient(create_app(config)) as client:
        headers = sign_in(client)
        failed = wait_run(client, begin(client, headers), 'FAILED')
        audit, original_counts = assert_audit(failed), role_counts(requests)
        old_context = failed['confirmed_context']['dataset_context']
        day[0] += timedelta(days=1)
        current = json_with_internal_audits(client, client.get('/api/v1/runs/'+failed['run']['run_id']))
        assert current['retry_available'] and current['current_inputs_state'] == 'CHANGED'
        assert retry(client, headers, current).status_code == 202
        recovered = wait_run(client, failed['run']['run_id'], 'SUCCEEDED')
        assert recovered['model_assessment_audits']['SAFETY'] == audit
        assert recovered['confirmed_context']['dataset_context'] == old_context
        assert role_counts(requests) == original_counts and not recovered['finalisation_available']
        response = change(client, headers, recovered, key='v3-next-day-reassessment-command')
        assert response.status_code == 202, response.text
        new = wait_run(client, response.json()['run_id'], 'SUCCEEDED')
        assert_audit(new)
        assert new['confirmed_context']['demo_context']['demo_today'] == '2026-10-27'
        assert new['confirmed_context']['dataset_context'] != old_context
        assert new['version']['content'] == recovered['version']['content']
        assert new['model_planning_trace'] == recovered['model_planning_trace']
        assert role_counts(requests) == {'PLANNING': 2, 'LOGISTICS': 6, 'SAFETY': 6}
