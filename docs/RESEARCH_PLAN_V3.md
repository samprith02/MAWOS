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

### 3.5.1 P0.5 result (run 2026-08-15) — passes, on weak evidence

`evaluation/gate_p05.py`. Decision: **P4 proceeds** under the
pre-registered rule. But the two halves of the gate disagree in a way that
changes what P4 is actually testing.

**The gate mechanism is excellent.** AUC(margin → lexicon error) = **0.983**.
Median margin is 0.00 for the lexicon's errors and 3.00 for its correct
answers — the lexicon fails almost exactly when no keyword matches at all
and it silently dumps the query into `profile_query`. 9 of its 11 errors
sit at margin 0. Confidence-gating can find the failures.

**The fixer is weak.** A perfect LLM escalated on 18.5% of queries would
reach 100%. The v2 3B model instead fixes only **4 of the 11** errors, and
at the same threshold **breaks 2** queries the lexicon had right. Net
**+1.9%** (91.7% vs 89.8%) at 10.2% escalation — two queries out of 108,
with a 95% bootstrap CI of **[-2.8%, +6.5%]** that straddles zero.

The pre-registered rule (`> lexicon + seed band`, band = 0.0 measured) is
met, so P4 proceeds and the threshold is **not** revised. But the effect is
not distinguishable from noise, and reporting the pass without the CI
would be exactly the overclaiming this plan exists to prevent.

**Consequence for the work order.** The router's bottleneck is not the
gate, it is the model's competence on the colloquial tail the gate
correctly identifies. That makes the model sweep the decisive experiment
for RQ3 rather than a supporting one: **P6 should run before P4 is
built out**, so the router is tuned against whichever local model can
actually exploit the 18.5%-escalation headroom the oracle shows exists.

Caveat on provenance: the realised curve uses per-query LLM correctness
reconstructed from `results/v2_historical/RESULTS.md` §1.2 — one run, one
seed, one model. The AUC and the oracle ceiling depend only on frozen
artefacts and will not move; the realised curve must be recomputed against
the frozen LLM baseline.

### 3.5.2 P6 result (run 2026-08-15) — 3B selected, and v2 is not comparable

`evaluation/analyze_sweep.py` → `results/v3_gates/p6_sweep.json`. Rule
§9.2, committed before the sweep. 324 records per model, three seeds,
**zero call failures**.

| Model | Solo | Hybrid | Net headroom recovery | fix/break | Median |
|---|---|---|---|---|---|
| **qwen2.5:3b-instruct** | 76.9% | **94.8%** | **48.5%** | 6.7 / 1.3 | 3414 ms |
| qwen2.5:1.5b-instruct | 64.8% | 91.4% | 15.2% | 2.7 / 1.0 | 3600 ms |
| *qwen2.5:7b-instruct* | *80.6%* | *95.1%* | *51.5%* | *6.7 / 1.0* | *ineligible* |

**Selected: `qwen2.5:3b-instruct`**, outright on the primary metric — no
tie-break needed. McNemar 3B vs 1.5B: b01=11, b10=24, **p = 0.041**.

Three things worth stating carefully.

**The 7B is out of competition, not merely slower.** It runs 81.7%
GPU-resident on a 6141 MiB GPU (`results/v3_llm/ELIGIBILITY.md`), so it is
in a different computational regime and is excluded from selection, from
every Pareto plot and from every paired test. Its accuracy is unaffected
by offload and is reported. What it licenses is a hedged statement, not a
headline: *under this configuration, increasing model size alone did not
obviously buy a large additional headroom recovery* — 51.5% against the
3B's 48.5%. It does **not** license "the hardware ceiling costs nothing",
because the comparison is not on a common axis.

**The 1.5B is slower than the 3B, and the mechanism is behavioural.** It
abstains 30.2% of the time against the 3B's 9.3%, and an abstention emits
a text reply (median 38 tokens) instead of a compact tool call (29). So:
*a smaller parameter count does not imply lower end-to-end agent latency
when model behaviour changes the execution path.* That is a more useful
observation than the raw latency ordering and is kept as one.

**The v2 equivalence check failed** — `results/v3_llm/CONDITIONS.md`. The
standard tier reproduces (83.3% → 83.8%) but the colloquial tier moves
44.4% → 62.9% and no-tool answers drop 23 → 10. A divergence confined to
abstention is the signature of a change in the runtime's tool-emission
path, and v2 did not record its Ollama version, so it cannot be tested.
Consequences: v2 and v3 numbers are **never differenced**; §10.1 now makes
runtime capture mandatory; and the LLM-vs-lexicon gap is restated
**within v3** as 76.9% vs 89.8%, **−12.9 points**, superseding v2's −19.4
as an estimate while leaving the direction — the LLM tier loses on
routing — unchanged.

### 3.6 P4 result (run 2026-08-15) — router built, τ = 0, effect not yet established

`evaluation/tune_router.py` → `results/v3_gates/p4_router.{json,md}`.
Rule §9.3, committed in `49be6dd` before the script was run. The complete
τ curve is published, not only the selected point.

The curve has one dominant feature. **Every lexicon error the 3B can
repair sits at margin 0** — `fixed` is 6.7 at every threshold from τ = 0
to τ = 8. Escalating anything above margin 0 repairs nothing further and
only breaks answers the lexicon had right (`broken` climbs 1.3 → 20.7).
So the argmax and the 1-SE selection coincide at the cheapest feasible
point:

> **τ = 0** — escalate exactly the queries where the keyword classifier
> matched nothing at all and silently defaulted to `profile_query`.

τ = 0 is therefore **structurally motivated rather than meaningfully
tuned**: it would have been selected under argmax, under the 1-SE rule,
and by anyone reasoning from the mechanism without seeing the curve at
all. That **greatly reduces** the threshold-overfitting concern — several
independent selection rules converge, and the resulting threshold has an
interpretable meaning ("the lexicon matched nothing"). It does not
*eliminate* the degree of freedom: the curve that makes τ = 0 look
structural is itself a dev curve, and only held-out data can confirm the
same failure class dominates there.

| | dev |
|---|---|
| lexicon | 89.8% |
| hybrid at τ = 0 | **94.8%** (95.4 / 94.4 / 94.4) |
| delta | **+4.9** points, 95% bootstrap CI **[+0.0, +10.2]** |
| bootstrap resamples with no gain | 3.8% |
| McNemar vs lexicon | b01 = 7, b10 = 1, **p = 0.070** |
| escalation | 10.2%, i.e. 11 of 108 queries |
| expected cost | **348 ms/query** vs 3414 ms for LLM-on-everything (9.8×) |

**What is not established.** Neither the CI nor McNemar clears
conventional significance at n = 108, and the CI's lower bound sits on
zero. More importantly **dev is contaminated by construction** (§11) —
the lexicon was tuned on these very queries. These numbers select τ.
They are not the result. The held-out set (P5) is, and it runs once
against the hashed config.

**Scope.** P4 as written in §8 also listed multi-tool composition and
conversational memory. Neither was built. Both change what the agent
*does* rather than how it *routes*, so folding them in here would confound
the router evaluation with two new capabilities; and neither is required
by any research question. They are dropped rather than deferred, and the
work order is corrected to say so.

**System change.** `backend/app/router.py` replaces v2's tier switch. v2
chose the LLM on Ollama *reachability* — an availability check — so with
the daemon running every query paid full LLM cost, including the ~90% the
lexicon answered correctly and ~60 000× faster. The UI, the metrics
endpoint and the startup banner previously called the lexicon a
"fallback"; under a confidence gate it is the primary tier, and they now
say so.

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

### 4.3.1 P1 result (run 2026-08-15) — the two defects are fixed

`evaluation/scheduler_eval.py` → `results/v3_scheduler/e4.{json,md}`. The
new solver is `backend/app/scheduler.py`: a compact greedy seed followed
by simulated annealing over two hard-feasible moves. The v2 comparator is
**read from the P0 freeze, not re-run**, and both are scored by the same
frozen metric module, now hashed under §1.5.

**Read the floor, not the percentages.** The best objective *any*
schedule could reach on this instance is **196.0** — gaps, late starts,
repeats and teacher gaps can all be zero, but the load-balance term
cannot, because 18 periods do not divide evenly into five days. P1 lands
**8.2 above that floor**; v2 sits **2245.4** above it.

| Metric (10 seeds) | v2 greedy | P1 SA |
|---|---:|---:|
| Late-start days (of 200) | 80.80 ± 5.56 | **0.90 ± 1.22** |
| Idle gaps inside days | 223.00 ± 11.44 | **0.00 ± 0.00** |
| Subject repeats in a day | 138.50 ± 7.06 | **0.20 ± 0.40** |
| Teacher idle gaps | 322.00 ± 11.30 | **3.90 ± 1.76** |
| Daily-load σ | 1.01 ± 0.04 | **0.49 ± 0.00** |
| Objective | 2441.3 ± 42.0 | **204.2 ± 5.3** |
| Placement rate / hard conflicts | 1.000 / 0 | 1.000 / 0 |
| Solve time | 163 ms | 1960–5646 ms |

**The zero is largely construction, not search, and is reported that
way.** The seed lays each section out as periods 0..load−1 on every day,
so it is gap-free before a single annealing step runs; gaps appear only
where a teacher conflict forces an overflow. A solver built to produce
compact days producing compact days is not a finding, and per CLAUDE.md
it is not headlined. The informative quantity is the 8.2-point residual —
0.90 late starts, 0.20 repeats, 3.90 teacher gaps the search could not
remove.

**A trade-off the frozen objective does not price.** Compaction raises
the longest unbroken run from 2.63 to 3.60 periods. With 18 periods over
five gap-free days that is arithmetic rather than a choice, but nothing
in the objective charges for it — so if four back-to-back classes are
worse than one mid-morning gap, this objective cannot say so.

**A defect in the objective, found by optimising it.** The frozen metric
divides by the number of *non-empty* section-days, so a solver that
empties a Friday shrinks the denominator and scores better without
scheduling better. The metric is frozen, so it was not patched; the
solver instead carries a hard invariant that every section-day keeps at
least one class, which blocks the exploit, preserves comparability with
v2 (whose 200 section-days are all occupied), and keeps the incremental
cost exactly equal to the frozen one. Recorded in §11 of PROTOCOL as an
instrument limitation.

**Ablation.** Every weight is load-bearing — zeroing one and re-scoring
with the *full* objective shows the damage it was preventing: idle_gap →
247 gaps, late_start → 140.7 late starts, subject_repeat → 141.7
repeats, faculty_gap → 143.3 teacher gaps, load_sigma → objective 373.1.

**No significance test.** v2's per-seed objectives were never stored at
P0, only the band, so a rank test would require inventing them. The
ranges are disjoint — v2 [2394, 2531] against P1 [198.0, 215.0] — and
that is reported instead.

**Timing is not a clean measurement on this host.** Identical 120 000-step
workloads ranged 1960–5646 ms with a 25 ms seed phase and one attempt, so
the spread is host contention, not the algorithm. The minimum is quoted
as the least-contaminated estimate (12× the v2 solve time). Measured with
a 2 GB Ollama model resident, per the CLAUDE.md condition.

**Still not a contribution.** §4.4's retraction stands: simulated
annealing for timetabling is decades old. This is applied engineering
with a measured before/after on a real defect.

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
| **P1** | Scheduler: objective + greedy seed + SA. Keep greedy runnable. E4 + weight ablation, 10 seeds. **Done — §4.3.1.** | before/after + convergence reproduce |
| **P1b** | ITC-2007 harness (§4.4), separate from production scheduler. E4b. **Harness done and validated — §8.2**; blocked on instance files. | official validator passes |
| **P2** | Agent reduction 10 → 4 (§7), tool surface held per §7.1. | tool count verified 13→12 |
| **P3** | PCN-style provenance gate. E3. | false-block rate acceptable |
| **P4** | Hybrid router, τ on dev only, complete curve published. E1. **Done — §3.6.** Multi-tool composition and memory are *not* included; see §3.6. | τ never touched test |
| **P5** | Held-out set → dual annotation → κ → **single** test run of E1/E2/E5. | test touched exactly once |
| **P6** | Model sweep 1.5B/3B/7B × 3 seeds. **Done — §3.5.2.** | all three GPU-resident, verified |
| **P7** | Figures F1–F9. **Harness done — §8.1**; 6 drawn, 3 blocked on P2/P3. | every figure regenerable by one command |
| **P8** | Rewrite README / ARCHITECTURE / RESULTS to match the evidence. | §9 threats written |

**Figures.** F1 cascade DAG · F2 routing accuracy × system × model size ·
F3 confusion matrices · **F4 RQ1 2×2: accuracy + attempted-vs-exposed +
abstention** · F5 gate on/off · **F6 accuracy–latency Pareto over τ** ·
F7 scheduler convergence + gap heatmap + ablation · F8 latency CDF ·
**F9 RQ4 dose-response over tool-space size**. F4, F6 and F9 carry the
claims; the rest are support.

### 8.2 P1b — ITC-2007 harness

`evaluation/itc2007/` holds the CB-CTT parser, cost model, annealer and
E4b runner. §4.4 named the risk exactly — *"a wrong mapping produces a
meaningless number, which is worse than no number"* — so the cost model
was not written from the competition's prose. It is transcribed function
by function from `validator.cc` v1.1 and then **differentially tested
against the compiled official binary**.

| Check | Result |
|---|---|
| `crosscheck.py`, two seeds | **1,900 random instance/solution pairs agree on all eight components**, not merely on the total |
| Published toy example | our model reproduces the officially stated `Violations = 5, Total Cost = 30` |
| Solver → official validator | toy instance solved to 0 violations from three seeds, confirmed by the binary with no warnings |
| Incremental cost | equals a full rescore after random move sequences (`tests/test_itc2007.py`) |

The validator is fetched, never vendored: `build.py` records its URL and
sha256, so the binary E4b validates against has provenance instead of
being a pasted-in file.

**Two findings worth keeping.**

* The official validator has an out-of-bounds read in
  `CostsOnCurriculumCompactness` when `periods_per_day == 1`: every period
  then satisfies `p % ppd == 0`, so the final period's lookahead reads one
  past the end of its row. No competition instance has ppd = 1 (comp01–21
  use 4–6), so `crosscheck.py` excludes that case and says why, rather
  than treating undefined behaviour as ground truth or quietly matching
  whatever the binary happened to return.
* **E4b is blocked on the instance files, not on code.** QUB serves the
  spec and the validator openly but puts the instances behind a login;
  the Udine mirror fails TLS with `SEC_E_WRONG_PRINCIPAL` — a hostname
  mismatch on a *currently valid* University of Udine certificate from a
  real academic CA. It is very probably fine, and it was still not forced
  with `--insecure`, because that is a call about the team's machine and
  the benchmark's provenance. `INSTANCES.md` documents the three ways to
  supply them; `run_e4b.py` hashes whatever it is given so the bytes
  behind a reported penalty stay recoverable.

No published-best table is hardcoded. `run_e4b.py` compares only against
an `instances/BESTS.json` that cites its source, and otherwise reports our
penalties and says the comparison is pending — a reference number nobody
can point at a source for is exactly what §1 rule 6 forbids.

### 8.1 P7 — figure harness

`python evaluation/figures.py` regenerates every figure that has data and
writes `evaluation/results/figures/FIGURES.md`, which lists each figure,
the JSON it was regenerated from, and what the blocked ones are waiting
for. `--pdf` adds vector copies; naming a figure (`figures.py F6`) draws
only that one.

**Drawn (6).** F1 from the live bus and the agent sources, so it cannot
drift from the wiring. F2, F3, F6, F8 from the frozen captures and the P0
freeze. F7 from `v3_scheduler/e4.json`.

**Blocked (3), and this is enforced rather than noted.** F4 needs RQ1
cells B and C (P2); F5 needs the provenance gate (P3); F9 needs the
tool-space dose-response capture (P2). Their builders raise `Blocked`
with the experiment named, `tests/test_figures.py` asserts they keep
raising, and no illustrative version of any of them exists in the
repository. A placeholder figure is a number on a slide that
`evaluation/` cannot regenerate, which rule 6 of §1 forbids.

**Two things the figures forced into the open.**

* F3's caption originally asserted that the lexicon's errors fall to
  `profile_query` by a registry-order tie-break. They do not: L131 of
  `lexicon_v2.py` assigns `profile_query` explicitly when nothing
  matches. The distinction matters, because it is *why* 9 of the 11
  errors carry margin exactly 0 — τ = 0 is structural, not fitted. The
  caption is now computed from the lexicon rather than asserted.
* The same structure caps the router. The other 2 errors score above 0
  and are never escalated at τ = 0, so the reachable ceiling on dev is
  98.1%, not 100%. F6 shows the whole curve, including that the argmax
  never exceeds it.

**One weakness the figures exposed.** E4 records a convergence trace for
seed 0 only, so F7A is a single trace with the 10-seed band quoted beside
it. Recording all ten is a one-line change to `scheduler_eval.py`, but it
would re-run E4 and move numbers already reported, so it waits for the
next E4 run rather than being slipped in here.

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
