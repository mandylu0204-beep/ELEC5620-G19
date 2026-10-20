# A65: opt-in SafetyAgent integration review

Date: 2026-10-20, Australia/Sydney.

The integration branch combines latest main `e959477` with the complete audited
safety runtime from `feature/a45-safety-integration`. There were no conflicts.
Compared with the A64 runtime `05568f0`, backend sources are identical; main's
subsequent frontend profile/failure guidance is retained. Compared with main,
the production changes are confined to HybridPlanningAgent and Orchestrator.

When safety model mode is explicitly registered, Hybrid delegates to SafetyAgent
and Orchestrator saves the complete validated assessment/advice/trace through the
existing atomic RecoveryPort. Checkpoint replay validates exactly the enabled
saved audit-role set, preserves prior planning/logistics outputs, and does not
regenerate an audit after a lost receipt or treat corrupt audit data as retryable.
Deterministic safety facts remain authoritative and separate from model advice.

Default `safety_execution` remains `rules`. No default configuration, prompt,
public model parameter, shared schema, database structure or personal file changed.
No diagnostic transport or private acceptance harness is imported by production.
This work does not authorize enabling model safety for users automatically.

## Acceptance evidence and B review

A64 used the identical backend runtime, a consistent isolated original-run copy,
and an explicit four-request approval. Three real safety requests completed with
HTTP 200, formal assessment/audit/receipt saving and restart/browser readback.
Original planning/logistics content was retained; current historical-date guards
remained STALE_CONTEXT and final save stayed disabled. See
`docs/a64_live_safety_recovery.md` and `evidence/a64-live-safety-recovery.json`.

The user relayed B's independent review: 20 evidence-consistency checks and 16
offline control tests passed; no blocking issue in shared evidence/public
controls, zero new campus calls. B explicitly did not independently reproduce
the private database or screenshots. This attribution is not an additional B
source commit or a reproduction of private artifacts.

## Combination checks

Front-end tests: 47 passed; typecheck and production build passed. Shared schema
check and pip check passed. Data v2: 68 static checks passed. Data v2.1: 24 checks
and 600 weather coverage queries passed. Full backend and hosted CI results will
be recorded in the PR before it is marked ready for review.

All A65 checks are offline. New campus requests: 0. No merge to main is performed
as part of preparing this PR; B should review compatibility and CI before a
merge decision. Prior 502 causes and remaining quota are still undetermined.
