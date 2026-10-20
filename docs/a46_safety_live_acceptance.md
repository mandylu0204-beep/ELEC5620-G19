# A46 real campus safety acceptance: partial failure

Date: 2026-10-17, Australia/Sydney. Code under review: `05568f0`, combining B `5cbe255` with main `012929b`. The exact code passed combined CI (1360 backend tests, 39 frontend tests, schema and build): https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/39001085367 . Main remains unchanged by this safety integration.

The application used the real Sydney clock, rolling synthetic 2.1 snapshots, actual authentication/confirmation/dispatcher, an isolated SQLite database and the real campus client. No model reply, campsite selection, business result or trace was mocked. The request was the synthetic normal profile, October 18–20, two people, AUD320 budget. The actual planning model selected Wattle Rest.

The existing private file still specifies 2048 completion tokens. This acceptance explicitly used the previously accepted candidate configuration only in its process: 4096 completion tokens, reasoning_effort=low, 45-second timeout, at most two attempts and four role turns. These results do not validate the private 2048 settings. Private environment files, the existing user database, sealed data, default safety mode and production source were not changed.

## Observed result

Seven actual campus HTTP requests: PLANNING 2x200, LOGISTICS 3x200, SAFETY 1x200 followed by 1x502. The safety failure occurred on its second model turn, after reading safety facts. The transport observed response headers with HTTP502 after approximately 30.3 seconds. This does not establish the upstream cause or prove that increasing the local timeout would help. No complete safety proposal was returned or accepted, so output completeness at 4096 tokens is still unverified.

The acceptance transport imposed a 24-request cap and stopped further network requests after the first HTTP/network failure. It passed real successful responses unchanged to the production client. After the 502, this guard blocked the client's automatic retry before transmission. Consequently the application's final recoverable error is the client's network-failure message; it must not be described as the exact error/message an uninstrumented second attempt would produce. No manual retry was performed and no token/timeout/retry limit was increased.

The application saved version1, its original planning trace, a PASSED logistics assessment and an independent logistics audit. It then failed at ASSESSING_SAFETY. There is no safety assessment, safety audit or final record produced by this run. Model failure did not become rule success and finalisation_available is false. The trip estimate AUD251 is synthetic trip cost, not model/API billing. Token usage and monetary charges were not measured.

## Failure-state acceptance

After an application restart, the saved plan still shows the original itinerary and AUD251 logistics estimate, an incomplete run, safety not checked, a retry entry and disabled final save. No fabricated AI safety advice is displayed. Browser console error log was empty. No retry/replan control was activated.

A direct finalisation request containing the only saved assessment was rejected with HTTP422 because a complete assessment pair is absent. This is request-contract rejection, not a claimed business-level HTTP409 finalisation test. The public finalisation eligibility is false. SQLite integrity_check returned ok, foreign_key_check returned no rows. Counts: one version, one assessment, one planning trace, one logistics audit, zero safety audits. Restart/read verification sent no further campus calls.

Evidence: [sanitised summary](evidence/a46-live-safety-check.json), [browser failure state](evidence/a46-live-safety-502.png). The database, session, credentials, full prompts, raw model replies and private reasoning are not included.

## Next action for A/B

This round is not a live acceptance pass and does not justify merging safety integration into main. B should review the second-turn safety request's latency/output size and the campus proxy's upstream timeout/error behaviour, retaining strict output validation, deterministic safety conclusions and existing audit identities. A will retain the isolated failed run and prior artifacts for a bounded retry once an appropriate next diagnostic is agreed. A single502 does not establish a B implementation defect. Do not switch to rule success, fabricate a trace, relax blockers or silently enlarge token/retry budgets.

Real successful safety advisory rendering, final save, REVISE, REASSESS and post-commit safety receipt recovery remain unaccepted in this round. The previous mock/offline coverage must remain clearly distinguished.

## Diagnostic field clarification for B

The saved SafetyAgent error context reports `request_message_bytes=15364`: the sum of UTF-8 lengths of message content strings. This excludes JSON framing/escaping, message roles, model parameters and HTTP headers, so it is **not** the actual HTTP request-body size. The latter was not captured. The 30.266-second transport measurement is time to response headers for the failed request. Component `elapsed_ms=31484` starts at the safety assessment entry and includes the first successful turn and locally blocked retry; it is not the second request duration alone.

Response-header correlation IDs were **not captured** by the original observer. Their value is null with an explicit NOT_CAPTURED status in the summary; this does not mean the proxy returned none. No new campus call was made to invent or obtain a replacement ID. A future bounded diagnostic should record actual request-body byte length and allowlisted request/trace ID response headers, excluding credentials, cookies, full prompts and raw replies. The absent safety dependency check is marked not applicable, rather than a mismatched dependency.
