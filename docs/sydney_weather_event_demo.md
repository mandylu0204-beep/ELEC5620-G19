# Versioned Sydney forecast event

The synthetic weather reference `data/weather/sydney_weather_events_v1.json`
adds heavy rain at Bonnie Vale to the snapshot generated on 2026-11-04. The
forecast covers 2026-11-04 through 2026-11-10, including a two-night trip from
2026-11-05 through 2026-11-07. Its numeric facts are 12–22 C, a rain field of
60 mm and wind of 35 km/h. The rain field is not a per-day observed measurement.
This is synthetic demonstration input, not a real forecast.

Bonnie Vale still meets required toilets, showers, drinking-water facilities
and vehicle access. With the verified two-adult profile, ready-to-eat meals,
one two-seat car, confirmed equipment and AUD 1000 budget:

- Logistics passes without missing inputs or equipment blockers; complete trip
  cost remains AUD 349.00.
- Weather, fire, road and restriction evidence are AVAILABLE for the full trip.
- Existing safety rules produce HIGH risk and REVIEW, routing to ESCALATED.
- The only finalisation blocker is REVIEW_REQUIRED. The normal review process
  must approve the current assessments before the Camper can save the final plan.

The reference contains facts only; no expected route, approval or eligibility
is supplied as business input. Planning/model parameters, rules and audit
schemas are unchanged. Lane Cove and all other campsites retain their generated
conditions; dates outside the registered event retain legacy snapshot identity.
Selecting Bonnie Vale is still necessary to demonstrate this event: the model
may choose another valid campsite.

## Identity and replay

Only an applicable rolling Sydney snapshot registers `a_weather_events_policy`
and `a_weather_events_sha256`. The exact reference bytes and digest enter the
snapshot manifest and cache identity. Snapshot content is checked against the
deterministic expected bytes on every resolution, including cache hits.

The old synthetic-daily-v1 builder remains byte-compatible when no event policy
was registered. `for_scope()` reconstructs absence for old runs, pins the saved
checking date, and validates the reference digest for new event-bearing runs.
Missing, changed or malformed reference inputs fail closed. Existing snapshots,
sealed releases, stored assessments, traces, approvals and final plans are not
rewritten. No migration or personal configuration change is required.

Restart the backend to load this source change. On 4 November, newly confirmed
runs and new reassessments use the event. Refreshing an old plan does not insert
new weather into its saved results. The normal current Sydney clock and finite
forecast horizon remain in force.

## Offline checks

`backend/tests/test_weather_events.py` covers the event's campsite/date bounds,
legacy manifest bytes and replay, malformed references, warm-cache digest
checks, resealed cache rejection, and review-to-final-save flows in both rules
mode and the actual three model components using MockTransport. Real HTTP
transports are blocked. These are offline checks, not a live campus acceptance.
