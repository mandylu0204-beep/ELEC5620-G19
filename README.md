# CampMate AI

ELEC5620 Stage 2 — a local web application with a React/TypeScript frontend,
FastAPI backend and SQLite database. This is a web project, not an Android/iOS
application; no mobile build is required for this source package.

Campers register/sign in, save group/equipment/transport details, confirm
requirements, generate plans, compare revisions, update checks, obtain human
review, save final plans and export PDFs. Founder accounts handle review and
request assistance. Access is scoped by user and role.

Planning, logistics and safety model roles are integrated. Logistics proposes
supply choices while code calculates quantities/costs. Model safety provides
advice alongside the authoritative deterministic assessment. Missing facts,
hard blockers, identity checks and approval guards remain enforced.

## Install from the submitted source

Install Python **3.12** and Node.js **22.12+**, including npm, before the on-site
demonstration. Initial dependency installation requires network access. Open the
extracted `campmate_app` folder. No private GitHub access or existing database
is required.

Windows PowerShell:

```powershell
py -3.12 scripts/setup.py
```

macOS/Linux:

```sh
python3.12 scripts/setup.py
```

Setup creates `.venv`, installs `backend/requirements.lock`, installs the local
backend package, runs `npm ci` and creates `.env` from `.env.example` only if
missing. No PowerShell execution policy change is needed. Do not copy a virtual
environment or `node_modules` from another checkout.

## Start all three model roles

Copy `config/campus_llm.example` to `.env.llm.local` in the project root and enter
your own campus API key there. Keep it out of Git, Canvas, screenshots and
reports. Connect to the campus network or USYD VPN. Prepare this local secret
configuration separately from the source ZIP.

Windows, from the project root:

```powershell
$env:ELEC5620_MAX_COMPLETION_TOKENS = "4096"
$env:ELEC5620_REASONING_EFFORT = "low"
.\.venv\Scripts\python.exe scripts/sydney.py --mode agent --logistics model --safety model --safety-protocol compact
```

macOS/Linux:

```sh
export ELEC5620_MAX_COMPLETION_TOKENS=4096
export ELEC5620_REASONING_EFFORT=low
.venv/bin/python scripts/sydney.py --mode agent --logistics model --safety model --safety-protocol compact
```

Open **http://127.0.0.1:5173**. API docs: http://127.0.0.1:8000/docs.
Services bind to loopback only. Ctrl+C stops both. Restart after backend edits;
refresh after frontend updates. If ports are occupied, append
`--backend-port 8001 --frontend-port 5174`. No existing process is stopped.

The Sydney launcher selects data **2.2.0**, the current Sydney date, rolling
evidence, `var/sydney/campmate.sqlite3` and `var/sydney/daily-snapshots`. Empty
databases are created/migrated automatically; normal restarts retain them.
Running `dev.py` alone retains configured defaults (stub unless overridden),
so use the explicit Sydney command for the full application.

Model actions consume campus requests. Health/readiness is not a model probe.
Do not repeatedly submit failed runs; inspect the saved error/recovery options.
External service availability and quota are not guaranteed. A model failure
is not converted into rule success.

## Rules-only startup

For installation checks without campus credentials or model calls:

```powershell
.\.venv\Scripts\python.exe scripts/sydney.py
```

On macOS/Linux use `.venv/bin/python`. Rules results do not establish model
acceptance. Use the independent database/cache described in the rehearsal guide
for controlled tests; do not replace a saved execution's configuration identity.

## Accounts and walkthrough

| Role | Username | Public local demonstration password |
|---|---|---|
| Camper A | `camper.a` | `CampMate-A-2026!` |
| Camper B | `camper.b` | `CampMate-B-2026!` |
| Founder/reviewer | `founder` | `CampMate-Founder-2026!` |

These are intentionally public local accounts, not campus credentials. New users
can register Camper accounts. Profiles start empty; no successful plan,
assessment or approval is preloaded.

1. Camper A saves group, available equipment and transport.
2. Enter destination, dates, meals, budget and required conditions.
3. Generate/review the summary, acknowledge it and start planning.
4. Inspect itinerary, equipment, costs and safety. Use specific correction links
   for missing details. Profile edits require a new confirmation/check.
5. High risk with complete information can enter Founder review. Approval cannot
   waive hard blockers or missing evidence.
6. Founder reviews the exact current assessments. Camper A then acknowledges
   and saves the final plan. Check history/PDF and restart readback.

For **4 November 2026**, use the complete
[Bonnie Vale request/rehearsal guide](docs/demo/bonnie_vale_review_request.md).
It uses 5–7 November, two adults, AUD 1000 and verified inventory. The heavy-rain
event applies to the **4 November checking snapshot**, not every date. Earlier
rehearsal uses a fixed application date and independent database/cache; do not
change the computer clock. The guide explains possible alternative campsite
selection and a normal revision to Bonnie Vale.

If browser translation changes page nodes and rendering fails, disable automatic
translation for CampMate and reload. The recovery panel does not automatically
resubmit a model action.

## Data and services

Campsite names, documented facilities/access and permanent restrictions derive
from official sources in the sealed `data/sydney_surrounds_v2_2` catalogue.
Weather and changing fire/road conditions are **synthetic, finite demonstration
inputs**; costs are reference allowances, not live quotes. No live forecast,
transit timetable, booking inventory or real route API is queried. Explain this
scope to the tutor. Do not use this prototype for real trip safety/availability.
Source provenance remains in the dataset and audits.

The model endpoint and public parameters are in `config/campus_llm.example`.
Local credentials and campus connectivity must be available on the demo computer.

## Checks and source delivery

See [Canvas submission](docs/canvas_submission.md) and
[packaging/clean deployment](docs/deployment_preparation.md). Historical reports
apply only to their own source/environment and do not prove this final ZIP was
installed or tested from Canvas.

Using the project virtual environment:

```text
python scripts/check.py                 # broad backend/frontend checks
python scripts/package.py              # checkout: committed source ZIP + SHA-256
python scripts/package.py --verify PATH_TO_ZIP
python scripts/smoke.py                 # isolated rules HTTP deployment check
```

From `backend`, `python -m app.export_contracts --check` verifies shared schema.
The smoke uses no campus model or personal database and is not JavaScript/browser
or live-model acceptance. No cloud CI is necessary for local submission checks.

## Layout

```text
backend/app/              API, auth, agents, rules, SQLite, PDF
backend/app/contracts/    shared schema 1.0
backend/app/assets/fonts/ PDF fonts and license
backend/tests/            offline tests
frontend/src/             React application
frontend/browser-tests/   isolated DOM regression
data/                    sealed catalogue and versioned synthetic weather
scripts/                  setup, startup, tests, packaging
docs/demo/               repeatable input and walkthrough
```

The ZIP excludes Git metadata, keys/environment files, databases/sessions,
runtime logs/caches, installed dependencies and untracked local diagnostics.
Old datasets/validators remain for archived replay compatibility. User-facing
text and these entry-point instructions are English; historical development
records/comments may retain their original language.
