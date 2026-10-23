# A90 review-status presentation

Base: main fee6bb7. Resolves the two A88 presentation limitations only.

- display_status recognises explicit saved ROAD/CLOSED evidence before the review
  route. PENDING/RUNNING/FAILED/CANCELLED and immutable FINALISED display priority
  remains unchanged. It does not change the saved assessment, routing, eligibility
  or review policy. The ordinary status label says adjust plan.
- Safety summary, action guidance and road warning consistently ask the user to
  change to an accessible campground instead of waiting for approval. No road
  closure is inferred from prose or an unknown road state.
- Historical approved finals require matching final-history plan/run/version and
  APPROVE version context including input fingerprint, a succeeded FINALISED
  version, and no current-input error. They show a past-approval label and suppress
  the incorrect pending-review warning. This is distinct from validApproval and
  never changes finalisation_available or any command body. Current and final
  snapshot approval display behaviour remains intact.

Local verification: backend 50 passed, frontend 110 passed, no failures/errors/
skips; shared schemas, types and build pass. Existing >500 kB chunk warning
remains. Browser checks used a fresh backup of the explicit isolated A88 fixtures:
closed road now says adjustment/change campground; historical final says approved
at that time; successor still waits for its own review and cannot be saved.
No campus calls, cloud testing, full-suite rerun, migrations or personal data
changes. Screenshots and raw logs/DB remain ignored under var; finite hashes and
results are in evidence/a90-review-display.json.

The old A88 limitations remain a historical report; this new result supersedes
those display limitations only, not real-model acceptance or full regression.
B should review the display-only historical matching and road priority boundaries.
