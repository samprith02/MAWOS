# MAWOS v3 — Evaluation Protocol

**Frozen 2026-08-15 at P0.** Changes require a dated entry in §12. A change
made without one invalidates every result computed after it, because
nobody will be able to tell which protocol produced which number.

This document is the instrument. `docs/RESEARCH_PLAN_V3.md` is the study
design and says *why*; this says *exactly what is measured and how*.

---

## 1. Immutability rules

1. **The test split is touched once.** τ, constraint weights, prompts,
   lexicon edits and distractor choices are selected on **dev** only.
2. **Held-out queries are authored outside the team**, blind to
   `backend/app/llm.py::_LEXICON`.
3. **Stochastic components run multi-seed**, reported mean ± std, never
   best-of-N. Scheduler: 10 seeds. LLM: 3 seeds.
4. **Abstention is never merged into error.**
5. **Baselines stay executable, and the instrument is hashed.**
   `evaluation/baselines/` is pinned. `evaluation/FROZEN.sha256` records
   a digest of every file that defines *what is measured* — the task
   set, gold labels, distractors, tool-space construction,
   instrumentation fields, schedule metrics and both v2 baselines. A
   test enforces it. Changing one of those files is permitted only as a
   dated §12 entry that regenerates the manifest; changing one silently
   is the failure mode this rule exists to prevent, and it matters most
   while unrelated work (P1's scheduler, P7's figures) is in flight.
6. **No number that `evaluation/` cannot regenerate. No 100% headline.**
7. **Latency compares only within identical Ollama-residency conditions.**
8. **A null result is a result.** No threshold in this document may be
   revised after seeing the data it governs.

---

## 2. Splits

| Split | Source | n | Use |
|---|---|---|---|
| **dev** | the 108 MAWOS v2 queries, team-authored | 108 | τ, weights, prompts, P0.5 gate, all tuning |
| **test** | authored **outside the team**, blind to the lexicon | ≥60, target ~100 | every headline number |

`evaluation/benchmark/tasks.py::tasks("test")` **raises** while the test
split is empty. That is deliberate: a headline number computed before P5
is invalid by construction, so the harness refuses rather than quietly
returning dev data.

The 108 v2 queries are dev **because** CLAUDE.md already records that the
lexicon was tuned to their phrasing. That disqualifies them as test data
and makes them ideal dev data.

### 2.1 Held-out authoring procedure

Violating any step voids the set:

- Authors see a plain-English description of the portal and the five
  roles. They never see the tool list, the lexicon, or the intent taxonomy.
- Each author writes as their own role.
- **Two independent annotators** assign the gold tool. Cohen's κ is
  reported. Disagreements are adjudicated *before* any system runs.
- **Strata are pre-registered by the annotators at authoring time.**
  v2's "hard" tier was team-assembled after the fact and is therefore
  **not a clean stratum**; it is labelled
  `stratum_provenance="team-assembled-v2"` in `tasks.py` and must never be
  reported as one.
- The file is frozen and hashed; the hash appears in results.

---

## 3. Task definitions

`evaluation/benchmark/tasks.py`. Each `Task` is immutable and carries
`id, query, gold_intent, gold_tool, stratum, asker_role, source,
stratum_provenance`.

**The gold answer is defined independently of any tool registry.**
`gold_tool` is a name, not a reference — it does not require that tool to
exist in the system under test. Every condition is obliged to construct a
tool space *containing* it.

This exists because the original RQ4 design ("10-agent vs 6-agent
registry") would have removed `get_admissions_funnel` and made 9 tasks
unanswerable, turning a tool-space experiment into an answerability
experiment. Registry-independence makes that failure impossible rather
than merely discouraged.

---

## 4. Tool-space construction

`evaluation/benchmark/toolspace.py`. Three invariants, enforced in code:

1. **The gold tool is always exposed.** Verified across all
   99 × 6 × 3 = 1782 cells (99 dev tasks after P2 dropped the 9
   admission_query tasks, §12 2026-08-19).
2. **Composition is tabulated, not sampled freely.** Free sampling keeps
   the expected distractor share constant but lets its variance explode at
   small N — a 5-tool space could come out all-real by chance, confounding
   "size" with "realism".

   | N | gold | real non-gold | distractors | distractor share of non-gold |
   |---|---|---|---|---|
   | 5 | 1 | 2 | 2 | 0.500 |
   | 9 | 1 | 3 | 5 | 0.625 |
   | 13 | 1 | 5 | 7 | 0.583 |
   | 20 | 1 | 8 | 11 | 0.579 |
   | 30 | 1 | 11 | 18 | 0.621 |
   | **12-real** | 1 | 11 | 0 | 0.000 |

   `12-real` (renamed from `13-real` at P2, the registry lost
   `get_admissions_funnel`) is the **deployed-system reference**, reported
   separately and never plotted on the dose-response curve — its
   composition differs from every curve point, so it answers a different
   question.

3. **Presentation order is shuffled per seed.** Models are position-
   sensitive over tool lists; fixed registry order would let position bias
   masquerade as a size effect. Verified: gold-tool position at N=30 has
   median 15.0 against a uniform expectation of 14.5.

**Role scoping is deliberately not applied inside the RQ4 arm.**
Role-scoped exposure is RQ1's independent variable; applying it here too
would rebuild the persona × tool-space confound that made v2's 14.8%
uninterpretable. Persona remains the task's natural `asker_role` so
first-person queries stay answerable — that varies across tasks but
identically within every condition, so it is controlled by design.

---

## 5. Distractors

`evaluation/benchmark/distractors.py`. 20 frozen tools, 17 required for
N=30, 3 spare.

Two properties, in tension: **plausible** (reads like a real portal
function, same register as the genuine tools) and **never correct** (not a
defensible answer to any task — if an annotator could argue otherwise, the
gold label is ambiguous and the measurement is corrupted).

`check_disjoint()` enforces the second mechanically: each distractor
declares domain keywords, and none may appear in any benchmark query.
**Word-boundary matching, not substring.** Substring matching was tried
first and flagged `get_mess_menu` against "Did I get any me*ssages*?" — a
false positive, since a dining tool has no overlap with a notifications
query. This check is a necessary condition only; it catches lexical
overlap, not semantic overlap, so the human argument is recorded in
`WHY_DISJOINT`.

Two rejected candidates are documented in the module rather than silently
dropped: `get_counselling_appointment` (collides with the admissions
lexicon and with task `adm-h01`) and `get_campus_events` (a reader could
argue it answers "When is the next campus drive?").

---

## 6. Instrumentation

`evaluation/benchmark/instrumentation.py`. The seven fields RQ1 depends on
exist to keep apart:

> **"could not use the tool"** — never exposed, or the guard blocked it
> **"did not attempt the tool"** — exposed, permitted, and declined

A harness recording only final accuracy collapses these and cannot answer
the primary RQ.

### 6.1 Derivation rules (mechanical, applied uniformly)

- **Correctness is strict and first-call**: correct iff the *first*
  attempted tool is the gold tool. This matches v2, which is what keeps
  the frozen baseline comparable. Later recovery is captured separately in
  `gold_attempted`.
- **Selection accuracy and task success are different variables.**
  A model can select the gold tool correctly and still fail, because the
  role guard blocked the call and no data ever arrived. `task_success`
  requires `outcome == "correct"` **and** the gold tool not in
  `blocked_calls`. Merging them inflates accuracy with trials that
  returned nothing.
- **A blocked call still counts as an attempt.** Attempt and permission
  are separate facts.
- **Clarifying vs silent abstention**: decided by whether the reply
  contains `?`. Crude, but deterministic and preregisterable. The
  alternative — an LLM judge — injects a second model's failure modes into
  the measurement of the first. Limitation recorded in §11.
- **`declined_despite_exposure`** is computed over the subset where the
  gold tool was exposed. This subsetting is mandatory: without it, H1a is
  trivially true.

---

## 7. Seed policy

| Component | Seeds | Notes |
|---|---|---|
| Scheduler (greedy, SA) | `0..9` | 10 seeds |
| LLM conditions | `0,1,2` | 3 seeds; passed to Ollama `options.seed` |
| Tool-space sampling & ordering | same seed | `sha256(task_id\|condition\|seed)` |

Per-cell RNG is seeded from a hash of the cell identity, not a global
counter, so rerunning one condition reproduces byte-for-byte without
rerunning the others.

**Decoding**: temperature stays at **0.1**, matching v2, for comparability
with the frozen baseline. Seeds vary sampling. Greedy decoding is not used,
because changing it would break the comparison the baseline exists for.

---

## 8. Metric definitions

### 8.1 Routing / tool selection

`selection_accuracy` · `task_success_rate` · `wrong_tool_rate` ·
`abstention_rate` (split clarifying / silent) · `gold_exposed_rate` ·
`gold_attempted_rate` · `declined_despite_exposure` · `blocked_call_rate` ·
latency p50/p95.

### 8.2 Scheduling

`evaluation/benchmark/schedule_metrics.py`, shared between the frozen v2
solver and the P1 solver so "we improved the scheduler" cannot be an
artefact of two definitions of "gap".

- **section-day** — one (dept, year, section, weekday). 40 × 5 = 200.
- **idle gap** — an unfilled period lying *between* two filled periods on
  the same section-day. Free periods before the first or after the last
  class are **not** gaps; they are a late start or an early finish.
- **late start** — a section-day whose first class is not period 0.

The gap/late-start distinction is load-bearing: it separates a student
waiting around mid-morning from one going home early.

Hard constraints (`faculty_conflicts`, `section_conflicts`) must be 0 in
every seed, in every solver.

---

## 9. Statistical tests

- Mean ± std across seeds; per-seed tables in an appendix.
- **McNemar's test** for paired accuracy comparisons on identical queries —
  the correct test for paired classifiers, not a t-test.
- **Bootstrap CIs**, 10 000 resamples, on deltas and the Pareto envelope.
- **Holm correction** across the comparison family.
- **Effect sizes accompany every p-value.** At n≈200, small deltas will be
  significant and meaningless.

### 9.1 P0.5 router viability gate — thresholds pre-registered

**Primary (simulation).** From dev data alone, compute the best achievable
hybrid accuracy at every escalation rate given the observed margin ranking
and both tiers' per-query correctness.

> If max achievable hybrid accuracy ≤ lexicon accuracy + seed-noise band
> **at every escalation rate below 50%**, P4 is abandoned.

**Secondary (descriptive).** AUC of lexicon margin as a predictor of
lexicon error. Bands stated a priori and **conventional, not derived**
(0.5 = chance; 0.7 = acceptable discrimination, standard Hosmer–Lemeshow
reading): <0.60 no signal · 0.60–0.70 weak, simulation decides · ≥0.70
consistent with proceeding.

Both are reported whatever the outcome, including if they cancel P4.

### 9.2 P6 model selection rule — pre-registered 2026-08-15, before the sweep

P0.5 showed the router's ceiling is set by the escalation model, not the
gate (AUC 0.983, but the 3B recovers only part of the available headroom).
That makes model choice an experimental variable, which in turn makes it a
researcher degree of freedom unless the selection rule is fixed in advance.

**This rule was written and committed before any model other than the 3B
had been run.** It is not revisable after seeing the sweep.

**Primary metric — net headroom recovery**, computed on **dev**:

```
        (lexicon errors fixed by the model)
      - (lexicon-correct answers the model breaks)
      ----------------------------------------------
        (total lexicon errors)
```

evaluated at the escalation threshold maximising hybrid accuracy under the
50% escalation cap. This normalises against the oracle ceiling, so it
answers "how much of the available correction does this model actually
recover?" rather than "which model has the higher raw accuracy?" — the
latter is dominated by queries the lexicon already handles and where
escalation never occurs.

**Tie-break.** If two models fall within one seed-σ of each other on net
headroom recovery, select the one with lower **median** per-query latency.
RQ3 is explicitly about a fixed local compute budget; at indistinguishable
competence the cheaper model wins.

**Hard eligibility constraint.** A model is eligible only if it runs
**fully GPU-resident**, verified via `ollama ps` reporting 100% GPU. A
partially offloaded model measures the offload rather than the model (§10)
and is excluded regardless of accuracy.

**Frozen across the sweep.** Changing any of these between models would
confound model size with implementation: system prompt, tool descriptions,
temperature (0.1), seeds (0,1,2), the benchmark, the scoring rules, the
margin definition, the escalation policy, and the 50% cap.

**Split discipline.** The sweep runs on **dev**. The test split stays
empty and untouched until P5.

### 9.3 P4 escalation-threshold selection — pre-registered before tuning

τ is the router's only free parameter, so it is the project's largest
remaining researcher degree of freedom. This clause fixes how it is chosen
and is written **before `tune_router.py` was run**.

**Model.** `qwen2.5:3b-instruct`, selected under §9.2. Not revisable at
P4: a router that is retuned across models turns τ and model choice into
one confounded knob.

**Candidate set.** Every distinct observed margin value, plus −1.0
(escalate nothing). Escalation is `margin <= tau`, so ties escalate
together — that is what a deployed threshold actually does, and it means
not every escalation rate is achievable. The 50% cap of §9.1 still binds.

**Objective, evaluated on dev only.** At each τ, mean hybrid accuracy
across seeds 0/1/2, where an escalated query is scored by that seed's LLM
correctness and a kept query by the (deterministic) lexicon.

**Selection rule — one-standard-error, favouring the cheaper operating
point.** Let `A*` be the maximum mean hybrid accuracy over the candidate
set and `σ*` the across-seed standard deviation at that τ.

> Select the τ with the **lowest escalation rate** among all τ whose mean
> hybrid accuracy is ≥ `A* − σ*`. Ties on escalation rate break to the
> lower τ.

Two reasons, both fixed in advance. (i) Picking the argmax of a curve
computed on 108 queries fits τ to seed noise; the 1-SE rule (Breiman et
al. 1984, CART §3.4.3) is the standard remedy and is imported here rather
than invented. (ii) Escalation rate *is* the cost axis RQ3 is defined
over — every escalated query costs an LLM call — so at statistically
indistinguishable accuracy the cheaper threshold wins, exactly as in
§9.2's latency tie-break.

The rule can only move τ **downward** from the argmax, so it can only
reduce the reported hybrid accuracy. It cannot flatter the router.

**Prior exposure, disclosed.** `analyze_sweep.py` already reported the
3B's accuracy *at the argmax* (§9.2's primary metric requires it), so
`A*` was known when this clause was written. The shape of the curve
elsewhere, the σ at the argmax, and every non-argmax operating point were
not. The rule is therefore fixed against a partially observed curve, not
a blind one; it is recorded this way rather than claimed to be blind.

**Reporting.** The **complete** τ curve is published — every candidate
threshold with its escalation rate, mean accuracy, per-seed accuracies,
fixes and breaks — not only the selected point. Threshold selection must
be auditable end to end.

**Freeze.** The selected τ, the margin definition, the model and the
prompt are written to a config file and hashed. Held-out evaluation (P5)
loads that file and runs **once**. τ is never recomputed on test, and no
test result may motivate a change to it — a revised τ makes it a new
experiment reported as such, not a correction.

### 9.4 P5 held-out run procedure — fixed in advance

Written now, while the held-out set does not yet exist, so the procedure
cannot be shaped by the data. Executed exactly once.

1. Verify `backend/app/router_config.json` against
   `results/v3_gates/p4_router_config.sha256`. A mismatch **aborts** the
   run; it means τ moved after P4 and the pre-registration is void.
2. Verify the frozen instrument against `evaluation/FROZEN.sha256`
   (§1.5). Same consequence.
3. Capture the held-out split under the §10/§10.1 conditions used at P6
   — same prompt, schemas, temperature 0.1, seeds 0/1/2, GPU-resident,
   runtime recorded.
4. Score three arms on identical queries: **lexicon**, **LLM-only 3B**,
   **hybrid at the frozen τ**.
5. Report paired statistics: McNemar per pair with Holm correction across
   the family, bootstrap CIs on each delta, effect sizes beside every
   p-value.
6. Report escalation rate and latency, and state whether the realised
   escalation rate matches the dev 10.2%. A large divergence is a
   finding about the benchmark and is reported as one.
7. Report inter-annotator agreement (Cohen's κ) on the held-out gold
   labels before any accuracy number.
8. **Do not retune τ.** Do not add arms, drop arms, or change the
   scoring rule after seeing the result.

A null or negative held-out result is reported as the result (§1.8).

---

## 10. Hardware and run conditions

Measured 2026-08-15. Every latency table states these.

| | |
|---|---|
| CPU | Intel i5-12450HX, 8C/12T |
| RAM | 15.71 GB total |
| GPU | RTX 4050 Laptop, **6141 MiB VRAM** |
| Disk | 474.72 GB, 129.44 GB free |

Models: **qwen2.5 1.5b / 3b / 7b**, all GPU-resident. **14B is excluded**
— at ~9 GB it offloads ~40% to system RAM, and since latency is a primary
metric, a partially-offloaded point measures the offload rather than the
model and would silently corrupt the Pareto curve.

**Hygiene**: interleave conditions rather than running blocks (laptop
thermals); report medians of interleaved runs; log GPU temperature and
clocks; discard warm-ups; report model load time separately; state Ollama
residency on every latency table — CLAUDE.md records that cascade timing
differs 3–4× between resident and non-resident.

### 10.1 Runtime capture is mandatory

Every LLM result file records the **Ollama version**, the model digest,
`num_ctx`, temperature, seeds, and measured GPU residency. A result file
missing any of these is not citable.

This was added after the fact, and the reason is on the record: the v2↔v3
equivalence check (`results/v3_llm/CONDITIONS.md`) failed with the entire
divergence concentrated in *whether the model emitted a tool call at all*
— the signature of a change in the runtime's tool-calling path, not in
the model. v2 had not recorded its Ollama version, so the hypothesis
cannot be tested and the two runs cannot be differenced. The rule exists
so that never recurs; it cannot repair v2.

**Consequence for reporting.** A v2 number and a v3 number are never
subtracted. v2 figures are cited as *what v2 reported under an unrecorded
runtime*, and any comparison of tiers is made **within** v3.

---

## 11. Known limitations of the instrument

Stated here so they are criticised as design, not discovered as defects.

- **The `?` heuristic** for clarifying vs silent abstention will
  misclassify a rhetorical question, and a clarification phrased as a
  statement ("I need the student's USN").
- **Distractor disjointness is checked lexically only.** Semantic overlap
  rests on the argument in `WHY_DISJOINT`.
- **Strict first-call scoring** penalises a model that self-corrects on
  round two. Deliberate, for baseline comparability; `gold_attempted`
  captures the difference.
- **The dev split is contaminated by construction** — the lexicon was
  tuned on it. Every dev number is a tuning aid, never evidence.
- **The scheduling objective can be gamed by emptying a day.** It
  divides by the number of *non-empty* section-days, so a solver that
  leaves a section free on Friday shrinks the denominator and scores
  better without scheduling better. Found at P1 by trying to optimise
  it. The metric is frozen and was **not** patched; the P1 solver
  instead holds every section-day non-empty, which also preserves
  comparability with v2 (all 200 of its section-days are occupied).
- **Nothing in the scheduling objective prices block length.** A fully
  compacted day is four classes back to back; the metric records
  `longest_block_mean` but does not charge for it.
- **One institution, synthetic data, one model family, English only.**
- **Temperature 0.1 with 3 seeds** is a thin sample of decoding
  variability.

---

## 12. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-15 | Protocol frozen at P0. | Initial. |
| 2026-08-15 | Added §9.2, the P6 model selection rule. | P0.5 found the router's ceiling is set by the escalation model, promoting model choice to an experimental variable. Committed **before** any model beyond the 3B was run, so the rule cannot be fitted to the sweep. No existing clause changed. |
| 2026-08-15 | Added §10.1, mandatory runtime capture. | The v2↔v3 equivalence check failed on a shift confined to abstention, and v2 had not recorded its Ollama version, so the cause could not be established. Recording it is now a requirement. Retrospective only in the sense that it cannot repair v2. |
| 2026-08-15 | Added two scheduling limitations to §11. | Found at P1 while optimising the frozen objective: it can be gamed by emptying a section-day, and it does not price block length. Documented, **not** patched — the metric is the instrument and the P1 solver carries an invariant instead. |
| 2026-08-15 | Added §1.5 hashing, `FROZEN.sha256`, §9.4 the P5 run procedure. | P4 is done and P1/P7 now run in parallel with the research path. §1.5 makes silent edits to the instrument a failing test rather than an invisible one; §9.4 fixes the held-out procedure while the held-out set still does not exist, so it cannot be shaped by the data. |
| 2026-08-15 | Added §9.3, the P4 threshold selection rule. | τ is the router's only free parameter and therefore the largest remaining degree of freedom. Committed **before** `tune_router.py` was run. Prior exposure to `A*` via §9.2 is disclosed inside the clause rather than denied. No existing clause changed. |
| 2026-08-19 | P2 executed: Exam+Scholarship merged into one Eligibility agent; Admission/Finance/Placement/Records/Notification reclassified as tool-backed components or a bus subscriber, not agents (docs/RESEARCH_PLAN_V3.md §7). `get_admissions_funnel` retired as a tool (§7.1), 12 tools remain. `evaluation/benchmark/tasks.py` **modified**: the 9 admission_query tasks removed, 108→99 dev tasks — this was the planned, documented consequence, not a metric-definition change. `evaluation/benchmark/toolspace.py` **modified**: `COMPOSITION[30]` moved from (12,17) to (11,18) and `DEPLOYMENT_REFERENCE` renamed `13-real`→`12-real`, because the real non-gold tool pool shrank from 12 to 11; re-verified the gold-tool-always-exposed invariant across all 99×6×3=1782 cells. `evaluation/baselines/lexicon_v2.py` **untouched** — it is a byte-pinned historical snapshot of what v2 measured and stays that way; it still scores `admission_query`, which is why `tests/test_orchestrator.py::test_live_lexicon_matches_the_frozen_baseline` carries one documented exception for it. This invalidates the dev-set-size-dependent P4/P6 numbers computed before this date (89.8%/76.9%/94.8%, τ=0 selection) — they must be recomputed against the 99-task set before being cited again; the pre-P2 numbers remain historically accurate for what was run, and are superseded, not corrected, per §10.1's own precedent. |
| 2026-08-21 | P4 recaptured GPU-resident against the current 99-task/12-tool instrument: `capture_llm.py` ran qwen2.5:3b-instruct alone, 3 seeds, 297 records, 0 call failures, `gpu_residency.fully_resident: true`. `tune_router.py` re-ran §9.3's pre-registered rule against it and reselected τ ≤ 0 (lexicon 88.9%, LLM-alone 83.5%±0.5%, hybrid 94.6%). `backend/app/router_config.json` and `FROZEN.sha256` were rewritten accordingly. | Supersedes, does not correct, the pre-P2 108-task numbers (89.8%/76.9%/94.8%) invalidated by the 2026-08-19 entry above — the instrument changed, not the protocol. No clause changed. |
| 2026-08-25 | P6 completed: 1.5B and 7B recaptured against the current 99-task/12-tool instrument (297 records each, 0 call failures; 1.5B fully GPU-resident, 7B 81.7% and reported out-of-competition per §9.2, same as the pre-P2 sweep). `analyze_sweep.py` now runs against all three captures and reconfirms qwen2.5:3b-instruct (McNemar vs 1.5B, p = 0.003). `evaluation/results/v3_gates/p6_sweep.json` rewritten; F2/F6/F8 now draw from it. | Closes the gap left by the 2026-08-19 entry — only the 3B had been recaptured before this date. No clause changed. |
| 2026-08-21 | `backend/app/router_config.json` re-frozen: `tune_router.py` re-ran §9.3's pre-registered rule against a fresh GPU-resident `qwen2.5:3b-instruct` capture on the post-P2 99-task instrument (297 records, 99/99 task IDs matched, 3 seeds, 0 call failures, `fully_resident: true`). Selected τ≤0 again — same decision rule, same threshold, new evidence. Hybrid vs lexicon on the 99-task set: 94.6% vs 88.9% (+5.7 pts, 95% bootstrap CI +0.3% to +11.8%, McNemar p=0.070) — supersedes, not corrects, the pre-P2 94.8%/89.8%/+4.9-pt numbers invalidated above. `evaluation/results/v3_gates/p6_sweep.json` is **not** re-frozen: it is not in `FROZEN` (it's `analyze_sweep.py` output, not instrument), but it is still the pre-P2 108-task file because 1.5B/7B have not been recaptured GPU-resident yet — a laptop GPU driver dropout (`nvlddmkm` service stopped mid-session, no reboot) blocked that recapture; `evaluation/figures.py`'s new `sweep_fresh()` check blocks F2/F6/F8 rather than drawing from it. |
