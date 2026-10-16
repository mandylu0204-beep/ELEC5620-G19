# A31: Clarify meals before confirming a trip

Date: 2026-10-16, Australia/Sydney. Base: main `8a40deb`.

## Problem and resulting behaviour

The reported Lake Meadow plan had passed safety and feasible car transport.
Its missing meal choice produced an unknown food cost, a conservatively assumed
stove shortage and duplicate meal clarification. The page then suggested
changing equipment or transport without identifying the actual decision.

Requests now expose an explicit meal selector. Rules interpretation requires
one confirmed meal mode before request confirmation; unresolved or contradictory
choices stay in clarification. No default is chosen. The selector writes the
existing canonical preferences, preserving shared schema 1.0. Empty structured
preferences are omitted from the frontend payload so they do not suppress a
meal preference stated in natural-language input. Explicit structured choices
still take precedence over text, as in the existing contract.

For existing requests without a meal mode, v2 conditional cooking equipment is
UNCONFIRMED with unknown required/missing quantities, rather than a confirmed
stove shortage. Unknown food/equipment cost lines remain unknown; totals remain
null. The meal choice is one actionable clarification rather than duplicate
rule-input, conditional-stock and derived-cost questions. Independent missing
stock, prices and transport requirements remain enforced. A self-catered choice
still requires applicable cooking equipment and cannot be replaced by a model
proposal or an automatic inventory confirmation.

The result page explains that the meal choice is required and directs the user
to edit/reconfirm the request. It does not claim already feasible transport is
unconfirmed. Old saved assessments are immutable and are not rewritten on read;
display guidance recognises their existing meal clarification fields.

## Identity and history

New kernel and v2 rules identities append `/a-meal-clarification-v1`. New runs
therefore cannot silently reuse the previous rule identity. The prior logistics
audit kernel identity remains supported by the pure verifier over saved input
and baseline snapshots; it does not trigger model calls or replay today's rule
baseline over historical records. All four A29 model logistics audits were
verified through A's loader using a read-only SQLite connection after this
change. No user database, migration, private configuration or sealed dataset
was changed.

## Browser acceptance

An independent database, actual FastAPI/React services and deterministic rules
were used. No campus model calls were made in this round.

1. Entered October 17–19, two people, AUD 1000, quiet preference and showers.
   Intentionally omitted meal mode. The summary required a meal choice and
   disabled confirmation. The correction button focused the meal selector.
2. Explicitly chose ready-to-eat meals and regenerated the summary. The request
   became confirmable without changing date, budget, group size or showers.
3. Confirmed and planned through the UI. Rules selected River Flat, estimated
   AUD 241, passed logistics and safety and enabled final saving. Campsite
   selection was not forced to equal the earlier model-selected Lake Meadow.
4. Explicitly acknowledged and saved a real final snapshot through the browser.
   Console error inspection returned no entries.

[Saved browser result](evidence/a31-meal-choice-final.png).

Automated coverage includes HTTP refusal of unresolved confirmation, explicit
correction and successful planning, legacy missing-meal conditional gear,
preservation of unknown costs and independent questions, plus the existing
planning/logistics/model audit regression suites. Exact verification counts are
recorded in [the verification summary](evidence/a31-validation-summary.json).
Full backend coverage: 926 cases, 882 passed and 44 Windows symlink-privilege
skips, no errors or failures. After consolidating the derived conditional-cost
question, the affected HTTP/logistics/model-component/audit suite passed again.
Frontend: 9 tests, type checking and production build passed. Shared JSON
schema verification passed without generated schema changes.

## Scope and next use

Restart the normal development services and refresh the browser to load the
change. For an existing confirmed request, use Adjust request and reconfirm,
choose meals, regenerate the summary and explicitly confirm. Existing plans
and final snapshots remain available. Genuine equipment gaps, invalid dates,
unsupported regions and missing safety evidence can still require action;
this fix addresses the meal-related chain, not every possible planning failure.

The separate A30 safety-agent proposal is still a draft and is not part of
this business change. No GitHub push or new live campus acceptance is implied
by this local report.
