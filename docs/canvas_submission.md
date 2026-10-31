# Canvas source submission

## Delivery target

Deploy on-site from the source attachment downloaded from Canvas. CampMate is a
web frontend plus API, not a mobile app. Prepare Python 3.12, Node.js 22.12+ and
network/VPN in advance; install/build the project on-site from submitted source.
The archive must work without private GitHub access, an author's absolute path,
existing environment, copied database or hidden harness.

## Final checks

1. Freeze the final commit. Reconcile B's exact live-test source/report and any
   later changes; do not relabel historical evidence as a new full test.
2. Commit intended source/data/docs. Packaging blocks tracked changes and reads
   committed HEAD only. Private untracked diagnostics stay local, not published
   or deleted. Review new intended untracked files before committing them.
3. Generate the ZIP and SHA-256. Include source, locks, data/weather, migration
   code, PDF font/license and current English setup/start/demo instructions.
   Exclude keys, environment files, sessions, SQLite/WAL, dependencies and caches.
4. Extract to a new folder and run setup for its own `.venv` and `node_modules`.
   Verify backend imports resolve inside that extraction. No dependency links or
   borrowed editable installation may be used to claim a clean install.
5. Check isolated rules HTTP workflow, schema/build and appropriate browser paths.
   Model testing separately needs credentials/network and an agreed call budget;
   coordinate with B rather than repeating their calls.
6. Where practical, have a teammate deploy the same ZIP on another computer.
   Record hash, source, OS/runtime, mode and actual results/limitations.
7. Upload, download the actual Canvas attachment, compare SHA-256 and inspect the
   extracted folder/instructions. Submit before the deadline.
8. Keep the downloaded ZIP/hash and separately prepared local secret config for
   on-site deployment. Changes after acceptance require a new release/check.

## Presentation configuration

- Use the README's explicit three-model startup, 4096/low and compact safety.
  Rules remain default. Startup is not a live model probe.
- Configure `.env.llm.local` privately; never upload it. Check VPN connectivity.
- Empty databases are created automatically. Enter/confirm the synthetic test
  inventory and request normally; no successful run or approval is preloaded.
- Founder approval applies to exact current assessments. Historical approval,
  hard blockers or missing evidence must not authorize final saving.
- For 4 November: check date **2026-11-04**, trip **2026-11-05 to 2026-11-07**.
  Early rehearsal uses a fixed application date, not changed OS time. See the
  [Bonnie Vale guide](demo/bonnie_vale_review_request.md).
- Explain to the tutor that dynamic weather/road/fire inputs and costs are
  synthetic/reference data, while catalogue names/facilities have cited sources.

## Acceptance status

A candidate's release report must name its commit and ZIP hash. Actual Canvas
upload/download and on-site deployment remain user/team actions until completed.
Do not claim another-machine installation, latest-source full backend regression
or final live-model acceptance without evidence for that source. Local rules
smoke, browser checks and model acceptance are different scopes. Do not re-enable
GitHub Actions against the owner's quota.
