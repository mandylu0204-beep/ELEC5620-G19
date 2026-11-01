# Compact safety v4 runtime integration

## Selection and identity

Default safety remains `rules`. Model safety's `standard` protocol selects v3
for dataset 2.2 and v2 for dataset 2.1. `CAMPMATE_SAFETY_PROTOCOL=compact` selects
v4 and requires agent mode, model safety and dataset 2.2. Unsupported combinations
fail before inference. The Sydney launcher accepts `--safety-protocol compact`.
See the [README](../README.md) for the complete startup command.

V4 registers agent/tool/validation version 4 and the exact
`safety-lossless-facts-1` codec seed. Role seeds are collected before composing the
final workflow identity. Prompt, kernel, dataset rules, source digests, client and
configuration identities participate. Unknown codecs and mixed registrations
are rejected. Frozen replay implementations remain unchanged.

## Persistence and recovery

The formal safety assessment remains the complete deterministic result. Model
advice cannot change risk facts, restrictions, required human review or final
eligibility. Assessment, audit and receipt use the existing atomic save contract.
V4 has a separate registered replay dispatch.

Recovery rebuilds the original protocol and snapshot date, checks the registered
role/configuration/source identity, and reuses saved artifacts. It does not call
a model to replace missing trace evidence. Current eligibility and final saving
resolve the current configuration and checking date separately. Advancing the
date or changing protocol cannot authorize an older assessment.

## User-facing advice

Advice is presented alongside the official checks, with controlled action codes
and verified references. It does not replace the authoritative safety result.
Founder approval is tied to the exact eligible run/version. Missing evidence,
closures and hard blockers cannot be approved away.

## Validation boundaries

The maintained offline regression covers protocol selection, identity, replay,
model/rules logistics combinations, persistence, receipt loss, user isolation,
PLAN/REVISE/REASSESS and current-date guards. Tests use MockTransport; they do not
contact the campus proxy. Historical acceptance reports are retained in Git
history and apply only to their own source/environment.

Do not infer that an earlier 502 has been eliminated from an offline result.
Live acceptance requires an explicit call budget, stops at the first error and
must not repeat PLAN unnecessarily. Use the documented 4096/low configuration;
smaller output limits have produced truncated safety responses. No model or
cloud request is authorized merely by reading these instructions.
