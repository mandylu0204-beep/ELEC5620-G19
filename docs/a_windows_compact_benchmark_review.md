# Native Windows review of B's compact benchmark fix

Date: 2026-10-26, Australia/Sydney. B patch: `350a033` on `57bbdc0`.
Combined source: `ca15292` on A's `d223b74`. The cherry-pick retains B's authorship
and records the source commit. Main is unchanged.

## Review and native checks

The Runner creates its event loop before network interception starts. Fixture
loading and both model comparisons then execute under the connection and real
HTTP guards. The explicit `runner.close()` remains inside those guards, covering
task cancellation, async-generator finalisation and executor cleanup. The outer
context's second close is idempotent. No arbitrary localhost exception is added.

A independently ran the exact B source in a separate checkout on native Windows
with Python 3.12.14: **87 passed, 0 failed/errors/skipped, exit code 0**. This
includes the 24 benchmark lifecycle/guard cases and 63 compact component cases.
The real HTTP test guard recorded zero unexpected hits.

The benchmark CLI also exited zero on that exact source. All parsed public
fixture metrics and all six request digests match the original archived public
comparison. Second request sizes remain v3 **17,321** and v4 **12,481 bytes**.
This is the public fixture, not B's private Euroka input. Complete deterministic
results, expanded advice and lossless fact projection remain equal. Fake usage
is not treated as a token or cost measurement.

A then applied the patch to the integration branch and ran the same bounded
scope on native Windows: **87 passed, 0 failed/errors/skipped, exit code 0**.
The benchmark and its new test file are byte-identical Git blobs to B's patch.
These are two runs of 87 cases, not 174 distinct cases. Existing Starlette/httpx
deprecation warnings remain; no dependencies were changed.

Shared summary: [native Windows evidence](../evidence/a-windows-compact-benchmark-review.json).
Local JUnit and CLI outputs are preserved under the integration checkout's
ignored `var/` directory.

## Limits and next boundary

This closes the Windows benchmark portability gap only. The patch changes no
production model parameters, prompt, schema, identity, runtime registration,
database, personal environment or default rules setting. No campus calls or
cloud tests were started, and no saved application run was operated on.

The prior integration report remains valid as a separate, incomplete regression:
one legacy 2.1 lease-related failure is unresolved and 37 selected cases were not
executed after that failure. Neither count is erased by these benchmark passes.
The integration branch is still **not ready for main**. This work does not
establish stable resolution of HTTP 502 or replace formal live runtime acceptance.
