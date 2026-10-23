# A88 human review browser acceptance

Base application source: 0c7dbbd; 81e7825 adds A85 documentation only.
See evidence/a88-human-review-browser.json for finite results and screenshot hashes.

Used an independent SQLite backup, normal local HTTP service and browser at
loopback ports 8088/5188. All roles use existing public seed accounts. Normal
runtime date, permissions and persistence guards remain enabled. High-risk and
closed-road cases are explicit saved assessment fixtures built through original
ports from a copied Sydney context, not real model or live-risk findings.
The successor request was created, interpreted and confirmed through the browser;
a separate fixture reassessment supplies its new risk-review requirement.

Founder queue -> approval with mandatory reason -> Camper result/reason read ->
explicit final save passed. A closed-road task exposes correction/help only;
forced local HTTP APPROVE was rejected with 409 INVALID_STATE. A successor with
new review-required assessment had no review and no valid_review_id; its final
save using the predecessor review was rejected with 409 STALE_CONTEXT. The old
final snapshot remains readable and does not authorise the successor.

Browser discovery: after finalising, current plan details lost the approval label
because eligibility becomes null. The narrow frontend fix recognises only a
succeeded FINALISED result with a current final matching both run and version.
It grants no operation; all commands still depend on server flags and guards.
The browser rechecked final save -> return to current plan: approved label remains
and the false pending-review warning disappears. Added regression checks reject
mismatched run/version, non-current final and running execution.

Frontend 108 passed / 0 failed / 0 skipped; types and build pass. Existing chunk
warning >500 kB remains. No backend production changes, full-suite rerun, cloud
CI or campus model request. Private DB, setup scripts, sessions and screenshots
remain ignored under var/a88-review-browser. Initial fixture setup attempts were
corrected locally before acceptance; no shared source guard was relaxed.

Presentation limitation: the deliberately injected closed-road REVIEW fixture
still has a waiting-review top badge, while its decision panel correctly says
correction-only and rejects approval. Historical plan detail may show its original
assessment review requirement; the final snapshot retains the original approval.
These do not grant approval/finalisation capabilities. New display fix needs B's
narrow source review; do not relabel the previous candidate review as covering it.
