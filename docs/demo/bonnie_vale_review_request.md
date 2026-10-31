# Bonnie Vale review-flow request

## Handoff scope

This example combines the versioned Bonnie Vale weather event and the logistics
v2 envelope-correction policy. It is a synthetic demonstration/rehearsal, not a
real forecast. A has completed offline checks only; live campus reliability is
not guaranteed. Do not operate A's old failed runs or private database.

The **checking date must be 2026-11-04**, with rolling evidence generation.
The trip is **2026-11-05 through 2026-11-07**, three days/two nights. The event
supplies weather through 2026-11-10. Running the ordinary current-clock launcher
on 2026-10-31 only supplies weather through 2026-11-06 and will not activate this
event. Refreshing or recovering that old October run does not change its input.

## Early rehearsal without changing the computer clock

Use an independent SQLite database/cache. Keep all ordinary date, identity,
permissions, audit, review and finalisation checks enabled. The application
explicitly supports a fixed checking date; this does not falsify the operating
system clock or edit persisted contexts.

From the repository root, save the following as an ignored local file such as
`var/rehearse_bonnie.py`, then run it with the project's Python environment. It
starts a separate frontend on port 5184 and API on port 8014. It does not send a
model request merely by starting; user actions can invoke the configured roles.
Use the local campus credentials/VPN and any separately agreed request budget.
This launcher is portable between Windows and macOS; it does not contain a key.

```python
import os
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
if not (root / 'scripts/dev.py').is_file():
    raise SystemExit('Run from the repository root.')
env = {key: value for key, value in os.environ.items()
       if not key.startswith('CAMPMATE_')}
env.update(
    CAMPMATE_DATASET_PATH=str(root / 'data/sydney_surrounds_v2_2'),
    CAMPMATE_EXECUTION_MODE='agent', CAMPMATE_PLANNING_ENABLED='true',
    CAMPMATE_LOGISTICS_EXECUTION='model', CAMPMATE_SAFETY_EXECUTION='model',
    CAMPMATE_SAFETY_PROTOCOL='compact', CAMPMATE_CLOCK_MODE='fixed',
    CAMPMATE_DEMO_TODAY='2026-11-04', CAMPMATE_SYNTHETIC_EVIDENCE_MODE='rolling',
    CAMPMATE_DATABASE_PATH=str(root / 'var/bonnie-review-rehearsal/campmate.sqlite3'),
    CAMPMATE_SNAPSHOT_CACHE_PATH=str(root / 'var/bonnie-review-rehearsal/snapshots'),
    CAMPMATE_DATASET_SCENARIO_FILES='[]', CAMPMATE_DATASET_SELECTION='{}',
    CAMPMATE_WORKFLOW_SAFETY_CASE_IDS='[]', CAMPMATE_SEED_DEMO_ACCOUNTS='true',
    CAMPMATE_SECURE_COOKIES='false', ELEC5620_MAX_COMPLETION_TOKENS='4096',
    ELEC5620_REASONING_EFFORT='low',
)
raise SystemExit(subprocess.call([
    sys.executable, str(root / 'scripts/dev.py'), '--backend-port', '8014',
    '--frontend-port', '5184',
], cwd=root, env=env))
```

Do not call `scripts/sydney.py` inside this launcher: it deliberately restores
the current clock. Stop the rehearsal using Ctrl+C. On 4 November, the normal
Sydney launcher can be used with a new confirmation/run. The rehearsal database
is separate and is not an instruction to move its fixed-date records into the
normal user database. Do not submit databases, sessions, keys or raw replies.

## Camping profile

- Two adults; Some experience (`INTERMEDIATE`); no children; child count 0.
- No accessibility requirements.
- Car transport: one confirmed available vehicle, two seats including driver.
  Save vehicle quantity/capacity in Transport arrangements. Estimated distance
  may be left blank; this example uses the registered transport reference.
- Save the profile before confirming the request. Explicitly confirm available
  stock for every item in the following synthetic test inventory.

| Item | Quantity | Unit | Capacity per item |
|---|---:|---|---:|
| Tent | 1 | item | 2 people |
| Groundsheet | 1 | item | — |
| Tent repair kit | 1 | item | — |
| Sleeping bag | 2 | item | — |
| Sleeping mat | 2 | item | — |
| Warm liner | 2 | item | — |
| Warm clothing (`warm_layers`) | 2 | item | — |
| Raincoat (`rain_jacket`) | 2 | item | — |
| Drinking water | 20 | litre | — |
| Meals | 18 | portion | — |
| First-aid kit | 1 | item | — |
| Headlamp / Torch | 2 | item | — |
| Hand sanitiser | 1 | item | — |
| Vehicle (under Transport arrangements) | 1 | vehicle | 2 people |

## Request to paste

```text
Two adults plan to camp in Sydney & Surrounds from 2026-11-05 for two nights,
returning on 2026-11-07. Our total group budget is AUD 1000.
We prefer quiet surroundings and ready-to-eat meals.
The campsite must have toilets, showers, drinking-water facilities and vehicle access.
```

Set the structured fields to the same values:

- Destination: Sydney & Surrounds.
- Start: 2026-11-05. Duration: 2 nights / 3 days. End: 2026-11-07.
- Whole-group budget: AUD 1000.
- Preferences: Quiet surroundings; Ready-to-eat meals.
- Required conditions: Must have toilets; Must have showers;
  Drinking-water facilities required; Vehicle access required.
- Do not select Walk-in access only or add unrelated hard requirements.
- Generate/review the summary and confirm it against this saved profile.

Ready-to-eat meals avoid unnecessary stove/fuel gaps. Do not register imaginary
stock in a personal profile; this list is an explicit synthetic test inventory
for the isolated rehearsal.

## Selection and expected path

Both Bonnie Vale and Lane Cove meet the four required conditions. Natural
language cannot guarantee the model selects Bonnie Vale. If necessary use the
existing custom revision input, without changing confirmed fields:

```text
Please change the campsite to Bonnie Vale campground (bonnie-vale).
Keep the confirmed dates, group size, budget, ready-to-eat meals and all required
conditions unchanged. Recalculate equipment, costs and safety using registered facts.
```

Review the candidate and adopt it if appropriate. Do not alter candidate
filters or fabricate a model response to force the selection.

For Bonnie Vale with this complete input, the offline baseline is:

- All four safety evidence categories AVAILABLE for the whole trip.
- Logistics PASSED, no missing-input clarification or hard blocker.
- Deterministic complete trip cost AUD 349.00. The model's optional supply
  choices can affect its draft allocation; compare actual saved results.
- Weather facts: 12–22 C, rain field 60 mm, wind 35 km/h. The rain field is not a
  per-day observed measurement.
- Safety HIGH / REVIEW; no hard safety blocker; review queue ESCALATED.
- Before approval: final save disabled with REVIEW_REQUIRED.
- Founder reviews the current run/assessments, then the Camper reads the
  approval and saves the final plan if the unchanged guards permit it.
- Reload/restart readback retains the same audits/receipt and final snapshot.

Do not infer that every REVIEW can be approved. Missing evidence, hard blockers,
changed inputs and outdated approvals must continue to prevent finalisation.

## B's test focus

First independently confirm the fixed date, rolling snapshot marker, forecast
range, profile/units, candidate constraints and v2 registered logistics identity
offline. The existing tests exercise both rules and mocked three-model flows.
The final combined weather-event and format-recovery check passed 50 tests
(zero failures/errors/skips); shared-schema and frontend type checks passed.
The documented rehearsal launch was checked with a mocked subprocess only.
If live calls are authorized within an agreed budget, then check the saved
model logistics/safety audits, Founder review, Camper final save and restart
readback. Count interpretation and any revision/correction requests as well;
do not reset a request guard to gain extra calls. On failure retain only
bounded redacted metadata, stop the test, and report the stage/turn and counts.

The envelope fix is preventive; a live model need not make the nesting mistake
for the normal-path test to pass. Its forced-failure/correction behaviour is
covered offline. Existing v1 audits remain readable. No repeat of A's broad
offline suite or cloud CI is required just to read this handoff.
