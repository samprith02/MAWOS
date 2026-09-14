# Redactions applied to archived evidence

**Date:** 2026-09-14
**Scope:** every file under `evaluation/results/`
**Reason:** real personal and institutional identifiers were captured into archived
LLM output during v2/v3, when the database was still seeded from real data. This
repository is public. The project's standing constraint is that no real data appears
anywhere — the identifiers below predate that constraint and survived it.

This file exists so the redaction is **visible**. Silently editing archived evidence
and saying nothing would be worse than the exposure it fixes.

## What was replaced

| Replaced | With | Count |
|---|---|---|
| `Samprith C Amin` | `[REDACTED NAME]` | 18 |
| `Mangalore Institute of Technology & Engineering (MITE)` | `MAWOS` | 1 |
| `Mangalore Institute of Technology & Engineering` | `MAWOS` | 1 |
| `MITE` | `MAWOS` | 3 |
| `4MT` (USN prefix, all occurrences) | `1VT` | 1724 |

Verified afterwards: zero remaining occurrences of `Samprith`, `4MT`, `MITE` or
`Mangalore` anywhere under `evaluation/results/`.

## Files touched

```
v3_archive/v3_gates/p3_provenance.json
v3_archive/v3_gates/p3_provenance.md
v3_archive/v3_llm/qwen2-5_1-5b-instruct.json
v3_archive/v3_llm/qwen2-5_3b-instruct.json
v3_archive/v3_llm/qwen2-5_7b-instruct.json
v4_gates/_r05_checkpoint.json
v4_gates/r05_findings.md
v4_gates/r05_provider.json
v4_gates/r05_provider_20260901.json
```

## What this does and does not change

**Does not change any measurement.** Every substitution is a same-shape string swap
inside free-text fields and identifier strings. No score, latency, count, verdict or
threshold was touched, and no file's structure changed. Every number in these files
still means exactly what it meant before.

**The USN substitution is the one already on record.** `4MT` → `1VT` is the same
repair `OPEN_DECISIONS.md` records for `evaluation/probe/items.py` on 2026-09-14
(the R1 institution's prefix replacing the retired v3 one). Applying it to the
archives makes the actor identifier consistent across every artefact in the
repository rather than leaving the archives as the sole place the retired prefix
survived.

**The name redaction is marked, not substituted.** `[REDACTED NAME]` rather than a
replacement name, so a later reader can see that a redaction happened at that exact
point instead of reading a pseudonym as though it were the captured output.

**None of these files are hashed.** `evaluation/freeze_manifest.py` freezes eight
files — the benchmark and baseline sources plus `router_config.json` — and no results
file is among them. `python evaluation/freeze_manifest.py` still verifies clean after
this pass.

## Still outstanding — a decision, not an oversight

`git history` is not rewritten. The identifiers remain in commits already pushed to
`github.com/samprith02/MAWOS`. Removing them from history requires a force-push that
rewrites every commit since the data was introduced, which breaks every existing
clone and every commit hash cited in `OPEN_DECISIONS.md` and the execution ledger.
That trade is the repository owner's call, not a cleanup to perform silently.

`CLAUDE.md`'s header line still names the team's real department and institution as
project provenance. That is documentation about who built this, not seeded data, and
it is deliberately left alone — but it is the last place a real institution name
appears in the repository, so it is recorded here as a known, deliberate exception.
