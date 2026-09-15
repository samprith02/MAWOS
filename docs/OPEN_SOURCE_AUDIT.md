# Open-source readiness audit — 2026-09-15

**Scope:** the whole `samprith02/MAWOS` repository (236 tracked files, 75 commits), audited
before applying an open-source licence.
**Question asked:** is there anything here — third-party code, dependencies, embedded source
material, secrets, or licence restrictions — that would prevent public distribution?
**Outcome:** **VidyaERP was split out and published**; MAWOS was **not** licensed.

---

## 0. The finding that set the shape of everything else

`samprith02/MAWOS` was **already public** — created 2026-08-12, `license: NONE`, 0 forks,
0 stars, 0 watchers.

That inverts the usual reasoning. "Already public with no licence" means the code is visible
but *all rights are reserved*: nobody may legally copy, modify or reuse it. **Adding a licence
is therefore not a formality — it is the act that grants the world permission to redistribute
everything in the tree.** Anything in the repository that is not the owner's to license had to
be resolved *before* a LICENSE file, not after.

---

## 1. Method

| Surface | How it was checked |
|---|---|
| Secrets, tracked files | regex sweep for provider key shapes + assignment patterns |
| Secrets, history | same sweep across all 75 commits (`git grep` over `git rev-list --all`) |
| Personal data, tracked | identifier sweep (name, institution, USN prefix, teammate names, emails) |
| Personal data, binaries | OOXML unzip + text extraction from `.docx` / `.pptx` |
| Personal data, history | identifier sweep across all commits |
| Data provenance | inspected every tracked archive and database |
| Third-party code | copyright-header and SPDX sweep; external `<script>`/CDN reference sweep |
| Dependencies | manifest read; per-package licence identification |
| Copyright ownership | commit-author tally, then **repo-wide `git blame`** on every tracked text file |

---

## 2. Findings

### 2.1 Clear — no action needed

- **No secrets.** Nothing key-shaped in tracked files, and nothing across all 75 commits.
  `.env` is correctly ignored everywhere, including `VidyaERP/erp/.env`; both `.env.example`
  files carry blank values.
- **No vendored third-party source.** No copyright headers, no SPDX identifiers, no bundled
  libraries. The frontends reference no CDN — the only external URLs in the tree are provider
  API endpoints.
- **The ITC-2007 harness was already correct.** `evaluation/itc2007/build.py` *fetches* the
  official validator and records its URL and SHA-256 rather than vendoring it, and the
  competition instances are gitignored as not ours to redistribute. This is the pattern the
  UCI data in §2.3 should have followed.

### 2.2 Copyright — smaller than the commit log suggests

Four commit identities: the owner (57 commits), plus three classmates (9, 8 and 1 commits)
who contributed real work — the Placement Agent, a Postgres/Alembic baseline, a library agent.

A repo-wide `git blame` over every tracked text file returned **122,000 lines, all attributed
to the owner — zero surviving co-author lines in HEAD.** Their files were either removed or
rewritten during the v4 re-aim. So the *current snapshot* is the owner's alone to license.

Their contributions remain in **git history**, which ships with every clone. That is a weaker
claim than live code, but it is why a licence over the MAWOS repo still deserves a one-line
"fine by me" from each of them, and why a fresh history avoids the question entirely.

### 2.3 Blockers for licensing the MAWOS repository

**Third-party personal data in tracked presentation binaries.**
`MAWOS_Review1.pptx` and `MAWOS_Review1_Manuscript.docx` contain the real USNs of all four
team members, the real institution, the team number, and two faculty guides' real names; the
`.pptx` also carries the owner's name in its document metadata. The owner can consent to
publishing his own identifiers. He cannot consent on behalf of three classmates and two staff
members, and an Apache 2.0 grant would invite redistribution of exactly that.

**A third-party dataset is redistributed.**
`ml/data/external/` ships UCI dataset #320, *Student Performance* (Cortez & Silva) — real
records of 1,044 Portuguese secondary-school students, minors, including sex, age, family
cohabitation status, alcohol consumption and grades. It is tracked **twice**, zipped and
extracted as `student-mat.csv` / `student-por.csv`.

`.gitignore:11` reads `ml/data/*.csv`, so the intent not to redistribute these was already
there — the rule simply does not reach `ml/data/external/student/`. The data is also
**unnecessary**: only the derived correlation matrix `ml/data/calibration.json` is read at
runtime, and `ml/calibrate.py:43` already handles the raw files' absence by printing the UCI
download URL. It is UCI-licensed, not the owner's, so Apache 2.0 cannot be applied over it.

**Residual identifiers in tracked source.** `tests/test_generator.py` still carries real first
names and the retired `4MT` prefix; `README.md` and `CLAUDE.md` still name the real
institution. The 2026-09-14 redaction pass covered `evaluation/results/` only.

### 2.4 Dependency licences

All permissive except one: **`psycopg[binary]` is LGPL-3.0** — already flagged in
`requirements.txt`. Importing it from Python does not impose LGPL terms on this code; static
linking or modification would. It is worth knowing given the stated intent to take this work
into a commercial setting. Everything else is MIT or BSD. **VidyaERP does not use psycopg at
all.**

### 2.5 Correction to the project record

`CLAUDE.md` describes `teacher-erp-with-timetable-simulation/` (Chronos) as "a teammate's"
reference app. Its git remote is `github.com/samprith02/chronos-teacher-erp-timetable` — **it
is the owner's own repository.** This matters: `VidyaERP/solver.py` is a port of Chronos's
solver, and the port is therefore the owner's to relicense. Recorded in the published
`NOTICE` rather than left to inference.

---

## 3. What was done

Every blocker above is a *MAWOS* problem. VidyaERP was re-scanned in isolation and is clean:
zero hits for any name, institution, USN, teammate identifier or email; entirely synthetic
data; two permissive dependencies.

**VidyaERP was published as its own repository with fresh history** —
<https://github.com/samprith02/VidyaERP>, Apache 2.0, 20 files. This resolves all three
blockers at once: no classmates' USNs, no UCI records, no co-author history.

Deliberately excluded from the published repository:

| Excluded | Why |
|---|---|
| `MAWOS_Review1.pptx`, `.docx` | college presentation material, and §2.3's personal data. Left untouched on disk |
| UCI dataset | not ours to redistribute; VidyaERP never used it |
| `college.db` | `db.seed()` reproduces it — verified table-by-table — and a tracked 244 KB binary churns on every run. The copy it replaced had five stray `audit` rows from a demo, committed by accident |
| `.env` | secret |

Added: `LICENSE` (canonical Apache 2.0, fetched from apache.org), `NOTICE` (provenance,
dependency licences, synthetic-data statement), `requirements.txt` (which VidyaERP previously
lacked entirely), a real `.gitignore`, and a README quickstart and licence section.

Verified before publishing: a clean-slate clone seeds its own database, `solver_test.py`
passes 44/44, the rule-engine smoke regression routes identically, and the app serves with the
solver stream working.

---

## 4. Still open — decisions for the repository owner

1. **The MAWOS repository is still public, still unlicensed, and still exposes §2.3.** The
   presentation binaries and the UCI records are readable by anyone today. Removing them from
   `HEAD` is a normal commit; removing them from *history* needs `git filter-repo` and a
   force-push, which rewrites every commit hash — including those cited in
   `docs/v4/OPEN_DECISIONS.md` and the execution ledger. Only four commits touch those paths,
   so the rewrite itself is small. `evaluation/results/REDACTIONS.md` already records the same
   trade-off for the name redaction and reaches the same conclusion: it is the owner's call.
2. **Licensing MAWOS** would additionally want a one-line agreement from the three co-authors
   (§2.2).
3. **AI-assistant terms.** VidyaERP was generated with LM Arena Agent Mode. Most providers
   assign output ownership to the user, but that was not verifiable from here and is worth
   confirming against their terms.

---

## 5. One-line summary

MAWOS could not be licensed as it stood — it redistributes a third-party dataset of minors'
records and three classmates' and two staff members' identifiers. VidyaERP shared none of those
problems, so it was split out and published under Apache 2.0 with clean history.
