# Frontend recovery after external DOM changes

## Report and scope

After saving equipment, the user saw a blank page at the trip's `/update`
route and reported `NotFoundError` from React's `removeChild` operation.
Local read-only inspection confirmed the profile was saved, a linked update
draft existed, and no new planning run had begun after that save. The existing
plan/check results were retained. This was not a new campus-model failure.

The error is consistent with external DOM mutation. React tracks the same
failure when translation software replaces text nodes before a later commit:
[React issue 11538](https://github.com/react/react/issues/11538) and
[React issue 26048](https://github.com/react/react/issues/26048). The specific
extension/action on the user's browser was not independently identified.

## Change

- The React-owned root declares `translate="no"` and `notranslate`, so automatic
  translators that honour these markers leave its nodes intact. This does not
  guarantee protection against extensions that ignore them or forcibly edit DOM.
- The root uses React 19's documented
  [onUncaughtError callback](https://react.dev/reference/react-dom/client/createRoot)
  to show a small native recovery panel after an uncaught render/commit failure.
  Recovery is outside the failed React tree and does not replay commands.
- The panel offers an explicit reload and a local link back to the source plan
  (or plan list). DOM mismatch errors also suggest disabling automatic page
  translation before reloading. No raw exception, profile or model text is shown.
- No Node prototype patches, silent DOM-operation suppression, automatic
  remount/retry, storage clearing, confirmation, planning call or backend change.
- No logs or error data are sent or persisted by the recovery handler.

The already loaded damaged page may still need the translation tool switched
to its original-text mode, followed by Ctrl+Shift+R. Publication to main does
not establish which extension modified the original user's page; that source
remains unconfirmed.

## Offline validation

The final full frontend suite passed **251 tests**, zero failures/skips, with
type checking and production build passing. The existing large-chunk build
warning remains. One older presentation assertion still required the cooking
warning paragraph the user had explicitly requested to delete; it now checks
the paragraph stays absent while the real fuel requirement/availability/gap
remain visible and the saved gap stays unchanged.

Four independent browser scenarios passed in both installed Chrome and Edge:

1. An unprotected React control reproduces the reported `NotFoundError` and
   blank root after simulated translation replaces its conditional text nodes.
2. A marker-respecting translator leaves the protected control intact through
   the same state change.
3. Forced mutation ignoring the markers still triggers the error, but the
   recovery panel remains visible instead of a blank page.
4. The actual ProfilePage, login guard, TripUpdateEntry and RequestDetail run
   under StrictMode: edit equipment, save once, prepare the idempotent draft,
   and navigate to it. No interpret, confirm or planning endpoint is called.

The manual browser suite uses installed Chromium, fresh profiles under ignored
`var/`, blocked DNS/HTTP and in-memory API mocks. It does not attach to the user's
browser, run an application server, use an original database or call a model.
Windows GUI headless stdout was empty, so the runner uses only the private
local debug endpoint generated in its own newly created browser profile. Early
runner/fixture failures were corrected; neither is presented as an app result.
There were no cloud tests or campus calls.

To run the reusable browser regression from `frontend`:

```text
node browser-tests/run_dom_recovery.mjs
```

Set `CAMPMATE_TEST_BROWSER` to an installed Chromium executable when necessary.
No browser or dependency is downloaded. The user-browser extension itself has
not been automated or independently reproduced.
