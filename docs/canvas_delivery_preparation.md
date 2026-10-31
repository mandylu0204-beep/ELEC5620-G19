# Canvas delivery preparation — 31 October 2026

This update refreshes the English README, Canvas/deployment/VS Code guides,
public configuration comments, source packager and local deployment check.
It does not change agents, business rules, prompts, model parameters, database
schema, role permissions or original user data.

The packager archives committed HEAD only. Untracked private diagnostics stay
local, without being staged or deleted. Tracked changes still block packaging;
private/runtime files, database sidecars and unsafe paths remain forbidden.
The manifest records the source commit without an outdated development-scope
claim. The public Bonnie Vale input JSON contains test inventory/requirements,
not pre-saved successful plans, approvals or hidden expected outcomes.

## Local checks and candidate scope

- Source-package boundary, weather/review flow and private-config path checks:
  30 passed, zero failures/errors/skips; shared schema and whitespace passed.
- Updated HTTP smoke on the original checkout: 9 steps passed using an
  independent fixed-date Sydney rules database, including review, final save,
  PDF, owner isolation and restart readback. Campus requests: zero.
- Initial candidate 8b7c8de was extracted without config, databases or installed
  dependencies. Setup created its own environment and installed locked packages;
  backend imports resolved inside that extraction and `pip check` passed.
- On that extracted source: 268 frontend tests passed; schema, type check and
  production build passed; 4 isolated Edge DOM/save-navigation scenarios passed.
  The existing large-chunk build warning remains.
- Two full HTTP attempts from the deeply nested extraction did not become ready
  in 45 seconds. Their reports are retained; they are not recorded as passes.
  Controlled long/short path comparison identified a 263-character snapshot
  path that failed ordinary Windows lookup while the same file was readable
  using the extended path namespace. Shorter paths were readable. No data bytes
  were missing or repaired.
- The smoke now uses a shorter isolated directory name. Its original 45-second
  readiness and 30-second workflow deadlines, all dataset guards and all real
  application logic are unchanged. A new candidate must be packaged and checked
  after this source change; the first candidate is not the final submission.

The exact final candidate commit/hash and extracted-run result are recorded in
the release sidecar report under ignored `var/releases/` after packaging. A
manifest cannot contain its own ZIP hash. This report does not predeclare those
results. Installed dependency caches may be used normally by pip/npm; original
`.venv`/`node_modules` were not copied or linked. Toolchain is the same Windows
computer, not another-machine validation.

No cloud CI or campus model was called. Latest-source full backend regression,
actual Canvas upload/download, on-site deployment and B's live-model results
remain separate acceptance scopes. Historical English/Chinese development
records remain archived; the current entry-point instructions are English.
