# Sydney & Surrounds catalogue

The new independent `data/sydney_surrounds_v2_2` package is version **2.2.0**.
Its ten places are The Basin, Bonnie Vale, Bents Basin, Cattai, Euroka, Lane Cove,
Putty Beach, Little Beach, Tallow Beach and Cockatoo Island waterfront campground.
Their names, access notes, verified facilities and permanent restrictions were
checked against NPWS/operator pages on 23 October 2026. Field-level URLs,
unknowns, derived tags, supported group limits and cost assumptions are in
`data/source_catalogue.json`. That file is sealed and consumed as part of both
the registered dataset and Adapter identity, including daily snapshots.

## Start locally

From the project root, with dependencies already installed:

```powershell
.\.venv\Scripts\python.exe scripts\sydney.py
```

For this existing development worktree, the installed environment is next door:

```powershell
cd C:\Users\87901\Desktop\ELEC5620\Stage2\campmate_runtime_optimization
& ..\campmate_app\.venv\Scripts\python.exe scripts\sydney.py
```

Open http://127.0.0.1:5173. If those ports are occupied, use
`--backend-port 8001 --frontend-port 5174`; no existing service is stopped.
Ctrl+C stops the two child services. The entry point does not install tools or
modify any environment file. It selects current-date local rules, automatic
evidence selection, `var/sydney/campmate.sqlite3` and `var/sydney/daily-snapshots`.
Existing user accounts, profiles, plans and databases are not copied or deleted.
The new database therefore initially has no personal saved profiles or plans.

Explicit `--mode agent` opts into the existing campus planning client;
`--mode agent --logistics model` also opts into model logistics and requires the
user's existing local model configuration. Neither was called for this delivery.
Safety defaults to **rules**. Explicit `--mode agent --safety model` selects the
independent 2.2/v3 safety adviser; add `--logistics model` for all three model
roles. These options can incur real campus requests and require separate user
approval for acceptance testing. Do not run them as a health probe. The 2.1/v2
path and archived validators remain separate; unsupported or incomplete safety
wiring fails rather than falling back after a model error. The new 2.2/v3 path
has offline regression coverage only, not real-campus/browser acceptance.
See [B's v3 integration handoff](b_sydney_v22_model_safety_handoff.md).

## Facts, assumptions and presentation

- Real English names and `Sydney & Surrounds` replace fictional names for new
  inputs. Legacy packages, IDs and saved plans retain their original identity.
- Ordinary user pages omit Demo prefixes and simulation banners. The shared
  source-family provenance remains frozen internally; it is not live evidence.
- Coordinates remain unknown unless an official coordinate was found. No
  fictional coordinate grid or invented driving time was retained.
- Vehicle arrival at an officially described carpark followed by a documented
  walk is distinct from camping beside a vehicle. Explicit `vehicle_access`
  requirements still exclude walk-in camps. Walk and ferry details are displayed;
  no live route or timetable service is claimed.
- Nightly fees are whole-group reference allowances for the supported single
  site, not copied per-person tariffs or booking quotes. Entry/parking allowance
  is included, so the separate generic parking line is zero; real parking is not
  asserted to be free. Most sites have a conservative supported planning cap of
  four, explicitly a product limit rather than the real campground's capacity.
- Weather/current road/fire conditions remain finite simulated inputs with date,
  coverage, missing/conflict and permission guards intact. They are not live
  forecasts or official clearance. Old fictional closure events were not attached
  to the real places. Wood-fire prohibitions still block requested campfires;
  they are not rewritten as a comprehensive ban on all gas/electric cooking.
- The visible location-information panel is restricted to the matching 2.2
  source-catalogue digest; it is not projected into an unrelated saved snapshot.
  The role-scoped server view emits only a public `campsite_catalogue_id` after
  matching the registered version and seal. Internal digests and configuration
  remain hidden from ordinary users.

## Local verification

`python scripts/build_sydney_catalogue.py --check` compares all 12 package files
without writing. No old package is resealed. Targeted backend checks cover new
identity, source tampering, daily snapshots, legacy seals, transport, cooking,
evidence selection and existing rule behavior. Frontend tests, types, production
build and shared-schema check pass. No complete-suite, Actions or campus call was
performed for this update.

The independent browser check used two people, 25–27 October 2026 and AUD 1000.
Little Beach was selected. An initial 12 litres of water was correctly flagged
as four litres short, with a direct highlighted field link. Updating to 16 litres
and replanning without retyping the request removed that issue. The resulting
AUD 261 estimate passed rule checks, was finalised and reread after page reload.
The 750-metre walking access, lack of drinking-water supply, toilets and absence
of showers were displayed along with the official link. Normal visible final
page text contained no Demo/Synthetic labels. Private browser DB, snapshot,
session, raw JUnit and screenshots remain in ignored `var/sydney-review/`.

## Integration with main 49035a6

The integration candidate combines Sydney source dd04109 with main 49035a6.
Main's trip-series updates, profile adoption/diff, permission-scoped presentation,
cooking preparation and database migration 11 are retained. Lightweight progress
polling and validated parsed-snapshot reuse are retained from the Sydney parent.
The SQLite migration was exercised on a backup of the prior isolated browser DB;
no personal database or environment file was changed.

Local integration verification: 96 targeted backend tests, 107 frontend tests,
types, build, shared schemas and deterministic 12-file package comparison pass.
This is not a complete backend regression or cloud CI result. The frontend build
still reports the existing >500 kB chunk warning.

The browser check reused the saved Little Beach request (25–27 October, two
people, AUD 1000), changed registered water from 16 to 18 litres, displayed the
exact profile difference, and explicitly confirmed a new check. The request did
not need retyping. The new AUD 261 plan was finalised, while the previous final
remained linked as same-trip history. No model service was called. The private
SQLite copy, snapshots, JUnit and screenshots stay under ignored
`var/sydney-main-review/` and `var/sydney-main-*.xml`.
