# A review of B safety advisory component and contract

Date: 2026-10-16, Australia/Sydney.
Reviewed B commit: `7eab8e71e7610e0ab2e65bb6bc8d6d546cf5b44f`, branch
`feature/llm-safety-agent`, based on main `8a40deb`.

Status: **overall design accepted; final contract freeze pending R-S01/R-S02
and a common integration baseline. Not merged or enabled.**

## Verified scope

The remote commit exists and its GitHub CI completed successfully:
[B component CI](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38833918484).
The diff adds six component modules, component fixtures/tests, contract JSON,
handoff and verification evidence. It does not change production factories,
settings, Hybrid, Orchestrator, persistence, sealed datasets or frontend.

A inspected the implementation from a Git-exported isolated snapshot. It was
not checked out over the pending local A31/A32 work. A's independent component
test results are recorded in `evidence/a30-safety-a-review.json` after completion.
B's reported full 1001-test result is B's evidence, not an A rerun of the full
suite or a combined A31/A32 result. No campus inference was performed by A.

## S-01 through S-10 disposition

| Item | A decision |
| --- | --- |
| S-01 API | Accept `SafetyOutcome(assessment, plan, trace)`, standalone trace method and proposed A-owned `save_model_safety_assessment(context, result, plan, trace, write_key)`. Kind is SAFETY; use the existing safety write key; no gear checklist. Do not apply the rule annotation helper to the exact baseline. |
| S-02 facts/proposal | Accept full canonical finding coverage, separate priority permutation, deterministic keys and host-added references/sources. Model supplies no evidence or references. Accept restricted action choices. Text policy needs R-S02 before final freeze. |
| S-03 replay | Accept version-registry API and exact whole-result baseline equality. A reconstructs authoritative input, pinned selection and rule baseline; a caller-provided baseline is never trusted. Historical reads use archived input/baseline/selection plus the saved validator, not current files, key or clock. |
| S-04 bounds | Accept proposed count and joint UTF-8 byte limits as structural bounds. Individual maxima are not a supported Cartesian product. Do not trim findings, raise paid limits automatically or claim 64 findings fit 4096 tokens. |
| S-05 identity | Accept seed-without-context and final fingerprint with one common context. Both model roles must be instantiated and checked after all enabled-role markers are composed. R-S01 must align supported kernel identity with the actual integration baseline. |
| S-06 atomic storage | Accept separate immutable audit, same transaction as assessment/receipt, exact logistics dependency and A-generated association/attempt metadata. All authorised reads and finals validate the required audit. |
| S-07 recovery | Accept reuse after complete commit, no model regeneration of missing audit, and nonrecoverable integrity errors through both orchestration layers. Uncommitted inference is not exactly-once. |
| S-08 flag/readiness | Accept rules default, explicit opt-in only for the supported agent/2.1 binding, local readiness without probes, and no fallback. Both rules/model logistics combinations need application tests. |
| S-09 ownership | A owns port/migration/readers/identity/meta/flag/guards/UI; B owns component/schema/pure helpers and later Hybrid/Orchestrator. No parallel production database or uncoordinated factory edits. |
| S-10 acceptance | Accept proposed offline matrix and distinct live acceptance. Existing component, A29 and mock maximum evidence do not establish production safety audit or real-token readiness. |

## R-S01: kernel identity must match the combined baseline

Priority: integration blocker, not a claim that B's `8a40deb` branch is broken.

`backend/app/llm/safety_identity.py:70` restricts SafetyIdentitySeed.kernel_version
to the literal `b02-v1-rules-2`. `safety_identity_seed()` obtains that value from
the live imported common RULES_VERSION. A31 changes the latter to
`b02-v1-rules-2/a-meal-clarification-v1` and adds the equivalent v2 rules suffix.
Thus the standalone component cannot construct an identity after that pending
A change is integrated.

A reproduced this without inference: using the component's public client
identity and the actual pending common kernel value causes Pydantic
ValidationError on kernel_version in safety_identity_seed().

Required agreement/change:

1. A supplies a shared baseline including the completed A31/A32 work and its
   exact SHA before production safety wiring. These changes are local and not
   yet pushed at the time of this review; do not pretend current origin/main
   already contains them.
2. B explicitly registers the kernel value(s) supported by the v1 replay
   implementation and regenerates the machine-readable identity schema. Do not
   accept arbitrary version strings or falsely emit the old value for new runs.
   Preserve explicitly supported archived verification, while rejecting unknown
   kernels. If a separate safety-kernel identity is preferred, agree its exact
   authoritative construction before A duplicates registration assumptions.
3. Add tests for the common A31 kernel, all role combinations against the same
   final context, old supported replay and unknown-kernel rejection. A will
   cover factory/readiness and actual application recovery after wiring.

## R-S02: make the text policy and validators agree

Priority: protocol freeze correction. This is not an approval bypass finding.

The candidate document says advice contains no control characters or URLs.
`backend/app/llm/safety_schema.py:38-47` currently rejects ASCII C0 controls,
DEL, numeric literals, HTTP(S) prefixes, matched HTML tags/code fences and a
selected phrase list. A reproduced acceptance of:

- U+0085 (Unicode C1 control) inside otherwise ordinary advice;
- U+202E (bidirectional formatting control) inside otherwise ordinary advice;
- `See www.example.com for guidance.`

These are concrete detectable-policy gaps, not a request to solve general
semantic truth or prompt injection with regex. Plain-text rendering and the
unchanged official checks must remain independent safeguards.

Before freeze, either tighten the declared exclusions (including Unicode
control/format characters and supported URL forms), with exact tests, or amend
the contract to accurately describe a narrower blacklist. A prefers rejecting
Unicode control/format characters and link-like advice in this English-only
role. Do not silently clean/normalise a received proposal to pass validation;
reject it. Regenerate contract JSON and record validator/prompt identity changes
where applicable. No claim of complete truth/injection detection is accepted.

## Production and live boundaries

A will implement safety storage/readers and common registration against the
agreed strict helpers after these points and the shared baseline are settled.
Required audit keys remain a function of both enabled roles and actually saved
assessments, including empty/in-progress/NO_MATCH states. Replacing the current
LOGISTICS-only exact-key check with an unconstrained dictionary is insufficient.

Initial live acceptance should start with a small normal single-campsite input,
an explicit process-only output/timeout budget and a bounded request count,
then unresolved/blocked cases. There are no live safety results yet. Count,
byte, request and token limits remain separately enforced; 64 offline findings
must not be advertised as a validated 4096-token live capability. No automatic
additional paid calls or increase in limits is authorised by this document.

The current application continues to use rules for safety. This review does
not change user configuration, existing databases, model flags or main.

## Suggested short reply to B

> A reviewed 7eab8e7. S-01–S-10 are accepted in principle, but final freeze is
> pending two small items: SafetyIdentitySeed currently accepts only the old
> kernel and must align with A31's new rule identity; the declared no-control/
> no-URL advice policy needs to match the actual Unicode/link validators.
> Please address R-S01/R-S02 with schema/export and regression updates. A will
> supply the shared A31/A32 baseline SHA before production wiring. No Hybrid,
> Orchestrator or production safety enablement yet. 64 offline findings do not
> establish 4096-token live support. Detailed review: a30_safety_a_review_reply.md.
