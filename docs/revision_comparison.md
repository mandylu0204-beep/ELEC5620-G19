# Revision comparison and camper selection

The web application creates revisions through `POST /plans/{plan_id}/revision-proposals`.
The existing `/revise` API remains compatible with older clients. Both use the same
confirmed input, revision guards, model roles, persistence ports and audit validation.
The cheaper-campsite preflight runs before either endpoint creates a task.

Database migration 13 adds proposal origins and idempotent choice receipts. The
selected `plans.active_run_id` and `current_version_id` remain the original values
while a candidate runs. A pending proposal grants execution access only to its
registered candidate run, on the same owned plan and unchanged selected origin.
Checkpoint recovery, heartbeat and late-write fencing apply to that execution.
Startup recovery also discovers pending candidate runs.

An owner can choose ADOPT or KEEP after generation has ended. ADOPT requires a
successful completed run, its own two assessments, routing receipt, valid model
audits, current runtime context and matching proposal/run revisions. It switches
the selected pointers atomically with the decision and command receipt. It does
not finalise the plan or transfer any approval. KEEP leaves the selected pointers
unchanged. Failed candidates cannot be adopted. Closed candidates cannot write,
resume or overwrite the selection. History and immutable saved finals remain.

While a choice is pending, other revisions, reassessments, successor requests,
review submissions and finalisation are blocked. Owner-scoped reads still show
the original plan; lightweight progress identifies the separate candidate.
Existing successful revisions gain a read-only comparison, without retroactively
creating a choice or changing selected records.

Comparison values come from the two runs' saved logistics assessments, not model
prose or current catalogue prices. Campsite savings and whole-trip savings are
separate. Missing totals or prices remain unknown. Safety outcomes are displayed
beside the fee comparison. This workflow needs no additional model calls when
reading a comparison or making a selection.
