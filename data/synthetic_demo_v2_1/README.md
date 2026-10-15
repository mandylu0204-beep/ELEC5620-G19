# CampMate Synthetic Demo Dataset 2.1.0

Independent synthetic snapshot; never use for real travel or safety decisions.
Sealed 2.0.0 is unchanged. Business rules, campsites, equipment and fees are
byte-identical to 2.0.0. Normal safety indices are replaced, not appended with
mutually exclusive test worlds. See coverage.json for exact dates and retained
closures/no-fire facts. All dates are finite; weather forecasts cover at most
seven days and future observations cannot be used early. Missing/stale/conflict
fixtures are isolated under tests/fixtures and are not loaded in normal runs.

Use workflow_safety_case_ids=[] and dataset_scenario_files=[] with this package.
Changing package/policy/check clock requires a newly registered run. Existing
SQLite schema and shared contracts remain 1.0; there is no database migration.
Do not copy 2.1 files over the sealed synthetic_demo_v2 directory.

Read-only validation from the repository root:
    .venv/bin/python scripts/validate_trip_dataset.py
