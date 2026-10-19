# A64: bounded live safety recovery acceptance

Date: 2026-10-20, Australia/Sydney. Result: **live recovery succeeded in an isolated copy**.

## Authorization and scope

The initial launch was rejected by automatic approval review because the previous
generic continuation was insufficient authorization for credential use and sending
historical trip/safety context. It made zero requests and created no round marker.
The user then explicitly approved the described four-request safety-only round.
Exactly one live recovery was executed after that approval.

Runtime and frontend source: `05568f0672c62bd2ad26d861f1ad1d3092d4be91`.
Recovery controls: `617051f`; offline integration evidence: `7a686ef`.
The original A46 failure was restored with sqlite3.Connection.backup from the
retained consistent export, with matching snapshot files, into a new local
acceptance database. The original database was not retried or modified.
Public model parameters, prompts, validators and identities were unchanged.

## Real requests

| Safety turn | Sydney start (+11:00) | Body bytes | HTTP | Complete seconds | Request ID |
| --- | --- | ---: | --- | ---: | --- |
| Read facts | 2026-10-20 09:43:25.782588 | 6382 | 200 | 1.203 | req_85fe3d71395c4f56ade267b0678cdc1e |
| Evaluate | 2026-10-20 09:43:26.988414 | 17014 | 200 | 27.531 | req_216de45015734c6ba28e8fbe263e08b1 |
| Final | 2026-10-20 09:43:54.528901 | 22232 | 200 | 10.953 | req_a77c9aed4575410b8225906cc626a301 |

Three actual upstream dispatches, maximum four, no blocked transmissions or
retries. The second body digest equals the A53/A60 candidate anchor. The unchanged
SafetyAgent completed its read/evaluate/final validation and pure replay, then
the real authenticated HTTP retry/dispatcher and RecoveryPort saved the result.
Saved trace: SAFETY, turns=3, http_attempts=3, validation_passed=true. Reported usage:
13002 prompt + 3668 completion = 16670 total tokens, not a monetary charge or
remaining-quota measurement. No planning or logistics model calls were made.

## Persistence, restart and permissions

- Retry HTTP 202; original run in the isolated copy reached SUCCEEDED / COMPLETED.
- One safety assessment and one safety audit were saved, linked to the original
  logistics assessment. A safety write receipt was present. Recommendations,
  version, logistics, safety and route receipts are present after completion.
- Original version ID/content/creation metadata, planning trace, logistics
  assessment/audit and run-version binding remain identical. Version status and
  revision changed through the normal assessment workflow; they are not claimed
  to be byte-identical to the failed version row.
- Fresh app construction/lifespan, authenticated HTTP readback 200, both assessment
  kinds and audit validation succeeded. Receipt count stayed unchanged. Another
  camper received 404. SQLite integrity passed and foreign-key violations were zero.
- No final record was written. No lost-receipt fault injection or additional
  recovery was performed. Completion proves the exercised checkpoint reuse/save
  path, not every possible crash/lease timing condition. Individual heartbeat
  timestamps were not separately recorded.

## Date and browser acceptance

Clock mode remained current: October 20. Registered snapshot is October 17 and
trip starts October 18. Pinned historical recovery is allowed by the existing
runtime path; current-scope validation correctly returned STALE_CONTEXT before
and after recovery. No date, scope or finalisation guard was bypassed.

The frozen frontend was opened against a restarted local backend using a dummy
key with all model completions disabled. Browser login and viewing were the only
actions. The original campsite, itinerary and AUD 251 estimate loaded. The safety
tab displayed the rule result separately from the saved AI advice, marked the
advice as historical/reference information, and kept final save disabled. No new
planning, revision, reassessment or finalisation action was clicked.

Local screenshots remain under `var/a64-live-recovery-20261020/`; they include
model advice text and are not included in shared Git evidence. Temporary browser
and acceptance servers were closed after inspection.

## Evidence and next step

Sanitized machine report: `evidence/a64-live-safety-recovery.json`. No database,
session, key, complete prompt, raw reply, advice values or trace body is shared.
The checked private runner remains local; B can review public controls and the
execution record but must not claim an independent rerun of private artifacts.

Please review these real acceptance results. The safety integration is **not
merged into main** by this report. This success does not explain prior 502,
network failures or A57's discarded invalid output, prove quota availability,
or make the historical trip eligible for current finalisation. No additional
campus request is authorized by completing this round.
