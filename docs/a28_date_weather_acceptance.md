# A28 date and weather flow acceptance

Date: 2026-10-16, Australia/Sydney. Base: main `848fc29` plus the local A27
user-journey improvements. This acceptance uses real frontend interactions,
FastAPI, rule agents and an isolated SQLite database. No campus model requests,
real weather API requests, Canvas package build or clean-install acceptance were
performed in this round.

## Observed browser results

1. Login from `/profile` returned to `/profile`, preserving the original
   destination. The optional editable profile sample worked with dataset 2.1.
   Equipment quantities were edited in the UI and explicitly saved.
2. The user's 2026-10-22 through 2026-10-26 request (two people, four nights,
   AUD 1000, quiet and ready-to-eat meals) passed date interpretation and
   confirmation. Version 1 selected Demo Wattle Rest, estimated AUD 407, and
   retained the itinerary. Weather remained unavailable for the whole trip;
   other source types were available. The page showed the 2026-10-16 checking
   date, forecast through 2026-10-22 and a suggested recheck on/after 2026-10-20.
   Finalisation remained unavailable.
3. Changing the copied request to 2026-10-18 through 2026-10-20, two nights,
   generated a separate request and plan without hidden derived-date conflicts.
   Logistics and safety passed, estimated AUD 251, and the user acknowledged
   and saved an actual immutable final snapshot through the browser.
4. A 2026-10-15 request was rejected with an explicit Chinese message naming
   the actual checking date (2026-10-16, Sydney). Confirmation was disabled.
5. Same-day reassessment of the four-night plan created a new successful run
   and new assessment IDs, retaining the same itinerary/version and snapshot.
   The page explicitly reported that the completed check matched the previous
   result; the unresolved forecast interval remained unresolved.

Read-only SQLite evidence is recorded in
[`evidence/a28-browser-results.json`](evidence/a28-browser-results.json).
Browser console inspection reported no errors during these flows.

## Screenshots

* [Future trip retained](evidence/a28-current-date-future-trip.png)
* [Forecast interval and suggested recheck](evidence/a28-weather-coverage-guidance.png)
* [Near-term final snapshot saved](evidence/a28-current-date-normal-final.png)
* [Past-date validation](evidence/a28-past-date-validation.png)
* [Same-day reassessment completed without fabricated coverage](evidence/a28-same-day-reassessment.png)

## Related user-journey fixes

The local A27 work found that Chinese structured labels for quiet/ready-to-eat
meals reached English business rules without translation. Known structured
labels now map to existing canonical terms; unknown, negated and compound
requirements remain intact. Raw prose is not reinterpreted by this UI mapping.
Accessibility-specific meaning is preserved. Confirmation displays readable
labels and the stored canonical values are visible in the SQLite evidence.

Login restores a role-appropriate internal destination. The final-save panel
shows a processing state during active planning/reassessment. Known synthetic
itinerary boilerplate is translated for the current Chinese preview without
rewriting stored itinerary content. User-supplied optional days/end dates remain
explicit constraints; automatically derived values are not copied into hidden
editable constraints. The final English conversion remains a later task.

## Data, recovery and operational boundaries

See [current date and snapshot behavior](current_date_and_daily_snapshots.md).
The original data packages, personal `.env`/`.env.llm.local` and the user's
application database were not modified. No shared DTO or database migration was
required. The ordinary service on ports 8000/5173 was not stopped or restarted.
Independent acceptance services on 8760/5360 and the temporary browser tab were
closed after verification.

No additional B interface implementation is required to run this change.
The generator builds independent simulated inputs using the existing adapter
and selector. Historical fixed scenarios remain available via the explicit
fixed/sealed mode, including `scripts/demo.py`.

## Final validation

The complete backend suite was partitioned by file across three independent
pytest processes, each with separate temporary databases and pytest caches.
JUnit aggregation verified 925 unique cases: **881 passed, 44 skipped, zero
failures/errors**. All skips were existing Windows symbolic-link cases that
could not create their test links because of WinError 1314; they are not claimed
as passing. The 14 new daily-clock/recovery/guard cases all passed. Existing
fixed-date tests now explicitly select fixed mode where that is their intent.

Frontend: 7 tests passed; TypeScript and production build passed. Shared schema
export remained unchanged. The sealed v2.1 generator byte comparison passed;
static release validation passed 24 checks and 600 weather coverage queries.
`git diff --check` passed. The known FastAPI TestClient deprecation warning is
unchanged; no dependency upgrade was included.

Machine-readable totals:
[`evidence/a28-validation-summary.json`](evidence/a28-validation-summary.json).
