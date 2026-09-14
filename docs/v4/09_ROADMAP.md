# 09 — Roadmap, Critical Path, and Phase Gates

Covers R0 requirement **12**.

v3's P0–P8 numbering is retired. v4 phases are **R0–R8**. The two schemes are not comparable
and must never be mixed in a status report.

---

## 1. Dependency graph

```
R0  decision freeze  (this directory)
 │
 ├──► R0.5  provider probe ─────────────┐
 │                                      │
 └──► R1  foundations ──────────────────┼──► R3  agent runtime ──► R4  writes + cascade
        │                               │         │                      │
        ├──► R2  timetable ─────────────┘         │                      │
        │                                          └──► R6  UI additions │
        └──► benchmark authoring (external) ─────────────────────────────┴──► R5  evaluation
                                                                                  │
                                                                          R7  deploy
                                                                                  │
                                                                          R8  write-up
```

**Critical path:** `R0 → R1 → R3 → R4 → R5 → R7 → R8`

**Parallelisable:** R0.5 (with R1) · R2 (after R1) · R6 (with R3/R4) · benchmark authoring
(from R1, externally)

---

## 2. Phases

### R0 — Decision freeze *(this directory)*

**Purpose.** Convert the agreed rework into written, versioned decisions so R1 starts with no
ambiguity, and record every decision that still needs evidence rather than settling it by
habit.

**Output.** `docs/v4/` (11 documents) · a `CLAUDE.md` pointer and status correction.

**Gate.** All twelve R0 requirements mapped to a named section; `OPEN_DECISIONS.md` carries an
entry for every reasoning-only decision; `git status` shows changes only under `docs/v4/` and
`CLAUDE.md`; 52 tests and `freeze_manifest.py` still pass, proving nothing executable moved.

---

### R0.5 — Provider viability probe

**Purpose.** Choose an LLM provider empirically against thresholds pre-registered before any
run.

**Output.** `evaluation/provider_probe.py` · `results/v4_gates/r05_provider.{json,md}` ·
a `PROTOCOL.md` §12 entry · `OPEN_DECISIONS.md` §D1 closed.

**Depends on.** R0 only — it needs the existing tool schemas, which already exist.

**Gate.** ≥ 1 provider meets **every** mandatory threshold in `03_LLM_LAYER.md` §4.3; the
selection rule is applied as written; the decision is dated and recorded. If no provider is
eligible, the thresholds are **not** relaxed — the architecture is reconsidered, and that is
itself a finding.

---

### R1 — Foundations *(critical path)*

**Purpose.** Everything downstream depends on the entity model existing and being right.

**Output.** `institution.yaml` · `data/generator/` · new schema (rooms, availability,
conversations, traces, guard decisions, one request type) · Alembic · fixtures · v3 results
archived to `results/v3_archive/` with `SUPERSEDED.md` · **benchmark author kit prepared and
authors recruited**.

**Gate.**
1. `pytest tests -q` green against fixtures.
2. Generator byte-reproducible from a fixed seed (generate twice, compare hashes).
3. The **existing, unmodified** solver still yields placement rate 1.000 on the new schema.
4. `grep -ri "mite\|mangalore\|4MT" backend/ frontend/ data/` returns zero hits
   **outside `data/generator/config.py`**, which is the loader that *enforces* the ban
   and therefore has to name the banned tokens. Refined at R1 on 2026-09-01: the gate as
   originally written was unsatisfiable, since the enforcement point is inside the searched
   tree. The exemption is one named file and is itself covered by a test
   (`tests/test_generator.py::test_config_rejects_reintroducing_the_v3_identity`).
5. Generated instances are feasible by construction (the generator asserts it).
6. Author kit sent.

---

### R2 — Timetable minimum *(parallel with R3)*

**Purpose.** Make the timetable a credible ERP capability without letting it become a second
project.

**Output.** Room as a decision variable · generalised unavailability · per-slot failure
reasons · counterfactual scoring endpoint · seed-failure instrumentation · NDJSON solver
stream.

**Gate.** The full regression gate in `05_TIMETABLE_SCOPE.md` §7 — including *no worse than
current P1 on the frozen objective over 10 seeds*, zero room conflicts, no teacher in an
unavailable slot, the ITC-2007 cross-check still passing, and the seed-failure rate recorded
against the §4 MRV trigger whether or not it fires.

---

### R3 — Agent runtime *(critical path — the contribution)*

**Purpose.** Build the thing the project is actually about.

**Output.** Provider abstraction · persisted conversation memory · plan → delegate → observe
loop with bounded re-plan · typed `Task`/`Result`/`NeedInfo`/`Refusal` contract · guard layer ·
write confirmation · provenance gate rewired · trace persistence.

**Gate.**
1. A trace shows a real plan containing ≥ 2 delegations.
2. An underspecified query produces a clarification and **executes no tool** on a guessed
   interpretation.
3. A cross-role read is blocked at the guard **and the attempt is logged**.
4. Removing the system prompt entirely changes **no** guard verdict (a test, not an
   assertion).
5. p95 turn latency inside budget; re-plan depth measured against `OPEN_DECISIONS.md` §D9.

---

### R4 — Writes and the cascade *(critical path)*

**Purpose.** Make multi-step execution real rather than describable.

**Output.** ≥ 3 guarded write tools · the confirmation turn · the end-to-end attendance
cascade under LLM planning · (SHOULD) Comms promoted · (SHOULD) bus outbox + replay.

**Gate.**
1. The MVRS demonstration cascade (`02_SCOPE.md` §1.2) completes end to end.
2. No write executes in the same turn it was proposed.
3. `workflow_events` reconstructs the full chain across ≥ 3 agents.
4. (If built) a deliberately failed subscriber replays successfully from the outbox.

---

### R5 — Benchmark and evaluation *(critical path)*

**Purpose.** Produce the numbers the report rests on.

**Output.** Ingested task suite · deterministic outcome checker · adversarial suite · runs
with seed variance · the four claims' evidence · figures.

**Gate.**
1. All six categories populated; dev/test split assigned before any run; **test touched once**.
2. Every claim in `07_CONTRIBUTION.md` has its evidence or is explicitly dropped with a stated
   limitation.
3. **Zero unauthorised executions.** A single one is a critical defect that blocks the phase.
4. **No metric appears as a 100% headline.**
5. Every number regenerable by a command in `evaluation/`.

---

### R6 — UI additions *(parallel with R3/R4)*

**Purpose.** Make the system demonstrable.

**Output.** Three panels on the existing SPA: chat with clarification and confirmation · agent
trace timeline · live solver stream. Plus the degradation banner.

**Gate.** Every role's dashboard renders on live data; the solver stream animates; the trace
panel shows plan, delegations, guard verdicts and the provenance result; the banner names the
active tier.

---

### R7 — Deployment

**Purpose.** A URL someone else can open.

**Output.** Postgres migration · secrets · rate limiting · CORS · container · deployed
instance · smoke test.

**Gate.** Deployed URL reachable; smoke test green against Postgres; **disabling the provider
degrades visibly through the ladder**; the full demo rehearsed once on the local tier.

---

### R8 — Write-up

**Purpose.** Documents that match the evidence.

**Output.** Figures · `docs/ARCHITECTURE.md` and `RESULTS.md` rewritten (v3's pending P8) ·
`README.md` synced · viva defences · limitations.

**Gate.** No document cites a number `evaluation/` cannot regenerate; every v3-era number is
labelled with its instrument; the limitations section names every dropped SHOULD-tier item.

---

## 3. Where the effort goes

| Phase | Share | Note |
|---|---|---|
| R1 | ~20% | Everything is downstream |
| R3 | ~30% | The contribution; highest value per unit effort |
| R2 | ~15% | Four small additions to working code |
| R4 | ~10% | Mostly wiring existing pieces through the guard |
| R5 | ~15% | Authoring is external; the checker is ours |
| R6 | ~5% | Three panels on an existing SPA |
| R7 | ~5% | |

R0 and R0.5 are small and precede this accounting.

---

## 4. Postponement order

If time runs short, cut **in this order**. Cutting from the top of this list first preserves
the most research value per unit of effort saved.

| # | Item | Consequence of cutting |
|---|---|---|
| 1 | Next.js frontend rewrite | None — already NICE-tier |
| 2 | CP-SAT oracle · ITC-2007 E4b · room capacity · break slots | None to the claims |
| 3 | Streaming token output | Perceived quality only |
| 4 | Timetable diagnosis | Counterfactual still carries claim 4 |
| 5 | Lab blocks · teacher load caps | Timetable less realistic; claim 4 unaffected |
| 6 | Bus outbox + replay | v3's at-most-once weakness stays a stated limitation |
| 7 | Leave-request / general Requests module | Attendance cascade still satisfies R4's gate |
| 8 | Min-conflicts repair | Only matters if the seed actually fails — which §4 of `05_TIMETABLE_SCOPE.md` measures |
| 9 | Comms promoted to an agent | Drops to **3 agents**; MVRS still holds |
| 10 | **Second provider run** | **Claim 2 is dropped** and the limitation stated. Cut this last — it is the highest-value postponed item |

**Never cut:** anything in the MUST tier. If the MUST tier does not fit the available time,
the correct response is to say so early, not to half-build it.

---

## 5. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Scope on a fixed deadline** | High | The MUST column is the contract. The old SPA stays working throughout, so a demoable system always exists |
| **Benchmark authors block R5 again** | High | Recruit at R1. Bar lowered from "external co-authors" to "blind to the implementation" — department peers qualify. Fallback: team-authored with the limitation stated prominently |
| **Timetable eats the project** | High | `05_TIMETABLE_SCOPE.md` caps it: two new hard constraints; no second search algorithm unless a pre-registered 5% failure threshold actually fires |
| **No eligible provider at R0.5** | Medium | Thresholds are **not** relaxed. Reconsider the architecture; report it as a finding about small-model agentic capability |
| **Provider change invalidates v3 numbers** | Medium | Already accepted at R0. Archive, never difference |
| **Guide objects to cloud dependence** | Medium | Claims stated under the local configuration; the gap is claim 2 |
| **No internet at the viva** | Medium | Rehearse on Tier 2; cached demo path; recorded fallback |
| **Rooms regress timetable quality** | Medium | The frozen metric and preserved baseline make regression *detectable*; R2's gate blocks on it |
| **Agent loop slow or looping** | Medium | Bounded re-plan (N=1), per-turn step cap, latency budget in the trace |
| **Losing v3's rigor while moving fast** | Medium | `PROTOCOL.md`, the freeze manifest, seed variance and the no-100% rule are kept verbatim. Change *what* is measured, never *how honestly* |
| **Postgres free tier insufficient** | Low | SQLite on a persistent volume; models are agnostic |

---

## 6. Standing rules across all phases

1. **Test is touched once.** Every threshold, prompt and weight is selected on dev.
2. **Every stochastic component is multi-seed**, mean ± std, never best-of-N.
3. **No number that `evaluation/` cannot regenerate.**
4. **No 100% headline, anywhere.**
5. **Report in the direction the data points.** A losing configuration is reported, not
   deleted.
6. **Cite which instrument produced each number.** v3 and v4 numbers are never differenced.
7. **A null result is a result.** No hypothesis is rescued by changing the metric after seeing
   data.
8. **Changing a frozen artefact requires a dated `PROTOCOL.md` §12 entry.**
9. **Closing an open decision requires recording the measurement that closed it** —
   `OPEN_DECISIONS.md` §4.
