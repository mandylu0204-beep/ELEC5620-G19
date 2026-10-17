# A48 failure and recovery presentation

Date: 2026-10-17 (Australia/Sydney). Local branch feature/a48-failure-recovery builds on A47 ed5c6a7. Pending safety-model integration A45/A46 is not included or merged into main.

## Change

The failed-plan panel now identifies the interrupted stage, lists saved artifacts and presents the server-authorised continuation action. Missing safety results say Continue safety check; missing logistics results say Continue equipment and cost check. When safety is already saved, the panel offers Continue unfinished steps instead of implying another safety run. Saved current-run assessment claims require matching run, plan, version and input fingerprint. A saved result does not imply it passed or permits finalisation.

Detailed failure reasons are expandable. A separate, collapsed replanning entry explains that continuing uses the already confirmed inputs, while profile changes require reviewing the latest saved profile and generating a new plan. Duplicate generic incomplete-check and next-step cards are removed on failures; specific equipment/safety issues remain. Historical failures cannot expose an active retry, missing backend retry permission fails closed, and input/confirmation errors provide the requirement-edit link. Existing command-key reuse and server request/revision handling are unchanged.

## Validation

- 45 frontend tests passed; TypeScript and Vite build passed; whitespace check passed.
- New tests cover interrupted safety, already-saved safety with completion failure, mismatched/historical assessment contexts, server retry flags, reassessment, generation before any saved itinerary, and NO_MATCH completion recovery.
- Two actual browser flows used real auth, dispatcher, repository and deterministic 2.1 rules with independent SQLite. Only one persistence failure per scenario was injected: before safety assessment save, and before route save. This was not a real service outage or a model-role test.
- Both pages showed the correct saved artifacts and continuation labels, with replanning collapsed. Browser continuation completed both runs. Original version IDs and all previously saved assessment IDs were unchanged. Total database counts were two versions and four assessments, with integrity_check=ok. Finalisation became available only after success; no final-save operation was performed. Browser console errors: none.
- Local screenshots: var/a48-safety-interrupted.png and var/a48-completion-interrupted.png. Machine verification: var/a48-browser/recovery-check.json. Temporary services/tabs were stopped.

Campus calls: zero. No backend source, schema, migration, retry policy, permission, finalisation guard, personal configuration, user database or sealed data changed. This does not complete the pending real campus safety acceptance or Canvas deployment acceptance. No GitHub CI run is claimed for this local change.
