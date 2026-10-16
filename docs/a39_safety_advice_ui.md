# A39 user-facing safety advisory presentation

Date: 2026-10-17. Base: A38 338ea23 on feature/a36-safety-audit-storage.

The safety tab now supports a separate AI preparation-advice section, below the
official checks and existing next steps. It renders only an authorised saved
SAFETY audit matching the selected run, version, assessment, logistics dependency
and input fingerprint. Both selected assessments must match the displayed
version context. Missing audit, rules-only runs and incomplete/NO_MATCH flows
show no model-advice label or invented advice.

The section labels model text as unverified reference advice and preserves the
official result and controls. Saved action codes receive concise user-facing
titles. Actionable findings retain saved priority; first three are visible,
remaining suggestions and informational findings can be expanded without loss.
Outdated checks and historical/final snapshots explicitly retain their temporal
context. No automatic approval, reassessment, navigation or mutation is added.

React renders model prose as escaped plain text. There is no HTML/Markdown/link
execution. Finding keys are React keys only, never displayed. Trace, model names,
tokens, hash values, fact pointers and internal association IDs are not rendered.
The API keeps the validated audit internally; this change adds no raw audit UI.

The frontend audit type now distinguishes LOGISTICS and SAFETY instead of
treating every role as a logistics plan. No backend DTO/shared schema changed.
There is no new role activation: until B completes the guarded orchestration,
ordinary production use still runs rule-based safety and has no model section.

Validation: all 20 frontend tests pass (eight additional safety-advice tests),
TypeScript/Vite build passes, diff check passes. New tests compile/render the
actual React panel with ReactDOMServer and verify binding mismatch rejection,
priority integrity, unverified labels, internal-field omission, plain-text
escaping, temporal context and complete expandable groups. Fixtures are explicit
UI test records, not live model evidence. No real browser or campus acceptance
is claimed. No backend tests repeated for this frontend-only change.

A38 CI run 38978915016 was still in progress when this UI work was prepared;
do not report it as passed until its exact final result has been checked.
