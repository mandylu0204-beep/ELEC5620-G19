# Packaging and independent deployment

The [README](../README.md) is the current setup/start guide. Historical handoffs
and screenshots remain in Git history rather than the delivery tree.

## Package committed source

From the repository root, using the project Python environment:

```powershell
.\.venv\Scripts\python.exe scripts/package.py
.\.venv\Scripts\python.exe scripts/package.py --verify var/releases/ACTUAL_FILENAME.zip
```

The ZIP contains `campmate_app/` and `PACKAGE_MANIFEST.json`, recording the exact
commit and file digests; a SHA-256 sidecar checks the entire ZIP. This is integrity
checking, not deployment/model acceptance. Existing output is not overwritten.
Tracked changes block packaging; untracked/ignored private files are excluded by
`git archive HEAD`, never automatically staged or deleted. Commit new intended
source first. Runtime/private files and unsafe paths/symlinks are rejected even
if accidentally committed.

## Independent installation

Extract to a new empty folder with no dependency links or original configuration.
On Windows, prefer a short destination rather than nesting one checkout inside
another; snapshot identities add long path components. Do not change system
security/path settings to run this project.
In its `campmate_app` directory run:

```powershell
py -3.12 scripts/setup.py
.\.venv\Scripts\python.exe scripts/smoke.py
```

macOS/Linux: use `python3.12` then `.venv/bin/python`. Setup needs dependency
registry network access and uses the backend lock plus `npm ci`. Git history
and private repository access are not needed. Verify the installed backend
points to the extracted folder. `python scripts/check.py` runs broader tests;
record what was actually executed rather than treating collection as a pass.

The smoke uses owned loopback services on 18010/15180 (overridable), an isolated
fixed-date Sydney rules database/cache, and explicit inputs from
`docs/demo/bonnie_vale_inputs.json`. It checks frontend/proxy, readiness,
authentication, migrations, planning, risk review, final save/PDF, isolation,
restart readback, logout and process cleanup. It inserts no fake successful
artifacts and makes no campus calls. It does not execute browser JavaScript.
Reports/logs stay in the extracted `var/`; only owned child services are stopped.

For models, privately configure the extracted folder's own `.env.llm.local`,
connect campus/VPN and use the README command. Coordinate live-call budget with
B. Do not copy original user data. The [rehearsal guide](demo/bonnie_vale_review_request.md)
explains fixed-date early practice; a rules smoke is not model acceptance.

## Canvas download verification

Upload the accepted ZIP, download that actual attachment and compare its hash:

```powershell
Get-FileHash -Algorithm SHA256 .\DOWNLOADED_FILENAME.zip
```

An existing checkout's package verifier can check the downloaded file; source
creation needs Git, deployment from the extracted ZIP does not. Follow the
[final submission checklist](canvas_submission.md).
