# Sydney & Surrounds catalogue

The current package is `data/sydney_surrounds_v2_2`, version **2.2.0**.
It contains The Basin, Bonnie Vale, Bents Basin, Cattai, Euroka, Lane Cove,
Putty Beach, Little Beach, Tallow Beach and Cockatoo Island waterfront campground.
Names, access notes, facilities and permanent restrictions cite NPWS/operator
pages in the sealed `data/source_catalogue.json` inside the package.

## Use and configuration

Install and start from the project root using the [README](../README.md).
`scripts/sydney.py` selects the current Sydney date, independent daily snapshots
and `var/sydney/campmate.sqlite3`. Rules are the default. The explicit three-model
command uses planning, logistics and compact safety; it requires private campus
credentials and network access. Startup is not a model probe.

For the November demonstration use the [Bonnie Vale guide](demo/bonnie_vale_review_request.md).
Early rehearsal fixes the application date in an independent database; do not
change the computer clock or copy personal saved plans.

## Facts and assumptions

- Unknown facilities remain unknown. A hard requirement needs an explicit
  supporting fact. Walking from a carpark is distinct from vehicle-access camping.
- Coordinates are not invented. Access notes do not claim live navigation,
  measured distances or ferry timetables.
- Nightly fees are whole-group reference allowances, not live booking quotes.
  Supported planning group limits are product limits, not campground capacities.
- Dynamic weather, road and fire inputs are synthetic. Their dates, missing facts,
  conflicts and restrictions remain enforced. Explain this scope to the tutor.
- The visible location panel must match the registered source-catalogue digest.
  An unrelated current catalogue cannot replace facts attached to a saved run.

## Compatibility and checks

Old data releases and versioned reference resources remain byte-for-byte intact.
They are required by historical recovery and offline compatibility tests. They
are not selected for a new Sydney launch. See [delivery scope](source_delivery_scope.md).

`python scripts/build_sydney_catalogue.py --check` verifies the generated package
without writing. The shared-schema check and isolated rules deployment smoke
cover different scopes; neither is a new live-model or whole-backend acceptance.
