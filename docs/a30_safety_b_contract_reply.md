# A30 safety advisory: B component and exact contract reply

Date: 2026-10-16, Australia/Sydney. Branch: `feature/llm-safety-agent`.
Base: main `8a40deb`, including A28/A29. Reply to A's user-supplied A30 draft.

**Status: component implemented; proposed v1 wire contract awaiting A agreement.**
This is not production safety-model integration or a live acceptance report.
Shared schema 1.0, existing factories, settings, Hybrid, Orchestrator, database,
personal configuration, sealed datasets and frontend are unchanged. No campus
inference calls, model probes or automatic messages were made for this component.
Commit and remote publication status follow Git records. Safety in the running
application still uses rules.

## S-01: API and ownership

Implemented standalone B methods in `backend/app/llm/safety_agent.py`:

```python
agent = SafetyAgent(dataset, client, workflow_configuration=final_configuration)
outcome = await agent.assess_safety_with_trace(saved_safety_input)
# SafetyOutcome(assessment: SafetyResult, plan: ValidatedSafetyPlan, trace: SafetyTrace)
agent.validate_safety_artifacts(saved_safety_input, result, raw_plan, raw_trace)
```

The result is the **complete original pure rule baseline**, not a relabeled or
augmented model judgment. Advice, priorities and independent SAFETY trace are
separate artifacts. There is no `last_trace` cache and no result-only method
that silently discards advice/audit data. Do not apply Hybrid's rule-step
annotation helper to the model outcome: that would change the exact baseline.

A's proposed `save_model_safety_assessment(context, result, plan, trace,
write_key)` is accepted as the intended boundary, but is NOT implemented or
called here. A owns migration, transaction, write receipt, ownership, attempt,
lease, dependency association, readers and finalisation guards. B will delegate
Hybrid and extend Orchestrator after that complete capability is available.
There is no independent production database, new checklist or shared AgentPort
change in this delivery.

## S-02: Exact keys, facts, schemas and actions

The committed machine-readable bundle is
[`contracts/safety_advisory_v1.schema.json`](contracts/safety_advisory_v1.schema.json).
Its `schemas` contains `action`, `proposal`, `validated_plan`, `trace`,
`finding_definition` and `identity_seed`. It matches
`app.llm.safety_contract.safety_contract_document()` exactly; a test detects
drift. Both the schemas **and versioned validators** are required for acceptance.

`SafetyProposal` has required `findings`, `action_priority`, and
`decision_summary_unverified`. Each choice contains `finding_key`,
`interpretation_unverified`, `action_code`, `action_unverified`. The model must
not provide sources or fact references. `ValidatedSafetyPlan` contains the same
top-level fields plus authoritative `source_refs`; each finding also receives
the exact tool-generated `fact_refs`. Proposal finding order is preserved and
is hashed; priority is a separate complete permutation. Extra, missing,
duplicate or invented findings/references/actions fail, never get repaired.

Canonical JSON: sorted object keys, compact separators, UTF-8, array order and
nulls retained, nonfinite values forbidden. Finding construction is exactly:

```python
finding_key = 'finding-' + sha256(canonical({
    'category': category, 'campsite_id': campsite_or_none, 'locator': locator,
}).encode('utf-8')).hexdigest()
```

Categories and locators:

| Category | Locator |
| --- | --- |
| STATUS | `/baseline` |
| EVIDENCE | `/checks/<RFC6901-escaped campsite ID>/<WEATHER or FIRE or ROAD or RESTRICTION>` |
| UNASSOCIATED_EVIDENCE | `/baseline/evidence/<original index>` |
| BLOCKER | `/baseline/mandatory_blockers/<original index>` |
| CONFLICT | `/baseline/unresolved_conflicts/<original index>` |
| UNCERTAINTY | `/baseline/uncertainties/<original index>` |
| HAZARD | `/baseline/hazards/<original index>` |
| LOGISTICS | `/input/saved_logistics_assessment/result` |

Pointer escaping replaces `~` with `~0`, then `/` with `~1`. References address
original DTO fields, not a reordered or model-authored fact array. The catalog
projects only referenced fields; it is not another evidence database. Array
occurrences stay distinct, including identical messages. Per-campsite checks
retain all matching evidence and source distinctions. A rule baseline may
already deduplicate identical hazard text; we do not pretend to recover lost
origins from that string, and retain separate source-specific campsite checks.
Unassociated baseline evidence receives additional findings rather than being
silently dropped. Keys are stable for the same canonical invocation, not an
assertion that an array index has permanent identity across changed baselines.

Every baseline blocker, conflict, uncertainty and hazard is covered; there are
four checks per actual campsite, plus one overall status and one logistics
dependency. STATUS references risk/confidence/outcome/review, baseline actions
and assumptions, confirmed requirements, clock and selection digest. LOGISTICS
references outcome, blockers, clarifications, transport, total and uncertainties.
No owner/plan/run/version/assessment IDs or API keys are sent in prompts.

Allowed-action policy:

| Finding | Allowed action(s) |
| --- | --- |
| Physical closure/prohibited-fire blocker | CHANGE_TRIP only |
| Evidence explicitly closing road/campsite | CHANGE_TRIP only |
| Conflicting evidence / conflict | RESOLVE_SOURCE_CONFLICT |
| Missing/stale/unobserved/unknown evidence | OBTAIN_APPLICABLE_INFORMATION; WEATHER may also CHECK_NEAR_DEPARTURE |
| Complete applicable evidence | ACKNOWLEDGE_INFORMATION or CHECK_NEAR_DEPARTURE |
| Unknown activity hazard | CONFIRM_ACTIVITY_DETAILS |
| Other hazards / required overall review | REQUEST_HUMAN_REVIEW |
| Other uncertainty | OBTAIN_APPLICABLE_INFORMATION or REQUEST_HUMAN_REVIEW |
| Logistics blocker/non-PASSED logistics | RESOLVE_LOGISTICS |
| Passed logistics / overall status without required review | ACKNOWLEDGE_INFORMATION |

All eight action literals in A's draft are retained. A fire-ban evidence check
can acknowledge a known restriction when no fire is requested; a separate
actual FIRE_PROHIBITED blocker still requires CHANGE_TRIP. Requesting a human
review in advice does not modify the official `requires_human_review` value.
Safety may independently PASSED while logistics remains REVISION; the latter
continues to prevent finalisation. Neither outcome is rewritten to conflate roles.

**Additional candidate restrictions requiring A confirmation:** advice uses no
numeric literals, control characters, URLs, HTML or code fences. This avoids
model-authored dates, quantities and thresholds; exact dates stay in structured
host facts/guidance. Selected false-clearance/instruction-injection phrases are
also rejected. These guards are intentionally conservative and are NOT proof
of English language, semantic truth, absence of all hallucinations or complete
prompt-injection resistance. English prompting, unverified labels and human
inspection remain necessary; number words can still express false claims.

## S-03: Pure replay and current-date data

Implemented pure entry point and version registry:

```python
from app.llm.safety_validation import safety_validator_for

validator = safety_validator_for(saved_seed['validation_version'])
plan, trace = validator(
    reconstructed_input, authoritative_baseline, supplied_result,
    raw_plan, raw_trace, identity=registered_identity,
    selection=authoritative_selection,
)
```

A must rebuild input from the saved authorized context/version/current-run
logistics, reconstruct the pinned snapshot and selection, and recompute the
baseline with `agents.rules.safety.assess(..., expected_mode=AGENT)`. Do NOT
trust a caller-provided baseline or an arbitrary identity. The pure helper
does not authenticate the owner or prove the dataset bytes were actually read.

It checks the complete result against the baseline, input/baseline hashes,
strict raw JSON round-trip equivalence, full identity and bounds, exact
deterministic proposal replay, canonical fact/source references and payload
size. The selection digest is recomputed from the registered policy/index,
confirmed query and complete selection; the baseline must carry that same
selection digest. All model text is still unverified.

The standalone component requires agent/2.1 with the existing selector; it
does not load a test scenario or consult the host clock. Daily mode's seven-day
window, next-check suggestion and staged-check flag follow A28's existing
registered date policy. Future daily `OUTSIDE_VALIDITY` and sealed
`NOT_YET_OBSERVED` remain different; neither becomes approval. The forecast
guidance is structured host output, not a model-generated date or promise.

Input and baseline digests use the original DTO `model_dump_json()` UTF-8
bytes. A must preserve/reconstruct that serialization for archival validation,
not substitute a differently sorted JSON string before hashing. Result/plan
semantic comparison uses canonical JSON; object ordering is immaterial, array
ordering remains material. No current key, current clock, files or network are
needed by the pure replay helper. Unknown historical validator versions fail
PERSISTENCE_FAILURE, nonrecoverable, CONTACT_OPERATOR.

## S-04: Bounds and complete-payload analysis

| Bound | Candidate v1 limit |
| --- | --- |
| Findings / priority | 1–64, exact unique coverage |
| Catalog entries | 512 |
| Fact references per finding | 1–32, unique, each at most 512 characters |
| Baseline evidence / plan source references | at most 128 each |
| Interpretation / action text | 1–600 nonblank characters each |
| Summary | 1–1200 nonblank characters |
| Complete proposal | 24 KiB encoded UTF-8 |
| Complete action | 32 KiB encoded UTF-8 |
| Read-facts projection | 32 KiB encoded UTF-8 |
| Original SafetyInput | 128 KiB encoded UTF-8 |
| Complete audit payload | 512 KiB encoded UTF-8 |
| Existing client request / response | unchanged 128 KiB / 256 KiB |

The complete payload is exactly canonical JSON of `{context, kind:'SAFETY',
result, plan, trace}`; `context` is the VersionContext. Its SHA256 can be derived
from this same envelope. No estimate is used in place of the final size check.

Let C be campsite count, U unassociated evidence, and B/F/N/H baseline
blocker/conflict/uncertainty/hazard counts. Findings = `4*C + U + B+F+N+H + 2`.
Even ten campsites require at least 42 findings, so only 22 additional entries
fit the count cap; arbitrary unknown activities can overflow it. Per-finding,
catalog, byte and source limits also apply independently. All facts are kept
or the invocation fails; there is no truncation, pagination or favorable subset.

Before inference the tool constructs every finding/ref and checks facts/input
bounds. It also reserves the global proposal budget plus 16 KiB for the strict
maximum trace on top of full result/context and a full-reference plan skeleton.
The tested worst trace fits that reservation. The final complete payload is
checked exactly. The existing client rejects oversized requests before HTTP.
Limits are NOT the unrestricted Cartesian product of every field's maximum.

Normal and maximum-supported fixtures are executable in
`backend/tests/safety_fixtures.py`: `safety_fixture()` and
`maximum_safety_fixture()`. The latter uses the real rule kernel and 57 explicit
unclassified itinerary segments, producing 64 findings and REVIEW; all findings
complete the offline three-turn loop. Additional synthetic tests reject the
65th finding and individually legal text fields exceeding the global byte cap.

**Offline structural support is not live token/latency support.** In particular,
64 full hash keys plus prose can exceed a real 4096-token completion. The mock
maximum does not prove any provider token setting can complete it. Do not
silently reduce findings or increase paid limits. Live readiness for the intended
fact count, output budget and latency remains an A/B freeze/acceptance item;
provider truncation fails rather than saving partial advice. Consider a later
separately versioned compact-key protocol if live limits make the current
64-finding wire form impractical.

Trace fields/bounds follow S-04 exactly: role SAFETY, 3–6 successful turns,
attempts between turns and turns*registered max_attempts (max three), first tool
read, at least one evaluation, tools length turns-1, one raw response digest
per successful turn, unique served model names and optional-by-key integer usage.
Missing usage stays missing. No raw messages/replies, credentials or reasoning
are included. Hashes alone do not prove real inference or the model weights.

## S-05: Identity composition

Implemented helpers `safety_identity_seed(dataset, public_client_identity)` and
`compose_safety_identity(seed, final_workflow_context)`. Seed fields match A's
seven proposed fields and strict schema. Seed has no context/fingerprint/key;
secret rotation does not alter it. The complete fingerprint hashes the seed
plus `workflow_context`. `reasoning_effort` is omitted when unset, not invented.

A should collect planning/logistics/safety identities from the common inspected
base, add all trusted role markers, build one final WorkflowConfiguration, then
instantiate/check both model roles against it. The four marker combinations are
tested at component identity level, not claimed as production factory acceptance.
Accept A's proposed marker names and once-only `/a-model-safety-audit-v1` suffix;
their registration remains A-owned and unimplemented here. Do not append safety
markers after constructing logistics or modify personal environment files.

## S-06 and S-07: Storage, checkpoints and recovery

Accept A's proposed separate safety audit, same-transaction assessment/audit/
receipt, kind SAFETY, null gear_checklist_id, exact saved logistics dependency,
scope safety write key, immutable associations and original successful attempt.
Accept `model_assessment_audits['SAFETY']` beside LOGISTICS with planning trace
kept separate. Current Orchestrator remains LOGISTICS-only: coordinated B/A
changes are still required before wiring, not just a relaxed dictionary check.

The expected audit key set must be derived from enabled model roles AND which
assessments are already saved. Before safety is saved, a required safety audit
must not be demanded; after save, missing/corrupt/swapped audit must fail closed.
This includes safety-only, logistics-only, both and neither, at checkpoint,
receipt, reads, review, route, completion, finalisation and historical finals.

Component malformed artifacts/unsupported bounds: CONTRACT_INVALID. Changed
snapshot/configuration identity: STALE_CONTEXT. Unknown archived validator:
PERSISTENCE_FAILURE, nonrecoverable. A must wrap corrupt saved artifacts as
nonrecoverable persistence failures at the storage/read boundary, and preserve
them through Dispatcher/Orchestrator, never add RETRY. A retains rollback RETRY,
same-key changed-payload IDEMPOTENCY_CONFLICT and lease/owner enforcement.

No production recovery has been implemented/tested for safety audits yet. A
reconstructs and reuses saved assessment/advice/trace after committed receipt
loss, never reruns a model to manufacture a missing audit. Hybrid/Orchestrator
will keep heartbeat during model waits after coordinated integration. Uncommitted
calls may repeat; exactly-once external inference/cost is not promised.

## S-08 and S-09: Activation and next joint delivery

Accept default `CAMPMATE_SAFETY_EXECUTION=rules` and explicit opt-in model mode
in supported agent/2.1 bindings only, but no setting/factory/meta/UI change is
made here. Readiness must be local and complete, with no billable probe. The
rules/model logistics combinations both need production tests. NO_MATCH must
skip downstream safety calls. Old rule histories acquire neither an audit
requirement nor a model label.

UI must retain official checks/coverage, independently render prioritized model
advice/supporting facts as plain text, label it unverified, collapse technical
trace and never turn completed checks into an approval. English code/schema/
prompt/example content is provided; display translations remain A-owned.

Suggested next sequence:

1. A reviews the exact schema/helper API, additional text/byte limits and live
   token caveat; freeze or revise them before storage assumptions are committed.
2. A implements the complete safety port, archive validation/readers, common
   identity registration, migration and flag on a shared integration branch.
3. B integrates Hybrid and Orchestrator there, including all audit-role sets,
   heartbeat, lost-receipt reuse and nonrecoverable integrity failures.
4. Joint offline HTTP/SQLite/factory/UI tests and schema/frontend checks.
5. Only with user-approved limits: bounded real-campus safety/browser acceptance.
   A29 is planning/logistics evidence, not safety-model acceptance. No automatic
   repeat of old paid tests; the new role must get its own small initial sample.

## S-10: Verification and remaining acceptance

New component tests cover exact baseline, real structured action/priority
choices, future-window/missing/stale/conflict/high-risk, road/campsite/fire
blockers, unknown activities and logistics, source distinction, strict JSON/
types/references, old-evaluation final mismatch, identity/selection drift,
secret-free seeds, limits, maximum facts, sanitized errors and pure replay.
Recorded results and fixture byte sizes are in
[`evidence/a30-safety-component-check.json`](evidence/a30-safety-component-check.json).

Final local verification: **1001 backend passed, 0 failed, 0 skipped** (312.12s),
including all 76 new tests; one existing Starlette TestClient/httpx warning.
Frontend 7 tests, TypeScript/Vite build, shared schema 1.0 check, exact internal
schema export and pip dependency check passed. A final agent module docstring
clarification changes no executable code or prompt identity. No live-model
token/latency result is inferred from these offline checks.

Explicitly NOT delivered/accepted: production SafetyOutcome saving, migration,
all-four-combination HTTP readiness, checkpoint/rollback/lost-receipt safety
recovery, old database safety migration/history, finalisation and permission
integration, UI, live safety inference, midnight live transition or Canvas ZIP.
Existing application tests are regression evidence, not substitutes for these
new safety-model acceptance items. This contract remains pending A confirmation.
