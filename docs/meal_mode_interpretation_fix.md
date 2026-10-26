# Meal-mode interpretation fix

Base: `03464cf`. Branch: `fix/meal-mode-interpretation`.

The 2026-10-27 isolated live acceptance stopped before PLAN: the saved summary
put ready-to-eat meals in mandatory_constraints, removed the explicit preference,
and then required both an unsupported facility and a missing meal choice.
The raw model response was discarded, so this patch does not claim to replay
that exact response. Synthetic quoted proposals reproduce the observed result.

## Behavior

Whole, registered meal labels are arrangements rather than campsite facilities.
Positive ready-to-eat and self-catered choices enter the existing meal-choice
contract in preferences, even when stated as required. A required raw meal no
longer overrides or deletes the same explicit choice. Exact registered labels
can also be recovered from canonical=null without guessing an unknown phrase.

Quoted evidence, ambiguity, negation, competing meal choices, required facility
conditions and unverified dietary qualifiers remain checked. Meal quotes cannot
be reassigned to an unrelated facility. Shared DTOs, database tables, safety v4,
model limits, leases and finalisation guards are unchanged.

The request component and validation identities advance to version 2, and the
prompt distinguishes arrangements from facilities. The JSON shape stays at
request-mentions-1. Existing pending summaries require regeneration when the
interpreter identity changes; confirmed snapshots and old runs are not rewritten.
The existing request identity remains separate from planning/workflow identity.

## Offline validation

- Before the repair, nine selected reproductions failed with the old projection;
  one existing meal-alias case in that selection passed.
- After the repair: 115 passed, 0 failed, 0 errors, 0 skipped across request-model,
  request-lifecycle, request-terms and meal-choice-flow modules.
- Includes 17 new cases, with four real-factory/MockTransport HTTP scenarios
  confirming meal summaries and reading the immutable confirmed request after
  application restart. The original hard-facility and lifecycle tests remain.
- Shared contract check passed. Real-HTTP guard attempts: 0. Campus calls: 0.
  Cloud tests: 0. Existing Starlette/httpx deprecation warning remains.

This is targeted offline regression, not a full-suite or real v4 acceptance.
Restart the local backend and regenerate an unconfirmed summary to use the fix.
The prior live round remains closed; no new live calls are authorised by this
report. Personal configuration, existing user databases and frozen evidence
were not changed. No merge or push is part of this repair.
