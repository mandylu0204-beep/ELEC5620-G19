# Compact safety v4 runtime integration

Base: B's `57bbdc0`, on main `0c56764`. Integration branch:
`feature/safety-v4-integration`. This document describes A's integration, not a
new standalone campus diagnostic. B's original evidence remains archived as-is.

## Selection and identity

Default safety remains `rules`. For model safety, the default `standard`
protocol still selects v3 for dataset 2.2 and v2 for dataset 2.1. The new
`CAMPMATE_SAFETY_PROTOCOL=compact` explicitly selects v4 and requires agent mode,
model safety and dataset 2.2. Unsupported combinations fail before inference.

The Sydney launcher forwards `--safety-protocol standard|compact`. Its existing
mode, logistics and safety arguments remain unchanged. No personal environment
file is edited by the launcher or this integration. The compact option is not
enabled in the user's ordinary application configuration.

V4 registers agent/tool/validation version 4 plus the exact
`safety-lossless-facts-1` codec seed. All role seeds are collected before the
final workflow identity is composed. Prompt, kernel, dataset rules, source
digests, model client and configuration identities still participate. Unknown
codecs and mixed v3/v4 registrations are rejected. No v3 prompt or frozen replay
implementation is rewritten.

## Persistence and recovery

The formal safety assessment is the complete deterministic result; compact
advice does not change risk, restrictions, human review or final eligibility.
The existing save signature, audit envelope 1.0, database tables, atomic save
and receipt contracts are retained. V4 gets its own registered replay dispatch.

Checkpoint recovery rebuilds the originally registered protocol and, for daily
data, its original snapshot date. It still checks the current role switches,
client configuration, source bytes and the complete scope identity. Current
eligibility and finalisation resolve the current configuration/date separately.
Selecting a different protocol or advancing the checking date cannot authorise
an older result as current.

Committed planning/logistics/safety artifacts are reused after restart or lost
receipt. Before-commit failures may repeat only the unsaved safety step. Missing
or corrupt saved audits remain terminal persistence failures and never cause
model regeneration, rule fallback or manufactured traces.

## User presentation

The server derives `single-advice-v1` from the validated v4 trace; query strings
and model prose cannot select this format. Ordinary users receive the bound
advice without internal traces or configuration identifiers. Founder diagnostic
access remains governed by the existing role checks.

V4's one sentence occupies both compatibility fields in storage. The page
renders it once per finding, rather than suggesting two independent model
statements. Unknown formats or inconsistent compatibility fields are rejected
by the presentation parser. Legacy v1/v2/v3 advice retains its original format.

## Local verification

Validation details and final counts are recorded in the accompanying integration
evidence. All runtime checks use real application/factory/workflow/SQLite code
with MockTransport model responses and a real-HTTP rejection guard. The original
database, sealed data and personal settings are untouched. Tests use short,
separate temporary paths under this worktree's `var/` for Windows compatibility.

The isolated browser fixture covers an owned plan, independent safety advice,
one visible copy of a compact sentence, final save, final readback after opening
the page again and rejection of the same final URL for another Camper. It uses
a new SQLite database and daily snapshot; after fixture seeding, all model calls
are disabled. Browser results are offline integration acceptance, not live model
acceptance.

## Remaining boundary

This integration does not establish that 502 has been eliminated. B's earlier
three-response v4 standalone success does not certify formal runtime persistence
over the campus network. Any bounded live integration acceptance is a separate,
explicitly authorised step. Do not repeat a complete normal PLAN by default or
change an old failed run's registration to v4. The normal token budget remains
4096/low; B's recorded second completion used 2565 tokens.

B's Windows benchmark guard portability fix can be reviewed independently; the
integration does not relax that guard or change the benchmark measurements.
No cloud CI or campus requests are part of A's work here. Main is unchanged.
