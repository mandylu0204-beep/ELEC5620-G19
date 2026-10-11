"""Apply the deterministic review fixes to this synthetic release copy."""
import csv
import json
from pathlib import Path
from release_files import seal_release

ROOT = Path(__file__).resolve().parents[1]


def load_json(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def save_json(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding='utf-8', newline='\n')


fixtures = load_json("tests/synthetic_test_fixtures.json")
fixtures = [item for item in fixtures if item.get("test_id") not in ("test-57", "test-58")]
by_id = {item["fixture_id"]: item for item in fixtures}

# A run has one immutable clock. The date at which safety is evaluated is not
# simulated by changing the clock partway through the same run.
success = by_id["fixture-test-34"]
success["demo_clock"] = "2026-11-06T08:00:00+11:00"
success["actions"] = [a for a in success["actions"] if a["action"] != "ADVANCE_DEMO_CLOCK"]

for fixture_id in ("fixture-test-43", "fixture-test-56"):
    fixture = by_id[fixture_id]
    plan = fixture["setup"]["plans"][0]
    plan["status"] = "AWAITING_REVIEW"
    plan["assessment_refs"] = ["assessment-gear", "assessment-logistics", "assessment-safety"]
    plan["review_refs"] = []
    plan["required_review"] = True
    fixture["actor"] = {"user_id": "founder-demo", "role": "FOUNDER", "authenticated": True}
    safety = next((a for a in fixture["setup"]["assessments"] if a["kind"] == "safety"), None)
    fixture["setup"]["assessments"] = [
        {"assessment_id": "assessment-gear", "plan_version_id": "plan-extra-v1", "kind": "gear",
         "outcome": "PASSED", "complete": True, "evidence_complete": True, "mandatory_blockers": []},
        {"assessment_id": "assessment-logistics", "plan_version_id": "plan-extra-v1", "kind": "logistics",
         "outcome": "PASSED", "complete": True, "evidence_complete": True, "mandatory_blockers": []},
    ]
    if fixture_id == "fixture-test-43":
        fixture["setup"]["assessments"].append(
            {"assessment_id": "assessment-safety", "plan_version_id": "plan-extra-v1", "kind": "safety",
             "outcome": "PASSED", "complete": True, "evidence_complete": True, "mandatory_blockers": []})
        plan["assessment_refs"] = ["assessment-gear", "assessment-logistics", "assessment-safety"]
        # The only remaining reason finalization cannot succeed is this blocker.
        plan["mandatory_blockers"] = ["campfire at no-fire site"]
        decision_reason = "All checks pass; mandatory no-fire blocker must still be enforced."
        key = "blocker-save"
    else:
        fixture["setup"]["assessments"].append(
            {"assessment_id": "missing-safety", "plan_version_id": "plan-extra-v1", "kind": "safety",
             "outcome": "REVIEW", "complete": False, "evidence_complete": False, "mandatory_blockers": []})
        plan["assessment_refs"] = ["assessment-gear", "assessment-logistics", "missing-safety"]
        decision_reason = "Safety evidence is incomplete; approval cannot manufacture evidence."
        key = "missing-save"
    # Each action has its own authenticated actor: founder review, then owner finalize.
    fixture["actions"] = [
        {"action": "REVIEW_PLAN", "actor": {"user_id": "founder-demo", "role": "FOUNDER", "authenticated": True},
         "parameters": {"plan_version_id": "plan-extra-v1", "decision": "APPROVE", "reason": decision_reason}},
        {"action": "FINALIZE_PLAN", "actor": {"user_id": "camper-a", "role": "CAMPER", "authenticated": True},
         "parameters": {"plan_version_id": "plan-extra-v1", "idempotency_key": key}},
    ]
    # A same-setup control removes only the target condition and should be eligible.
    control = json.loads(json.dumps(fixture))
    suffix = "57" if fixture_id.endswith("43") else "58"
    control.update(fixture_id=f"fixture-test-{suffix}", test_id=f"test-{suffix}",
                   notes="Paired control for test-" + fixture_id[-2:] + "; only the target blocker/evidence condition is resolved.")
    control["setup"]["plans"][0]["plan_version_id"] = f"plan-control-{suffix}"
    control["setup"]["plans"][0]["assessment_refs"] = [f"assessment-{suffix}-gear", f"assessment-{suffix}-logistics", f"assessment-{suffix}-safety"]
    control["setup"]["plans"][0]["mandatory_blockers"] = []
    control["setup"]["plans"][0]["review_refs"] = []
    control["setup"]["latest_version_id"] = f"plan-control-{suffix}"
    for assessment in control["setup"]["assessments"]:
        assessment["plan_version_id"] = f"plan-control-{suffix}"
        assessment["assessment_id"] = f"assessment-{suffix}-" + assessment["kind"]
        assessment.update(outcome="PASSED", complete=True, evidence_complete=True)
    control["setup"]["assessments"] = control["setup"]["assessments"]
    for action in control["actions"]:
        action["parameters"]["plan_version_id"] = f"plan-control-{suffix}"
    control["actions"][0]["parameters"]["reason"] = "All checks pass and the target condition is resolved."
    control["actions"][1]["parameters"]["idempotency_key"] = f"control-save-{suffix}"
    fixtures.append(control)

    if safety is not None:
        safety["evidence_complete"] = safety.get("evidence_complete", False)

save_json("tests/synthetic_test_fixtures.json", fixtures)

# Add action-level actor context to the fixture schema so role transitions are
# explicit and machine-checkable instead of implied by a single fixture actor.
schema = load_json("schemas/synthetic_test_fixtures.json")
action_schema = schema["items"]["properties"]["actions"]["items"]["properties"]
action_schema["actor"] = {
    "type": "object",
    "properties": {"user_id": {"type": "string"}, "role": {"type": "string"}, "authenticated": {"type": "boolean"}},
    "required": ["user_id", "role", "authenticated"], "additionalProperties": False,
}
save_json("schemas/synthetic_test_fixtures.json", schema)

# Add two paired-control acceptance specifications and their independent oracles.
with (ROOT / "tests/synthetic_agent_test_cases.csv").open(encoding='utf-8', newline="") as stream:
    reader = csv.DictReader(stream)
    fieldnames, rows = reader.fieldnames, list(reader)
rows = [row for row in rows if row["test_id"] not in ("test-57", "test-58")]
for target, control, title, request, campsite, assertion, oracle_note in [
    ("43", "57", "Resolved mandatory blocker permits eligible finalization", "request-01", "demo-ridge-lookout",
     {"result": "FINALIZED", "finalization_eligible": True, "final_record_count": 1}, "Paired control for test-43; blocker removed."),
    ("56", "58", "Resolved safety evidence permits eligible finalization", "request-01", "demo-pine-camp",
     {"result": "FINALIZED", "finalization_eligible": True, "final_record_count": 1, "evidence_complete": True}, "Paired control for test-56; safety evidence completed."),
]:
    source = next(row for row in rows if row["test_id"] == f"test-{target}")
    new_row = dict(source, test_id=f"test-{control}", title=title,
                   fixture_id=f"fixture-test-{control}", test_mode="INTEGRATION",
                   plan_version_id=f"plan-control-{control}",
                   preconditions=f"Reset store and load fixture-test-{control}; replay every action with the action-level actor.",
                   request_id=request, campsite_id=campsite, pass_criteria=json.dumps(assertion, ensure_ascii=False),
                   notes="Paired condition-resolved control; application execution pending.",
                   actor_user_id="founder-demo", actor_role="FOUNDER")
    rows.append(new_row)
for target, cause in [("43", "campfire at no-fire site"), ("56", "SAFETY_EVIDENCE_INCOMPLETE")]:
    row = next(row for row in rows if row["test_id"] == f"test-{target}")
    row["test_mode"] = "INTEGRATION"
    row["expected_outcome"] = "FINALISATION_BLOCKED"
    row["pass_criteria"] = json.dumps({"result": "FINALISATION_BLOCKED", "blocker_codes": [cause], "final_record_count": 0}, ensure_ascii=False)
    row["notes"] = "Founder approval followed by owner finalization; target blocker must remain explicit."
with (ROOT / "tests/synthetic_agent_test_cases.csv").open("w", encoding='utf-8', newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)

oracles = load_json("tests/synthetic_oracles.json")
oracles["test_oracles"] = [item for item in oracles["test_oracles"] if item["test_id"] not in ("test-57", "test-58")]
next(item for item in oracles["test_oracles"] if item["test_id"] == "test-43")["assertions"] = {
    "result": "FINALISATION_BLOCKED", "final_record_count": 0,
    "finalization_eligible": False, "blocker_codes": ["campfire at no-fire site"],
    "review_actor": "founder-demo", "finalize_actor": "camper-a",
}
next(item for item in oracles["test_oracles"] if item["test_id"] == "test-56")["assertions"] = {
    "result": "FINALISATION_BLOCKED", "final_record_count": 0,
    "finalization_eligible": False, "evidence_complete": False,
    "blocker_codes": ["SAFETY_EVIDENCE_INCOMPLETE"],
    "review_actor": "founder-demo", "finalize_actor": "camper-a",
}
for target, control, assertions in [
    ("43", "57", {"result": "FINALIZED", "finalization_eligible": True, "final_record_count": 1}),
    ("56", "58", {"result": "FINALIZED", "finalization_eligible": True, "final_record_count": 1, "evidence_complete": True}),
]:
    source = next(item for item in oracles["test_oracles"] if item["test_id"] == f"test-{target}")
    cloned = json.loads(json.dumps(source))
    cloned["test_id"] = f"test-{control}"
    cloned["assertions"] = assertions
    cloned["notes"] = f"Paired condition-resolved control for test-{target}."
    oracles["test_oracles"].append(cloned)
save_json("tests/synthetic_oracles.json", oracles)

oracle_schema = load_json("schemas/synthetic_oracles.json")
assertion_properties = oracle_schema["properties"]["test_oracles"]["items"]["properties"]["assertions"]["properties"]
assertion_properties.update({
    "blocker_codes": {"type": "array", "items": {"type": "string"}},
    "review_actor": {"type": "string"},
    "finalize_actor": {"type": "string"},
})
save_json("schemas/synthetic_oracles.json", oracle_schema)

# Canonicalise the meal enum everywhere in authored test content and guidance.
for name in ("tests/synthetic_test_fixtures.json", "docs/synthetic_data_dictionary.md"):
    path = ROOT / name
    path.write_text(path.read_text(encoding='utf-8').replace('"SIMPLE"', '"SELF_CATERED"').replace("SIMPLE 使用 cost-04", "SELF_CATERED 使用 cost-04"), encoding='utf-8', newline='\n')

# Re-seal registered release files, excluding caches; original-source hashes
# stay as provenance for the uploaded archive and are intentionally unchanged.
manifest = load_json("manifest.json")
manifest["counts"]["acceptance_specs"] = len(rows)
manifest["revision_date"] = "2026-10-11"
manifest["provenance"]["revision_date"] = "2026-10-11"
manifest["clock_policy"] = "Immutable clock per scenario run; scenario fixtures set it before startup. Host clock is never used."
save_json("manifest.json", manifest)
seal_release(ROOT)
