# MAWOS — an event-driven multi-agent workflow orchestration engine for universities

B.E. Final-Year Research Prototype · Dept. of AI&ML, MITE · Group 12

MAWOS models a **real institution** — 5 departments × 4 years × 2 sections
(1,200 students, 75 faculty, 100 subjects, 180,000 attendance records, an
admissions intake of 400 applicants) — and runs it through a **multi-agent
system**: currently ten agents, each owning an institutional domain,
coordinating over an instrumented event bus, behind a **confidence-gated
hybrid router** that calls role-scoped tools rather than answering from a
script.

The research contribution is the **orchestration engine**, not the agent
count: `intent → tool selection → permission-checked execution → grounded
answer` on the query path, and `attendance upload → attendance → {exam,
scholarship, placement, notification}` on the propagation path — where
**every hop is measured** under a workflow ID.

This is a live research project, not a finished paper. The **v3-research**
branch reframes v2's "LLM-first assistant" into a routing experiment with
pre-registered thresholds, held-out evaluation and an external benchmark.
§ [Research status](#research-status-v3) below says exactly what is done,
what is frozen, and what is still blocked — read it before citing any
number from this repository.

---

## Quickstart

```bash
pip install -r requirements.txt
python ml/calibrate.py       # estimate distributions from the real UCI dataset
python ml/train.py           # generate calibrated data + train CART & RF
python run.py                # -> http://localhost:8000
```

First launch seeds the institution and solves the timetable. Roughly 60 s of
one-time setup.

### Turning the LLM tier on

The router works with **no LLM at all** — the keyword lexicon is the
*primary* tier and answers ~90% of queries by itself. Ollama only adds the
escalation tier for the low-confidence remainder (see
[Routing](#routing-v3-a-confidence-gated-hybrid) below).

```bash
%LOCALAPPDATA%\Ollama\ollama.exe serve          # FIRST — leave running
%LOCALAPPDATA%\Ollama\ollama.exe pull qwen2.5:3b-instruct
python run.py
```

`llm.py` caches the Ollama availability check at startup, so the header
badge only flips to `AI · hybrid router` if Ollama was already serving when
MAWOS booted; otherwise it says `AI · lexicon only` and the system still
answers everything, including the queries it would normally escalate.

If `winget install Ollama.Ollama` downloads and then hangs (it blocks on a
UAC prompt that never appears in a non-interactive shell — and the partial
download can fail `Get-AuthenticodeSignature` with `HashMismatch` even
though it looks complete), skip the installer and use the portable build
instead — no admin rights required: download `ollama-windows-amd64.zip`
from the GitHub release, `unzip` it to `%LOCALAPPDATA%\Ollama`, verify the
signature, then run the two commands above.

### Demo accounts (five different portals, not five skins)

| Role | Login | What that role can actually do |
|---|---|---|
| Student | `4MT23AI049` / `student123` | attendance & CIE marks, fees + pay, hall-ticket status, scholarship, placements, personal timetable + CSV download, notices, assistant |
| Faculty | `aiml.f02` / `faculty123` | own teaching assignments, **mark class attendance** (only for assigned subject-sections — enforced server-side), enter internal marks, own teaching timetable |
| HOD | `hod.aiml` / `faculty123` | department analytics, section-wise timetables, **regenerate the department timetable**, fee-defaulter list |
| Principal | `principal` / `principal123` | institution-wide analytics: department comparison, fee collection, placements, admissions funnel |
| Admin | `admin` / `admin123` | **full admissions pipeline** (verify → merit rank → allot seats vs intake → enrol), demo cascade trigger |

Any USN from `4MT23AI001`–`4MT26CV6xx` works as a student login; faculty are
`{dept}.f02`…`{dept}.f15`; HODs are `hod.{dept}` for aiml/cse/ece/me/cv.

---

## Routing (v3): a confidence-gated hybrid

**The numbers below are pre-P2 and stale as of 2026-08-19.** P2 (agent
reduction, `docs/RESEARCH_PLAN_V3.md` §7) retired `get_admissions_funnel`
and, with it, 9 dev tasks — the benchmark this section describes moved
from 108 tasks/13 tools to 99 tasks/12 tools. A fresh GPU-resident
recapture is required before these percentages are current again; see
[Research status](#research-status-v3) for exactly what's blocked and why.
The routing *mechanism* described below is accurate and unaffected.

`backend/app/router.py` escalates to the LLM only when the lexicon's own
confidence is low — margin (top-1 score minus top-2 score) ≤ τ — not
whenever Ollama happens to be reachable. τ = 0 is frozen in
`backend/app/router_config.json` (sha256-hashed; hand-editing it makes it a
different experiment, see `PROTOCOL.md` §9.3) and was selected by a
pre-registered rule on the 108-query dev set **before** any held-out data
existed.

The lexicon is the **primary** tier — it handles the other ~90% of queries
unassisted. It is never called a "fallback" in this codebase.

```mermaid
flowchart TD
    Q["Query text"] --> LX["Lexicon scores every intent by keyword match"]
    LX --> MG["margin = top1 score − top2 score"]
    MG --> CMP{"margin ≤ τ ?\nτ = 0, frozen"}
    CMP -- "no — confident" --> LXA["Lexicon answers directly"]
    CMP -- "yes — low confidence" --> LLM["Escalate: LLM tool-calling loop\nover role-filtered schemas"]
    LLM --> LLMA["Answer composed from tool result"]
    LXA --> OUT1["~0.09 ms median"]
    LLMA --> OUT2["~3.4 s median"]
```

This is the actual decision in `router.py` — a structural diagram, not a
result, so it holds regardless of which experiment is currently running.

**The LLM tier loses the routing comparison.** On the same 108 queries,
3 seeds, `qwen2.5:3b-instruct` alone scores **76.9% ± 2.0%** against the
lexicon's **89.8%** — a **12.9-point loss** (`evaluation/results/v3_llm/`).
Escalating only the lexicon's own low-confidence cases recovers some of
that: the hybrid scores **94.8%**, a **+4.9-point** gain over the lexicon
alone — but that gain's 95% CI is **[0.0, 10.2] points** (lower bound
touches zero) and McNemar's exact test gives **p = 0.070**. It is not a
significant result. It was also measured on the same 108 queries the
lexicon was tuned on, so the dev set cannot be trusted to confirm it either
way — **the held-out set (P5) decides**, and P5 has not run yet
(`evaluation/results/v3_gates/p4_router.json`).

| | Lexicon (primary) | LLM tier alone | Hybrid, τ = 0 |
|---|---|---|---|
| Accuracy (dev, 108 queries) | 89.8% | 76.9% ± 2.0% | 94.8% |
| Median latency | 0.09 ms | 3,414 ms | 348 ms (expected) |
| vs lexicon | — | **−12.9 pts** | +4.9 pts, not yet significant |

This supersedes v2's finding of a −19.4-point LLM loss (70.4% vs 89.8%,
single uncontrolled run) — but v2 and v3 **fail an inference-condition
equivalence check** (`evaluation/results/v3_llm/CONDITIONS.md`, PROTOCOL
§10.1) and must never be differenced against each other. Both numbers are
reported; neither corrects the other.

**Model sweep (P6, stale — pending recapture):** the last valid run was
1.5B / 3B / 7B × 3 seeds, all GPU-resident on a 6 GB laptop except the 7B,
which could only reach 81.7% GPU residency and was reported **out of
competition** — its accuracy was valid, its latency was not comparable to
the eligible models, and it was excluded from the Pareto frontier and all
paired tests. The 3B was selected under a pre-registered one-standard-error
rule. That selection was made against the pre-P2, 108-task instrument and
needs re-confirming against the 99-task set once GPU access is available.

---

## The agents

**Four**, as of P2 (`docs/RESEARCH_PLAN_V3.md` §7 — a component is an
agent iff it owns state/policy that outlives one request *and* can act
without direct invocation; `backend/app/agents.CORE_AGENTS` is the
queryable source of truth, not just prose):

| Agent | Kind | Responsibility |
|---|---|---|
| **Orchestrator** | router + tools | Confidence-gated tool-calling loop; deterministic lexicon as primary tier |
| **Attendance** | rules + proactive | percentages, <75% shortage, absence streaks, autonomous periodic scan |
| **Eligibility** | rules + CART | hall-ticket eligibility *and* scholarship scoring — merged from Exam+Scholarship at P2, since both owned the same two upstream triggers (attendance/fee updates) and the same shape of policy |
| **Scheduling** | constraint solver | objective-driven simulated annealing (P1) over a greedy seed; CSV export |

**Still real, still running, not counted as agents.** Academic, Admission,
Finance, Placement and Notification stay in the registry — tools.py and
the REST routes call into them exactly as before — but fail the criterion
above: Academic/Admission/Finance/Placement have no policy of their own
that outlives a request, and Notification reacts to events but owns
neither state nor policy, so it is a bus subscriber, not an agent.
Merging Exam+Scholarship did **not** merge their tools: `get_hall_ticket`
and `get_scholarship` stay two distinct tools (§7.1) — agent merging is
not tool merging. `get_admissions_funnel` *was* retired (13→12 tools):
Admission's only chat-facing capability, dropped since Admission no longer
qualifies as an agent; the admissions funnel itself is untouched, still
served directly by the admin/principal REST routes.

Dropped from v1: Library, Smart-Event, and the pseudo "Student/Faculty
agents" — students and faculty are *roles with permissions*, not agents.

---

## Scheduler (P1): objective-driven, not just feasible

v2's timetable solver was a randomized greedy with restarts — feasible, but
with no defined objective to improve against. P1 adds an explicit
multi-term objective (idle gaps, late starts, load balance, block length,
repeats) and a simulated annealer (Metropolis acceptance, geometric
cooling, incremental delta-cost) seeded by the same greedy construction, so
the comparison isolates the search rather than the seed.

10 seeds each, same institution instance (`evaluation/results/v3_scheduler/e4.json`):

| | v2 greedy (frozen) | P1 (SA) | Instance floor |
|---|---|---|---|
| Objective (mean) | 2,441.3 | 204.2 | 195.96 |
| Objective (range across seeds) | 2,394 – 2,531 | 198 – 215 | — |
| Solve time (median) | 163 ms | 5.3 s | — |

The two ranges are **disjoint by roughly an order of magnitude**
(v2-best ÷ P1-worst ≈ 11×), so no significance test was needed to call it —
a per-seed rank test was skipped rather than fabricated, since v2's
individual seed values were never stored, only the band. P1 lands within
~4% of the instance's known lower bound. A weight-ablation run (zeroing
each objective term in turn) confirms every term is load-bearing: none of
them can be dropped without moving the objective.

---

## External benchmark: ITC-2007 track 3 (P1b)

Plan §4.4 names the risk directly: *"a wrong mapping produces a
meaningless number, which is worse than no number."* So before running the
scheduler against the competition's curriculum-based course timetabling
instances, the cost model (`evaluation/itc2007/ctt.py`) was transcribed
function-by-function from the competition's own `validator.cc` and
**differentially tested** against the compiled binary:

- **1,900 random instance/solution pairs, 2 seeds** — agree with the
  official validator on **all eight cost components**, not just the total.
- The published toy example reproduces the officially stated
  `Violations = 5, Total Cost = 30`.
- The solver (`evaluation/itc2007/solver.py`) solves the toy instance to
  0 violations from 3 seeds, confirmed by the official binary.
- Along the way this found a genuine **out-of-bounds read in the official
  validator** at `periods_per_day == 1` (documented in `crosscheck.py`);
  no competition instance uses that value, so it is excluded from the
  generator rather than reproduced.

**Blocked on data, not on code.** The `comp01–comp21` instance files sit
behind a login at the competition's own site, and the maintained mirror
currently fails TLS verification with a certificate hostname mismatch — see
`evaluation/itc2007/INSTANCES.md` for exactly why, and the three ways to
supply the files. `run_e4b.py` will not invent a number to fill the gap; it
exits with that explanation instead.

---

## Figures

```bash
python evaluation/figures.py          # every figure that has data, one command
```

Six of nine are drawn from real captured data
(`evaluation/results/figures/`, manifest in `FIGURES.md`):

| Figure | What it shows |
|---|---|
| F1 — cascade DAG | live bus topology: 8/10 agents in cascades, 11 edges, depth 2 |
| F2 — routing accuracy | lexicon 89.8%; best eligible hybrid 94.8%, by model size |
| F3 — confusion matrices | where the lexicon's 11 dev misses actually land |
| F6 — accuracy–latency Pareto | τ = 0: 94.8% at 348 ms vs LLM-only 76.9% at 3,414 ms |
| F7 — scheduler | P1 204.2 vs v2 2,441, floor 196.0 (seed-0 convergence trace) |
| F8 — latency CDF | 89.8% of queries answered in 0.09 ms; escalated tail median 3,418 ms |

**Three are intentionally not drawn** — there is no placeholder or
illustrative version anywhere in this repository, only a `Blocked`
exception naming what phase unblocks them, enforced by
`tests/test_figures.py`:

- **F4** (RQ1 2×2 factorial) — needs P2 for the conditions and P5 for the
  held-out data.
- **F5** (provenance gate on/off) — needs P3; the gate doesn't exist yet.
- **F9** (dose-response over tool-space size) — needs P2 and P5.

Reading rules that travel with every figure: all accuracy numbers are
**dev-set** results; the LLM tier loses; v2 and v3 are never differenced;
the 7B never shares a frontier with an eligible model. Full detail in
`evaluation/results/figures/FIGURES.md`.

---

## Measured results

| Metric | Result | Run |
|---|---|---|
| Intent routing, lexicon (primary tier) | **89.8%** — 108 labelled queries, 12 intents | v3, **pre-P2, stale** — see [Research status](#research-status-v3) |
| Intent routing, LLM tier alone | **76.9% ± 2.0%** (3 seeds) — **loses to the lexicon by 12.9 pts** | v3, **pre-P2, stale** |
| Intent routing, confidence-gated hybrid, τ = 0 | **94.8%** — +4.9 pts over lexicon, CI touches zero, not yet significant | v3, **pre-P2, stale** |
| Intent routing, LLM tier alone (historical, superseded — not corrected) | 70.4%, single uncontrolled run | v2 |
| Scheduler objective (lower is better) | v2 greedy 2,441.3 → P1 SA **204.2**, instance floor 195.96 | v3 |
| ITC-2007 external benchmark | harness validated against the official scorer; result **pending instance files** | v3 (P1b) |
| Attendance computation | 0 mismatches / 1,000 summaries — reported as *deterministic verification*, **not** an AI accuracy claim | v2, unaffected by v3 routing changes |
| Cross-agent propagation | avg 466 ms, p95 479 ms with the LLM resident; ~127 ms with Ollama stopped — **not comparable across those two conditions**, resource contention only | v2 |
| Ablation — event bus removed | 0 downstream tables auto-update, 4 manual office interventions per upload vs 0 with the bus | re-verified 2026-08-20, post-P2 |
| Failure injection | Eligibility Agent crashed mid-cascade (owns hall-ticket *and* scholarship since the P2 merge, so both withhold together) → Placement and Notification, independent subscribers to the same event, still complete; error audited, replay recovers — **PASS** | re-verified 2026-08-20, post-P2 |
| Scalability | institution 4× larger, identical workload: latency did not grow (0.72×, within run-to-run noise) | v2 |
| Scholarship CART / Placement RF | 90% / 82% test accuracy — deliberately **not** ~100% | v2, unaffected |

**Nothing here is reported as 100%.** Every number above is regenerable
from `evaluation/` — see [Reproduce everything](#reproduce-everything).

---

## Reproduce everything

```bash
python -m pytest tests -q                 # 44 tests
python evaluation/gate_p05.py             # P0.5 router viability gate
python evaluation/capture_llm.py          # frozen-protocol LLM capture (live Ollama)
python evaluation/analyze_sweep.py        # P6 model selection, PROTOCOL 9.2
python evaluation/tune_router.py          # P4 threshold selection, PROTOCOL 9.3
python evaluation/scheduler_eval.py       # E4: P1 solver vs frozen v2 greedy
python evaluation/freeze_manifest.py      # verify the frozen instrument (PROTOCOL 1.5)
python evaluation/evaluate.py             # v2 harness: both routing tiers
python evaluation/evaluate.py --no-llm    # skip the 108 live LLM calls
python evaluation/ablation.py             # is the architecture load-bearing?
python evaluation/failure_injection.py    # fault isolation + replay
python evaluation/scalability.py          # constant workload vs institution size
python evaluation/figures.py              # every figure, one command
python evaluation/itc2007/build.py        # fetch+build the official ITC validator
python evaluation/itc2007/crosscheck.py   # our CB-CTT cost model vs that validator
python evaluation/itc2007/run_e4b.py      # E4b (needs instances -- see INSTANCES.md)
python fl/federated_poc.py                # appendix / future work only
```

`evaluate.py::_verdict` derives its conclusion from the *sign* of the
measured deltas — the report cannot claim the LLM helps when it doesn't.

---

## Project structure

```
backend/app/
  agents/            4 core agents (CORE_AGENTS) + 5 tool-backed components
    orchestrator.py    confidence-gated router + tool-calling loop [agent]
    eligibility.py     hall-ticket + scholarship, merged at P2 [agent]
    timetable.py       objective + greedy seed + simulated annealing (P1) [agent]
    attendance.py      intake, recompute, proactive scan [agent]
    tools.py           typed tool registry (12 tools) with ROLE ENFORCEMENT
    admission.py       admissions pipeline [tool-backed, not an agent]
  router.py          v3 confidence gate: margin <= tau -> escalate
  router_config.json frozen tau=0, sha256-hashed (PROTOCOL 9.3)
  bus.py             instrumented pub/sub, workflow IDs, fault isolation
  llm.py             Ollama chat; startup availability cache
  models.py          shared institutional context store
  seed.py            the synthetic institution
  api/routes.py      role-guarded FastAPI gateway
frontend/static/     five role portals (no build step)
ml/                  UCI calibration -> copula generation -> CART/RF
evaluation/          v2 + v3 harnesses; see `evaluation/results/` and PROTOCOL.md
  itc2007/           ITC-2007 CB-CTT harness (P1b): parser, cost model, SA, validator crosscheck
  results/figures/   P7 figure harness output + FIGURES.md manifest
fl/                  federated-learning PoC (future work)
docs/                RESEARCH_PLAN_V3.md (the plan, phase-gated) · ARCHITECTURE ·
                     DATASET_METHODOLOGY · CODE_WALKTHROUGH · PLAN_V2 (historical)
tests/               44 pytest tests
```

Optional: `set MAWOS_DATABASE_URL=postgresql://user:pass@localhost/mawos`
switches the context store to PostgreSQL with no code changes.

---

## Research status (v3)

Full detail, gates and rationale: `docs/RESEARCH_PLAN_V3.md`. Short form:

| Phase | What | State |
|---|---|---|
| P0 | Freeze v2 baseline, RQ1 instrumentation, protocol | done |
| P0.5 | Router viability gate | done |
| P1 | Objective-driven scheduler (greedy seed + SA) | done |
| P1b | ITC-2007 external benchmark harness | harness validated; **blocked on instance files** |
| P2 | Agent reduction 10 → 4, tool surface held 13→12 | **code + frozen instrument done**; recapture blocked on GPU access |
| P3 | PCN-style provenance gate | **pending** |
| P4 | Confidence-gated hybrid router, τ frozen on dev | **stale** — computed against the pre-P2 108-task/13-tool instrument |
| P5 | Held-out set → dual annotation → single test run | **blocked — the largest schedule risk** |
| P6 | Model sweep, 1.5B/3B/7B × 3 seeds | **stale**, same reason as P4 |
| P7 | Figures F1–F9 | harness done; F2/F3/F6/F8 read stale P4/P6 data until recaptured |
| P8 | Rewrite ARCHITECTURE.md / RESULTS.md to match the evidence | pending — README above is current except where flagged stale above, those two still carry v2-era numbers by design until P8 |

**Why P4/P6 are stale, and why that's not a code problem.** P2 dropped 9
admission-intent dev tasks when `get_admissions_funnel` was retired
(108→99 tasks, 13→12 tools) — every number computed against the old
instrument describes a benchmark that no longer exists. Recapturing needs
Ollama with real GPU access: this environment's Ollama instance can only
see CPU (`nvidia-smi` fails with "insufficient permissions" — a sandboxing
restriction, not a laptop problem; PROTOCOL.md measured this same RTX 4050
on 2026-08-15), and `evaluation/tune_router.py` correctly hard-exits on a
non-GPU-resident capture (PROTOCOL §9.2) rather than let a CPU timing
masquerade as the real thing. A CPU-only diagnostic 3B capture was still
run for a sanity check on accuracy (not latency, not τ selection) — see
`evaluation/results/v3_llm/`, marked `gpu_residency.fully_resident: false`
and not citable as a P4/P6 result.

### Known limitations (say these before an examiner does)

- The 108-query routing benchmark and the lexicon it scores were written
  by the same project — evidence about this classifier on this benchmark,
  not a general claim about language understanding. A held-out set written
  outside the team (P5) is the fix, and it hasn't run yet.
- τ = 0 was selected on that same contaminated dev set. The hybrid's
  +4.9-point gain is not statistically confirmed (CI touches zero,
  McNemar p = 0.070) — P5 decides, not this README.
- The model sweep is one family (Qwen 2.5), one temperature, three seeds.
- The 7B could not stay GPU-resident on this 6 GB laptop and is reported
  out of competition — valid accuracy, non-comparable latency.
- Data is synthetic (UCI-calibrated, copula, 3% label noise); the bus is
  in-process and at-most-once; replay recovery is manual.
- The agent count is currently 10, not the 4 the pre-registered criterion
  (§7) settles on — P2 has not been implemented yet.
