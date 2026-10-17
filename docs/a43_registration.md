# A43 camper account registration

Date: 2026-10-17. Base: A42 cbec236.

The login page links to `/register`. Registration collects a display name,
username, password and password confirmation. A successful registration returns
to login with the normalized username prefilled and a success notice; successful
login continues to the intended permitted page, or profile onboarding for a new
signup. Passwords are not passed in route state or URLs. Password mismatch is
handled before submission; duplicate usernames and service errors remain visible.

`POST /api/v1/auth/register` accepts `username`, `display_name`, and `password`
with the existing same-origin client header. It returns HTTP 201 and public user
data with no-store caching, without issuing a session. Login continues using the
existing HttpOnly/SameSite cookie and CSRF lifecycle. New users always receive
the CAMPER role; extra privilege/owner fields are rejected by the input model.

Usernames are ASCII, 3-32 characters, alphanumeric first, followed by letters,
digits, dot, underscore or hyphen. Registration and login normalize case; the
registration transaction checks case-insensitive uniqueness under SQLite's
existing immediate-write lock. Demo usernames stay reserved. Nicknames are
trimmed, 1-80 characters, without control/format characters. Passwords are 8-256
characters and cannot be all whitespace. They retain their exact input and use
the existing salted PBKDF2-SHA256/600000 implementation. Public responses do not
expose passwords or hashes. The existing users table supports this directly;
there is no migration or dependency change.

Validation: 13 registration/account backend tests passed, including password
hashing, login after restart, new-profile isolation, review permission denial,
duplicate/case handling, client header, privilege injection and invalid inputs.
All 37 frontend tests, TypeScript/Vite build, shared schema and diff checks passed.
No full backend regression pass is claimed for this change.

Browser verification used a separate `var/a43-browser.sqlite3` database and
local services on ports 8791/5391. The login registration link opened the form;
mismatched passwords produced an inline error. Matching passwords registered a
synthetic account, returned to login and successfully signed in to an empty
profile as Camper. The new account saved its own profile successfully. No browser
console errors were recorded. Screenshot: `evidence/a43-register-page.jpg`.

Personal configuration and existing user database/accounts were not changed.
No campus model calls were made. Restart the backend to enable the new endpoint.
