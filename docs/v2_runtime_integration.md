# v2 runtime integration handoff

The v2 adapter consumes the sealed package's six business files, both runtime JSON files, and manifest. Every consumed byte digest is checked against A's inspected DatasetContext and the manifest. It does not read tests/oracles or execute package scripts. A's file/fixture digests, selection configuration, normalization identity and A13 revision feedback are preserved; B appends adapter/rule identities. Default stub/v1 settings and personal .env are unchanged; invalid v2 never falls back to v1.

Safety freshness uses observed_at; source_date remains provenance. Gear/cost expressions use the sealed JSON DSL. Money stays integer cents/Decimal. Unknown expression inputs are clarification items, not zero.

## Locked environment and schema

Use Python 3.12 and install backend/requirements.lock, not an unconstrained editable install. This run used an isolated environment: Pydantic 2.13.5 and pydantic-core 2.46.5. The existing personal backend/.venv was not changed.

Pydantic 2.14.1 generated a different decimal-string schema. Regeneration under the lock restored the canonical schema; docs/contracts.schema.json now has no diff from main. No DTO or contract version change was required.

Reproduce from backend with a separate environment (the following creates a new directory; do not replace an existing personal environment):

```sh
python3.12 -m venv .venv-locked
.venv-locked/bin/python -m pip install -r requirements.lock
.venv-locked/bin/python -m pip install --no-deps -e .
.venv-locked/bin/python -m pip check
.venv-locked/bin/python -m app.export_contracts --check
.venv-locked/bin/python -m pytest --basetemp ../var/pytest-v2-verification
```

If intentionally regenerating contracts, use this same locked interpreter for app.export_contracts before checking the diff. Do not accept dependency-induced schema drift.

## Four executable demo inputs

docs/demo/v2_inputs.json contains one explicitly confirmed synthetic profile and four independent cases: process settings, request raw text/explicit fields, and revision feedback where applicable. It contains no expected outcomes, forced candidate lists, saved IDs, or oracle-derived business inputs. The profile is demo input, not a default user profile.

The real RuleAgent automatically ranks/selects the following campsites. No campsite-selection API is simulated.

| Case | Fixed clock; trip (two nights) | Requirements and evidence | Actual HTTP result |
| --- | --- | --- | --- |
| normal | 2026-11-05; Nov 6–8 | AUD 320, quiet, ready-to-eat; safety-15 | Wattle Rest; AUD 251; both assessments pass; Camper finalises and reads SQLite snapshot. |
| budget_revision | 2026-10-26; Oct 27–29 | AUD 245, quiet, ready-to-eat; safety-16 and safety-17 | Wattle Rest AUD 251 exceeds budget; cheaper campsite feedback automatically selects Moonlit Field AUD 231, passing both assessments and finalisation. |
| missing_evidence | 2026-10-20; Oct 21–23 | AUD 320, ready-to-eat, mandatory showers; safety-02 | River Flat AUD 241; weather remains MISSING and safety REVIEW; Founder approval and Camper finalisation cannot bypass the incomplete evidence. |
| road_closure | 2027-04-09; Apr 10–12 | AUD 320, ready-to-eat; safety-18 | Moonlit Field AUD 231; logistics passes, safety BLOCKED on ROAD_CLOSED; approval/finalisation rejected. |

To demonstrate manually, select exactly one case and launch an isolated application/database using that case's settings (environment prefix CAMPMATE_, JSON encoding for list/dict settings, dataset path relative to repository root). Do not change the fixed clock during a run or mix cases' safety IDs. Keep local .env unchanged; use explicit process environment overrides. Then log in as Camper, PUT /api/v1/profile using the shared profile, POST /api/v1/requests using case.request, interpret, explicitly confirm, and start /plan. For the budget case, submit case.revision_feedback at /plans/{plan_id}/revise with the actual current revisions and a new command key.

The HTTP tests implement those steps through create_app, TestClient, the real dispatcher/RuleAgent and an isolated SQLite database; all artifact IDs come from saved application responses. Tests never manufacture ConfirmedContext, versions, assessments or recommendation candidates.

## Revision, reassessment and recovery

backend/tests/test_v2_http_demo.py additionally verifies:

- A13 a_revision_feedback and B revision_feedback are identical in the saved REVISE context.
- REASSESS reuses the saved itinerary, creates a new run/assessment IDs, and clears revision feedback. The prior final snapshot remains unchanged and historical.
- A recoverable failure after append_plan_version has already saved the revised itinerary can be retried. The saved version ID and exact content are reused; an instrumented real generation method proves retry does not regenerate the itinerary or create another version.
- REVISE and REASSESS use distinct command keys. Reusing one key across different operations correctly produces IDEMPOTENCY_CONFLICT.

backend/tests/test_synthetic_dataset_v2.py retains adapter hash/identity and changed-byte rejection tests. The previous manually selected component scenarios were replaced by actual HTTP demo coverage.

## Data publication

Added synthetic safety-15..18 to match automatically selected sites and dates, retaining all existing campsite/ranking data and previous scenario records. runtime_safety_evidence is generated by the same allowlist as the business records. Expected results remain isolated in synthetic_oracles. Counts, README, changelog and checksums are synchronized.

The package's independent static success fixture still uses Pine Camp/AUD 261; it is not the normal HTTP demo. Do not change that oracle just to match the new HTTP example.

## Verification run (2026-10-12)

- Backend: 486 passed, no skips/failures, Python 3.12 and backend/requirements.lock; includes all seven sealed-release regression tests.
- Focused v2 adapter/HTTP tests: 7 passed (four scenarios plus budget reassessment and saved-version retry).
- Shared JSON Schema: app.export_contracts --check passed; generated schema matches main.
- Dependency consistency: pip check passed.
- Static package checks: 68 passed, 0 failed; 31 registered release files sealed.
- The package validator's 58 acceptance specifications remain NOT_RUN. This static status is not a claim that all 58 were executed; HTTP evidence is recorded separately here.
- Frontend: package-lock installation, TypeScript build and Vite production build passed with Node 24.19.0/npm 11.21.0. CI uses Node 22; remote CI has not been run by this local check.
- git diff --check passed.
- One existing Starlette test-client deprecation warning remains; no dependency was upgraded to suppress it.

B's four backend HTTP scenarios, revision/reassessment and recovery now pass; no new A backend prerequisite is needed for these paths. A should next review/merge this branch and verify browser UI, fresh install and final submission/demo integration. LLM mode, remote CI, browser/Canvas acceptance and execution of every package acceptance specification are not claimed complete.
