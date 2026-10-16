# A34: delete saved requests

Saved requests retain editable drafts and confirmed inputs. Users need not keep
every entry visible. The request history now offers inline Delete / Cancel
confirmation, with isolated busy/error state and removal only after success.

DELETE /api/v1/requests/{request_id} requires CAMPER ownership and the existing
session/client/CSRF checks. Missing, foreign or deleted requests return 404;
ANALYSING requests return 409. Migration 9 adds deleted_requests tombstones,
preserving existing request rows, confirmations and plan references. Deleted
requests cannot be read, edited, interpreted, confirmed or used for new PLAN
operations. Existing plans retain confirmed snapshots, audits and access;
REVISE/REASSESS continue using their existing trusted request context.

Deletion is logical removal, not erasure of internal historical records.
The confirmation explicitly states that existing camping plans are retained.
Restarts preserve removal. No user database was used by implementation tests.

Frontend TypeScript/Vite build passed. Request deletion, requests and plan
deletion regression results: var/request-delete.xml. No model calls or GitHub
push. Browser interaction has not been separately verified.

Safety integration must use migration 10 or later on this combined baseline:
A33 reserves 8, A34 reserves 9.
