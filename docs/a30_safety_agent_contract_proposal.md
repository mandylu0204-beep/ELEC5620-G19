# A30: Safety model contract proposal for B

Date: 2026-10-16, Australia/Sydney. Reviewed baseline: main `8a40deb`,
including A28 `fb8c8ce` and A29 live acceptance evidence.

Status: **DRAFT for A/B agreement. Documentation only.** None of the methods,
flags, safety audit records or model capabilities proposed here is implemented
by this document. Current safety execution remains deterministic rules.
No new campus calls, migration or application changes were performed here.

## Existing implementation and proposed first release

The three business roles are Planning Coordinator, Gear and Logistics Manager,
and Safety and Compliance Officer. Planning and logistics have real-model paths;
`HybridPlanningAgent.assess_safety()` currently calls `agents/rules/safety.py`.
The existing `SafetyInput` already binds the saved itinerary, requirements,
current VersionContext, saved logistics assessment, selected scenario and clock.

The first model safety release should be a grounded advisory agent: read the
verified safety facts, interpret their implications for this trip, prioritise
what needs attention and propose actions through controlled tools. Its output
must not merely be a model label pasted onto a rules result. A saved structured
advisory and independent model trace are required.

The official SafetyResult remains exactly the deterministic baseline in this
first release. The model cannot upgrade or downgrade risk, confidence, quality,
outcome, blockers, review requirements or source facts. An unclassified activity
remains unresolved and subject to the existing review rule; model prose does
not turn it into a supported safe activity. Adding new model-driven risk
decisions later requires a separate contract and validation design.

## S-01: Internal methods and persistence boundary

Keep shared AgentPort and JSON schema 1.0 unchanged. Proposed B-owned extension:

```python
async def assess_safety_with_trace(input: SafetyInput) -> SafetyOutcome: ...

# Pure local validation; raises ContractFailure on mismatch.
def validate_safety_artifacts(input, result, plan, trace): ...
```

`SafetyOutcome` contains `assessment: SafetyResult`, `plan: ValidatedSafetyPlan`
and `trace: SafetyTrace`. No global last_trace or shared mutable result slot.

Proposed A-owned RecoveryPort capability:

```python
async def save_model_safety_assessment(
    self,
    context: VersionContext,
    result: SafetyResult,
    plan: Mapping[str, object],
    trace: Mapping[str, object],
    write_key: str,
) -> StoredAssessment: ...
```

The port fixes kind=SAFETY and uses `scope.write_keys['safety']`. It requires
the current claimed attempt, valid lease, owner, active scope and exact saved
version. It independently verifies `depends_on_assessment_id` against the saved
LOGISTICS assessment from the same run and version. There is no new gear
checklist; StoredAssessment.gear_checklist_id stays null. Model-required safety
cannot bypass the new port through ordinary `save_assessment`.

## S-02: Read-only tools and structured advice

Proposed tools: `read_safety_facts` and `evaluate_safety_plan`, followed by a
final proposal identical to the last successfully evaluated proposal. At least
one read and one evaluation are required; no network, database write, evidence
creation, permission grant or automatic itinerary modification tool is exposed.

B supplies a deterministic SafetyToolset and a complete strict schema before
freeze. The proposed plan contains these required fields:

| Field | Proposed type and meaning |
| --- | --- |
| `findings` | 1–64 entries covering every canonical baseline finding exactly once |
| `action_priority` | Ordered list of every finding key exactly once |
| `decision_summary_unverified` | Nonblank English model explanation, 1–1200 characters |
| `source_refs` | Exact authoritative references derived by the tool; not model-authored sources |

Each finding contains `finding_key`, `fact_refs`, `interpretation_unverified`
(1–600 nonblank characters), `action_code` and `action_unverified`
(1–600 nonblank characters). Findings may not alter the baseline facts.

The tool generates stable finding keys and fact references from canonical facts
for this invocation. It includes all baseline blockers, conflicts, uncertainties,
hazards, all four evidence-kind checks for every actual campsite, and logistics
dependencies. Identical messages must retain their source/campsite distinction;
duplicate keys are rejected. B must provide the exact key construction and
maximum-list analysis with component schemas; list overflow is an explicit
unsupported-input error, never silent omission.

Proposed action vocabulary: `ACKNOWLEDGE_INFORMATION`, `CHECK_NEAR_DEPARTURE`,
`OBTAIN_APPLICABLE_INFORMATION`, `RESOLVE_SOURCE_CONFLICT`, `REQUEST_HUMAN_REVIEW`,
`CHANGE_TRIP`, `RESOLVE_LOGISTICS`, `CONFIRM_ACTIVITY_DETAILS`. Each fact has a
tool-generated allowed-action set. Explicit closure/fire-prohibition blockers
cannot be handled solely by acknowledgment or human approval. Missing weather
may suggest waiting/rechecking but cannot claim a future result is known.

The evaluated plan copies authoritative fact_refs and source_refs; the model
chooses only permitted actions, priority and explanatory text. Pure validation
can establish references, coverage, allowed choices and unchanged baseline; it
cannot prove natural-language advice true. The UI labels model prose as advice,
never as new verified safety information or an official approval. Unsupported
facts, invented thresholds/forecasts and instructions inside source text must
be rejected/ignored by the component where detectable; adversarial text tests
and human inspection remain required.

## S-03: Exact authoritative replay and current-date selection

A rebuilds SafetyInput from its saved confirmed context, itinerary, current-run
logistics assessment and that run's pinned dataset/clock/selection. It recomputes
the baseline through the registered pure rules with expected_mode=AGENT.
The supplied SafetyResult must equal the whole baseline, including provenance,
assumptions, uncertainties, evidence, blockers and logistics dependency.
The supplied plan must equal deterministic evaluation of its reconstructed
proposal. `validation_passed=true` alone is insufficient.

Use the same trip evidence selector as logistics and rules; do not introduce a
new safety scenario switch or infer information from expected test outcomes.
Do not splice partial evidence intervals or extend source validity. Daily
snapshot `OUTSIDE_VALIDITY` and sealed-source `NOT_YET_OBSERVED` remain distinct
source-selection results. Both prevent unsupported PASSED outcomes. Current
date/future weather window and next-check guidance come from the selector,
not model-generated dates. Recovery stays pinned; new reassessment gets a new
run and the current snapshot, without clearing the user database.

## S-04: Trace, strict types and payload limits

SafetyTrace follows the logistics trace conventions, with role fixed SAFETY:
requested_model, served_models, configuration_fingerprint, input_sha256,
rule_facts_sha256, proposal_sha256, prompt_sha256, tool_version, turns,
http_attempts, elapsed_ms, tool_calls, response_sha256, usage, validation_passed.

Input/baseline hashes use the original DTO `model_dump_json()` UTF-8 bytes.
Proposal/configuration/payload use canonical JSON with sorted keys, UTF-8,
compact separators, preserved array order and nulls, and nonfinite numbers
forbidden. Digest format is 64 lowercase hexadecimal characters.

All nested objects forbid extra fields. Ints reject bool/string/float; bools
require actual bool. Strings must be nonblank and bounded. JSON decoding rejects
duplicate keys and NaN/Infinity. Initial trace bounds: 3 <= turns <= registered
max_turns <= 6, turns <= http_attempts <= turns * registered max_attempts,
one response digest per successful turn, tools length turns-1, first tool read,
at least one evaluation and no unregistered tools. Usage is optional-by-key
nonnegative integer token counts, not fabricated zeros or a complete bill.

Proposed complete encoded payload limit: 512 KiB, including context, kind,
result, plan and trace. B provides normal and maximum supported fixtures before
freeze. Oversize input fails explicitly; do not truncate advice or omit facts.
Store no API key, Authorization, raw prompts/messages/replies or private
reasoning. Hashes do not independently prove a real model invocation.

## S-05: Registration and identity composition

Proposed markers: `a_safety_mode=model`, `a_safety_audit_required=1`,
`a_safety_audit_contract=1.0`, `a_safety_identity_seed=<canonical JSON>`.
Seed fields follow logistics: agent_version, tool_version, validation_version,
kernel_version, dataset_rules_version, prompt_sha256, model_client public
identity. No key, workflow_context or full configuration_fingerprint in seeds.

Collect trusted planning/logistics/safety seeds from the same registration base,
add all enabled-role markers, then build one final WorkflowConfiguration.
Compute each role's complete fingerprint against that same final context;
instantiate and check both logistics and safety against it. Merely appending
safety markers after constructing logistics would invalidate logistics identity.
Preserve dataset/snapshot digests, planning identity and revision feedback.
Conflicting markers fail explicitly. Proposed rules suffix is
`/a-model-safety-audit-v1`, appended once without removing logistics identity.

Public model/prompt/tool/rule/clock changes require new registered context and
the existing new-run/reconfirmation rules. Secret rotation alone does not
change public identity. Historical verification uses saved seed, facts and
versioned pure validators; it never needs the current key or a campus call.

## S-06: Atomic saving, reads and history

A owns the migration and table layout, provisionally a separate
`model_safety_audits` table; no migration number is reserved in this draft.
Save SAFETY assessment, safety audit and safety write receipt in one transaction.
No model or network calls occur inside it. A generates IDs, saved timestamp and
actual successful attempt association. Audits are immutable and unique per
run/assessment/write operation; changed payload with the same key conflicts.

Proposed authorised audit envelope: audit_contract_version, audit_id, plan_id,
run_id, plan_version_id, assessment_id, depends_on_assessment_id, kind=SAFETY,
attempt_id, input_fingerprint, configuration_fingerprint, plan, trace,
payload_sha256, created_at. A privately stores reconstructed input/baseline
snapshots and required validator identities; they are not API response fields.
There is no safety gear_checklist_id and no planning trace reuse.

Use `model_assessment_audits['SAFETY']` beside LOGISTICS, preserving planning
trace's separate origin-version-v1 semantics. Critical coordinated change:
current Orchestrator.checkpoint validates an exact LOGISTICS-only audit key set.
A readers and B checkpoint must derive the exact expected set from enabled
roles AND assessments already saved. Empty/in-progress/no-match steps are valid;
an already saved model assessment without its required audit is corrupt.

Validate associations and payloads at receipt hits, checkpoint, detail/queue,
route/completion, review, finalisation and immutable final reads. Keep v1
validators available for history; missing validators fail explicitly. Old rule
runs and old snapshots require no safety audit and acquire no model label.
Historical authorised reads do not depend on today's mode, data directory or key.

## S-07: Recovery and error behaviour

Successful checkpoint/receipt recovery reuses the saved assessment, advice,
trace and original successful save attempt. Never rerun a model to recreate a
missing audit. REASSESS creates a fresh safety assessment/audit referring to
this run's fresh logistics assessment, but keeps the itinerary's original
planning trace. REVISE creates a new version and all required new assessments.

Corrupt/missing required saved audit: PERSISTENCE_FAILURE, recoverable=False,
CONTACT_OPERATOR. Temporary transactional failure with complete rollback may
use RETRY. Caller payload invalid: CONTRACT_INVALID. Scope/identity/lease drift:
STALE_CONTEXT. Changed same-key payload: IDEMPOTENCY_CONFLICT. Neither Dispatcher
nor Orchestrator may promote a nonrecoverable integrity failure to RETRY.
Retain heartbeat during model waits. Uncommitted calls may repeat on recovery;
do not promise exactly-once external inference or cost.

## S-08: Flag, capabilities and user interface

Proposed `CAMPMATE_SAFETY_EXECUTION=rules|model`, default rules. Model safety is
opt-in in the supported agent/2.1 Hybrid binding for PLAN/REVISE/REASSESS, with
both rules and model logistics combinations explicitly tested. Other factories
fail readiness instead of silently ignoring the flag or falling back to rules.
NO_MATCH invokes no downstream model. Do not alter personal .env files.

Readiness checks capabilities, schema/migration, identity and registered limits
locally, without making campus calls. The initial live acceptance can use the
previously tested process-only 4096/low settings, but safety output and latency
need their own validation; A29 is not proof those settings suit every new role.

Meta reports safety=model only after full wiring/readiness. UI retains the
official checks and evidence coverage, then separately shows risk explanations,
prioritised actions and their supporting facts. User wording must explain what
is unresolved and the next action, rather than expose audit or workflow jargon.
Technical trace details stay collapsed. Keep model advice distinct from saved
facts, avoid duplicated rule/model paragraphs, and render plain text rather
than model-provided HTML. All new schemas, code, prompts and examples use English;
the current Chinese UI can use display translations until the agreed final
English conversion.

## S-09: Owners and delivery order

| Owner | Deliverables |
| --- | --- |
| B | SafetyAgent, strict proposal/trace schemas, facts/tool evaluation, pure replay helpers and versioned validators; Hybrid and Orchestrator integration; component/rules/recovery tests |
| A | RecoveryPort and migration, authoritative input/replay checks, audit readers, factory/identity/meta/flag, Dispatcher/review/final guards, UI and acceptance evidence |
| A/B | Exact schema/limits freeze, combined offline tests, bounded real-campus HTTP/browser acceptance |

B should update from main containing A28/A29 and send a component branch and
explicit S-01–S-10 replies. Do not implement an independent production database
or change A-owned factory/storage concurrently without coordination. A may
prepare storage after B returns exact strict schema/helpers; nobody enables
model safety on main merely because this proposal exists.

## S-10: Acceptance matrix and freeze checklist

- Normal complete data; deterministic risk/outcome unchanged, grounded advice
  and independent safety audit, explicit browser final save.
- Missing, future-window, stale and conflicting evidence separately; no PASSED
  upgrade, advice explains actual missing range and recheck/clarification.
- Road/campsite closure and prohibited requested campfire; neither advice nor
  Founder approval can override a mandatory blocker.
- High risk/unknown activity; review remains required; no fabricated temperature,
  probability, confidence or claim that an activity has been fully assessed.
- Logistics blocker/unknown fee/transport issue retained; safety links the exact
  saved logistics assessment, never another user/run/version's result.
- PLAN/REVISE/REASSESS; rules/model combinations; NO_MATCH skips safety; both
  model fingerprints use the same final context.
- Wrong owner, stale attempt/lease, altered input or snapshot, changed payload,
  duplicate keys, wrong strict types, unknown fact IDs, omitted/duplicated
  findings, invalid action/priority/source, overlimits and prompt injection.
- Transaction rollback at each write, lost receipt after complete commit,
  restart reuse with zero recovery model calls, missing/corrupt/swapped audit
  remains nonrecoverable through both orchestration layers.
- Old database upgrade and old final reads; safety-only, logistics-only, both
  enabled and neither enabled audit-key sets; no false audit requirement before
  a step has saved its assessment.
- Current-date pinned recovery, fresh reassessment and finalisation guards;
  unsupported history validators fail closed; no Canvas packaging in this round.

Before freeze, B must confirm: exact finding key and reference encoding; exact
proposal/plan/trace schemas; supported maximum facts and payload size; pure
validation API; identity seed construction; min/max tool rounds; error mapping;
all four audit-role combinations; division of code ownership and first live
acceptance scope. Any alternative that lets a model change the official
SafetyResult requires a new explicit design review rather than an implicit
extension of this draft.

## Suggested message to B

> A30 safety model proposal is ready on A's local workspace (not yet pushed).
> Please review S-01–S-10. First release uses model-generated grounded risk
> explanations and prioritised actions, while the formal SafetyResult remains
> exactly the rule baseline. B owns schemas/tools/agent and Hybrid/Orchestrator;
> A owns storage/readers/factory/UI/guards. Please return exact strict schemas,
> fact key conventions and replay helpers before storage wiring. Coordinate the
> LOGISTICS-only checkpoint audit check and both-role identity composition.
> Safety model execution remains disabled until combined acceptance passes.
