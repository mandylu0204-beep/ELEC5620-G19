# A51 failure guidance and main compatibility

Date: 2026-10-18, Australia/Sydney.

## Change

The failed-plan panel now explains the next step using the server error category. Service/adapter/contract failures and incomplete persistence explicitly say that the user does not need to refill the camping request solely because of this failure. Invalid or unconfirmed requests instead ask for correction and confirmation. Unknown errors retain neutral wording. The text does not infer VPN, quota, gateway or timeout causes. Technical details remain collapsed. Retry availability, role permissions, command keys, snapshot checks and finalisation guards are unchanged.

This builds on A47 profile save-and-return and A48 saved-step recovery guidance. A fresh fetch confirmed `origin/main` remains `012929bd031cbf6f1fa2e1b24c56a458f065e9d1`; it is an ancestor of the A47/A48 branch. There are no new main commits to combine or resolve. The pending A45 model integration is not included here.

## Verification

- All 47 frontend tests passed; TypeScript and Vite production build passed. Added coverage distinguishes user-input failures from service/persistence failures and ensures unavailable retries remain unavailable. Existing profile return, replanning, safety advice binding and escaping tests also passed.
- Two fresh actual browser flows used the real application authentication, HTTP retry endpoint, dispatcher and SQLite with deterministic rules. Independent test database: `var/a51-browser/acceptance2.sqlite3`. Campus transports were denied; no campus model was called.
- One controlled persistence failure occurred before safety assessment save. The page showed saved itinerary/logistics, said the request need not be refilled, and offered Continue safety check. Browser continuation succeeded.
- A second controlled failure occurred before routing, after safety was already saved. The page listed both saved assessments and offered Continue unfinished steps. Browser continuation succeeded without repeating those saved assessments.
- Both runs ended SUCCEEDED/COMPLETED. Original version IDs and all previously saved assessment IDs were reused. Database totals: two versions, four assessments, zero final records; integrity check `ok`. The page offered final confirmation only after completion; no final-save operation was performed.
- Browser warning/error console entries: none. Local screenshots: `var/a51-browser/safety-interrupted.png` and `var/a51-browser/completion-interrupted.png`; machine check: `var/a51-browser/recovery-check.json`.

This is offline rules acceptance of the user experience, not evidence of successful real safety-model recovery. A50 remains blocked by a real HTTP 502. No original database, personal environment file, sealed dataset, backend source or model parameters changed. No GitHub push, main merge, hosted CI result or Canvas deployment acceptance is claimed. Temporary services and browser tab were stopped after verification.
