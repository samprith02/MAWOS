# MAWOS — working notes for Claude

B.E. final-year research prototype (Dept. of AI&ML, MITE, Group 12).
Framing: **event-driven multi-agent workflow orchestration engine for
universities**. The contribution is the orchestration engine, not the agent
count. **4 core agents** as of P2 (2026-08-19) — Orchestrator, Attendance,
Eligibility, Scheduling; `backend/app/agents.CORE_AGENTS` is the queryable
source of truth. Academic/Admission/Finance/Placement/Notification are
still real, still in the registry, still called by tools.py and the REST
routes — just not counted as agents (§7 of `docs/RESEARCH_PLAN_V3.md`).

---

## ⚠ READ THIS BEFORE THE v4 SECTION — v5 is the current work (2026-09-14)

**`docs/superpowers/specs/2026-09-13-mawos-v5-design.md` is the current spec.
`docs/superpowers/plans/2026-09-14-mawos-v5-agentic-layer.md` is the plan being executed.**

v5 is **not** a third re-aiming. The research question, `docs/v4/07_CONTRIBUTION.md`,
`evaluation/PROTOCOL.md` and every rule below are unchanged. Four things changed, each
with a stated cause:

| Change | Cause |
|---|---|
| Orchestration moves to **LangGraph** (MIT) | Hand-rolled orchestration is neither a contribution nor a hiring signal. The contribution is the guard/provenance layer *above* it |
| Provider is **hosted**, never local | R0.5 measured that no local model passes. Local also cannot be deployed: no free host provides a GPU |
| New external surface: an **MCP server** | Puts an untrusted external LLM behind the same deterministic guard — a second experiment |
| Dependencies must be **permissively licensed** | The project is intended for commercial use; ERPNext/Frappe is GPLv3 and Indian colleges procure on-premise, which is distribution |

**Ollama is no longer used.** `%LOCALAPPDATA%\Ollama\ollama.exe serve` is historical. The
runtime provider is configured by `MAWOS_LLM_BASE_URL` / `MAWOS_LLM_MODEL` /
`MAWOS_LLM_KEY_ENV` (`backend/app/config.py`), reading its credential from a **gitignored
`.env`**. No key may ever enter git.

### New modules (v5)

| Module | Responsibility |
|---|---|
| `backend/app/guard.py` | **The deterministic authorisation layer — the project's primary contribution.** Single entry point `authorise(db, user, capability, args, turn_id=None)`. Logs allowed AND denied in the same shape, and records `was_exposed` so the attempt rate stays computable |
| `backend/app/contracts.py` | Typed delegation: `AgentTask → AgentResult \| NeedInfo \| Refusal`. Three outcomes, not two — `NeedInfo` stops the turn and asks |

### ⚠ BEHAVIOUR CHANGE — student isolation is now a DENIAL, not a coercion

v3: a student asking for another student's record silently received **their own** data
(`_resolve_usn` coerced the USN).
v5: the guard **denies** with `OUT_OF_SCOPE`.

This was deliberate. Silent substitution is a grounding hazard in an LLM-driven system — the
model would faithfully report the wrong student's name against the right student's numbers,
which is truthfully wrong, the worst kind for claim 3. A denial also writes a
`GuardDecision`, so the attempt is countable; a coercion never was.
`tests/test_workflows.py::test_tool_permissions_lock_students_to_self` encodes the new contract.

### Every capability call now passes the guard

`backend/app/agents/tools.py::execute()` calls `guard.authorise` before reaching any tool
function, and `execute()` is the **only** call site of `t["fn"]` anywhere in `backend/app`.
Three write tools are registered with `writes=True` — `mark_attendance`,
`apply_timetable_change`, `issue_eligibility_override` — and `write_tool_names()` reports them.

**Circular-import hazard:** `guard.py` imports `TOOLS` from `.agents.tools`, and `execute()`
imports `authorise` from `..guard`. **Both are function-level on purpose.** Hoisting either to
module scope breaks the import.

**`SessionLocal` is `autoflush=False`.** Calling `evaluate_hall_ticket` twice in one session
double-inserts a `HallTicket` and raises a UNIQUE constraint error. `EligibilityAgent.override`
calls `db.flush()` explicitly for this reason — do not remove those flushes.

### Decision state (v5)

- **D13 — closed** 2026-09-01 (M7 threshold 3.0 → 6.0 s).
- **D14 — closed 2026-09-14.** M7 is re-registered as the p50, over category `A_single`
  items, of **summed provider latency** (`sum(round.latency_ms)`), not wall-clock. Wall time
  included this harness's own rate-pacing sleep, which hosted providers need and local ones do
  not, so wall-clock M7 was never provider-agnostic. **Only the measure changed — the
  population is unchanged.** Neither completed run is re-scored. Verified executably by
  `tests/test_probe_scoring.py`. `m7_wall_p50_s` is retained as a diagnostic and reproduces the
  historically published values to ±1e-9.
- **D1 — STILL OPEN.** The clean hosted run of 2026-09-14 measured `groq:gpt-oss-120b`
  INELIGIBLE: it fails **M2 correct-tool at 75.0% against a >=85% threshold**, deterministically
  across all 3 seeds, while M1/M3/M4/M5/M6/M7/M9 all pass. Thresholds were **not** relaxed.
  The runtime nevertheless defaults to that model — recorded in `OPEN_DECISIONS.md` as
  *"a project decision made explicitly and recorded, not something the gate supports."*
  The guard is the mitigation: it authorises every action regardless of which tool the model
  picks, so a wrong-tool selection cannot produce an unauthorised effect.
  Note the *shape* of the result — the model is strong on the hard measures (clarifying before
  acting, refusing, grounding, multi-step) and fails on the simple one. That **inverts** v3's P6
  finding that tool-selection could not discriminate between models.
  An **earlier** run the same day was **discarded as harness-contaminated** (M9 = 83.1%: 60
  rate-limit + 14 malformed-request failures, none attributable to the model). **Do not cite it.**

**A number produced by a broken instrument is worse than no number.** Before reading any
gate result, check M9 first. Two separate harness defects have now been caught this way —
D14's pacing contamination and the 429/400 storm — and both would otherwise have been
published as findings about a model.

---

## ⚠ READ FIRST — the project is being re-aimed (v4, R0 signed off 2026-08-31)

**`docs/v4/` is the current blueprint. Start there, not with the v3 status table below.**

v3 built the university system as an *experimental platform* for a tool-space-restriction
study (`RESEARCH_PLAN_V3.md`, top). v4 re-aims it at **bounded LLM autonomy over a real
institutional system** — the model plans and delegates across agents, a deterministic guard
authorises every action, writes require confirmation, and the whole chain is traced and
measured. Verdict on the rework: **GO WITH REDUCTIONS**.

| Read this | For |
|---|---|
| `docs/v4/README.md` | index + why the re-aim |
| `docs/v4/02_SCOPE.md` | **the MVRS scope contract** — MUST / SHOULD / NICE / DO-NOT-BUILD |
| `docs/v4/OPEN_DECISIONS.md` | **12 decisions deliberately NOT locked**, each with its experiment and a pre-registered threshold |
| `docs/v4/09_ROADMAP.md` | R0–R8, critical path, phase gates |

**Phase state:** R0 (decision freeze) **done** — documents only, zero code changed.
**R1 (foundations) done 2026-09-01.** New schema (rooms, faculty availability,
requests, conversations, traces, guard decisions); `data/institution.yaml` +
`data/generator/` replacing the v2 inline seeder; Alembic; test fixtures;
v3 results archived. Admissions, `fl/` and **both ML models** deleted — the
CART/RF were trained on labels our own rules generated. 63 tests pass.
**R0.5 (provider viability gate) done 2026-08-31 — and NOTHING PASSED.** All three
local models fail the pre-registered thresholds (1.5B 7/8, 3B 5/8, 7B 4/8); both
hosted candidates were untestable (no API key in the environment) and are recorded
as untested, not estimated. Per the gate's own clause the thresholds were **not**
relaxed, so **no provider is adopted and D1 stays OPEN**. Evidence:
`evaluation/results/v4_gates/r05_provider.{json,md}` + `r05_findings.md`.
**R3 is blocked on D1.** R2 (timetable) is unblocked and is the next phase.
M7's latency threshold was re-registered 2026-09-01 (D13 closed,
`03_LLM_LAYER.md` §2.3.1) — verified to change no 2026-08-31 verdict.

**Four things a session must not quietly decide** (see `OPEN_DECISIONS.md`): the LLM
provider (D1 — closed by the R0.5 probe), a second timetable search algorithm (D2 — only if
seed failure > 5% over 10 seeds), a fourth agent (D3), and a frontend rewrite (D4). Each is
adopted only by recording the measurement that justified it.

**Everything in "Rules that matter here" and "Gotchas" below still applies verbatim.** The
v3 phase table is **historical record** — accurate for what was built up to 2026-08-25, and
no longer the plan.

---

## Status — v3 phases (HISTORICAL, frozen 2026-08-25; superseded by `docs/v4/09_ROADMAP.md`)

| Phase | What | State |
|---|---|---|
| P0 | Freeze v2 baseline, RQ1 instrumentation, protocol | done |
| P0.5 | Router viability gate | done |
| P1 | Objective-driven scheduler (greedy seed + SA) | done |
| P1b | ITC-2007 external benchmark harness | harness validated (1,900 cases vs official validator); **blocked on instance files**, see `evaluation/itc2007/INSTANCES.md` |
| P2 | Agent reduction 10→4, tool surface held 13→12 | **done** — code, frozen instrument, and all downstream figures/tests on the 99-task set (commit `9ed24c8`, 2026-08-19) |
| P3 | PCN-style provenance gate | **dev-only engineering pass done** (2026-08-25) — `backend/app/provenance.py`, gate on by default. 100% catch rate on synthetic corruption, 23.5% block rate on genuine dev answers (`evaluation/results/v3_gates/p3_provenance.md`). Not RQ2's confirmed result — one seed, synthetic ground truth, real annotated data still pending (tracks with P5) |
| P4 | Confidence-gated hybrid router, τ frozen on dev | **done, current** — GPU-resident recapture + `tune_router.py` re-run on the 99-task/12-tool instrument, 2026-08-21: 88.9%/83.5%/94.6%, τ=0 (see below) |
| P5 | Held-out set → dual annotation → single test run | **blocked on external authors — the largest schedule risk** |
| P6 | Model sweep, 1.5B/3B/7B × 3 seeds | **done** (2026-08-25) — all three recaptured against the 99-task/12-tool instrument; `analyze_sweep.py` reconfirms 3B as the §9.2 pick (McNemar vs 1.5B p=0.003); 7B out-of-competition, 81.7% GPU-resident |
| P7 | Figures F1–F9 | F1/F2/F3/F6/F7/F8 drawn from fresh data (2026-08-25); F4/F5/F9 blocked on P2-adjacent work/P3/P5 |
| P8 | Rewrite ARCHITECTURE.md / RESULTS.md to match the evidence | pending — README.md is current as of 2026-08-21; those two still carry v2-era numbers by design until P8 |

**P4 is done and current as of 2026-08-21.** GPU access came back (the
earlier block was a transient host-level driver/session fault, fixed by a
reboot — not a Claude Code sandbox restriction) and a clean, alone
99-task × 3-seed capture ran against `qwen2.5:3b-instruct`: 297 records,
99 unique task IDs matching `DEV_TASKS` exactly, 0 call failures,
`gpu_residency.fully_resident: true`, `mawos.db` hash unchanged
before/after. `tune_router.py` re-ran §9.3's rule against it and selected
τ≤0 again: lexicon 88.9%, LLM-alone 83.5% ± 0.5%, hybrid 94.6% (+5.7 pts,
95% CI [+0.3, +11.8], McNemar p=0.070). `backend/app/router_config.json`
was rewritten and `FROZEN.sha256` regenerated accordingly (PROTOCOL §12
changelog entry dated 2026-08-21). This **supersedes, does not correct**,
the pre-P2 108-task numbers (89.8%/76.9%/94.8%).

**P6 is done as of 2026-08-25.** The 3B was picked by the pre-P2 108-task
sweep; that pick is now reconfirmed against the current 99-task/12-tool
instrument. Recapturing 1.5B/7B had stalled earlier on a laptop NVIDIA
driver (`nvlddmkm`) dropout, but the driver came back clean this session
(RTX 4050 detected fine, driver 13.0, 6.0 GiB VRAM) and both models were
recaptured: `qwen2-5_1-5b-instruct.json` and `qwen2-5_7b-instruct.json`
in `evaluation/results/v3_llm/`, 297 records each, 99 unique task IDs,
0 call failures. `analyze_sweep.py` now runs clean and selects
**qwen2.5:3b-instruct again** (McNemar vs 1.5B, p=0.003) — the pick
behind P4's τ was not stale after all. 7B stayed only 81.7% GPU-resident
(same historical pattern as pre-P2) and is reported out-of-competition,
same as before. `evaluation/results/v3_gates/p6_sweep.json` is now the
current 99-task file; `evaluation/figures.py` draws F2/F6/F8 from it.

Getting there required real persistence: background captures kept being
killed by something outside this codebase — confirmed not the GPU driver
or Ollama (both checked healthy at every kill) — after 14 failed
attempts at varying points (instantly to 33 minutes in). The fix was
`evaluation/capture_llm_resume.py`, a checkpointed wrapper around
`capture_llm.py` that saves progress every 11 tasks and resumes from
wherever a kill left off; `dangerouslyDisableSandbox` on the shell calls
also seemed to help survival odds, though the correlation wasn't clean.
If P6 or a similar live-Ollama capture ever needs re-running and dies
repeatedly, reach for that resumable script rather than the plain one —
it's safe to just keep re-invoking the identical command.

P3's dev-only pass and P6 are both done as of 2026-08-25. P2, P4 and P6
are done; don't restart that work.

**Superseded 2026-08-31.** v3's remaining phases (P5 held-out set, P8 doc
rewrite) are **not** the next work — the project was re-aimed at R0. P5's
external-author blocker is carried into v4 with the bar corrected from
"external co-authors" to "authors blind to the implementation"
(`docs/v4/06_BENCHMARK.md` §6), and recruitment moves from late-phase to
R1. P8's doc rewrite becomes R8. The v3 routing, sweep and gate results
stay citable **for their own instrument** and are archived at R1 to
`evaluation/results/v3_archive/` — no v4 number may ever be differenced
against one of them.

## Run it

```bash
python run.py                              # -> http://localhost:8000
```

**Ollama is no longer part of this project.** v5 uses a hosted provider over an
OpenAI-compatible API; the credential lives in a gitignored `.env`. The old
`%LOCALAPPDATA%\Ollama\ollama.exe serve` step is historical and is only
relevant to re-running archived v3 captures.

**Deployment:** `docker build -t mawos:dev .` then run with `PORT` set; `/health`
returns `{"status","tier"}`. `render.yaml` declares the free web service + Postgres.
`MAWOS_ENV=production` refuses to boot on the dev JWT secret. Note `config.py`
rewrites bare `postgresql://` URLs to `postgresql+psycopg://` — SQLAlchemy would
otherwise reach for psycopg2, which is not installed, and Render's connection
string is the bare form.

**R1 changed how data is made.** The institution is defined entirely by
`data/institution.yaml` and built by `data/generator/` — deterministic,
scale-parameterised, and feasibility-asserting. `backend/app/seed.py` is now a
thin adapter, so `run.py` is unchanged. Useful commands:

```bash
python -m data.generator.build --digest --date 2026-09-01   # reproducibility check
alembic upgrade head                                        # apply migrations
```

The institution name in `institution.yaml` is a **placeholder** pending
`OPEN_DECISIONS.md` D12 — changing it is one edit plus a reseed. Nothing in
`backend/`, `frontend/` or `data/` hardcodes an institution identity any more;
`data/generator/config.py` refuses to load a config that reintroduces the v3 one.

`llm.py` caches the Ollama availability check at startup, so the header badge
only flips to `AI · hybrid router` if Ollama was already serving when MAWOS
booted. Without it the system still works — the lexicon answers everything,
including the low-margin queries it would normally escalate, and the badge
says `AI · lexicon only`.

**Routing is v3 now.** `backend/app/router.py` gates on the lexicon's own
confidence (margin ≤ τ, τ = 0 frozen in `router_config.json`), not on whether
Ollama is reachable. ~90% of queries never touch the LLM by design, so the
lexicon is the *primary* tier — do not call it a "fallback" in code, UI or
docs. Config is hashed; hand-editing τ makes it a different experiment
(PROTOCOL §9.3).

Logins: `4MT23AI049`/`student123`, `aiml.f02`/`faculty123`, `hod.aiml`/
`faculty123`, `principal`/`principal123`, `admin`/`admin123`.

**Timetable data can go stale.** `main.py` only auto-generates
`timetable_slots` once, the first time the table is empty — it never
regenerates after that, so if teaching assignments change (or the DB was
seeded a while ago) the live grid can drift from what the current P1
solver would actually produce. If a timetable looks wrong (gaps, a
lopsided day), that's very likely stale data, not a solver bug — confirm
by hitting "Regenerate department timetable" (HOD dashboard) or calling
`timetable_agent.generate(db)` before assuming the algorithm regressed.

**Live solver simulation (2026-08-25, UI-only, not a research phase).**
HOD dashboard → Department → "Watch solver (live simulation)" replays the
P1 scheduler's own event trace — seed placements, then the real
cost/temperature curve from annealing — so a section's timetable visibly
builds itself. Backend: `backend/app/scheduler_live.py`, a strictly
additive wrapper (zero diff to `scheduler.py`; duplicates only the
~45-line seed loop for eventing, calls the real unmodified `anneal()` via
its existing `trace_every` hook). Route: `POST
/hod/generate-timetable-live`. This exists because a teammate dropped a
separate Next.js/Postgres reference app
(`teacher-erp-with-timetable-simulation/`, untouched, not integrated) with
a nicer live-trace UI for its own timetable solver; MAWOS kept its own
frozen, ITC-2007-benchmarked SA scheduler and borrowed only the
visualization idea. Not part of P0–P8.

## Rules that matter here

- **Never headline a 100% figure.** Anywhere. This project was rebuilt
  specifically because v1 looked too clean to be real.
- **Report results in the direction the data points.** The LLM tier *loses*
  the routing comparison. Under v3's current (99-task, GPU-resident,
  2026-08-21) conditions that is **83.5% vs 88.9%, −5.4 points** (3 seeds,
  `results/v3_llm/`). The pre-P2 108-task v3 run (76.9% vs 89.8%, −12.9)
  and v2's single-run −19.4 are both superseded, **not corrected** — none
  of the three runs may be differenced against another; they failed an
  equivalence check or used a retired instrument (`v3_llm/CONDITIONS.md`,
  PROTOCOL §10.1). Do not re-frame the loss as a win, and do not delete
  the losing configuration from the report.
- **Cite v2 and v3 numbers separately, and cite which v3 instrument.**
  README.md is current to the 99-task/12-tool instrument as of 2026-08-21;
  `docs/ARCHITECTURE.md` and `evaluation/results/v2_historical/RESULTS.md`
  still carry v2-era numbers on purpose — P8 rewrites those. Until then,
  say which run a number came from.
- **Never present a number you cannot regenerate** from `evaluation/`.
- Label attendance accuracy as *deterministic verification*, never "AI
  accuracy"; label the manual-workflow comparison as a *modeled estimate*.
- Design decisions in the docs are deliberate viva defences. Don't casually
  change them — if something looks wrong, say so rather than silently
  "fixing" it.

## Gotchas that have cost real time

- **Stop the server before deleting `mawos.db`.** A running server holds the
  file, so `Remove-Item -ErrorAction SilentlyContinue` fails *silently* and
  leaves a contaminated DB. Reseed helper: `scratchpad/reseed.py`.
- **Don't run `evaluate.py` while the server is up** — both write the same
  SQLite file.
- **Shipped DB state is deliberate**: 400 submitted applications, 0 verified,
  so the admissions pipeline can be demoed live. Don't consume it by running
  verify/merit/allot against the shipped DB.
- **Cascade latency is not comparable across runs** with and without Ollama
  resident: ~127 ms idle vs ~466 ms with a 2 GB model loaded. The cascade path
  never calls the LLM; it is pure resource contention. State the condition.
- **Installing Ollama on this laptop**: `winget install Ollama.Ollama` hangs
  after downloading (blocks on a UAC prompt that can't appear in a
  non-interactive shell), and its temp file is preallocated to full size so it
  looks complete while still downloading — a mid-flight copy matches the
  remote byte-for-byte but fails `Get-AuthenticodeSignature` with
  `HashMismatch`. Use the portable zip instead; verify the signature.

## Evaluation

```bash
python -m pytest tests -q                 # 100 tests (v5, 2026-09-14)
python evaluation/gate_p05.py             # P0.5 router viability gate
python evaluation/capture_llm.py          # frozen-protocol LLM capture (live Ollama)
python evaluation/capture_llm_resume.py --models 1.5b,7b   # same, but checkpointed/resumable if the process keeps getting killed
python evaluation/analyze_sweep.py        # P6 model selection, PROTOCOL 9.2
python evaluation/tune_router.py          # P4 threshold selection, PROTOCOL 9.3
python evaluation/gate_p3.py              # P3 provenance gate, dev-only engineering pass (needs live Ollama)
python evaluation/gate_p3_figure.py       # P3 diagnostic chart (reads p3_provenance.json, no Ollama needed)
python evaluation/scheduler_eval.py       # E4: P1 solver vs frozen v2 greedy
python evaluation/freeze_manifest.py      # verify the frozen instrument (PROTOCOL 1.5)
python evaluation/evaluate.py             # v2 harness: both routing tiers
python evaluation/evaluate.py --no-llm    # skip the 108 live LLM calls
python evaluation/ablation.py             # is the architecture load-bearing?
python evaluation/failure_injection.py    # fault isolation + replay
python evaluation/scalability.py          # constant workload vs institution size
python evaluation/figures.py              # P7: every figure, one command
python evaluation/itc2007/build.py        # fetch+build the official ITC validator
python evaluation/itc2007/crosscheck.py   # P1b: our CB-CTT cost model vs that validator
python evaluation/itc2007/run_e4b.py      # E4b (needs instances -- see INSTANCES.md)
```

`evaluate.py::_verdict` derives §1.3's conclusion from the *sign* of the
measured deltas, so the report cannot claim the LLM helps when it doesn't.
Keep it that way.

## Known weak points (say these before an examiner does)

- The 99-query routing benchmark and the keyword lexicon it scores were
  written by the same project, so the lexicon is tuned to these phrasings.
  It is evidence about this classifier on this benchmark, not a general
  claim. A held-out set written outside the team is the fix.
- The model sweep (P6: 1.5B/3B/7B × 3 seeds) is now complete against the
  99-task/12-tool instrument (2026-08-25) and reconfirms 3B as the §9.2
  pick — but it is still **one family, one temperature, three seeds**.
  The 7B **could not stay GPU-resident** on this 6 GB laptop (81.7%,
  same both pre- and post-P2) and is reported out-of-competition; it
  must never share a Pareto frontier with an eligible model.
- **τ = 0 was selected on dev, and dev is contaminated by construction** —
  the lexicon was tuned on those 99 queries. The +5.7-point hybrid gain's
  95% CI now excludes zero ([+0.3, +11.8]), but McNemar p = 0.070 is still
  not significant at 0.05. It is not a confirmed result yet; the held-out
  set (P5) decides.
- Data is synthetic (UCI-calibrated, copula, 3% label noise), the bus is
  in-process and at-most-once, and replay recovery is manual.
