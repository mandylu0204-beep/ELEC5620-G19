# A47 profile correction and return flow

Date: 2026-10-17 (Australia/Sydney). This frontend-only change is isolated from the pending A45/A46 safety integration on feature/a47-profile-return, based on main 012929b.

A correction visit now offers Save and return to plan, preserving the separate save-only action. Navigation occurs only after a successful profile save. The plan displays a saved-profile notice pointing to the existing latest-profile replanning preview; saving a profile does not confirm a request or dispatch a workflow automatically.

Tent guidance compares confirmed quantity times capacity against the current group size rather than treating the previous person-space requirement as a count of tents. Other saved shortage quantities are explicitly described as previous-check values to be recalculated by replanning. The correction summary no longer claims blank equipment rows were added whenever an existing field was edited. Formal assessments and eligibility remain server-owned.

Validation: 40 frontend tests passed, including a regression for changed tent capacity, unconfirmed inventory, changed group size and multiple tents. TypeScript/Vite build and diff whitespace check passed. No backend source, schema, database migration or safety policy changed.

Browser acceptance used a new isolated SQLite database, actual auth and production deterministic rules with sealed 2.1 synthetic evidence. Initial plan had one confirmed one-person tent for two people, a tent/groundsheet shortage and unknown additional-gear cost. The browser followed the actual correction link, changed tent capacity to two, observed the false tent-count highlight disappear, saved and returned to the original plan, opened replanning preview, checked preserved dates/budget/preferences and the latest two-person tent snapshot, then explicitly confirmed replanning. The new plan passed logistics/safety, estimated AUD251, and was eligible for final save. The original plan was retained. No final save was performed. Console errors: none. Campus calls: zero.

Local screenshots: var/a47-saved-return.png and var/a47-replanned.png. Temporary acceptance services and browser tab were stopped. Existing user data, personal configurations and sealed datasets were untouched. This is not live safety-model acceptance, Canvas deployment acceptance or a GitHub CI result.
