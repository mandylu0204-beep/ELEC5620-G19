# Windows planning recovery test fixture repair

Base: `ffc28dcf234df17b643c6c3b28c2e5353cab17fb` (PR #10 merge).

## Failure and repair

`test_planning_details.py::test_http_save_final_revision_reassessment_recovery_and_restart`
previously exceeded the existing 30-second wait after starting REVISE. Its last
full-detail read reported `RUNNING/ROUTING`; the isolated database subsequently
contained a successful revision. That last observed stage does not establish
where the entire wait was spent.

The shared fault-injection helper `wrap_port()` hid the registered factory's
identity and discarded `parsed_snapshots` and `snapshot_key`. Runtime therefore
correctly used its legacy factory path, repeatedly rebuilding the Adapter.
The test-only repair uses `@wraps(original)` and forwards `**options` unchanged.
Port fault injection and all existing assertions remain active. No production
code, wait deadline, lease, model parameter or safety guard changed.

## Native Windows offline verification

- New forwarding regression before the helper repair: 1 failed, exit 1. The
  failure verifies that the old helper lost the parsed snapshot options.
- Forwarding and factory compatibility checks after repair: 3 passed, no
  failures/errors/skips, exit 0. Legacy two-argument factories remain supported;
  an internal factory TypeError is neither swallowed nor retried.
- Complete `test_model_logistics_wiring.py` plus the original failing planning
  case: **50 passed, 0 failed, 0 errors, 0 skipped**, exit 0, 117.861 seconds.
  The original planning case took 20.149 seconds across all its phases. This is
  not a measurement of an individual wait or model request.
- The three-case boundary group overlaps the 50-case group by one case; counts
  are not added. These results are targeted regression, not a backend full run.
- All tests used MockTransport with real httpx transports blocked. Campus model
  calls and cloud CI runs: 0. The user's configuration and database were untouched.
- JUnit records are retained under the isolated review checkout's `var/` as
  `planning-fixture-before.xml`, `planning-fixture-boundary.xml`, and
  `planning-fixture-windows-regression.xml`.

The fixture deviation is proven and the original test passed in this run. This
does not establish the cause of every historical Windows delay or campus proxy
failure.

## Combination with the UI follow-up

B's UI follow-up `767fc43` changes no backend files. Its two presentation fixes
were independently reviewed with 205 frontend tests passing, TypeScript and
Vite build passing, and no live calls. The combined checkout preserves the exact
backend fixture bytes used by the 50-case Windows run (SHA-256
`1c4a47db2969354258ce7e43528189f752146981076ea4ba5164cf55cffff344`).
The backend suite was not rerun merely for this frontend-only follow-up. These
separate checks are not a new full-system or live-browser acceptance run.
