# Heartbeat fixture forwarding repair and targeted coverage completion

Candidate source: `a81c829`, based on `3f795c7`. No production application,
frontend, dataset, model parameter, timeout, lease or existing assertion changed.
Main and the user's configuration/database remain untouched.

## Proven fixture deviation

`fast_heartbeat()` was intended to change only the test heartbeat interval. Its
plain two-argument wrapper also hid the registered factory identity and dropped
`parsed_snapshots`/`snapshot_key`. `AgentRuntime` therefore correctly chose its
legacy two-argument compatibility path and did not pass parsed snapshot options.
That unintentionally replaced the normal cached binding path with repeated full
Adapter construction during these heartbeat tests.

The repair adds `@wraps(factory)` and forwards `**options` unchanged. The existing
`.005` test interval is retained. All existing lease/cancellation assertions and
deadlines are retained. Production compatibility for genuine two-argument
factories is untouched.

A new regression uses the real registered factory to verify that initial and
subsequent binding both receive the same cache object/key, produce the same
registered context, retain the requested test interval, and make no model calls.
It failed on the old helper and passed after the repair. This establishes the
fixture deviation; it does not establish the cause of every historical delay.

## Fresh native Windows results

- Forwarding regression plus the original heartbeat-renewal and lost-lease
  cancellation cases: **3 passed, 0 failed/errors/skipped**, exit 0. JUnit:
  57.773 seconds. No application timing wrappers were installed.
- The previously pending tail, in its original order: **34 passed,
  0 failed/errors/skipped**, exit 0. JUnit: 208.171 seconds. The passive process
  monitor recorded 545 ordered events and did not trigger its process cap.
- Across the selected eight-module scope, the earlier unchanged passing cases
  plus these fresh runs provide passing evidence for all **238 distinct cases**:
  the original 237 and the new forwarding regression. There are no uncovered
  cases in that selected set. This is **not one same-commit whole-backend run**;
  historical failures and source revisions remain explicitly listed.

The HTTP guard recorded zero unexpected real-transport attempts. Campus calls
and cloud tests started: zero. Prior frontend/native benchmark results are not
presented as new runs here.

Summary: [repair evidence](../evidence/a-heartbeat-fixture-review.json).
Coverage: [per-case passing evidence](../evidence/a-heartbeat-selected-cases.json).
Passive monitor: [finite case events](../evidence/a-heartbeat-tail-watchdog.json).
Local full JUnit files remain in ignored `var/`.

## Source review and limits

The reviewed built-in factory does not establish a concrete reverse DB/runtime
lock cycle. Synchronous runtime checks under port validation can be expensive,
but observed nested intervals do not assign the old long delays to one operation.

Dispatcher failure recording invalidates the lease before its final cancellation
and drain. That prevents late writes. A reader can observe failure before all
cleanup finishes; no production ordering was changed to make a cancellation
assertion pass. The historical saved failures occurred before the intended
safety cancellation injection, so they do not demonstrate that separate window.

The historical 819.267-second and 2223.218-second delays remain unexplained. The
fixture defect is proven, but neither a causal explanation for both delays nor
a production bug is claimed. Preserve the earlier reports and finite diagnostic
records. Current passing regressions do not erase those limits.

## Requested B review

Please review the test-only wrapper repair, preservation of registered cache
identity/forwarding, unchanged assertions and the per-case evidence. The prior
request to rerun four cases on the old source is superseded. Preserve any old
results already obtained; do not repeat whole-project or live tests for this
small repair. No main merge or live safety enablement is implied by this report.
