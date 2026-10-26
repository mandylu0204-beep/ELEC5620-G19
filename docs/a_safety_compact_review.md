# A review of B compact safety candidate

Reviewed source: `57bbdc0`, based on main `0c56764`.
Date: 2026-10-26, Australia/Sydney.

## Conclusion

No blocking defect was found in the candidate's lossless fact projection,
short-reference binding, complete finding/action validation, strict text limits,
exact final proposal, expanded-plan hash or separation from existing protocols.
This is a standalone component review, not approval to enable production v4.

The commit adds ten files. Existing v1/v2/v3 implementations, the production
factory, audit dispatch, default rules mode and database schema remain unchanged.
The six frozen candidate file hashes in the live report match the commit bytes.

## Independent local checks

- Native Windows, Python 3.12.14: the eight-module guarded safety suite completed
  with 388 passed, zero failed/errors/skipped, exit code zero. Terminal wall time
  was 187.18 seconds; JUnit reports 187.109 seconds. The real HTTP guard was never
  triggered. This is not a whole-project or cloud CI result.
- v4 candidate schema and shared schema checks passed.
- 43 shared-evidence consistency checks passed, including frozen file hashes,
  request budget/count, no retry/reset, statuses, timestamps/time zones, usage
  arithmetic, the first two offline/live request byte counts and hashes, distinct
  v3/v4 identities, unchanged artifact summaries and no formal writes.
- The public fixture benchmark reproduces second-body sizes 17,321 to 12,481
  bytes, facts 9,621 to 6,079 bytes, and example evaluation output 2,258 to 873
  bytes. All request hashes match B's public fixture evidence. This does not
  independently reproduce B's private Euroka fixture.

## Windows benchmark issue

The unmodified `scripts/safety_compact_benchmark.py` patches all socket connects
before `asyncio.run` creates its event loop. Windows asyncio constructs a local
socket pair for its self-pipe, so the guard raises before the benchmark runs.
The failure is a benchmark portability issue, not a campus connection failure.

For independent measurement, A used a process-local wrapper that created both
asyncio runners before enabling the existing socket/HTTP guards, then executed
the same fixture and comparison under those guards. Network attempts were zero;
candidate source files and production code were not patched. B should provide a
portable benchmark fix and regression without broadly permitting network access.

## Meaning of the reported live result

B's report records three 200/stop responses and successful standalone replay.
The second response took 27.138386 seconds with completion_tokens=2565. It remains
near the earlier failure time and is not evidence of stable resolution of 502,
lower token use, or suitability of a 2048-token limit. The historical input uses
the original snapshot/date and is not current-date finalisation acceptance.

A checked the shared evidence, but did not rerun campus requests or independently
reproduce B's private database, live response bodies or private controller.
The archived single advice is correctly presented as one generated sentence
mapped to two compatibility fields, not two independent model explanations.

## Next integration boundary

1. Freeze explicit v4 new-write registration separately from archived v1/v2/v3
   replay. Keep complete seed/codec/prompt/client identity validation.
2. Connect A's factory, audit save/read dispatch and model-advice presentation;
   retain the existing persistence signatures and shared envelope.
3. Verify checkpoint roles, lost receipts, restart reads, ownership isolation,
   stale-context checks, human-review and finalisation guards locally. Do not
   relabel a v3 or 2048 failure as a v4 run or regenerate missing old traces.
4. Verify one advice is displayed once and formal deterministic safety results
   remain authoritative. Default safety stays rules.
5. Arrange any further bounded live integration acceptance separately. Do not
   repeat the completed standalone diagnostic merely to obtain another success.

This review created no campus calls, formal assessments/audits or cloud tests,
and did not change the user's main checkout, personal settings or original DB.
Local JUnit and evidence-check details are under this review worktree's `var/`.
