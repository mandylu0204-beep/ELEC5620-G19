# English source delivery and historical compatibility

Current UI source, maintained backend source, tests and delivery documentation
contain no literal Han characters. Non-English input aliases and fixtures use
Unicode escapes. Their parsed Python syntax trees and runtime strings, including
prompts and regular-expression patterns, are unchanged; this is a source spelling
change, not removal of multilingual support or a new model protocol.

## Removed development material

The delivery tree no longer includes 289 obsolete handoff/report/screenshot
files under `docs/`, or the superseded `scripts/run_manual_state_case.py` launcher.
Its old manual scenario input was removed with it. Current installation, startup,
Canvas, source contracts, request input, rehearsal, recovery and reference guides
remain. The removed material can be recovered from the preceding Git history;
no personal files, database or untracked private diagnostic was deleted.

## Necessary original-language resources

The following 11 immutable resources retain literal original-language text by
explicit agreement, to preserve registered hashes and historical replay:

- `data/planning/camp_activities_v1.json`
- `data/planning/camp_activities_v2.json`
- `data/synthetic_demo_v2/CHANGELOG.md`
- `data/synthetic_demo_v2/FINAL_VALIDATION_REPORT.md`
- `data/synthetic_demo_v2/README.md`
- `data/synthetic_demo_v2/docs/integration_contract.md`
- `data/synthetic_demo_v2/docs/original_validation_report_v1.md`
- `data/synthetic_demo_v2/docs/synthetic_data_dictionary.md`
- `data/synthetic_demo_v2/scripts/repair_review_findings.py`
- `data/synthetic_demo_v2/scripts/validate_dataset.py`
- `data/transport/sydney_city_v1.json`

The old activity versions are read by the historical planning-reference
validator. New planning uses English `camp_activities_v3.json`. The transport
reference also participates in saved identities; public presentation uses the
English origin label. The old v2 package's documentation and authoring scripts
are part of its sealed release manifest and release-integrity regression.
Deleting or translating these bytes would invalidate that sealed release.

All 71 tracked data files are preserved byte-for-byte by this cleanup. Legacy
validators, snapshot/recovery registration, audits, permissions, leases and
current-date/final-save guards remain unchanged. This archive is therefore an
English application/source delivery with an explicitly preserved compatibility
exception, not a claim that every historical byte is English.

## Verification scope

Language scanning, complete data-file SHA-256 comparison, Python AST comparison,
relative documentation-link checks and targeted offline tests verify the cleanup.
The release sidecar records actual commands/results and the final ZIP hash.
No cloud CI or campus-model request is part of this work. Earlier release checks
remain scoped to their original commit and do not certify the new ZIP.
