# Sydney & Surrounds catalogue 2.2.0

Official static names, locations, facilities and access notes were checked on
2026-10-23. See data/source_catalogue.json for field-level URLs, unknowns,
product planning caps and reference costs. This mixed catalogue retains frozen
synthetic provenance internally: weather, road and current fire state are
simulation inputs, not live forecasts or official safety checks. Real booking
availability was not queried. Do not use this snapshot as real travel clearance.

The original 2.0.0 and 2.1.0 directories are preserved. IDs intentionally differ
from fictional locations, so historical saved runs retain their original source.
The normal input contains no inherited fictional road closure or total-fire-ban
event. Static wood-fire rules do not establish a comprehensive gas-cooking ban.
Prices are whole-group nightly planning allowances, not per-person official rates.
The separate parking reference is zero to avoid charging the allowance twice;
this does not assert that actual park entry or parking is free.

Use automatic trip evidence selection with no manually forced scenario IDs.
The source catalogue must remain sealed and be retained in daily snapshots.
Reproduce or compare this package with scripts/build_sydney_catalogue.py.
