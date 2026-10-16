# R-S02: exact advisory text policy and versioned replay

Date: 2026-10-16, Australia/Sydney. Branch: `feature/llm-safety-agent`.
Base B component: `7eab8e7`; common application base: `8a40deb`.

**R-S02 implemented; final A30 freeze and production integration remain pending.**
R-S01 is intentionally NOT fixed in this change. A must still supply the complete
A31/A32 baseline and exact SHA before supported kernel registration is agreed.
Neither the old nor the new identity schema accepts arbitrary new kernels.

## Changed policy, not silently cleaned text

All three advisory fields use the same current validator:
`interpretation_unverified`, `action_unverified`, `decision_summary_unverified`.
The action parser, proposal, tool evaluation, validated plan and pure replay all
enforce it. No trimming, replacement, Unicode normalisation or repaired fallback
proposal is returned. Invalid current proposals fail CONTRACT_INVALID.

The current implementation rejects:

- Unicode categories **Cc** (including C0, DEL and C1) and **Cf** (including bidi,
  zero-width and BOM format controls), plus **Zl/Zp** line/paragraph separators.
  Classification uses the Unicode database recorded in the policy/identity.
- Case-insensitive generic `scheme://` forms and the explicit prefixes `http:`,
  `https:`, `ftp:`, `ftps:`, `sftp:`, `file:`, `mailto:`, `tel:`, `sms:`, `data:`,
  `javascript:`; these prefixes are rejected even if the remainder is malformed.
- `www.` prefixes and the IDN dot variants U+3002, U+FF0E and U+FF61.
- DNS-shaped bare domains and domain-shaped email destinations. The pattern
  supports Unicode word-character labels and those dot variants; the final
  label requires at least two characters. It does not query a TLD registry.
- Inline Markdown links, including relative targets such as `[guide](/help)`.
- The existing numeric-literal, matched HTML-tag, code-fence and selected
  detectable false-clearance/instruction-injection phrase exclusions.

The exact regular expressions, flags, Unicode database version and excluded
categories are exported under `text_policy` in
[`contracts/safety_advisory_v2.schema.json`](contracts/safety_advisory_v2.schema.json).
Each advisory-field schema carries the text-policy version and SHA256. The
action-schema digest therefore changes if this exported policy changes; it is
included in the registered prompt identity. Field/count/UTF-8 limits remain.

Examples A reported now fail in every advisory field and in evaluation/final
model actions: embedded U+0085, embedded U+202E and `www.example.com`. Ordinary
English prose, accented letters, permitted whitespace and abbreviations like
`e.g.`/`U.S.` remain valid and byte-for-byte unchanged after serialization.

These are **detectable syntax exclusions**, not complete URL, obfuscation,
language or truth recognition. For example, spelling out a domain using words
is not an actual dotted link and is not detected. Some benign dotted tokens or
scheme-like labels may be rejected conservatively. Plain-text UI rendering,
unverified labels, human inspection and all official rule/finalisation guards
remain independently required. Authoritative source text is not rewritten or
made subject to model-advice restrictions by this fix.

## Registration and historical separation

| Identity | Original component | New registration |
| --- | --- | --- |
| Agent | campus-safety-advisory-agent-1 | campus-safety-advisory-agent-2 |
| Tool | safety-read-only-tools-1 | safety-read-only-tools-2 |
| Validator | safety-advisory-validation-1 | safety-advisory-validation-2 |
| Text policy | original limited blacklist | safety-advice-text-2 |
| Machine bundle | safety_advisory_v1.schema.json | safety_advisory_v2.schema.json |

The prompt instructions and SHA256 change; full configuration fingerprints
change as well. This is a new registration/new-run identity, not a hidden change
under an existing scope/write key. No official SafetyResult or source fact is
altered. Shared schema 1.0 and the proposed A-owned audit-envelope contract 1.0
are unchanged; they are separate from B's component validator versions.

Frozen pure replay modules under `backend/app/llm/safety_v1/` preserve the
original `7eab8e7` implementation. Only package-relative import depths and an
archive comment differ. They include no SafetyAgent or inference entry point;
the old machine bundle remains unchanged. The registry now dispatches:

```python
safety_validator_for('safety-advisory-validation-1')  # archived v1 artifacts
safety_validator_for('safety-advisory-validation-2')  # current artifacts
```

A must select the version from the **trusted saved registration**, not a caller's
requested version. Current registration accepts only v2 seed versions. Current
v2 replay rejects a v1 identity, and v1 replay still rejects tampered artifacts.
Historical readers must dispatch before parsing a v1 plan with current v2
classes; retain the selected validator's version-specific models/JSON rather
than coercing the validated archive back through the current text policy.
An old archived advice string that was valid under v1 can be verified without
being cleaned or promoted to current-policy approval. Unknown validator versions
still fail nonrecoverable PERSISTENCE_FAILURE; no regeneration or RETRY is added.

This preserves original verification semantics rather than retroactively
tightening v1 and making legitimate history unreadable. There is no production
safety audit yet: the historical tests use explicit synthetic archive fixtures,
not invented live inference evidence.

## Verification

Targeted command, no campus calls:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_safety_text_policy.py \
  tests/test_safety_contract_export.py tests/test_llm_safety_agent.py \
  tests/test_safety_advisory_boundaries.py -o addopts='' -q
```

The targeted suite passes **250 tests**: original component cases, all known
235 Cc/Cf characters for the current Unicode database, representative controls
in every field, link-form matrices, allowed unchanged text, evaluation/final
rejection, plan validation, identity changes, frozen-v1 export/replay and
tampering/downgrade rejection. A loop checks the complete Cc/Cf set; 235 is a
codepoint count, not an additional pytest test count.

Full regression results are recorded separately in
[`evidence/a30-rs02-check.json`](evidence/a30-rs02-check.json). Original v1
verification evidence is retained without rewriting its old test claims.

Final full backend run: **1175 passed, 0 failed, 0 skipped** (306.72 seconds),
including the 250 scoped tests; one existing Starlette TestClient/httpx warning.
Shared schema 1.0 and both exact schema-export checks passed. No frontend rerun
was needed for this backend-only correction; its sources/shared DTOs are unchanged.

## Next joint step and limits

A can review this exact text policy/version split now. Once A supplies the
complete A31/A32 SHA, B can address R-S01 using the authoritative kernel values,
then regenerate the current schema and run identity/combination regressions.
Do not label the contract frozen before that agreement.

No Hybrid/Orchestrator/factory/storage/UI/flag/database/configuration/data changes
were made here. No real campus model calls or paid-limit increases were made.
No live safety, production recovery or new 4096-token capability is claimed;
64 findings remain an offline structural bound, not a live token guarantee.
