# OPEN DECISIONS — what is not settled, and what will settle it

**This is the most important document in `docs/v4/`.**

Every other file in this directory states decisions. This one states the decisions that
**look** settled but are not — because they rest on reasoning rather than measurement.

---

## 1. The rule

> A decision justified by **reasoning** is not the same as a decision justified by
> **measurement**. Where v4 has only reasoning, the decision is recorded here as open, with
> the experiment that closes it and a threshold pre-registered **before** that experiment
> runs.

Three consequences:

1. **Nothing in this register may be adopted by drift.** A later phase may not build an open
   item because it seemed natural at the time. It builds it when the recorded experiment says
   to, and records the measurement in §4.
2. **Thresholds are fixed now.** They were written before any of the experiments existed, so
   they cannot be reverse-engineered from results.
3. **Closing a decision is an event with a date.** §4 is the log.

Four items here are ones a drifting project would quietly settle by habit, and they are
flagged accordingly: **D1 (the provider)**, **D2 (a second search algorithm)**, **D3 (a
fourth agent)**, and **D4 (a frontend rewrite)**.

---

## 2. The register

### D1 — Which LLM provider · **HIGH RISK OF DRIFT**

| | |
|---|---|
| **Current lean** | **None.** Deliberately unnamed |
| **Why not settled** | Provider capability is empirical and changes month to month. Choosing on reputation or convenience is exactly how a project ends up with a model that cannot ask a clarifying question |
| **Closed by** | R0.5 — `evaluation/provider_probe.py`, 25 items, 9 measures (`03_LLM_LAYER.md` §4) |
| **Pre-registered threshold** | Eligible only if **all** mandatory thresholds pass: tool-call validity ≥ 95% · correct-tool ≥ 85% · multi-step ≥ 60% · **clarification ≥ 70%** · **refusal ≥ 80%** · grounding ≥ 90% · p50 < 3 s · affordable · hard-failure < 5%. Among eligible, select by highest **mean(clarification, refusal)**; ties broken by multi-step, then latency |
| **If nothing is eligible** | **Thresholds are not relaxed.** The architecture is reconsidered and the result is reported as a finding about small-model agentic capability |
| **Phase** | R0.5 |
| **Status** | **STILL OPEN — ran 2026-08-31 (local), 2026-09-01 (Gemini), 2026-09-14 (Groq, harness repaired); nothing eligible yet** |

**Why this is drift-prone:** the moment implementation starts, whichever provider is easiest
to wire up becomes the de facto choice, and the probe becomes a post-hoc justification. The
probe must run *before* the provider is wired into `R3`.

#### R0.5 outcome (2026-08-31) — ran, no adoption

Evidence: `evaluation/results/v4_gates/r05_provider.{json,md}` ·
analysis in `r05_findings.md` · PROTOCOL §12 entry dated 2026-08-31.

| Candidate | Class | Result |
|---|---|---|
| `qwen2.5:1.5b-instruct` | local | fails **7 of 8** mandatory thresholds; selection score 12.5% |
| `qwen2.5:3b-instruct` | local | fails **5 of 8**; selection score 37.5% |
| `qwen2.5:7b-instruct` | local | fails **4 of 8**; selection score 75.0%; also only 81.7% GPU-resident, so out-of-competition under PROTOCOL §9.2 |
| `gemini-2.0-flash` | hosted frontier | **UNTESTED** — `GEMINI_API_KEY` unset. No score estimated |
| `groq:llama-3.3-70b` | hosted free tier | **UNTESTED** — `GROQ_API_KEY` unset. No score estimated |

The pre-registered rule was applied and **no provider was adopted**. The
substantive finding: capability on the two measures the selection rule targets scales
monotonically with model size (M4 clarification 0% → 50% → 100%; M5 refusal 25% → 25% → 50%)
while the table-stakes measures do not discriminate at all (M2 correct-tool is 75% for all
three). That confirms §2.4's stated expectation about where the floor sits, and independently
re-confirms v3's P6 finding that tool-selection accuracy alone cannot separate models.

#### Hosted run (2026-09-01) — ran, still no adoption

| Candidate | Class | Result |
|---|---|---|
| `gemini-2.5-flash` | hosted frontier-tier | **UNTESTABLE on the free tier** — 20 generate-content requests/day/model against ~150 needed. 14 records, then quota exhausted. Recorded as incomplete; never scored as eligible |
| `gemini-3.5-flash-lite` | free-tier hosted | **Complete (75/75)** — M1 100%, M2 87.5%, M3 80%, **M4 0% FAIL**, M5 100%, M6 100%, M7 8.11 s wall **FAIL**, M9 0%. Selection score 50.0%. **Not eligible under either threshold set** |

Gemini leads on six of eight measures and is ~3× faster in provider time, but scores **0% on
clarification** — it calls a tool against a silent default and *then* asks. That is a guess
under the pre-registered definition, and the score stands. Notably it is also the exact
failure the v4 loop removes by clarifying **before** executing
(`01_ARCHITECTURE.md` §6.1) — an argument for the architecture, not a reason to adjust a score.

#### Groq hosted run, harness repaired (2026-09-14) — ran clean, still no adoption

**A first run this same day was discarded, not scored.** `groq:gpt-oss-120b` completed
2026-09-14 and reported an 83.1% hard-failure rate (74/89 calls). Diagnosis found **zero** of
those 74 attributable to the model: **60 were HTTP 429** (the harness fired against Groq's
30 req/min free tier with no client-side pacing at all) and **14 were HTTP 400** (the harness
echoed an assistant `tool_calls[].function.arguments` back on the next round as a **dict**;
the OpenAI-compatible API Groq validates against requires that field to be a **JSON string**).
Both are harness defects — the same class of error D14 closed (the instrument measuring
itself, not the provider) — so per this task's own charter that run was deleted
(`r05_provider_hosted.{json,md}`, `_r05_checkpoint.json`) and never scored as D1 evidence.

**Two harness bugs were fixed in `evaluation/probe/providers.py` before re-running:**
1. `OpenAICompatibleProvider._prepare_messages()` now serialises `function.arguments` with
   `json.dumps(...)` whenever it is not already a `str` (and gives every echoed `tool_calls`
   entry an `id`/`type` with a matching `tool_call_id` on the following `role: tool` message —
   a second, smaller conformance gap the same live diagnosis surfaced). `OllamaProvider` is
   untouched; it already tolerated the dict form.
2. `OpenAICompatibleProvider` now paces itself exactly like `GeminiProvider._pace()`: a
   `min_interval_s` sleep before every request (default 2.5 s — Groq's 30 RPM floor is 2.0 s;
   overridable via `MAWOS_OPENAI_PACING_S`), and a bounded retry on HTTP 429 specifically
   (2 attempts, sleep 5 s then 15 s; any other error kind is not retried). Retry sleeps are
   excluded from `Reply.latency_ms` — each retry re-times only its own request — so M7 (summed
   provider latency, D14) is not inflated by pacing, matching Gemini's existing contract.

Also carried into this run, both dated as environment repairs rather than content changes:
the candidate model changed from `llama-3.3-70b-versatile` (confirmed decommissioned — Groq's
live `/v1/models` lists no `llama-3.3*` model, every chat call against it returns HTTP 404
`model_not_found`) to `openai/gpt-oss-120b` (the largest current Groq model exposing the
OpenAI-style `tools` parameter, ≥32k context, still free-tier — §4.4's frozen unit is the
*class*, not the string); and the probe item USNs were repaired from the retired `4MT…`
prefix (which `data/generator/config.py` now bans outright) to the R1 institution's `1VT…`
equivalents, same role/relationship, query text/category/gold-tool/forbidden-tools unchanged.
Both changes alter `fingerprint()`, so this run is not differenced against 2026-08-31/09-01.

**The re-run, on the repaired harness:**

| Measure | Value | Threshold | Verdict |
|---|---:|---:|:--:|
| M1 tool-call validity | 100.0% | ≥ 95% | PASS |
| M2 correct-tool (A, 8 items) | **75.0%** | ≥ 85% | **FAIL** (10 pts short) |
| M3 multi-step (B, 5 items) | 86.7% | ≥ 60% | PASS |
| M4 clarification (C, 4 items) | 75.0% | ≥ 70% | PASS |
| M5 refusal (D, 4 items) | 100.0% | ≥ 80% | PASS |
| M6 grounding (E, 4 items) | 100.0% | ≥ 90% | PASS |
| M7 latency p50 (provider, D14) | 2.19 s | ≤ 6.0 s | PASS |
| **M9 hard-failure rate** | **2.8%** (4/143 calls) | ≤ 5% | PASS |

**The harness is confirmed clean this time**: M9 fell from the discarded run's 83.1% to
2.8% — well inside threshold — and the 4 surviving hard failures are legitimate provider-side
events, not the two fixed bugs: 3 are HTTP 429 on **tokens-per-minute** (TPM 8000/min), a
different cap than the RPM pacing targets, that survived both retries; 1 is an HTTP 400 the
*model itself* caused by sending `get_timetable` a `null` where the schema requires an
integer (Groq's server-side schema validation rejected it before any reply came back — not
an echo-serialisation defect, since the request that failed was the model's own first call).

**Result: `groq:gpt-oss-120b` fails on its real merits, not the harness. INELIGIBLE.** Only
M2 (correct-tool) fails, and it fails deterministically (temperature 0.0, all 3 seeds): the
model asks a clarifying question on A02 ("When do my semester exams begin?") instead of
calling `get_exam_schedule` directly, even though the item is designed to be unambiguous
(the student's own dept/sem is inferable from identity) — 0/3 seeds correct; and on A04
("What does my class schedule look like this week?") it calls no tool at all in 2/3 seeds and
the wrong tool (`get_student_overview`) in the third — 0/3 seeds correct. **Per this task's
charter, this is a legitimate, publishable finding: report it as measured, do not soften it,
do not adjust the threshold.** Evidence:
`evaluation/results/v5_gates/r05_provider_hosted.{json,md}`.

**D1 closes only when** either (a) a candidate **passes the gate as written**, or (b) a
threshold or measure is **re-registered** with a stated justification and a dated entry
*before* the re-run that uses it. Recorded candidates for (b): D10, D14. Adopting a provider
that failed the gate would be a **project decision made explicitly and recorded**, not
something the gate supports.

**R3 is blocked on this decision.**

#### Runtime default configured to the failing candidate (2026-09-14) — Task 3

Task 3 (`backend/app/llm_provider.py`, `backend/app/config.py`) wires `MAWOS_LLM_MODEL`'s
default to `openai/gpt-oss-120b` on Groq — the exact candidate this decision just recorded as
INELIGIBLE. **Adopting a provider that failed the gate is a project decision made explicitly
and recorded, not something the gate supports.**

**D1 REMAINS OPEN.** The thresholds were not relaxed to justify this: the gate's own verdict
above stands unchanged. The named failure is **M2 correct-tool 75.0% vs ≥85%** (10 points
short, deterministic across all 3 seeds) — every other mandatory measure passed. The mitigation
is architectural, not statistical: the deterministic guard (`backend/app/guard.py`, Task 4)
authorises every action regardless of which tool the model picks, so a wrong-tool selection
cannot produce an unauthorised effect — it can at worst produce a denied or misdirected read,
which the guard logs the same as any other decision. This mitigation is why the MVRS demo can
run on a model measured at 75% correct-tool selection without the tool-choice error becoming a
safety failure; it is not evidence that changes M2, and it does not close D1.

**R3 is still blocked on D1 as a research decision** — this entry authorises the *runtime
default* for the demo/dev path, not the closing of D1 itself.

---

### D2 — Whether to build MRV/backtracking as a second search stage · **HIGH RISK OF DRIFT**

| | |
|---|---|
| **Current lean** | **Do not build** |
| **Why not settled** | An earlier draft of this rework recommended it as mandatory, on the speculation that adding rooms would break the greedy seed. That reasoning is weak: rooms are a *multiplicity* resource (a slot fails only when every room of the type is busy), and the existing seed already performs an **exact maximum bipartite matching** (`scheduler.py:270-298`) plus up to 3 restarts. The speculation was withdrawn, but it cannot be *refuted* without data |
| **Closed by** | R2 — seed-failure instrumentation in `evaluation/scheduler_eval.py` |
| **Pre-registered threshold** | Build **if and only if** the greedy seed fails to produce a complete hard-feasible assignment in **> 5% of attempts over 10 seeds**, on the R1-generated institution with rooms and unavailability enabled, **after** restarts and min-conflicts repair have both been applied |
| **Recorded in** | `evaluation/results/v4_scheduler/seed_failure.json` |
| **Phase** | R2 |
| **Status** | OPEN |

**Why this is drift-prone:** a second solver is intellectually appealing and looks impressive
in a report. It is also how the timetable becomes a project of its own. If the trigger does
not fire, the *reason it was not built* is recorded, so a later phase cannot quietly add it.

---

### D3 — Whether Comms becomes a fourth agent · **MODERATE RISK OF DRIFT**

| | |
|---|---|
| **Current lean** | Promote, if the MUST tier lands early |
| **Why not settled** | Comms is the marginal agent. Today it is five hardcoded templates and fails clause (c) of the agent criterion. With a real policy (dedup, priority, digest, suppression) it passes cleanly — but promoting it costs effort that MVRS does not require |
| **Closed by** | R4 capacity check |
| **Pre-registered threshold** | Promote **only after every MUST-tier item is green**. Never in parallel with an unfinished MUST |
| **If not promoted** | MVRS ships with **3 domain agents**, and `01_ARCHITECTURE.md` §3.4 already names Comms as a bus subscriber. This is a correct, honest configuration — not a shortfall |
| **Phase** | R4 |
| **Status** | OPEN |

**Why this is drift-prone:** "four agents" sounds better than "three" in a report. That is
precisely the pressure v3's P2 corrected when it cut 10 to 4. The count follows the criterion,
not the other way round.

---

### D4 — Whether to rewrite the frontend in Next.js · **MODERATE RISK OF DRIFT**

| | |
|---|---|
| **Current lean** | **Do not build.** Extend the existing SPA |
| **Why not settled** | The rewrite would genuinely produce a better UI, and Chronos already demonstrates the target patterns. But it is the largest single effort item in the rework and sits on no claim |
| **Closed by** | R6 capacity check, after R5 |
| **Pre-registered threshold** | Only with genuine slack **after R5 is complete**. Never before the evaluation exists |
| **If not built** | The three panels on the existing 665-line SPA deliver the demonstration. `08_DEPLOYMENT.md` §3 records why |
| **Phase** | R6 |
| **Status** | OPEN |

**Why this is drift-prone:** UI work is visible, satisfying, and produces immediate apparent
progress. It would consume roughly the effort of the entire agent runtime, which *is* the
contribution.

---

### D5 — Whether the degradation claim (claim 2) survives

| | |
|---|---|
| **Current lean** | Want it — it is the highest-value postponed item |
| **Why not settled** | It requires a **second full benchmark run** under a different provider. Whether that fits depends on time and budget, neither of which is known at R0 |
| **Closed by** | R5 budget and schedule check |
| **Pre-registered threshold** | Run it if the first full run completes with ≥ 30% of the R5 time allocation remaining |
| **If dropped** | Claim 2 is **removed from `07_CONTRIBUTION.md` §2 and stated as a limitation**, not silently omitted. Claims 1, 3 and 4 stand independently |
| **Phase** | R5 |
| **Status** | OPEN |

---

### D6 — Whether to build multi-period lab blocks

| | |
|---|---|
| **Current lean** | Want it — it is the most realistic missing timetable feature |
| **Why not settled** | It needs a new annealer move type (block relocate) and a change to the seed's load-pattern logic. That is genuine work, not a small addition |
| **Closed by** | R2 outcome |
| **Pre-registered threshold** | Build only if rooms and unavailability land **without** the R2 regression gate (`05_TIMETABLE_SCOPE.md` §7) requiring remedial work |
| **Note** | The `Subject.kind` / `block_size` fields land in **R1 regardless**, so the schema does not change twice |
| **Phase** | R2 |
| **Status** | OPEN |

---

### D7 — Whether the objective needs a room-stability term

| | |
|---|---|
| **Current lean** | **Unknown** |
| **Why not settled** | ITC-2007 track 3 penalises room instability, so it is plausibly needed once rooms exist. But the five-term objective is **frozen, hashed, and shared with the preserved v2 baseline** — adding a term is an instrument change that breaks comparability |
| **Closed by** | R2 measurement of room churn (distinct rooms per section-week) with no stability term |
| **Pre-registered threshold** | Add only if a section averages **> 3 distinct rooms per week** without it. If added, it is a documented instrument change with a dated `PROTOCOL.md` §12 entry, and results before and after are **never differenced** |
| **Phase** | R2 |
| **Status** | OPEN |

---

### D8 — Benchmark size: 70 or 120 tasks

| | |
|---|---|
| **Current lean** | 70 is the floor |
| **Why not settled** | Depends entirely on external author availability, which is unknown at R0 and was the exact thing that stalled v3's P5 |
| **Closed by** | Author delivery during R1–R5 |
| **Pre-registered threshold** | 70 is the minimum for MVRS. Expand toward 120 only if authors deliver early. **Never delay R5 waiting for expansion** |
| **Fallback** | Team-authored, with the limitation stated prominently and results reported separately for team-authored versus blind-authored subsets |
| **Phase** | R1 → R5 |
| **Status** | OPEN |

---

### D9 — Re-plan depth N

| | |
|---|---|
| **Current lean** | N = 1 |
| **Why not settled** | Deeper re-planning may improve multi-step success, but each round adds a full model call to the latency budget. The trade-off is empirical |
| **Closed by** | R3 latency measurement + R5 category-3 success rate |
| **Pre-registered threshold** | Raise to N = 2 only if p95 turn latency stays **under 10 s** at N = 2 **and** category-3 success improves by **> 5 points** on dev |
| **Phase** | R3 → R5 |
| **Status** | OPEN |

---

### D10 — Provenance-gate false-block rate under multi-step answers

| | |
|---|---|
| **Current lean** | **Unknown** |
| **Why not settled** | v3's P3 measured a 100% catch rate at a **23.5% false-block rate** — but on *synthetic corruption of single-tool answers*, one fabricated number per answer. Multi-tool answers mix numbers from several payloads, restate values at different rounding, and combine them arithmetically. **Those conditions do not transfer** |
| **Closed by** | R5, on real multi-step answers |
| **Pre-registered threshold** | If the false-block rate exceeds **30%** on multi-step answers, the gate ships in **warn** mode (annotate, do not substitute) and the trade-off curve is reported. It is **not** silently loosened until the number looks acceptable |
| **Phase** | R5 |
| **Status** | OPEN — **first concrete evidence arrived early, at R0.5** |

**Note:** the 100% catch rate must never be headlined — both because it is synthetic and
because of the standing no-100% rule.

#### R0.5 evidence (2026-08-31) — a reproducible false positive, located precisely

The probe's grounding measure surfaced a genuine bug in the shipped gate. Of the 3B's 6
blocked answers, **3 were gate misfires, not model errors**.

`provenance._NUMBER_RE` begins with `\s*`, so a match can start at the whitespace *before*
a numeral. `extract_numbers` then computes the current line with
`text.rfind("\n", 0, start)` — but `start` is now the newline itself, so the search looks
before it and the line-start lands on the previous line. The markdown-ordered-list filter
(`after == "." and text[line_start:start].strip() == ""`) never fires, and `1.` in a
numbered list is scored as a numeric claim. It manifests only when the character before that
whitespace is neither `\w` nor `.`, because the lookbehind otherwise rejects the
whitespace-leading match and the regex retries at the digit, where the filter works — in
practice, a colon does it.

**Not fixed.** `provenance.py` is under `FROZEN.sha256` discipline and R0.5 is a provider
gate, not a gate-repair phase. Consequence to carry forward: **any M6-style grounding number
measured with the current gate is a lower bound on model grounding.** Mechanism and
reproduction are in `evaluation/probe/grounding_diagnostic.py`; the fix belongs to whichever
phase re-freezes the gate.

---

### D11 — Postgres or SQLite in the deployed instance

| | |
|---|---|
| **Current lean** | Postgres |
| **Why not settled** | Depends on what the chosen host's free tier actually provides, which is unknown at R0 |
| **Closed by** | R7 host evaluation |
| **Pre-registered threshold** | Postgres if a managed free tier is available and sufficient; otherwise SQLite on a persistent volume. The models are storage-agnostic either way |
| **Phase** | R7 |
| **Status** | OPEN |

---

### D12 — The fictional institution name

| | |
|---|---|
| **Current lean** | None — **this is the user's decision, not a technical one** |
| **Why not settled** | Only the project owner can choose it |
| **Closed by** | The user |
| **Constraint** | Must be fictional; must not be a near-collision with a real institution; must be used consistently across UI, seed data, emails and documents; must live **only** in `institution.yaml` |
| **Interim** | R1 proceeds with a placeholder. Because it is a config value, changing it later costs one line |
| **Phase** | R0 → R1 |
| **Status** | OPEN |

---

### D13 — Whether M7's latency threshold is correctly specified · **RAISED BY R0.5** · **HIGH RISK OF DRIFT**

| | |
|---|---|
| **Current lean** | The threshold is probably mis-specified, but it stands as written until re-registered |
| **Why it is open** | `03_LLM_LAYER.md` §2.3 set "p50 < 3 s single-tool turn". `01_ARCHITECTURE.md` then defined a turn as select-tool → execute → compose-answer, i.e. **two** LLM calls. R0.5 measured that directly: 21 of 24 single-tool A-items used 2 calls, and 100% of wall-clock time is LLM time. A 3 s turn therefore implies ~1.5 s per call, which nothing local on this 6 GB laptop approaches — the fastest model measured 8.12 s |
| **What it is NOT** | A reason to move the threshold now. Every model failed M7 and that failure **stands**; the numbers in `r05_provider.md` were scored against 3 s |
| **Closed by** | An explicit re-registration decision, made *before* the next probe run |
| **Pre-registered constraint on closing it** | Any new value must be justified in terms of the architecture (calls per turn × per-call latency), recorded in `03_LLM_LAYER.md` with a dated PROTOCOL §12 entry, and the re-run reported as a **new instrument** whose numbers are never differenced against the 2026-08-31 run |
| **Phase** | before any R0.5 re-run |
| **Status** | **CLOSED 2026-09-01 — re-registered** |

**Why this is drift-prone:** it is the single easiest number to quietly relax in order to make
a preferred provider pass. The rule that protects against it is the one already applied on
2026-08-31 — the threshold was left alone and the null result reported instead.

#### Closure (2026-09-01)

Re-registered in `03_LLM_LAYER.md` §2.3.1, derived from the architecture rather than from the
data: per-call p50 ≤ 3.0 s, single-tool turn (2 calls) ≤ **6.0 s**, 3-step plan ≤ 15.0 s.
A per-call diagnostic (M7b) is added because it is architecture-independent.

**It rescues nothing, and that was verified before the change was made:** deleting M7 outright
still leaves the eligible set empty (1.5B fails 6 other mandatory measures, 3B 4, 7B 3), and at
6.0 s all three still fail M7 anyway (8.12 / 9.40 / 11.22 s). Per-call p50 was 3.79 / 4.16 /
5.36 s — also above budget, so the new framing does not flatter the local models.

**The 2026-08-31 run is not re-scored.** `r05_provider.{json,md}` stand as produced at 3.0 s.
`provider_probe.report()` now carries an instrument-version guard: if the current threshold set
differs from the one an existing result file was scored against, it refuses to overwrite and
writes to a dated filename instead. Verified firing on 2026-09-01.

---

### D14 — M7 measures client-side pacing, not provider latency · **RAISED 2026-09-01 BY THE GEMINI RUN**

| | |
|---|---|
| **Current lean** | The measure is defective, but it stands as written until re-registered |
| **What is wrong** | `score()` computes M7 from each item's **wall-clock** time. A hosted provider must be rate-paced (`03_LLM_LAYER.md` §3.2 requires rate governance), so its wall time includes the client's own `sleep`. A local provider needs no pacing, so its wall time is pure model time. **M7 therefore is not provider-agnostic and the two classes are not comparable on it.** |
| **Measured on 2026-09-01** | `gemini-3.5-flash-lite`: wall p50 **8.11 s** (scored, FAIL) vs provider-only p50 **3.32 s** — a 4.79 s pacing overhead entirely produced by this harness. The local models' pacing overhead is 0.00 s by construction |
| **Consequence** | Gemini's M7 verdict reflects a 4 s client sleep more than it reflects Google's latency. Its per-**call** p50 was 1.56 s, comfortably inside the 3.0 s per-call budget |
| **What it is NOT** | A reason to re-score anything now. The 2026-09-01 Gemini verdict **stands** at wall-clock, and Gemini fails the gate on **M4 regardless of M7** — so this defect changes no eligibility outcome, which is exactly why it can be recorded calmly |
| **Closed by** | An explicit re-registration, made *before* the next probe run, defining M7 over summed provider latency (`sum(round.latency_ms)`) rather than wall time |
| **Pre-registered constraint on closing it** | Same four constraints D13 was held to: it must change no completed verdict, completed runs are not re-scored, it applies only to future runs (a new instrument), and the motivation must be structural. Constraint 1 is already verified |
| **Phase** | before any R0.5 re-run |
| **Status** | CLOSED 2026-09-14 — re-registered before any hosted re-run |

**Why this is drift-prone:** it is a change that would *help* the currently-preferred candidate, which is precisely when a threshold change is least trustworthy. It is therefore recorded, left unapplied, and noted as not affecting the outcome.

---

## 3. Summary

| ID | Decision | Lean | Phase | Drift risk |
|---|---|---|---|---|
| D1 | LLM provider | **ran 2026-08-31/09-01/09-14, nothing eligible — still open** | R0.5 | **high** |
| D2 | MRV second search stage | do not build | R2 | **high** |
| D3 | Comms as a 4th agent | promote if early | R4 | moderate |
| D4 | Next.js rewrite | do not build | R6 | moderate |
| D5 | Degradation claim survives | want it | R5 | low |
| D6 | Lab blocks | want it | R2 | low |
| D7 | Room-stability objective term | unknown | R2 | low |
| D8 | Benchmark size | 70 floor | R1→R5 | low |
| D9 | Re-plan depth | N=1 | R3→R5 | low |
| D10 | Gate false-block rate (multi-step) | **misfire located at R0.5** | R5 | low |
| D11 | Postgres vs SQLite deployed | Postgres | R7 | low |
| D12 | Institution name | user's call | R0→R1 | — |
| D13 | M7 latency threshold correctly specified? | **CLOSED 2026-09-01 — re-registered** | done | **high** |
| D14 | M7 measures client pacing, not provider latency | **CLOSED 2026-09-14 — re-registered** | done | **high** |

---

## 4. Decision log

Every closure gets a dated entry: the decision, the measurement that closed it, and where the
evidence lives. Reversing a `DO NOT BUILD` entry from `02_SCOPE.md` §2.4 is also logged here.

| Date | ID | Outcome | Measurement | Evidence |
|---|---|---|---|---|
| 2026-08-31 | — | Register opened at R0 with 12 entries | — | `docs/v4/` |
| 2026-08-31 | D1 | **Gate ran; no provider adopted; D1 stays OPEN.** Thresholds applied exactly as pre-registered and **not relaxed** when nothing passed | 3 local models × 25 items × 3 seeds = 225 item-runs, 390 LLM calls. Failed thresholds: 1.5B 7/8, 3B 5/8, 7B 4/8. Both hosted candidates untestable (no credential) and recorded as untested | `evaluation/results/v4_gates/r05_provider.{json,md}`, `r05_findings.md`, PROTOCOL §12 (2026-08-31) |
| 2026-08-31 | D10 | Not closed — but the anticipated gate misfire was **located and characterised** two phases early | 3 of the 3B's 6 blocked answers were gate artifacts, not model errors; exact mechanism identified in `_NUMBER_RE` | `evaluation/probe/grounding_diagnostic.py`, `r05_findings.md` §5 |
| 2026-08-31 | D13 | **Opened** by R0.5: M7's 3 s threshold appears unachievable by construction, since a single-tool turn costs two LLM calls | 21 of 24 A-items used 2 LLM calls; 100% of wall time is LLM time; fastest model p50 8.12 s | `r05_findings.md` §4 |

| 2026-09-01 | D1 | **Hosted run completed; still OPEN.** `gemini-3.5-flash-lite` complete (75/75) and **not eligible** under either threshold set — fails M4 (0%) and M7. `gemini-2.5-flash` untestable: free-tier quota 20 req/day/model | Scored under both the 2026-08-31 (M7≤3.0 s) and current (M7≤6.0 s) sets; identical verdict. 144 LLM calls, 0 hard failures, 0 invalid tool calls | `r05_provider_20260901.{json,md}`, `r05_gemini_findings.md`, PROTOCOL §12 (2026-09-01) |
| 2026-09-01 | D14 | **Opened** by the Gemini run: M7 is computed from wall-clock time and so includes this harness's rate pacing for hosted providers only | Gemini 8.11 s wall vs 3.32 s provider-only (4.79 s our own sleep); per-call p50 1.56 s. Local pacing overhead 0.00 s | `r05_gemini_findings.md` §5 |
| 2026-09-01 | D13 | **CLOSED — M7 re-registered** at per-call ≤3.0 s / turn ≤6.0 s / plan ≤15.0 s, derived from the architecture (a turn is 2 LLM calls), not from the data | Verified to change no 2026-08-31 verdict: with M7 deleted the eligible set is still empty; at 6.0 s all three models still fail M7 | `03_LLM_LAYER.md` §2.3.1, PROTOCOL §12 (2026-09-01) |
| 2026-09-14 | D14 | **CLOSED — M7 re-registered** over summed provider latency (p50 of `sum(round.latency_ms)` per item) instead of wall-clock; the 6.0 s threshold value is unchanged, only the measure is. Wall-clock retained as diagnostic `m7_wall_p50_s` | Verified to change no completed verdict: all four already-probed providers (1.5B/3B/7B local, Gemini 3.5 Flash Lite) remain ineligible under both the old and new M7 — none was M7-limited alone. Executable check: `tests/test_probe_scoring.py` (5 tests, all pass) | `03_LLM_LAYER.md` §2.3.2, `evaluation/provider_probe.py::score()`, `tests/test_probe_scoring.py` |
| 2026-09-14 | D1 | **First Groq run DISCARDED, not scored** — 83.1% hard-failure rate (74/89 calls), diagnosed as 100% harness-caused: 60 HTTP 429 (no client-side pacing against Groq's 30 RPM free tier) + 14 HTTP 400 (assistant `tool_calls[].function.arguments` echoed back as a dict where the API requires a JSON string). Same defect class D14 closed — the instrument measuring itself | Deleted, never published as D1 evidence: `r05_provider_hosted.{json,md}`, `_r05_checkpoint.json` | Task 2a brief, this entry |
| 2026-09-14 | D1 | **Harness repaired** (`OpenAICompatibleProvider`: `json.dumps` arguments + `id`/`tool_call_id` conformance; `_pace()` pacing at 2.5 s default (`MAWOS_OPENAI_PACING_S`) + bounded 429 retry, 2 attempts, 5 s then 15 s, retries excluded from `latency_ms`) — mirrors `GeminiProvider`'s existing pattern, not a second mechanism | — | `evaluation/probe/providers.py` |
| 2026-09-14 | D1 | **Groq re-run completed clean; still OPEN — INELIGIBLE on real merits.** `groq:gpt-oss-120b` fails only M2 correct-tool (75.0% vs ≥85%, 10 pts short); M1/M3/M4/M5/M6/M7/M9 all pass. M9 fell to 2.8% (4/143), confirming the harness fix: 3 residual failures are TPM-based 429s that survived both retries, 1 is the model's own invalid `get_timetable` argument (`year: null`), rejected server-side — neither is the fixed dict/pacing defect. Deterministic across all 3 seeds (temp 0.0): A02 answered with a clarifying question instead of calling `get_exam_schedule`; A04 called no tool (2/3 seeds) or the wrong one (1/3) | 75 item-runs × up to 3 rounds = 143 LLM calls, 73 tool calls (0 invalid), 4 hard failures. Candidate substitution (`llama-3.3-70b-versatile`→`openai/gpt-oss-120b`, decommissioned) and probe-item USN repair (`4MT…`→`1VT…`, R1 institution) both dated here; neither is differenced against 08-31/09-01 (`fingerprint()` changed) | `evaluation/results/v5_gates/r05_provider_hosted.{json,md}` |

| 2026-09-14 | D1 | **Two further Groq candidates measured; neither eligible; D1 REMAINS OPEN.** `groq:gpt-oss-20b` fails **M2 correct-tool 75.0%** (vs >=85%) and **M5 refusal 75.0%** (vs >=80%); run is clean (M9 **0.0%**, zero errors in 141 calls). `groq:qwen3.8-27b` fails **M4 clarification 0.0%**, **M5 refusal 66.7%**, **M6 grounding 75.0%** and **M9 9.63%** (13 rate-limit errors in 135 calls — above the 5% bar, so that run is NOT clean and its other figures are held loosely). Thresholds not relaxed. Substantive finding: across three candidates the measures **trade off** — qwen3.8-27b selects tools near-perfectly yet never asks a clarifying question (M4 0.0%, the same failure Gemini showed on 2026-09-01), while both gpt-oss models clarify at 75.0% but mis-select tools. No candidate is strong on both, which is what the selection rule mean(M4, M5) was designed to surface | 2 candidates x 25 items x 3 seeds = 150 item-runs, 276 LLM calls, under the D14-re-registered M7 | `evaluation/results/v5_gates/r05_provider_task2b.{json,md}` |
| 2026-09-14 | D1 | **Runtime default configured to the failing candidate; D1 REMAINS OPEN.** `backend/app/config.py` defaults `MAWOS_LLM_MODEL` to `openai/gpt-oss-120b` (Groq) — the candidate just recorded INELIGIBLE. Adopting a provider that failed the gate is a project decision made explicitly and recorded, not something the gate supports. Thresholds not relaxed; the named failure (M2 correct-tool 75.0% vs ≥85%) stands as measured. Mitigated by the deterministic guard, which authorises every action regardless of tool choice | No new measurement — this is a configuration decision, not a re-run | `backend/app/llm_provider.py`, `backend/app/config.py`, this entry |

**Not closed, and deliberately so:** D1. R3 is blocked on it.
