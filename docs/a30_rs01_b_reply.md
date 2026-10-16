# R-S01: shared A35 baseline and versioned safety identities

Date: 2026-10-16, Australia/Sydney. Branch: `feature/llm-safety-agent`.
Full shared main: `4c0662c`; merged without conflicts as `e948f59`, preserving
the already-published B component/R-S02 history (`ba7d9e5`).

**B has addressed R-S01 at component level. A's independent review and final
A30 contract freeze remain pending.** A separately accepted R-S02 after 250
targeted tests; that acceptance is not a production safety-model enablement.

## Exact identity agreement

Use the actual common kernel, not a new safety-only alias:

| Supported v2 replay / identity pair | Common kernel | Complete adapter dataset rules |
| --- | --- | --- |
| Historical | `b02-v1-rules-2` | `b02-v2-rules-2/trip-evidence-selection-1` |
| Current A35 | `b02-v1-rules-2/a-meal-clarification-v1` | `b02-v2-rules-2/a-meal-clarification-v1/trip-evidence-selection-1` |

The adapter base constant is `b02-v2-rules-2/a-meal-clarification-v1`; actual
agent/2.1 selector-enabled datasets append `/trip-evidence-selection-1`.
That full value, not just the base constant, belongs in the seed.

`SafetyIdentitySeed` accepts this closed set of exact matched pairs. Unknown
kernels/rules, unrecognised suffixes and cross-paired old/current values fail.
The schema exposes the enums plus paired `anyOf` constraints and a top-level
`supported_kernel_rule_pairs` list in the internal contract bundle.

`safety_identity_seed(dataset, public_client_identity)` still reads the actual
imported common `RULES_VERSION` and loaded `dataset.rules_version`. It never
substitutes the old kernel to get past validation. Current A35 registration
therefore uses the second pair; unsupported live configuration fails locally
before inference. Secret rotation does not change public identity.

Agent `campus-safety-advisory-agent-2`, tool `safety-read-only-tools-2`, validator
`safety-advisory-validation-2` and text policy `safety-advice-text-2` remain.
R-S01 changes supported kernel registration, not the R-S02 advice/pure-replay
algorithm or prompt. Prompt SHA256 remains
`348dcee55454f9d25f65e9e4d128858be182e512bc22dabf79f2d286c0865d31`.
The current kernel, dataset rules and complete workflow context still change
the full configuration fingerprint; old traces/write keys cannot be relabelled
as new outcomes. Shared DTO/schema 1.0 remains unchanged.

Machine bundle:
[`contracts/safety_advisory_v2.schema.json`](contracts/safety_advisory_v2.schema.json).
Both schema and pure validators remain required; schema validation is not
proof of correct snapshot bytes, ownership or authentic model execution.

## Historical replay is not new registration

Frozen `backend/app/llm/safety_v1/` and
`contracts/safety_advisory_v1.schema.json` are unchanged from `ba7d9e5`.
Dispatch by the trusted saved seed's `validation_version`:

```python
validator = safety_validator_for(saved_seed['validation_version'])
plan, trace = validator(
    saved_input, trusted_saved_kernel_baseline, supplied_saved_result,
    raw_plan, raw_trace, identity=trusted_registered_identity,
    selection=trusted_pinned_selection,
)
```

Original v1 preserves the original text semantics, including formerly allowed
text that current R-S02 rejects. Old-kernel v2 remains supported by the v2
validator under its original identity. Neither upgrades a saved registration,
rewrites advice, substitutes today's snapshot or regenerates missing model
audit data. Unsupported validator versions still fail nonrecoverably.

Before merging A35, B captured explicit offline old-kernel fixtures under
`ba7d9e5` in `backend/tests/fixtures/safety_archives_pre_a35.json`:

- v1: synthetic archival proposal/trace using the frozen original helper.
- v2: actual component outcome with `httpx.MockTransport`, not a real model.

Both include original input, rule baseline, plan, trace, complete identity and
pinned evidence selection. They use synthetic profiles/business IDs only and
are labelled `OFFLINE_SYNTHETIC_ARCHIVE_NOT_LIVE_INFERENCE`. No keys, raw
prompts/messages or private reasoning are stored. SHA256 of the fixture file:
`0d983613b08977e0107091b57e54af69c84f8e82b767574ef6746225e658b17b`.
Only tests load this file; it is not production data, a model cache or live
acceptance evidence. Current-rule outputs are never labelled with old rules
to manufacture a replay test.

Replay tests run both saved versions without loading a current dataset or
client. They assert unchanged plan/trace/input/baseline/selection/identity and
reject tampered unknown kernels, input, baseline, references, sources,
selection and fingerprints. An old v2 trace paired with the current identity
fails even though the R-S02 prompt hash is unchanged.

A still owns reconstruction and verification of the trusted archived baseline,
snapshot, saved logistics dependency and authorised registration. The pure
helper cannot authenticate a caller-supplied baseline. Historical reads must
use compatible saved-kernel semantics, not today's unresolved meal defaults or
newly calculated logistics. Full production historical-read/recovery tests are
part of the subsequent A-owned wiring, not delivered by these fixture tests.

## One final context for both roles

Four offline component combinations are tested: neither, logistics-only,
safety-only and both. Tests collect real logistics/safety seeds from the same
base, append enabled-role identity/audit markers, build one final hybrid
workflow configuration, then instantiate and check both components against
that exact context. Both seeds carry the authoritative A35 kernel/rules pair.
Seeds are context-independent; each complete role fingerprint hashes its seed
plus the same final context. Adding safety markers after binding logistics
changes its fingerprint and is not equivalent to the agreed ordering.

This is a test of the proposed registration composition, not an implementation
of A's future safety factory/flags or proof of production readiness for all
four combinations. Existing production logistics registration is unchanged.
The new meal-clarification case also verifies that missing meal choice remains
logistics REVISION_REQUIRED and model safety advice requests resolution, never
silently decides a meal mode or overrides the official route.

## Verification

```bash
cd backend
../.venv/bin/python -m pytest tests/test_safety_kernel_identity.py \
  tests/test_safety_text_policy.py tests/test_safety_contract_export.py \
  tests/test_llm_safety_agent.py tests/test_safety_advisory_boundaries.py \
  -o addopts='' -q
../.venv/bin/python -m pytest -o addopts='' -q
../.venv/bin/python -m app.export_contracts --check
cd ../frontend
npm test
npm run build
```

Targeted safety regression: **290 passed**, including 40 new R-S01 cases.
Full backend: **1238 passed, 0 failed, 0 skipped** (331.46 seconds), with one
existing Starlette TestClient/httpx deprecation warning. Shared schema 1.0
export check and dependency check passed. Frontend: **12 passed**, TypeScript
and Vite build passed. Results are recorded in
[`evidence/a30-rs01-check.json`](evidence/a30-rs01-check.json).
Earlier A29/R-S02/A35 reports retain their own bases and scopes; no result is
relabeled as new live safety acceptance.

No campus requests, provider probes, API keys, extra paid retries or output
limit increases were used. Component model calls are mocked; full-suite HTTP
checks are local test clients with independent temporary databases. No running
application service, personal settings, user database or sealed data changed.

## A next, then B

1. A independently reviews R-S01 and freezes the exact updated v2 bundle and
   helper/identity contract. No need to reopen the already-accepted R-S02 text
   policy unless a separate concrete issue is found.
2. A implements the agreed safety audit port/transaction/receipt, dependency
   links, readers, all-role registration/readiness/flags and UI. **Migrations
   8 and 9 are occupied; safety storage must allocate 10 or later.** B adds no
   migration and does not reserve 10 independently. Retain A35 ownership,
   deletion, review-queue and finalisation guards and immutable audit records.
3. Once the complete shared capability is available, B integrates Hybrid and
   Orchestrator: independent SAFETY audit, both-role checkpoint sets,
   heartbeat, lost-receipt reuse and nonrecoverable integrity failure handling.
4. Joint offline HTTP/SQLite/recovery/UI validation; only then, with agreed
   cost/limits, a small real-campus safety acceptance. Existing planning and
   logistics acceptance does not substitute for the new role.

Safety remains rules in the running application. This patch does not add a
safety flag, save interface, production migration, factory, Hybrid/Orchestrator
integration or safety UI, and does not claim those capabilities are ready.
