# A33: owner-controlled plan deletion

The My Plans cards now offer an inline delete confirmation and cancel action.
Deleting removes the card and denies subsequent owner reads, including run and
final-snapshot links. Failed requests retain the card and show the error.

DELETE /api/v1/plans/{plan_id} requires the existing session, client header,
CSRF token and CAMPER ownership. Missing, foreign and deleted plans return 404.
Any PENDING/RUNNING run prevents deletion inside the same write transaction.
Deleted plans also leave reviewer queues and reject further review submission.

Schema migration 8 adds nullable plans.deleted_at. This is a logical deletion:
immutable assessments, model audit records and final snapshots remain internally
stored for integrity; this operation is not personal-data erasure. Old profiles,
requests and historical artifacts are retained. Migration runs on normal startup;
the implementation tests use isolated databases, not the user's database.

Validation: frontend TypeScript/Vite build passed; plan/storage suite 28 passed;
deletion and historical-upgrade selection 9 passed (three deletion cases overlap
the first run). No model calls. Browser interaction has not been independently
verified for this change. Local implementation only; not pushed to GitHub.

Coordination: A34 subsequently reserves migration 9 for request deletion. Safety
storage must allocate migration 10 or later on this combined shared baseline.
