# Current dates and daily synthetic snapshots

Normal operation uses the current calendar date in `Australia/Sydney`, read
again for each new interpretation, confirmation and evaluation. A legacy
`CAMPMATE_DEMO_TODAY` entry does not freeze normal operation. Restart the
backend after updating the source; refreshing the browser alone cannot reload
backend code.

## Configuration

```text
CAMPMATE_CLOCK_MODE=current
CAMPMATE_SYNTHETIC_EVIDENCE_MODE=auto
CAMPMATE_DATASET_PATH=data/sydney_surrounds_v2_2
CAMPMATE_DATASET_SELECTION={}
CAMPMATE_DATASET_SCENARIO_FILES=[]
CAMPMATE_WORKFLOW_SAFETY_CASE_IDS=[]
```

These settings work with either the rule runtime or the existing campus hybrid
runtime. Model execution and credentials are configured separately. This change
does not enable a model, make weather API requests or alter personal credentials.

With `auto`, supported v2.1/v2.2 data and the current clock use generated daily synthetic snapshots.
Other source versions keep their sealed inputs. Explicit `rolling` requires
a supported v2.1/v2.2 package and automatic evidence selection; incompatible scenario selections fail
instead of falling back. `sealed` always reads the selected original package.

For a repeatable fixed scenario, set `CAMPMATE_CLOCK_MODE=fixed`,
`CAMPMATE_SYNTHETIC_EVIDENCE_MODE=sealed` and the desired
`CAMPMATE_DEMO_TODAY`. `scripts/demo.py` sets these explicitly. Python tests that
explicitly construct `Settings(demo_today=...)` also retain fixed-clock behavior
unless they explicitly specify `clock_mode=current`.

## What is simulated

The original v2, v2.1 and Sydney v2.2 packages are not overwritten. Independent snapshots
are materialized below `var/daily-snapshots/<date>/<identity>/`. Their identity
includes the inspected base context, date and generator policy. The full byte
digests, selection settings and checking date enter the existing run scope and
input fingerprint. Shared contracts remain 1.0; no SQLite schema migration is
required.

Each snapshot contains a seven-calendar-day mock forecast (today through
today + 6), plus a bounded 31-day simulated non-weather scenario. Original dated
road closures, campsite closures, fire bans and permanent campsite conditions
remain effective. Forecast conditions are deterministic by campsite/date,
include adverse conditions and do not depend on user requests or desired
assessment results. Neither the forecast nor the non-weather scenario is a
claim about real-world conditions. The manifest records the generator policy
and simulation notice; source-family provenance remains the v2 synthetic family
required by the existing adapter.

The runtime validates generated content against deterministic expected bytes,
including when a local manifest has been resealed. A damaged registered
snapshot is rejected, never silently regenerated in place. Scenario/oracle test
fixtures are not loaded into normal daily inputs. The shared builder also
reproduces the original sealed v2.1 release byte-for-byte with
`python scripts/build_trip_dataset.py --check`.

## User flow and time boundaries

* A future departure is allowed even when weather does not cover the whole trip.
  The itinerary, equipment and cost results remain saved as a preliminary plan.
* Coverage guidance shows the actual checking date, the forecast interval, the
  uncovered dates and, for a trip of at most seven days, when a full-trip
  forecast could first become available. This is a suggestion to check again,
  not a promise of safe conditions.
* Trips longer than seven days require staged weather checks. The application
  does not splice partial records or assert that the whole trip is safe.
* Reassessment registers a new run using the latest daily snapshot while
  retaining the itinerary/version and the original planning trace. Existing
  evidence, reviews and final snapshots are not rewritten.
* Recovery of the same interrupted daily run resolves its original snapshot
  date and reuses saved artifacts. A base/configuration/policy change still
  invalidates recovery; it must not mix snapshots or regenerate missing audit
  evidence for a saved model result.
* Eligibility, review and finalisation validate against the current runtime.
  An old run cannot be finalised with yesterday's eligibility after midnight.
  Already saved immutable final snapshots remain readable as historical records.

For example, on 2026-10-16 a 2026-10-22 through 2026-10-26 trip can be planned.
The current forecast ends on 2026-10-22, so weather remains unresolved and the
page suggests checking on or after 2026-10-20. It does not change the user's
dates or require a predefined scenario.

## Verification boundary

See `tests/test_daily_clock.py` for offline HTTP/SQLite, model-audit recovery,
date-boundary and server-side finalisation checks. Model roles in these tests
use independent offline HTTP fixtures. Browser evidence uses the real rule
runtime and an isolated SQLite database. This work is not a real weather
integration, a new live campus-model acceptance, or a Canvas packaging test.
