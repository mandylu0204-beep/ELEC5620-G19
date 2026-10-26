# Lease regression follow-up: local evidence and B comparison request

Application source: `d3b3601`; reproducible control source: `1bb321a`.
No production application, model parameters, timeout, lease, date or eligibility
guard was changed. Main, personal configuration and the original database are
untouched. All model responses are offline MockTransport fixtures.

## Results

1. The original permanent-persistence-error case passed once with timing wrappers
   (35.63 seconds), then passed in the original-order batch without those wrappers
   (32.936 seconds). Its required non-retryable persistence error was preserved.
   The historical 819.267-second delay remains unexplained.
2. The selected follow-up batch contained exactly the previous failed case plus
   the 37 previously unexecuted cases, in their original collected order. It
   stopped at the first failure: **3 passed, 1 failed, 34 not executed**, exit 1.
3. The new failure is
   `test_lost_lease_cancels_inflight_safety_and_rejects_late_artifacts`.
   It expected cancellation and `STALE_CONTEXT` after its deliberate safety lease
   fault. Instead, the saved run last reported `ASSESSING_LOGISTICS`, then the
   lease guard recorded recoverable `AGENT_FAILURE`. There is one planning trace,
   no logistics or safety audit, and no saved progress reaching the intended
   safety cancellation. The complete case took 2223.218 seconds; that number
   cannot be assigned to one logistics operation.
4. One separate bounded timing diagnostic of that new case passed in 40.73
   seconds. The cancellation and late-artifact rejection assertions held. This
   instrumented pass does **not** replace its uninstrumented failure.

Across the original 237-case selected scope, there are now **202 distinct
uninstrumented passes, one unclosed uninstrumented failure, and 34 unexecuted
cases**. Diagnostic passes are recorded separately. This is not a single
whole-project run and is not ready for main. No campus calls or cloud tests were
started; each offline HTTP guard reported zero unexpected real-transport hits.

## Observation boundaries

The opt-in control records finite method labels, paired timestamps, process CPU,
and code-location stacks. It never captures arguments, locals, SQL contents,
credentials, prompts or replies. Sequence timestamps are taken inside the record
lock. Each diagnostic process has a 180-second cap, separate from unchanged
application deadlines; neither completed diagnostic reached that cap.

- Persistence diagnostic: 789 events, no drops, 291 paired function intervals.
- Cancellation diagnostic: 729 events, no drops, 267 paired function intervals.
- Both event streams have consecutive sequence numbers and ordered elapsed times.
- Process CPU is process-wide. Concurrent/nested intervals cannot be added as
  saved wall time or attributed solely to one HTTP response.
- Sampling gaps cannot identify the cause of an interruption. The old long
  failures have no equivalent CPU/sampling record, so they cannot be assigned
  retroactively to an environment problem or a code defect.
- Direct version-save timing was not captured: the optional
  `SqlitePersistencePort.save_model_version` target was absent. Database and
  runtime spans are present; they do not substitute for that missing span.

The first diagnostic used the exact archived guard source under
`evidence/controls/lease_probe_guard_executed.py`; the second diagnostic and the
uninstrumented batch used `scripts/offline_http_guard.py`. The diagnostic wrapper
source is `scripts/offline_lease_probe.py`. The artifacts retain their actual
control hashes; no subsequently edited script is presented as executed source.

Summary: [follow-up evidence](../evidence/a-lease-followup-summary.json).
Finite event streams: [persistence](../evidence/a-lease-probe-persistence.json),
[cancellation](../evidence/a-lease-probe-cancellation.json).
Ordered case list: [four-case prefix and pending cases](../evidence/a-lease-followup-case-list.json).
Full local JUnit and isolated databases stay under ignored `var/`.

## Requested B comparison

Please use an isolated checkout at `1bb321a` and existing dependencies. First
review the finite controls and evidence. Then execute **only the four prefix
cases below, once and in order**, locally and without timing wrappers, to check
for order/platform dependence. Do not run a whole suite or call the campus model.
Keep every existing timeout, lease, assertion and production guard. Stop at the
first failure and retain the exact count, exit code and limited failure summary.

From the repository root on macOS (choose a fresh generated temp suffix):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:scripts python -m pytest \
  -p offline_http_guard \
  'backend/tests/test_model_safety_wiring.py::test_permanent_integrity_error_stays_terminal_through_dispatcher[save_model_safety_assessment]' \
  'backend/tests/test_model_safety_wiring.py::test_permanent_integrity_error_stays_terminal_through_dispatcher[load_checkpoint]' \
  'backend/tests/test_model_safety_wiring.py::test_safety_wait_keeps_lease_alive_without_exact_heartbeat_counts' \
  'backend/tests/test_model_safety_wiring.py::test_lost_lease_cancels_inflight_safety_and_rejects_late_artifacts' \
  --basetemp var/lease-b-prefix-unique --junitxml var/lease-b-prefix.xml -o addopts='' -x
```

B's result will be an independent platform comparison, not proof of Windows
success. Review it before deciding the next narrow observation or continuing the
34 pending cases. A will not repeatedly run batches to obtain a green result.
