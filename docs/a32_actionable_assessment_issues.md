# A32: Actionable logistics issues and correction navigation

Date: 2026-10-16, Australia/Sydney. Local changes on top of main `8a40deb`
and the A31 meal-choice fix. Not yet committed or pushed.

## Behaviour

The previous generic logistics warning did not identify the missing field,
distinguish a real shortage from missing information, or tell users where to
correct it. Some essential stock shortages had no clarification at all.

An authorised read-only `logistics_issues` projection now accompanies plan/run
detail. It is derived from that run's saved logistics assessment and confirmed
profile snapshot, not from the latest mutable profile or a model-generated
claim. Each item contains a stable issue key, code/category, field, observed
value, required value where known, correction target and a local action URL.
It does not change SafetyResult, LogisticsResult, eligibility, shared schema
1.0, database schema or immutable final snapshots.

The result page presents actual equipment counts/capacities/confirmation,
missing distance and transport data, meal choices, stock shortages and source
gaps. Root issues replace the generic equipment/transport and unknown-cost
warnings. Unclassified failures explicitly require operator investigation;
they do not ask the user to edit random profile fields. Existing model/service
failures keep their separate error/retry controls.

Known dependent cost/gear questions collapse under their upstream input:
missing kilometres explain the corresponding transport cost; missing tent
capacity can explain a derived groundsheet requirement. The latter dependency
is accepted only from the known generated clarification format, a corresponding
saved root clarification, unknown required quantity and known owned quantity.
An actual stock shortage or an independently missing price is not erased.
Unknown costs remain null and all finalisation guards continue to apply.

For self-catered meals without a verified stove, both supported corrections are
available: register real available stove equipment, or explicitly change meals
and reconfirm the request. Model procurement suggestions never become owned
equipment automatically.

## Correction flow

Profile links carry a recognised focus field and the original request/plan
identifiers. The profile page reads the owned plan's related issues, provides
same-page shortcuts and focuses the relevant capacity, quantity, confirmation,
distance or transport control. Switching shortcuts keeps unsaved edits.
If an equipment record is absent, the add button is focused; clicking it can
prepare an empty record of the requested category without setting quantity,
capacity or confirmation. It does not save or claim ownership.

After explicitly saving, the return link loads an editable copy of the original
request. The user must regenerate the summary, verify the updated profile and
explicitly confirm before planning. The original request/plan/assessment is not
rewritten. A newer profile does not retrospectively clear old issues.

Data gaps identify missing prices, weather/source information or unsupported
rule inputs as system-data issues. They do not link to arbitrary user fields.
Safety-related information has a safety-tab action. External redirect URLs,
arbitrary DOM selectors and model-supplied navigation are not accepted.

## Verification

Browser acceptance used isolated SQLite, actual React/FastAPI and deterministic
rules, with zero campus model calls:

1. Created October 17–19, two people, AUD 1000, quiet/ready-to-eat and showers,
   deliberately omitting tent capacity, vehicle capacity and distance.
2. Result showed exactly those three roots. Groundsheet and derived expenses
   were explained under tent capacity rather than additional user tasks.
3. Tent link focused `gear-capacity-0`; same-page shortcuts focused
   `estimated-km` and `gear-capacity-12`. Filled 2 people, 100 kilometres and
   4 vehicle seats, retaining all other equipment records.
4. Explicitly saved, returned through the original-request link, regenerated,
   confirmed and planned. The new plan had zero issue panels and was explicitly
   saved as a final snapshot. Browser error-log inspection returned no entries.

Unit/HTTP regression covers source vs user gaps, observed/required values,
root deduplication, true essential shortages, independent missing prices,
meal/stove alternatives, safe fallback, owner isolation, unchanged saved
assessments after profile edits, restart/read consistency, finalisation and
reassessment feedback. Frontend tests cover focus targets, duplicate equipment,
unit/confirmation controls and rejection of arbitrary field selectors.

Exact final verification counts are in
[the validation summary](evidence/a32-validation-summary.json).

- [Concrete issue list](evidence/a32-actionable-issues.png)
- [Corrected and explicitly saved plan](evidence/a32-corrected-final.png)

The previous A31 full regression remains separate evidence. This round runs
the affected read/HTTP/UI suites, not a new full backend/model acceptance.
Existing user databases, private configuration and sealed data were not
modified. Temporary acceptance services are stopped after verification.
Restart normal development services and refresh the browser to see these
changes on existing plans. No database reset or campus request is needed to
display the saved root causes.
