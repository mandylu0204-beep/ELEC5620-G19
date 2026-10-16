# Shared application baseline for A30 safety integration

This baseline contains A31 meal clarification, A32 actionable logistics issues,
A33 plan deletion, A34 request deletion and the requested user-page cleanup.
It builds on main 8a40deb. Use the complete commit containing this document;
do not cherry-pick just a schema or identity change into the old application.

## Authoritative identities

- Common RULES_VERSION: b02-v1-rules-2/a-meal-clarification-v1
- V2_RULES_VERSION: b02-v2-rules-2/a-meal-clarification-v1
- Historical common kernel: b02-v1-rules-2
- Shared DTO/schema: 1.0, unchanged

Current logistics registration uses the new common identity. Its existing pure
audit verifier explicitly supports both the new and historical common kernels;
saved results remain immutable. B must explicitly register supported safety
kernel values without accepting arbitrary strings or mislabelling new runs.

## Database coordination

Migration 8 adds plans.deleted_at; migration 9 adds deleted_requests.
The current database migration sequence is 1 through 9. Safety persistence must
allocate migration 10 or later and update readiness and historical upgrade
tests accordingly. Do not reuse 8/9 from an older base. Ordinary startup
performs migration; no database files or personal secrets are distributed.

Plan/request deletion is logical. Immutable audit/snapshot records remain
stored. Deleted plans deny owner reads and leave review queues. Deleted requests
leave user history but preserve existing plan snapshots and associated records.
Active planning prevents plan deletion; active interpretation prevents request
deletion. Future safety persistence must preserve these checks and audit guards.

## B next step

Rebase or merge the full updated main into feature/llm-safety-agent, retaining
the R-S02 v2 text policy and frozen v1 replay separation. Address R-S01 using
the identities above; regenerate the current contract and identity tests.
Check both enabled-role combinations against one final configuration context.
Do not enable model safety or add production orchestration before the storage,
readers, registration and flags are jointly agreed and implemented.

R-S02 remote branch was fetched during this baseline preparation; this baseline
does not claim to have independently approved its latest component commit or
rerun B's 1175-test suite. Safety remains rules; no new campus calls were made.

## Validation evidence

Combined validation is recorded in evidence/a35-baseline-validation.json.
Earlier A31/A32 screenshots and reports retain their original historical scope;
they are not a fresh browser acceptance of every later UI change.
