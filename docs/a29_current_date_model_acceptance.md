# A29 current-date campus model acceptance

Date: 2026-10-16, Australia/Sydney. Source: main `fb8c8ce`.

The application used the actual Sydney clock, dataset 2.1, daily synthetic
snapshots, real campus planning and logistics models, and an isolated SQLite
database under `var/a29-live`. Private configuration, existing user databases
and sealed source data were not modified. Process-only model settings were
4096 completion tokens and `reasoning_effort=low`, as in the previous successful
A26 acceptance. These results do not validate the private 2048-token settings.

## Results

| Flow | Observed result |
| --- | --- |
| PLAN, October 18–20 | Wattle Rest, version 1, AUD 251; logistics and safety passed; complete trip coverage. |
| Explicit browser final save | Acknowledged and saved version 1; immutable final page displayed the saved plan. |
| REVISE, cheaper campsite | Moonlit Field, version 2, AUD 231; new planning trace and logistics audit; logistics and safety passed using the newly selected campsite. |
| REASSESS | Version 2 and itinerary content unchanged; original planning trace exactly unchanged; new assessment records and independent logistics audit. The browser displayed completion time and unchanged itinerary. |
| PLAN, October 24–26 | Itinerary retained, forecast coverage October 16–22, weather `OUTSIDE_VALIDITY`; other safety source types applicable. The browser suggested checking on/after October 20. Finalisation HTTP 409 and disabled save control. |
| Backend restart | Current main plan and historical final snapshot read back exactly; no additional model calls. Camper B received 404 for Camper A's plan and final snapshot. |

The four operations were initiated through actual HTTP endpoints. Browser
coverage includes login, plan list/detail, equipment and budget suggestions,
reassessment feedback, weather coverage guidance and explicit normal final
save. This is not a claim that all request entry and revision actions were
performed in the browser.

There were **18 real campus HTTP requests, all returning 200**: normal planning
5, revision 5, reassessment 3, future planning 5. No model responses were mocked,
replaced or forced to select a campsite. The response reported
`Qwen/Qwen3.8-27B-FP8`; this does not independently attest model weights.
AUD 251 and AUD 231 are synthetic trip estimates, not API charges.

The acceptance transport recorded only request counts, HTTP status and elapsed
time; it imposed a 24-request cap and stopped further transport after a network
or HTTP failure. Neither guard triggered. Normal application retry and parsing
rules were not weakened.

The reused sealed-dataset harness initially expected `NOT_YET_OBSERVED` for the
future trip. Daily snapshots correctly returned `OUTSIDE_VALIDITY` with the
forecast interval and uncovered trip dates. The local harness assertion was
corrected and the already saved result and HTTP finalisation guard were checked
without repeating model calls. No product change was needed for this mismatch.

Final database counts: 4 runs, 3 versions, 8 assessments, 4 gear checklists,
3 planning traces, 4 logistics audits and 1 final record.
SQLite integrity was `ok`, with no foreign-key violations. Browser console
inspection returned no error entries.

## Evidence and limits

- [Sanitised machine summary](evidence/a29-live-campus-check.json)
- [Normal final snapshot](evidence/a29-live-normal-final.png)
- [Completed reassessment](evidence/a29-live-reassessed.png)
- [Future weather guidance](evidence/a29-live-future-coverage.png)

This round did not perform a new full regression run: the unchanged source
already passed main CI with 925 backend tests, schema verification and frontend
tests/build. It did not test a midnight transition against the live model,
perform a controlled lost-receipt recovery, integrate a model safety role, use
real weather services, create a Canvas ZIP or perform clean-install acceptance.
Those claims must not be inferred from this report.

Temporary acceptance services were stopped after verification. The independent
local database and raw acceptance files remain untracked for investigation.
