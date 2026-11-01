# Development and source delivery

Use the [README](README.md) for installation and startup. Each developer keeps
their own environment, credentials, database and snapshot cache. Never commit
keys, sessions, databases, logs, installed dependencies or private diagnostics.

## Application boundaries

The React application calls the FastAPI API. SQLite stores users, confirmed
requests, run checkpoints, versioned plans, assessments, model audits, review
decisions and immutable final snapshots. Camper access is limited to owned
records; Founder access is limited to review and assistance operations.

Shared DTOs, enums and ports live in `backend/app/contracts`. Exported schemas
are in `docs/contracts.schema.json` and `docs/contracts/`. Schema changes require
explicit coordination. Do not change a frozen schema or validator to accept a
previously invalid model response.

Planning selects registered candidates and creates itineraries. Logistics
proposes supply choices; code calculates quantities and costs. Model safety
provides advice while deterministic rules determine the formal safety result.
Missing facts, hard blockers and current-version approval checks remain binding.
Default execution uses rules; enabling models is an explicit startup option.

## Identity and recovery

Register the complete dataset, configuration and role identities before a run.
Save assessments, checklists, audits and receipts atomically. Recovery reuses
saved artifacts and the original snapshot; it must not call a model to invent
missing trace evidence. Reassessment keeps the itinerary and creates new checks;
revision creates a new plan version. Neither inherits authority from an older
review. Final saving validates ownership, current run/version, facts and approval.

Use current Sydney data for new work. Preserve sealed legacy resources and
validators for exact historical replay. New reference content requires a new
version rather than changing old registered bytes. Never pass test oracles or
expected results into production agents.

## Local checks

Use the project virtual environment and independent paths under `var/`. The
commands and verification scopes are described in the README and
[deployment guide](docs/deployment_preparation.md). MockTransport and the offline
HTTP guard are available for model tests. Keep original deadlines, leases,
permissions and integrity checks when investigating failures.

Do not run cloud CI against the owner's exhausted quota. Live campus tests need
an explicit request budget and must be coordinated to avoid duplicate calls.
Record the exact source, environment and actual pass/fail/error/skip counts;
targeted checks do not establish a complete regression result.

## Release maintenance

Keep current instructions and public text in English. Non-English input aliases
and fixtures remain supported. The [language and cleanup scope](docs/source_delivery_scope.md)
lists the necessary immutable resources that retain their original text.
Historical handoffs and screenshots removed from the source tree remain
available in Git history; they are not deployment prerequisites.

Commit intended source changes explicitly, then use `scripts/package.py`. See
the [Canvas checklist](docs/canvas_submission.md) before submitting the resulting
ZIP. Never add the whole working directory or copy an author's runtime data into
the delivery package.
