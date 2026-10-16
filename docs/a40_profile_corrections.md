# A40 guided profile corrections

Date: 2026-10-17. Base: A39 1cb010f.

The actionable-issues panel now has one profile link in its upper-right header,
instead of repeating that link under every item. Requirement changes and safety
data remain separate destinations when relevant. Historical/in-progress views
remain read-only.

The profile page fetches the authorised source plan's issues and checks the
request association. All known missing equipment types are prepared as blank
draft rows together. Existing input is retained; quantities/capacities are not
guessed, confirmation remains false, and saving requires an explicit user action.
Source-data problems do not create equipment rows. Failed issue loading has a
retry action that preserves edits.

Relevant inputs and equipment cards are marked red with field-specific hints.
The hints clear as the user fills the corresponding fields. Vehicle guidance
distinguishes available car count, seats per vehicle including the driver,
confirmed availability, matching transport count and total trip kilometres.
Tent capacity, quantities, units, confirmation, children and experience have
their own guidance. Zero stock remains an honest answer, not an invented fix.
These hints do not replace server assessment or relax eligibility rules.

After explicit saving, the return link opens an editable copy of the original
request for review and confirmation with the updated profile. Existing confirmed
snapshots are not silently rewritten. The long list of top-level equipment jump
buttons is replaced by a first-incomplete-field action.

Validation: 29 frontend tests passed, including nine new navigation/guidance
tests. TypeScript/Vite build and git diff check passed. Browser validation used
isolated SQLite data and rule execution on ports 8791/5391: the source plan
missed tent capacity, vehicle, sleeping bag and sleeping mat; one header link
prepared every missing row, focused tent capacity, and displayed red field hints.
Entering real fixture values cleared the red fields; explicit save, return to a
copied request, summary generation and re-confirmation succeeded. Planning from
that confirmed request completed with passed safety, AUD 251 estimated trip cost,
no equipment-correction panel and the ready-to-save status. No browser console
errors were recorded. Result screenshot: `evidence/a40-corrected-plan.jpg`.
Correction screenshot:
`evidence/a40-vehicle-guidance.jpg` (before completing the vehicle fields).
Personal configuration, existing user database and sealed datasets were not
changed. No campus model calls were made. Backend implementation is unchanged;
no new backend regression run is claimed for this UI change.
