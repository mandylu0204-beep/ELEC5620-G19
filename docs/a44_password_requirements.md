# A44 registration password requirements

Date: 2026-10-17. Base: A43 32a9009.

New registration passwords require 8-256 characters and at least one uppercase
ASCII letter, lowercase ASCII letter, ASCII digit and ASCII punctuation symbol.
Space does not satisfy punctuation. The form shows each requirement directly
under the password field, updating its text, icon and color as the user types.
The list has a polite live region and does not rely on color alone. Registration
submission stays disabled until all five rules pass; the submit handler repeats
the check, and the backend independently enforces the same categories. Existing
login authentication is unchanged and passwords are never silently trimmed.

Validation: 23 registration/account backend tests passed, covering missing
categories, whitespace, non-ASCII symbols, invalid lengths, accepted 8/256
boundaries, registration/login, hashing, persistence and isolation. All 39
frontend tests and TypeScript/Vite build passed. Browser checks used an isolated
database: lowercase-only showed only length/lowercase complete, adding uppercase
and digits left punctuation pending, and adding punctuation completed every
rule and enabled the registration button. No browser console errors. Screenshot:
`evidence/a44-password-progress.jpg`.

No migration, dependencies, user database changes or campus model calls. No full
backend regression pass is claimed. Restart backend for the API enforcement.
