# Request understanding before confirmation

The managed `agent` runtime now uses the existing Planning Coordinator to
interpret Chinese and English request conditions when the user generates a
summary. It combines the camping idea, preference text and mandatory-condition
text. It does not add another business agent.

The interpreter requests one JSON completion through the existing campus client.
The client's configured attempt, timeout and token limits still apply. There are
no keystroke requests, readiness probes, tool loops or automatic rules fallback
after a failed interpretation. Offline tests use MockTransport only; this change
has not yet been validated against a live campus completion.

## Confirmation flow

1. Keep the user's original wording in the request. The browser no longer
   translates free-text lists into canonical terms before sending them.
2. Supply numbered source clauses to the model. The local output protocol binds
   each clause and evidence quote to its original input; it rejects fabricated
   quotes, missing source records, extra fields and unknown canonical terms.
3. Project verified proposals to the existing `InterpretRequestResult` schema.
   Clear scalar controls such as dates and budget remain authoritative. Profile
   group size and transport facts remain owned by the saved profile.
4. Show preferences, mandatory conditions and unresolved questions in the
   summary. Empty dedicated text boxes do not erase requirements still present
   in the camping idea. To remove such a condition, edit the original wording
   and generate a new summary.
5. Confirm the summary explicitly before starting a plan. Unresolved mandatory
   meaning, contradictory requirements and unverifiable facility details remain
   unconfirmed; model confidence is not confirmation.

For example, a mandatory entry `need a shower` can become `showers`; `prefer showers`
is a preference; `do not need showers` must not produce a positive shower
requirement. Hot or private showers cannot silently become ordinary showers.
Unknown soft preferences remain visible as unverified preferences. A soft
preference to avoid campfires must not become a mandatory fire prohibition.

Candidate filtering remains deterministic. A mandatory facility still requires
an explicit positive fact, rather than an unknown value. Quiet-hours policies
are not guarantees of actual quietness. Near-match comparisons continue to
explain gaps without automatically relaxing the user's conditions.

## Identity, persistence and compatibility

Request interpretation has a separate prompt, protocol, validation and term-map
identity. A bounded observation stores public identity, allowed token counts,
attempt count, input digest and analysis revision inside the existing summary
JSON column. It contains no key, endpoint, complete prompt or raw response and
is removed from ordinary HTTP presentation.

Confirmation checks the new summary's identity and input association. Existing
revision, ownership, profile, dataset and date guards still apply. Editing while
analysis runs prevents its older result from replacing the new input. Failures
return the request to an editable draft.

The shared schema, database tables, planning trace identity, workflow context,
Hybrid version and logistics/safety audit identities are unchanged. Historical
confirmed requests and checkpoint recovery do not invoke this interpreter or
generate replacement records. Legacy direct Hybrid construction retains its
explicit rules interpretation; the production managed factory installs the new
model capability.

## Running

Use the existing original project directory and the existing campus settings:

```powershell
$env:ELEC5620_MAX_COMPLETION_TOKENS="4096"
$env:ELEC5620_REASONING_EFFORT="low"
& .\.venv\Scripts\python.exe scripts\sydney.py --mode agent --logistics model --safety model
```

Restart the backend after changing source. For an unconfirmed request, generate
its summary again. An already confirmed request uses the existing trip-update
flow rather than changing its immutable snapshot. The default `rules` startup
continues to provide local deterministic behavior; it does not offer general
model language understanding.

## Local verification

The new protocol and lifecycle tests cover quoted bilingual conditions, explicit
scalar priority, empty-list merging, negation and uncertainty, compound hard
conditions, facility qualifiers, independent observation metadata, concurrent
users, stale summaries, failure-to-draft, restart and idempotent confirmation.
A production-factory HTTP/SQLite test exercises the actual Coordinator and
CampusModelClient with MockTransport. Missing interpreter binding is rejected.

Existing planning, revision, reassessment, near-match, logistics, safety, audit,
receipt recovery and runtime-isolation regressions were checked locally. The
logistics/safety combination comprises 120 passing cases across its initial
two-case smoke and the remaining 118-case run. The final frontend suite has
121 passing tests; TypeScript, production build and shared-schema checks pass.
These are targeted backend checks and a full frontend suite, not a new full
backend acceptance run. No GitHub Actions or live campus requests were executed.
