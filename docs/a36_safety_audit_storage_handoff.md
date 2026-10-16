# A36 safety audit storage boundary

Base: complete main 4c0662c. Local branch: feature/a36-safety-audit-storage.
Status: storage groundwork implemented and tested; NOT production safety
enablement, NOT combined acceptance with B's old-base component. R-S01 remains
pending. No live campus calls, frontend changes, new factory or settings flag.

## Port and authoritative facts

```python
await recovery_port.save_model_safety_assessment(
    context, result, plan, trace, scope.write_keys['safety'])
```

The port requires the current claimed attempt and an explicitly registered
agent-mode scope with a_safety_mode=model, a_safety_audit_required=1,
a_safety_audit_contract=1.0 and canonical a_safety_identity_seed. Plain
save_assessment(..., SAFETY, ...) rejects such scopes. Kind/key are fixed;
there is no safety gear checklist.

A WorkflowService.safety_facts_provider is deliberately unregistered by default.
Its future trusted, local-only implementation receives
(scope, confirmed_context, stored_version, stored_logistics) and returns
(SafetyInput, complete_rule_baseline, TripEvidenceSelection). A checks the saved
requirements, itinerary, logistics dependency, scenario/selection, clock,
version and input fingerprint. It requires exact whole baseline equality.
The provider must resolve the pinned runtime dataset/selector and call registered
pure safety rules. B does not supply this provider or a trusted baseline.

The replay adapter lazily imports B's safety_validator_for. Missing component,
unsupported identity or R-S01 mismatch rejects saving; there is no fallback.
Version selection comes from the trusted saved scope. Current writes accept v2;
history explicitly dispatches v1/v2 before parsing version-specific advice.
Recognised kernel strings are explicit, not an arbitrary version wildcard.
This is not factory registration: a future factory must still build/check one
final workflow context for both logistics and safety and deny unsupported modes.

## Persistence and reads

Migration 10 adds model_safety_audits, unique by run and assessment, with exact
logistics dependency and same-run/version foreign keys. Update/delete triggers
keep audits immutable. Assessment, audit and safety receipt commit together or
roll back. Payload limit is 512 KiB over context/kind/result/plan/trace.

A stores its authoritative input/baseline/selection JSON and original successful
attempt privately. Receipt replay verifies the existing audit before returning;
changed content conflicts. Missing or corrupt already-saved audits are terminal
PERSISTENCE_FAILURE / recoverable=false / CONTACT_OPERATOR, never regeneration.
The actual successful save attempt remains attached when a receipt is reused.

Public model_assessment_audits['SAFETY'] includes audit contract, IDs, dependency,
attempt, context/configuration/payload hashes, time, validated plan and trace.
It exposes no private input/baseline/selection snapshots or owner ID. Historical
reads use saved facts and the selected pure validator, not today's data/API key.

assessment_audits.load_audits combines the existing LOGISTICS reader and the
SAFETY reader. Expectations depend on enabled roles and saved steps; incomplete
or NO_MATCH steps need no fabricated audit. Routing/completion additionally
require every enabled audit. Reads are integrated at checkpoint, plan detail,
review queue/detail, route/eligibility/completion and final snapshot write/read.
Existing rules scopes return no safety audit and gain no model label.

## B coordination

B should finish R-S01 against the authoritative common baseline first. A has
not merged or modified B's safety modules to disguise their old kernel literal.
Then jointly test this storage against B's real versioned pure validator and
selector, with both rules/model logistics. B still owns Hybrid/Orchestrator
integration and its exact checkpoint key-set update. A still owns production
facts-provider wiring, common seed composition, flag/readiness and user advice
presentation. Do not enable a factory before both halves agree.

No shared schema 1.0 methods or DTOs changed. Migration 10 is now allocated on
this branch; later migrations must not reuse it. Main has not been changed by
this local branch. No user database or personal configuration was migrated.

## Evidence and limitations

- 137 affected regression cases passed: safety storage, logistics audit, plans,
  finalisation, reviews and workflow recovery (var/a36-regression.xml).
- 28 storage/upgrade checks passed (var/a36-migration.xml), overlapping the
  previous run and including historical upgrades and migration 9 to 10.
- One extra final snapshot association/read-corruption check passed
  (var/a36-final-snapshot.xml).
- Shared schema export and git diff checks passed.

The new storage tests explicitly replace the pure-advisory replay boundary with
a synthetic test double. They use actual rules facts, SQLite transactions,
leases, snapshots and existing permission services. They do NOT establish real
SafetyAgent output/schema compatibility, both-model composition, real model
calls or browser acceptance. R-S02's separate 250-component acceptance remains
recorded in a30_rs02_a_acceptance.md, against B commit ba7d9e5. A full combined
backend/CI and live/browser acceptance remain required after R-S01 integration.
