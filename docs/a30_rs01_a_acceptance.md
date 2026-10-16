# A acceptance of R-S01 and component contract freeze

Date: 2026-10-16. Reviewed B commit:
35105501389099772fdc5e34b738cc2bb41006a9, feature/llm-safety-agent.
Shared application base: 4c0662c. A storage groundwork: dfc3df4.

R-S01 is closed at component level. Together with the previously accepted
R-S02, the A30 component/identity/pure-replay contract is frozen at this B
commit and its exact v2 machine bundle. This is not production safety enablement.

## Independent review

A exported B's exact commit into an ignored isolated directory, explicitly
imported that backend and independently ran the five safety suites. Result:
290 passed, zero failures/errors/skips; report
var/a30-rs01-review/var/rs01-a.xml. B's full 1238-test result was not rerun by A
and is not relabelled as A or combined storage acceptance.

The implementation reads the real common RULES_VERSION and full selector-enabled
dataset.rules_version. Both Python validation and JSON schema expose an exact
closed set of matched pairs, rejecting unknown values and old/current mixing:

- Historical: b02-v1-rules-2 with b02-v2-rules-2/trip-evidence-selection-1.
- Current: b02-v1-rules-2/a-meal-clarification-v1 with
  b02-v2-rules-2/a-meal-clarification-v1/trip-evidence-selection-1.

The original adapter base constant alone is insufficient for the identity seed.
The historical v1 code/bundle and R-S02 text policy are unchanged. Original
offline archive file SHA256 matches B's declared
0d983613b08977e0107091b57e54af69c84f8e82b767574ef6746225e658b17b.
Saved old v1/v2 replays and corruption/downgrade tests pass. Archives are mock
or synthetic evidence, not real campus inference. Four role-composition cases
pass against one final context; these remain component-level registration tests.

Frozen docs/contracts/safety_advisory_v2.schema.json SHA256:
632296a547ae3729c6e48410da021d8a5bf8c569c793da096161944469a7c6ed.
The current prompt identity remains the value recorded by B; kernel/rules/context
changes still produce different complete fingerprints.

## A36 real-component combination

B's accepted component was merged ONLY into local
feature/a36-safety-audit-storage (merge b7f8ed9). Main, personal configuration,
user database, model activation and running services were not changed.

New test_safety_audit_component.py uses the actual SafetyAgent, strict B replay,
actual rules facts and A SQLite/RecoveryPort. CampusModelClient uses MockTransport
for every request. Six combination cases pass: rules or model logistics, valid
atomic save/checkpoint/receipt reuse, modified-advice rejection and corrupt-trace
recovery rejection. Saved facts can be read without a current facts provider.

A also tightened its writer: historical kernels remain readable, but a new
safety write requires the current common kernel and current v2 validator.
Both-role scopes produce independent LOGISTICS and SAFETY audit entries, and
the safety dependency points to the same run's saved logistics assessment.

The expanded combined regression, including the 290 component cases, A storage
tests and six actual-component persistence cases, is recorded in
evidence/a37-rs01-acceptance.json. Earlier A36 test-double evidence retains its
historical scope; it is not silently promoted to real-component validation.

## Remaining A/B work

- A: production facts-provider wiring, all-role seed/final-context registration,
  validated mode/readiness flag and concise user-facing advice presentation.
- B: Hybrid/Orchestrator activation and exact checkpoint role-key expectations,
  pinned recovery and terminal integrity error propagation against this shared
  storage capability.
- Joint: broader offline HTTP/recovery/UI validation and full combined CI, then
  bounded real campus safety and browser acceptance. No live calls occurred here.

Migration 10 belongs to A36. No B migration was added. The current application
still executes rule-based safety; review acceptance does not grant automatic
approval, remove blockers or claim a 4096-token maximum-finding live capability.
