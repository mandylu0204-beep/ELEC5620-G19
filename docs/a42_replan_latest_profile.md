# A42 replan from the plan page with the latest saved profile

Date: 2026-10-17. Base: A41 02d0f5d.

An idle, active camper plan now offers a prominent replan action below its
overview. It preserves the plan's confirmed destination, dates, duration, budget,
preferences and mandatory constraints. The application copies the original raw
request and confirmed requirements through the existing request APIs, generates
a fresh authorised summary using the latest saved profile, and displays that
summary on the same plan page. The user does not re-enter the request fields.

The user must explicitly acknowledge the displayed requirements and latest
profile before the existing confirmation and planning endpoints are called.
Server ownership, profile revision, dataset/clock staleness, clarification,
availability and eligibility guards remain intact. Missing information still
leads to an editable prefilled request; there is no automatic waiver or assumed
inventory. This creates a new plan and preserves the original plan and its
confirmed snapshots. It is distinct from same-itinerary reassessment.

Profile links from a plan retain the source plan/request. After explicit profile
save, a return link takes the camper straight back to the plan's replan action.
No new backend endpoint, schema, storage migration or model role was added.

The controller retains the prepared request and stable confirmation/planning
command keys after failed-response retries. Reopening an unconfirmed preview
regenerates the summary using current saved profile data. A synchronous UI lock
prevents double-click submissions. Merely displaying a plan causes no request
creation, interpretation, confirmation or planning. Reviewer, historical-run
and saved-final snapshot views do not offer the action.

Validation: 37 frontend tests passed, including four workflow tests covering
exact requirement retention, no implicit confirmation, lost confirmation/plan
receipt retries, refreshed profile snapshots and clarification rejection.
TypeScript/Vite build and diff check passed. No backend implementation changed;
no new full backend regression pass is claimed.

Browser verification used isolated SQLite and rule-only services at 8791/5391.
From an incomplete original plan, the profile's route was changed from 100 to
120 km and explicitly saved. The profile returned straight to the original
plan. Replan preview retained November 6-8, two nights, AUD 320 and quiet/
ready-to-eat preferences while showing the newly saved 120 km and confirmed
vehicle capacity. Confirmation was disabled until acknowledgment. No request
fields were typed again. The browser then dispatched a new plan through the
existing HTTP workflow. It completed with passed safety, ready-to-save status
and AUD 258 estimated cost, reflecting the changed route rather than reusing
the prior 100 km/AUD 251 result. Browser console errors: none.

Preview screenshot: `evidence/a42-replan-preview.jpg`.
Result screenshot: `evidence/a42-replan-result.jpg`.
Personal configuration, user database and sealed data were not changed. No
campus model calls were made.
