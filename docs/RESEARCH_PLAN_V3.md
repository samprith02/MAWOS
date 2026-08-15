# MAWOS v3 — Research Plan (rev. 3, decisions resolved)

Status: **§10 resolved. Ready to cut `v3-research` on approval.**
Rev. 3 applies the review decisions, and **corrects two of them** where
checking the code and the ITC-2007 specification showed the decision as
stated could not work (§0.2).

**Positioning, fixed:** the university system is the **experimental
platform**, not the claimed contribution. The paper is an empirical study
of how tool-space restriction affects agent behaviour, plus a practical
confidence-gated router under constrained local compute.

---

## 0. Revision history

### 0.1 Accepted from review

| Decision | Status |
|---|---|
| RQ1 2×2 factorial as **primary** RQ | accepted, §3.1 |
| v2's 14.8% demoted, never used causally | accepted, §2 |
| 1.5B / 3B / 7B; reject 14B | accepted, §6 |
| P0.5 viability gate **with pre-registered thresholds** | accepted and strengthened, §3.5 |
| Scheduler is implementation, not contribution | accepted, §2.1 |
| Notification: remove | accepted, §7 |
| Records: re-evaluate under the same criterion | accepted — **and it fails**, §7 |
| 108 queries → dev only; new held-out set; κ | accepted, §5.2 |
| McNemar + bootstrap + Holm | accepted, §5.1 |
| Null results are acceptable and reportable | accepted, §1 rule 8 |

### 0.2 Corrected from review

Two decisions were checked against the code and the ITC-2007 spec and do
not survive as stated:

**(a) "Compare 10-agent vs 6-agent tool space" cannot be run as designed.**
The registry (`tools.py`) exposes **13 tools**. Removing the Admission
agent removes exactly **one** (`get_admissions_funnel`). A 13→12 change is
far too small to detect, and worse: the 9 admission queries in the dev set
become unanswerable under v3, so the comparison would measure *"we deleted
the answer,"* not tool-space size. Replaced by a proper dose-response
design, §3.4.

**(b) ITC-2007 "if reasonably cheap" — it is not cheap as scoped.**
Track 3 makes room assignment with capacity a first-class decision
variable plus a room-stability soft constraint. MAWOS has **no room model**
— `room` is a cosmetic f-string at `timetable.py:86`. Genericising the
production scheduler is a model extension, not a parser. A cheaper design
that buys the same evidence is in §4.4.

### 0.3 Retracted in rev. 2, still retracted

Numeric provenance gating (occupied by Proof-Carrying Numbers, arXiv
2509.06902) and soft-constraint timetabling (ITC-2007 curriculum
compactness; SA-with-penalization, *J. Scheduling* 2022) are **not**
contributions. Both are built, both are cited, neither is claimed. No
venue is targeted until §5 evidence exists.

---

## 1. Non-negotiable methodological rules

1. **The test set is touched once.** τ, weights, prompts and lexicon are
   selected on *dev* only.
2. **Held-out queries are authored outside the team**, blind to `_LEXICON`.
3. **Every stochastic component is multi-seed**, reported mean ± std.
   SA: 10 seeds. LLM: 3 seeds. Never best-of-N.
4. **Abstention is never merged into error.** Report accuracy /
   wrong-tool / abstained separately.
5. **Baselines stay executable**, not described.
6. **No number that `evaluation/` cannot regenerate. No 100% headline.**
7. **Latency compared only within identical residency conditions.**
8. **A null result is a result.** No hypothesis is rescued by changing the
   metric, the split, or the threshold after seeing data. Every threshold
   in this document is pre-registered *here*, before any run.

---

## 2. Literature position (unchanged from rev. 2, summarised)

Searches run 2026-08-15 at snippet level. **Every paper below is on a
mandatory read-before-writing list** — none of these citations may enter a
related-work section on the strength of a search result alone.

**Occupied — we implement and cite, never claim:**
- Numeric grounding: Proof-Carrying Numbers (2509.06902); VeriFin
  (2608.10213); EG-VAR (2607.12650).
- Timetabling: SA-with-penalization (*J. Scheduling* 2022); ITC-2007
  track 3 defines curriculum compactness — "a penalty for each isolated
  lecture" — as a standard soft constraint.

**Adjacent — must be positioned against carefully:**
- OrgAccess (2505.19165): does the model *reason* about permissions
  correctly? A competence question.
- Progent: can we *enforce* policy on tool calls? A mechanism question.
- ToolPrivacyBench (2606.28061); FragFuse (2606.15609).
- **Nearest prior work:** *LLM Abstention Can Be a Prompt Artifact*
  (2507.16199) — establishes abstention is partly a framing artifact. Our
  question is its **tool-space analogue**. Supportive, but it means we must
  state the distance honestly rather than overstate it.
- Setting: TinyLLM (2511.22138), small models for agentic tasks on edge
  hardware.

**The seam:** neither the competence question nor the mechanism question
asks whether *restricting the visible tool space changes what the model
attempts*. That is a **benchmark-validity** question, and it is what §3.1
tests.

**Honest ceiling.** One plausible research seam (RQ1, contingent on a real
read of OrgAccess and ToolPrivacyBench), one solid applied-systems result
(RQ3), and competent non-novel engineering. A strong B.E. project and a
plausible modest paper. Raising that ceiling requires the multi-model /
multi-domain scope in §10.5 — a deliberate decision, not a writing choice.

---

## 3. Research questions

### 3.1 RQ1 (PRIMARY) — Does tool-space restriction change what the model attempts?

**Design — 2×2 factorial, everything else frozen:**

| | Tool space = **role-scoped** | Tool space = **full (13 tools)** |
|---|---|---|
| Persona = **role-matched** | **A** (v2's main condition) | **B** *(new)* |
| Persona = **single admin** | **C** *(new)* | **D** (v2's §1.2b) |

v2 only ran A and D, changing both factors at once — which is why its
14.8% is uninterpretable. **B and C are the whole experiment.** The finding
is the interaction term, not any single cell.

**Hypotheses**
- **H1a.** Tool-space restriction changes selection accuracy beyond what
  removing the correct tool explains — i.e. the effect persists on the
  subset of queries whose correct tool remained in scope. *(This subset
  restriction is mandatory; without it the effect is trivially true.)*
- **H1b.** Abstention rises under a mismatched persona **even when the
  correct tool is in scope**.
- **Falsified if** differences fall inside the seed-variance band once tool
  availability is controlled.

**The measurement that matters.** Per review, the central distinction is:

> **"could not use the tool"** (it was not exposed / the call was blocked)
> vs **"did not attempt the tool"** (it was exposed and the model declined)

These require different instrumentation. Log, per query:
`tool_exposed` · `tool_attempted` · `call_blocked_by_guard` ·
`abstained_with_clarification` · `abstained_silently` · `wrong_tool` ·
`correct_tool`. The second column is the research object. A system that
only records final accuracy cannot answer RQ1 — this instrumentation is
built in P0, before any experiment.

**Secondary metrics:** task success, error type, latency, cost.

### 3.2 RQ2 — Mechanical traceability of numeric claims

**H2.** A deterministic extract-and-match gate reduces ungrounded numeric
claims at acceptable false-block and latency cost.
**Falsified if** false-block rate degrades usable answers, or claims escape
by paraphrase ("about three-quarters" for 74.6%).
**Framing: engineering evaluation of a PCN-style gate. Not a novelty claim.**

### 3.3 RQ3 — Division of labour under a fixed local compute budget

- **H3a.** A margin-gated hybrid dominates both pure tiers: accuracy ≥
  max(lexicon, LLM) at latency ≪ LLM-only.
- **H3b.** Advantage grows with colloquial/ambiguous query share.
- **H3c.** Larger local models shift the frontier but do not remove the
  escalation benefit.
- **Falsified if** no τ gives hybrid ≥ both tiers outside seed variance.

### 3.4 RQ4 (REDESIGNED) — Does tool-space *size* affect selection?

The refactor-based version is dead (§0.2a). The replacement is a proper
**dose-response** experiment, which is both stronger and independent of our
architecture decisions:

**Design.** Hold queries, persona, model and prompts fixed. Vary only the
number of exposed tools — **5 / 9 / 13 / 20 / 30** — by (i) subsetting the
real registry and (ii) padding with plausible **distractor tools** that are
never correct. Every condition keeps the correct tool exposed.

- **H4.** Selection accuracy degrades monotonically with tool-space size,
  and abstention rises.
- **Falsified if** accuracy is flat across the range outside seed variance.

This folds RQ4 into RQ1 as the *dose* axis of the same phenomenon, gives a
real gradient instead of a 1-tool delta, and — usefully — tells us whether
our own agent-reduction decision had any measurable benefit, without that
decision contaminating the experiment.

**Distractor design is the risk here.** Distractors must be plausible and
domain-appropriate but never correct; if they are obviously irrelevant the
task gets trivially easier and H4 is untestable. Distractors are authored
at P0, reviewed, and frozen with the protocol.

### 3.5 P0.5 — Router viability gate, thresholds pre-registered

Per review: the gate must not become "AUC > 0.5 therefore proceed."

**Primary criterion (simulation, not a proxy).** From dev data alone,
compute the best achievable hybrid accuracy at every escalation rate, given
the observed margin ranking and the observed per-query correctness of both
tiers. This is the quantity we actually care about, computable before
building anything.

- If max achievable hybrid accuracy ≤ lexicon accuracy + seed-noise band
  **at every escalation rate below 50%** → **abandon the router (P4).**

**Secondary criterion (descriptive).** AUC of lexicon margin as a predictor
of lexicon error, with conventional discrimination bands stated a priori
(0.5 = chance; 0.7 = acceptable discrimination, the standard
Hosmer–Lemeshow reading). These are **conventional, not derived**, and are
reported as description alongside the simulation, never as the decision.

- AUC < 0.60 → no useful signal.
- 0.60–0.70 → weak; the simulation criterion decides.
- ≥ 0.70 → consistent with proceeding.

Both criteria are computed and reported **whatever the outcome**, including
if they cancel P4.

---

## 4. Baseline freeze — before any code changes

**Deliverable: `evaluation/baseline_freeze.py`** → `evaluation/results/v2_frozen/`.
Run at P0, never again.

### 4.1 Scheduler baseline (measured on the shipped DB)

| Metric | v2 greedy |
|---|---|
| Section-days with **no first period** | **84 / 200 (42.0%)** |
| Total idle gaps inside a day | **225** |
| Idle gaps per section-day | **1.12** |
| Within-section daily-load σ (mean) | **1.0** |
| Hard violations | 0 (by construction) |

Cause, for the record: `timetable.py:59` optimises **hard feasibility only**
— no objective function exists, so a schedule with holes at 9:00 and 12:15
scores identically to a compact one. The quality criterion was never
written.

Also frozen at 10 seeds: first-period coverage, idle-gap *distribution*,
longest contiguous block, faculty idle gaps, subject-repeats-per-day, daily
load spread, placement rate, unplaced count, solve time, restarts.

### 4.2 Router baseline

v2 lexicon 89.8 / 100.0 / 69.4 · v2 LLM (3B) 70.4 / 83.3 / 44.4 @ 4474 ms.
Both re-run at 3 seeds to establish the variance bands v2 never had.
`llm.py::_LEXICON` preserved verbatim as `evaluation/baselines/lexicon_v2.py`
so later edits cannot silently improve the baseline.

### 4.3 RQ1 instrumentation

The seven-field per-query log in §3.1 is implemented and verified at P0.
Nothing downstream is measurable without it.

### 4.4 ITC-2007 — approved, but re-scoped

**Decision: yes, as a separate benchmark harness sharing the annealing
core — not by genericising the production scheduler.**

Rationale: the claim we want is narrow — *"our SA implementation is
competent, evaluated against a standard benchmark"* — and that does not
require the MAWOS scheduler to speak ITC. Building a small ITC harness
(`evaluation/itc2007/`) that reuses the same annealing engine against the
ITC constraint model buys the external comparability while keeping a room
model out of a production scheduler that has no rooms.

Cost: ~1 day (parser ≈100 LOC, ITC constraint model, official validator).
Genericising the production scheduler instead: 1–2 days with real risk of a
subtly wrong mapping — and a wrong mapping produces a meaningless number,
which is worse than no number.

Reported as: *"the scheduler implementation was evaluated against a
standard timetabling benchmark to establish baseline competitiveness."*
Never as a contribution. If our gap to published bests is large, **that is
reported too.**

### 4.5 Frozen protocol

`evaluation/PROTOCOL.md` at P0: metric definitions, seeds, splits, tests,
hardware conditions, distractor tool list. No edits without a dated
changelog entry.

---

## 5. Experiment matrix

| ID | RQ | Systems / conditions | Data | Primary metrics | Seeds |
|---|---|---|---|---|---|
| **E1** | RQ3 | lexicon · LLM-only · hybrid(τ) · oracle upper bound | dev for τ; held-out for final | accuracy, escalation rate, latency p50/p95, accuracy@latency-budget | 3 |
| **E2** | **RQ1** | **2×2 factorial A/B/C/D** × 5 roles | held-out | accuracy, **attempted vs exposed**, abstention (clarifying vs silent), blocked calls | 3 |
| **E3** | RQ2 | gate on / off | annotated answers | ungrounded-numeric rate, false-block rate, overhead | 3 |
| **E4** | sched. | v2 greedy · greedy+SA · weight ablations | our instance | objective, first-period coverage, idle gaps, load σ, hard violations | 10 |
| **E4b** | sched. | SA core vs published bests | **ITC-2007 track 3** | ITC penalty, validator pass | 10 |
| **E5** | **RQ4** | tool-space size **5/9/13/20/30** | held-out | accuracy, abstention (dose-response curve) | 3 |
| **E6** | system | cascade / fault-injection / scalability | live bus | propagation latency, isolation, replay | 10 |

Model axis (1.5B / 3B / 7B) applies to E1, E2, E5.

### 5.1 Statistics

Mean ± std across seeds; per-seed appendix. **McNemar's** for paired
router comparisons on identical queries (not a t-test). **Bootstrap CIs**
(10k) on deltas and the Pareto envelope. **Holm correction** across the
comparison family. **Effect sizes with every p-value** — at n≈200, small
deltas will be significant and meaningless.

### 5.2 Splits

| Split | Source | Size | Use |
|---|---|---|---|
| **dev** | v2's 108 team-authored queries | 108 | τ, weights, prompts, lexicon, P0.5 |
| **test** | **authored outside the team**, blind to the lexicon | ≥60, target ~100 | every headline number |

The v2 108 are demoted to dev precisely because CLAUDE.md already admits
the lexicon was tuned to their phrasing — which is exactly what makes them
good dev data and useless as test data.

**Held-out authoring protocol** (violate any step and the set is worthless):
authors see only a plain-English description of the portal and the roles —
never the tool list, lexicon, or intent taxonomy; each writes as their own
role; **two independent annotators** label the target tool and report
Cohen's κ, adjudicating before any system runs; **strata (straightforward
vs colloquial/ambiguous) are pre-registered by the annotators at authoring
time**, not assigned post-hoc by us — v2's "hard tier" was team-assembled
and is therefore not a clean stratum; file frozen and hashed, hash reported.

---

## 6. Hardware — measured 2026-08-15

| | |
|---|---|
| CPU | i5-12450HX, 8C/12T |
| RAM | **15.71 GB total, 6.83 GB free** (14.38 committed) |
| GPU | RTX 4050 Laptop — **6141 MiB VRAM, 4905 MiB free** |
| Disk | 129.44 GB free / 474.72 GB |

(`Win32_VideoController.AdapterRAM` reports ~4.0 GB — uint32 saturation.
Use `nvidia-smi`.)

| Model | ≈Q4_K_M | Fits 6.0 GB VRAM | Verdict |
|---|---|---|---|
| qwen2.5:1.5b | ~1.0 GB | yes | **add** |
| qwen2.5:3b | ~1.9 GB | yes (pulled) | **keep** |
| qwen2.5:7b | ~4.7 GB | tight; needs KV headroom | **add, close other GPU apps** |
| qwen2.5:14b | ~9 GB | **no** — ~40% CPU offload | **reject** |

Disk is not the constraint; **VRAM is**. The disqualifier for 14B is not
slowness but **measurement validity**: latency is a primary E1 metric, and
a partially-offloaded model measures the offload. One CPU-offloaded point
would silently corrupt the Pareto curve. 1.5B/3B/7B gives three
GPU-resident points — a cleaner sweep than 3B/7B/14B and cheaper (~5.7 GB
to pull; portable path per CLAUDE.md, not winget).

**Hygiene:** interleave conditions (laptop thermals); report medians of
interleaved runs; log GPU temp/clocks; state Ollama residency on every
latency table; discard warm-ups; report model-load time separately.

---

## 7. Agent set — preregistered criterion, applied without exception

The rev. 2 criterion ("authorization, grounding, or coordination") was too
loose — it let weak components argue their way in. **Preregistered
replacement.** A component is an agent **iff both**:

- **(A)** it owns **state or policy that outlives a single request**, and
- **(B)** it can **act without direct invocation** — event-triggered, not
  only called.

Applied literally, with no special pleading:

| Component | (A) owns state/policy | (B) acts on events | Verdict |
|---|---|---|---|
| **Orchestrator** | routing policy, τ, tool filter | n/a — it is the system under test | **Agent** (declared special status) |
| **Attendance** | records + recomputation invariant | publishes `attendance.uploaded` | **Agent** |
| **Eligibility** (Exam+Scholarship) | hall-ticket & scholarship state | recomputes on attendance/fee events | **Agent** |
| **Scheduling** | the timetable solution | re-optimises on availability events | **Agent** |
| **Records** | data, but **no policy of its own** | no — pure request/response | **→ tools** |
| **Notification** | none | yes | **→ bus subscriber** |
| Admission, Finance, Placement | CRUD / model call | no | **→ tools or removed** |

**Result: 4 agents.**

**Why Records fails is the interesting part.** It fails *because of our own
design decision*. We made authorization a **pre-inference filter in the
Orchestrator** — that is the architecture. Having done that, no downstream
component owns an authorization policy any more. Records cannot be an agent
under our criterion because our own design took its only claim away. That
is self-consistent, not special pleading, and it is worth stating in the
paper: the criterion has teeth precisely because it removed a component we
wanted to keep.

Going 10 → 4 rather than padding to 6 is the point. Per review, preserving
a component to protect a number is the arbitrariness we are removing.
**E6 is unaffected** — the notification subscriber still exists and still
logs events; it simply is not called an agent.

### 7.1 Constraint the refactor must respect

**The agent refactor must not change the tool surface except by
deliberate, documented removals.** Specifically: Exam and Scholarship merge
into one *agent* but remain **two distinct tools**
(`get_hall_ticket`, `get_scholarship`). Merging them into one tool would
collapse two benchmark intents and shift the gold labels, breaking
comparability with the dev set. **Agent merging ≠ tool merging.**

Net tool-surface change: 13 → 12 (`get_admissions_funnel` removed). The
9 admission queries are dropped from dev with the removal documented.

---

## 8. Work order

| Phase | Work | Gate |
|---|---|---|
| **P0** | Cut `v3-research`. Freeze v2 (§4.1–4.2). RQ1 instrumentation (§4.3). Write `PROTOCOL.md` + distractor tool list. Preserve v2 lexicon + greedy as executable baselines. | baseline frozen **and reviewed** |
| **P0.5** | Router viability gate (§3.5) — simulation primary, AUC descriptive. | **may cancel P4** |
| **P1** | Scheduler: objective + greedy seed + SA. Keep greedy runnable. E4 + weight ablation, 10 seeds. | before/after + convergence reproduce |
| **P1b** | ITC-2007 harness (§4.4), separate from production scheduler. E4b. | official validator passes |
| **P2** | Agent reduction 10 → 4 (§7), tool surface held per §7.1. | tool count verified 13→12 |
| **P3** | PCN-style provenance gate. E3. | false-block rate acceptable |
| **P4** | Hybrid router + multi-tool composition + memory. τ on dev only. E1. | τ never touched test |
| **P5** | Held-out set → dual annotation → κ → **single** test run of E1/E2/E5. | test touched exactly once |
| **P6** | Model sweep 1.5B/3B/7B × 3 seeds. | all three GPU-resident, verified |
| **P7** | Figures F1–F9. | every figure regenerable by one command |
| **P8** | Rewrite README / ARCHITECTURE / RESULTS to match the evidence. | §9 threats written |

**Figures.** F1 cascade DAG · F2 routing accuracy × system × model size ·
F3 confusion matrices · **F4 RQ1 2×2: accuracy + attempted-vs-exposed +
abstention** · F5 gate on/off · **F6 accuracy–latency Pareto over τ** ·
F7 scheduler convergence + gap heatmap + ablation · F8 latency CDF ·
**F9 RQ4 dose-response over tool-space size**. F4, F6 and F9 carry the
claims; the rest are support.

---

## 9. Threats to validity

**Internal.** Lexicon tuned on dev queries → mitigated by external test
set. Single laptop; thermals; Ollama-residency confound (§6). Prompt
sensitivity — tool descriptions materially affect selection, so prompts are
fixed at P0 and changed only on dev, with every change logged. **Distractor
plausibility** (§3.4) is a new internal threat: unconvincing distractors
make H4 untestable.

**External.** One institution; **synthetic data** (UCI-calibrated copula,
3% label noise); one model family; English only; Indian academic
conventions. E4b partially addresses scheduler external validity; nothing
addresses the single-institution limit.

**Construct.** Gold labels are human-assigned — κ bounds the ceiling.
Abstention may be correct behaviour (rule 4). v2's "hard tier" is not a
clean stratum; the held-out set fixes this by pre-registering strata at
authoring time.

**Conclusion.** n≈200 is small; Holm correction across §5; effect sizes
mandatory. **RQ1 may return null.** That is an acceptable, publishable
outcome and no analysis choice will be revisited to avoid it.

---

## 10. Decisions — resolved

| # | Decision | Resolution |
|---|---|---|
| 1 | Primary RQ | **RQ1**, 2×2 factorial (§3.1) |
| 2 | v2's 14.8% | demoted; never causal |
| 3 | Models | **1.5B / 3B / 7B**; 14B rejected on measurement-validity grounds |
| 4 | P0.5 gate | **yes**, simulation-primary with pre-registered thresholds (§3.5) |
| 5 | Scheduler | implementation, **not** a contribution |
| 6 | ITC-2007 | **yes — re-scoped** to a separate harness sharing the annealing core (§4.4), ~1 day |
| 7 | Notification | **removed** → bus subscriber |
| 8 | Records | **removed** → tools; fails our own criterion for a principled reason (§7) |
| 9 | Agent count | **4**, as the output of the criterion — not a target |
| 10 | RQ4 | **redesigned** as tool-space dose-response (§3.4); refactor-based version dropped as underpowered |
| 11 | Dev / test | 108 → dev; external held-out → test; κ reported |
| 12 | Statistics | McNemar + bootstrap + Holm + effect sizes |

### 10.5 Still open — owner: team

- **Held-out authoring: who, and by when?** All of P5 blocks on it. This is
  now the single largest schedule risk in the plan.
- **Scope ceiling.** §2 says this is a strong B.E. project and a modest
  paper. The only honest lever is a multi-model, multi-domain RQ1 study —
  substantially more work. Decide consciously now, not in March.
- **Different-family model** (llama3.1:8b) to separate size from family —
  defer until the size sweep shows a trend worth disambiguating.

---

## 11. Carried-over constraints (CLAUDE.md)

Never headline 100%. Report in the direction the data points — the LLM's
routing loss stays as the τ=0 endpoint of the hybrid curve, not a deleted
configuration. Never present a number `evaluation/` cannot regenerate.
Attendance accuracy is *deterministic verification*, never "AI accuracy";
the manual-workflow comparison is a *modeled estimate*. Stop the server
before touching `mawos.db`; never run `evaluate.py` against a live server.
**This is a prototype built to test a claim, not a product for a client.**
