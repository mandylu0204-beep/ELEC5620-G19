# A38 safety runtime registration and facts provider

Date: 2026-10-17, Australia/Sydney. Branch: feature/a36-safety-audit-storage.
Includes A36 storage, accepted B 3510550, A37 combined-component acceptance and
this registration change. Use the complete branch, not an isolated cherry-pick.

## Delivered by A

- CAMPMATE_SAFETY_EXECUTION=rules|model, default rules, documented in .env.example.
  Personal .env and .env.llm.local were not edited.
- Explicit agent/2.1 mode guard. Rules mode rejects model-safety registration
  markers. Unsupported/incomplete wiring fails before inference, with no fallback.
- Factory collects both enabled-role seeds before building one final hybrid
  workflow context, then constructs and verifies both components against it.
  Current kernel/full selector rules identities, revision feedback and pinned
  source selection are preserved. Components must be bound to the actual Hybrid.
- Dispatcher registers the trusted local safety facts provider. It resolves the
  run's pinned RuntimeSnapshot, checks exact context, selects evidence for the
  actual itinerary and builds SafetyInput from confirmed requirements, saved
  itinerary and saved logistics. Formal baseline comes from actual safety rules.
- Readiness remains local-only. Database migration 10 is required for opted-in
  assessment roles. Metadata exposes features.model_safety and the safety stage
  only when planning capability is actually available.

## B integration requirements

Production enablement deliberately rejects the current unwired Hybrid and
Orchestrator. The following explicit capability contract is required:

1. HybridPlanningAgent.safety_audit_contract == '1.0'.
2. HybridPlanningAgent.assess_safety_with_trace is callable.
3. Constructor accepts safety_agent=registered_component and retains that exact
   object as self.safety_agent, alongside optional logistics_agent.
4. Orchestrator.safety_audit_contract == '1.0', added only with complete safety
   save/checkpoint/recovery integration. A marker alone does not implement it.

The factory passes both assessment roles against the same final configuration.
B must preserve/check the registered safety identity, call the trace-returning
role and save through RecoveryPort.save_model_safety_assessment(context, result,
plan, trace, scope.write_keys['safety']). No replacement baseline or source facts
come from the model. B must update the exact checkpoint audit-role set according
to both enabled roles and saved assessments, including partial and NO_MATCH runs.
Reuse persisted artifacts after a lost receipt; never regenerate missing audit
data. Integrity failures remain terminal in both orchestration and dispatch.

The setting is available for wiring, not a request to turn on today's runtime.
Do not edit user secrets/default configuration or claim live acceptance.
Migration 10 is already allocated to A36; no new migration is introduced here.

## Validation and limits

- 144 affected regression tests passed: registration, actual component storage,
  storage boundary, logistics audit, offline campus HTTP, model planning and
  plan changes (var/a38-regression.xml).
- Final registration suite: 12 passed, including four role combinations,
  wrong-mode/dataset rejection, feedback preservation and authoritative facts
  reconstruction (var/a38-final-registration.xml). This overlaps the prior run.
- Shared schema 1.0 export, dependency and diff checks passed.

The safety-enabled factory composition tests use an explicit registration-only
Hybrid subclass plus an Orchestrator capability marker. They never invoke that
fake orchestration. This proves A's construction/order/guards, not completion of
B's production workflow. Actual SafetyAgent/pure replay + SQLite acceptance is
separately recorded by A37; no real campus requests occurred in either step.

Production safety stays rules until B completes the interfaces above. Remaining
joint work: full combined regression/CI, workflow HTTP/recovery tests, concise
user-facing safety advice and bounded real campus/browser acceptance.

This supersedes A36's note that safety_facts_provider is unregistered in the
application: the provider is now registered, but model activation remains gated.
