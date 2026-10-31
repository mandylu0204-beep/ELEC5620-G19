# Logistics envelope correction

## Observed failure

The local run `2fbbd70ca81e44878838874f75ec5488` failed during logistics on
2026-10-31 at 14:02 Sydney time. Stored structural diagnostics identify a
missing root `name` and a forbidden `arguments.name` in the second response.
The original rejected response was not retained, so its complete contents
cannot be reconstructed. This change does not claim to reproduce that response
or explain historical proxy 502 failures.

## New execution policy

New registrations use `campus-logistics-agent-2`. Each phase supplies a
`next_action` envelope template. The prompt explicitly places `action`, `name`
and `arguments` at the same root level. Templates and the fixed correction
instruction participate in the prompt identity.

One format correction is permitted only when:

- Facts have already been read and no proposal has been evaluated.
- Strict JSON decoding succeeds, with no duplicate keys or nonfinite values.
- The root is exactly `action` and `arguments`, with `action="tool"`.
- `arguments` contains exactly the three proposal fields and
  `name="evaluate_logistics_plan"`; the proposal has valid field types.
- No previous correction has been issued in this logistics invocation.
- The existing turn budget leaves room for both a fresh evaluation response
  and a final response.

The application does not relocate the field or adopt the rejected proposal.
It sends a fixed, bounded error description and requests a fresh complete
evaluation action, using the facts already supplied. The rejected raw reply,
unknown field names, and field values are not echoed into this instruction.
The next response must be an evaluation action, not another facts read or an
early final. It must pass the unchanged parser, coverage/allowed-method
checks, deterministic calculations, and final-proposal equality check.

Ordinary missing fields, unknown tools, malformed JSON, invented numeric or
confirmation fields, invalid methods, missing gear/cost rows, and unevaluated
finals do not activate this format policy. A second bad envelope stops the
invocation even if unused turns remain. An HTTP error does not activate a
format correction; existing configured HTTP handling remains unchanged.

## Accounting, persistence and compatibility

- No increase to `max_turns`, HTTP attempts, tokens, timeout or leases. At the
  usual four-turn setting, a successful correction consumes four turns rather
  than three; with only three turns available it is not attempted.
- V2 traces require `format_correction_turns` (empty or one turn index).
  All replies, including the rejected one, contribute to response hashes,
  served-model metadata, token usage, turns and HTTP attempts. `tool_calls`
  continues to contain only successfully dispatched tools.
- The registered agent version selects the exact trace shape. V1 archives keep
  their original shape and accounting; they cannot contain v2 correction
  metadata. Unknown versions and missing/mixed trace shapes are rejected.
- Existing assessment/audit/receipt transactions and deterministic recomputation
  remain in force. A saved corrected audit is reused after checkpoint/restart;
  recovery does not call the model to replace an existing trace.
- No shared schema or database migration. Old failed runs and their identities
  are not rewritten. The new policy applies to newly registered executions.

Restart the backend to load the new code. Preserve old failures; use the trip's
existing update/confirmation flow to start a new execution under the new
identity. Do not force recovery of an old scope with a replacement identity.

## Validation scope

All validation for this patch uses offline transports and isolated databases.
No original user database is modified, and no campus or cloud test is run.
The offline scenarios include fresh correction, repeated failure, exhausted
budget, business-rule rejection, identity change, complete accounting, v1/v2
replay boundaries, atomic audit storage and lost-receipt restart reuse.
Live model reliability still requires a separately authorized bounded test.

A read-only check against five existing local v1 logistics audits also passed
with the new verifier. Their trace shapes were unchanged; this check created no
application instance and performed no database writes or model calls.

The initial combined component, cost-priority, diagnostic, persistence and
runtime-wiring regression passed 206 tests, with zero failures, errors or skips.
After tightening the correction response to evaluation-only and matching the
existing parser's fenced-JSON handling, the final component/diagnostic and
HTTP-restart suite passed 113 tests, also with zero failures, errors or skips.
These overlapping counts are not added together and are not a full backend
suite. The shared-schema and whitespace checks passed. There is one existing
Starlette/httpx deprecation warning. All HTTP replies were mocked; no campus or
GitHub Actions tests were run. Source publication is separate from live model
acceptance; the published patch does not claim that a campus retest passed.
