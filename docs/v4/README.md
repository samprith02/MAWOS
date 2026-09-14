# MAWOS v4 — Decision Record (R0)

**Status: R0 decision freeze. Written 2026-08-31. No implementation has begun.**

This directory is the blueprint for MAWOS v4. It exists so that R1 starts with no ambiguity
about what is being built, and — equally important — what is deliberately **not** being
built.

---

## Why v4 exists

MAWOS has been rebuilt twice (v1 → v2 → v3-research). The v3 branch is methodologically
disciplined: frozen instruments, pre-registered thresholds, hashed configs, an externally
cross-validated cost model, and an explicit rule against headline 100% figures. None of that
is being discarded.

What is being changed is the **aim**. `docs/RESEARCH_PLAN_V3.md` states its own position at
the top:

> "the university system is the **experimental platform**, not the claimed contribution."

That single decision is the root cause of the four problems v4 addresses:

| Symptom | Root cause in v3 |
|---|---|
| The assistant feels like a command interface | τ = 0 routes ~90% of queries *around* the LLM by design, to minimise local-inference cost. The remaining path is `regex → 1 tool → hardcoded formatter` |
| No multi-step tasks | All 12 tools are read-only getters. There are no steps to execute |
| The timetable model is thin | Rooms were explicitly descoped — §0.2(b): *"MAWOS has no room model"* |
| Nothing is deployable | SQLite file + a portable Windows Ollama install + a 2 GB model on a 6 GB laptop GPU |

v4 re-aims the project at a question the system can actually answer, and that requires the
multi-agent architecture to exist rather than merely to be claimed. See `07_CONTRIBUTION.md`.

**This is a re-aiming, not a rewrite.** Roughly 40% of the v3 codebase survives verbatim.

---

## Relationship to v3 documents

| v3 document | v4 status |
|---|---|
| `docs/RESEARCH_PLAN_V3.md` | **Historical record. Not edited, not deleted.** It is the dated, pre-registered decision trail for P0–P8 and remains a viva defence for everything done before 2026-08-31 |
| `evaluation/PROTOCOL.md` | **Still binding.** v4 inherits the protocol wholesale — dev/test separation, seed variance, instrument-version guards, the changelog requirement |
| `evaluation/results/v3_*` | **Superseded, not corrected.** Archived at R1 with a `SUPERSEDED.md` naming the instrument that produced each. No v4 number may be differenced against a v3 number |
| `docs/ARCHITECTURE.md`, `evaluation/results/v2_historical/RESULTS.md` | Still carry v2-era numbers by design. Rewritten at R8 (this was v3's pending P8) |
| `docs/DATASET_METHODOLOGY.md` | **Carries forward.** The UCI calibration survives; only its consumers change. See `04_DATA_MODEL.md` |
| `CLAUDE.md` working rules | **Kept verbatim.** Never headline 100%; report in the direction the data points; cite which instrument; never present an unregenerable number |

---

## The documents

| File | Covers | One-line summary |
|---|---|---|
| `01_ARCHITECTURE.md` | target architecture, agent criterion and boundaries, delegation contract | What the system is and how its parts talk |
| `02_SCOPE.md` | MVRS, MUST/SHOULD/NICE/DO-NOT-BUILD | The scope contract if time collapses |
| `03_LLM_LAYER.md` | LLM requirements, fallback ladder, R0.5 probe spec | What the model layer must do, and how a provider gets chosen |
| `04_DATA_MODEL.md` | dataset and schema design decision | What data exists and where it comes from |
| `05_TIMETABLE_SCOPE.md` | minimum constraint model and algorithm | How the timetable stays a capability, not a second project |
| `06_BENCHMARK.md` | task categories, outcome checking, authoring protocol | The instrument the claims rest on |
| `07_CONTRIBUTION.md` | contribution statement, claims made and not made | What is technically meaningful here |
| `08_DEPLOYMENT.md` | deployment topology and hardening | How this actually runs somewhere real |
| `09_ROADMAP.md` | R0–R8, dependencies, critical path, gates | Build order and what closes each phase |
| `OPEN_DECISIONS.md` | **the not-yet-settled register** | Every decision awaiting evidence, with its experiment and threshold |

### Mapping to the R0 requirements

| # | Requirement | Where |
|---|---|---|
| 1 | Final target architecture | `01_ARCHITECTURE.md` §1–§2 |
| 2 | Final MVRS scope | `02_SCOPE.md` §1 |
| 3 | Agent boundaries + criteria for what qualifies as an agent | `01_ARCHITECTURE.md` §3–§4 |
| 4 | Agent communication / delegation contract | `01_ARCHITECTURE.md` §5–§7 |
| 5 | LLM provider requirements + probe specification | `03_LLM_LAYER.md` (whole) |
| 6 | Dataset / schema design decision | `04_DATA_MODEL.md` (whole) |
| 7 | Minimum timetable scope | `05_TIMETABLE_SCOPE.md` (whole) |
| 8 | Benchmark categories + outcome-checking methodology | `06_BENCHMARK.md` (whole) |
| 9 | Research contribution and claims | `07_CONTRIBUTION.md` (whole) |
| 10 | Deployment architecture | `08_DEPLOYMENT.md` (whole) |
| 11 | MUST / SHOULD / NICE / DO NOT BUILD boundaries | `02_SCOPE.md` §2 |
| 12 | Updated roadmap and critical path | `09_ROADMAP.md` (whole) |
| — | Decisions requiring empirical evidence | `OPEN_DECISIONS.md` (whole) |

---

## The R0 discipline

One rule governs this whole directory:

> **A decision justified by reasoning is not the same as a decision justified by
> measurement.** Where v4 has only reasoning, the decision is recorded in
> `OPEN_DECISIONS.md` as open, with the experiment that closes it and a threshold
> pre-registered *before* that experiment runs.

Twelve decisions are currently open. Four of them are ones a drifting project would quietly
settle by habit: the LLM provider, a second search algorithm for the timetable, promoting a
fourth agent, and a frontend rewrite. None may be adopted without recording the measurement
that justified it.

---

## Sign-off

| Field | Value |
|---|---|
| Phase | R0 — decision freeze |
| Written | 2026-08-31 |
| Supersedes | the aim (not the methods) of `docs/RESEARCH_PLAN_V3.md` |
| Verdict carried in | GO WITH REDUCTIONS |
| Baseline at freeze | 52 tests passing; `freeze_manifest.py` verifies 8/8 frozen files unchanged |
| Code changed in R0 | none |
| Next phase | R0.5 (provider probe) and R1 (foundations) — both blocked on approval of this record |

Changes to any document in this directory after sign-off require a dated entry in
`OPEN_DECISIONS.md` §4 (Decision log), in keeping with `evaluation/PROTOCOL.md` §12.
