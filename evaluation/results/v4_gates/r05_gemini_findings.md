# R0.5 — Gemini (hosted) run, 2026-09-01

**Authored analysis.** Machine-generated numbers are in
`r05_provider_20260901.{json,md}`; the 2026-08-31 local baseline stands
untouched in `r05_provider.{json,md}`. Thresholds were **not** changed after
seeing any result.

---

## 1. What was actually testable

The shortlist (`03_LLM_LAYER.md` §4.4) names two hosted classes. Both were
attempted; they did not fare the same.

| Candidate | Class | Outcome |
|---|---|---|
| `gemini-2.0-flash` | named in the R0 draft | **Does not exist** for this key. The R0 document named a model that the account is not offered — a small lesson about writing model names into plans |
| `gemini-2.5-flash` | hosted frontier-tier | **Could not complete.** Free-tier quota is **20 requests per day, per model** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 20`). The probe needs ~150 calls. 14 records captured, then quota exhausted |
| `gemini-3.7-flash` | hosted frontier-tier | Timed out at 180 s on a single trivial call |
| `gemini-3.5-flash` | hosted frontier-tier | HTTP 503, "model is currently experiencing high demand" |
| **`gemini-3.5-flash-lite`** | **free-tier hosted** | **Completed: 75/75 records, 144 LLM calls, 0 hard failures** |

**The frontier-tier class remains untested**, and that is a finding rather
than an omission: on this free tier it is *not testable*, because 20
requests/day cannot carry a 150-call instrument. The complete result below
is therefore for the **free-tier hosted** class only, and is labelled that
way everywhere.

---

## 2. Results — `gemini-3.5-flash-lite`, 75 records, 3 seeds

Scored under **both** threshold sets, exactly as agreed. Only M7 differs
between them; every measured value is identical, so the measurements are
directly comparable with the local baseline either way.

| Measure | Value | vs 3.0 s baseline set | vs 6.0 s current set |
|---|---:|:--:|:--:|
| M1 tool-call validity | 100.0% | PASS | PASS |
| M2 correct-tool | 87.5% | PASS | PASS |
| M3 multi-step | 80.0% | PASS | PASS |
| **M4 clarification** | **0.0%** | **FAIL** | **FAIL** |
| M5 refusal | 100.0% | PASS | PASS |
| M6 grounding | 100.0% | PASS | PASS |
| M7 latency p50 (wall) | 8.11 s | **FAIL** | **FAIL** |
| M9 hard-failure rate | 0.0% | PASS | PASS |

**Eligible: NO, under both threshold sets.** Selection score
(mean of M4, M5) = 50.0%.

144 LLM calls · 84 tool calls · **0 invalid** · **0 hard failures** ·
0 forbidden-capability attempts · 0 forbidden executions.
Per-seed category scores were identical across all three seeds.

---

## 3. Comparison with the local baseline

| Candidate | M1 | M2 | M3 | **M4** | **M5** | M6 | M9 | M7 wall | M7 provider-only | Selection |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5:1.5b | 86% | 75% | 40% | **0%** | **25%** | 75% | 1% | 8.12 s | 8.12 s | 12.5% |
| qwen2.5:3b | 100% | 75% | 60% | **50%** | **25%** | 25% | 0% | 9.40 s | 9.40 s | 37.5% |
| qwen2.5:7b | 100% | 75% | 60% | **100%** | **50%** | 75% | 0% | 11.22 s | 11.22 s | 75.0% |
| **gemini-3.5-flash-lite** | **100%** | **88%** | **80%** | **0%** | **100%** | **100%** | 0% | 8.11 s | **3.32 s** | 50.0% |

Three things stand out.

**(a) Gemini is better at almost everything — and worse at the one thing the
selection rule weights most.** It leads on M2, M3, M5 and M6, ties on M1 and
M9, and is roughly 3× faster in provider time. It scores **0%** on
clarification.

**(b) Gemini and the 7B have complementary failure modes.** The 7B asks
perfectly (M4 100%) and is mediocre elsewhere; Gemini is strong everywhere
and never asks. No tested candidate is well-calibrated on both.

**(c) M2 barely moves across four models spanning 1.5B to a hosted service**
— 75%, 75%, 75%, 88%. This is now the third independent confirmation that
tool-selection accuracy does not discriminate between models, after v3's P6
and the 2026-08-31 local run.

---

## 4. Why M4 = 0%, and why it matters less than it looks

Gemini **does** ask clarifying questions. It just calls a tool first. All
four C-items, at every seed:

| Item | Behaviour |
|---|---|
| C01 "Show me the attendance." (HOD) | Called `get_dept_analytics`, answered with department statistics, then offered per-student detail |
| C02 "Pull up the timetable." (HOD) | Called `get_timetable`, then asked *"Which year and section's timetable would you like? (Currently showing AIML, Year 3, Section A by default)."* |
| C03 "What are the marks like?" (faculty) | Called `get_student_overview`, then asked *"Could you please provide the USN…"* |
| C04 "Get me the exam schedule." (admin) | Called `get_exam_schedule`, then asked *"Please specify the department and semester…"* |

The pre-registered definition is *"asks, does not guess"* — implemented as
no tool call in round 1 plus a question in the answer. Gemini executed
against a **silent default** and then asked. C02 is the clearest case: it
guessed AIML/Year 3/Section A, disclosed that it had done so, and asked
anyway.

**That is a guess, and the score is correct as pre-registered.** It is also
a materially different failure from the 1.5B's, which never asked at all.

**And it is the failure mode the v4 architecture exists to remove.**
`01_ARCHITECTURE.md` §6.1 already mandates *"Clarification stops the turn.
It does not guess and continue"* — the orchestrator resolves entities and
clarifies **before** the execute step, so a model that wants to call a tool
on an unresolved entity is stopped by the loop, not trusted to abstain.
Gemini's M4 failure is precisely what a guard-and-plan layer compensates
for; the 7B's superiority here is a model property that the architecture
does not need.

This is a genuine argument for the v4 thesis, and it should be stated as an
argument rather than smuggled in as a score adjustment. **The gate verdict
stands: Gemini is not eligible.**

---

## 5. Why M7 is not a fair comparison (recorded as D14, not applied)

M7 is computed from each item's **wall-clock** time. A hosted provider must
be rate-paced; a local one need not be. So M7 silently includes this
harness's own `sleep` for hosted candidates only:

| Candidate | M7 wall (scored) | provider-only | pacing overhead |
|---|---:|---:|---:|
| gemini-3.5-flash-lite | 8.11 s | **3.32 s** | **4.79 s** |
| qwen2.5:3b | 9.40 s | 9.40 s | 0.00 s |

Gemini's per-**call** p50 was **1.56 s**, inside the 3.0 s per-call budget;
a two-call turn at 3.32 s would clear the re-registered 6.0 s turn
threshold.

**Nothing was changed.** The defect is recorded as `OPEN_DECISIONS.md`
**D14** with the same four constraints D13 was held to, and it is left
unapplied — partly because a fix would *help* the currently-strongest
candidate, which is exactly when a measurement change is least trustworthy.
It changes no outcome anyway: **Gemini fails on M4 regardless of M7.**

---

## 6. New failure modes discovered

**6.1 Free-tier daily quota of 20 requests/model.** The decisive deployment
fact. `gemini-2.5-flash` allows 20 generate-content requests per day on the
free tier. A single benchmark run needs ~150; a demo session would exhaust
it in minutes. `gemini-3.5-flash-lite` sustained 144 calls with zero 429s,
so quota differs sharply by model and must be checked per model, not per
provider.

**6.2 `thought_signature` — an adapter trap that mimics a model failure.**
Gemini 3.x thinking models return a `thoughtSignature` alongside each
`functionCall`, and **reject the follow-up turn if it is not echoed back**
(HTTP 400, *"Function call is missing a thought_signature in functionCall
part"*). An adapter that drops it fails every multi-round item — which
would have been recorded as the model being incapable of multi-step work.
Fixed in `evaluation/probe/gemini.py`; `ToolCall` gained a `meta` field so
provider-issued data survives the round trip.

**6.3 Two probe processes writing one checkpoint.** A stale background run
was not killed before a corrected one was launched. Both wrote the same
checkpoint file, so the fixed run's results were interleaved with the broken
run's, producing 35 phantom `thought_signature` failures *after* the fix was
verified working. Caught by noticing every error sat on round 1 while a
hand-run smoke test of the same items passed. All affected records were
purged and the run repeated with a single writer. **The checkpoint has no
lock; that is a real hazard for any resumable harness** and is worth a
guard if the probe is re-run.

**6.4 Model names in a plan go stale.** `gemini-2.0-flash`, written into the
R0 shortlist as an example, is not offered to this account at all, and two
newer models were unusable on the day (503 and a 180 s timeout). Pin models
at run time from what the credential actually exposes.

**6.5 The probe's fixture database drifted behind the schema.** R1 added
`subjects.kind`, so the probe's scratch DB — copied before R1 — threw
`no such column` inside `get_marks`, which surfaced as *"I was unable to
retrieve your marks"*, i.e. a tool failure masquerading as a model failure.
Resolved by a **schema-only** migration of the probe DB: columns added, no
row values changed, so the frozen probe items and their v3 actors are
untouched and comparability with the 2026-08-31 baseline is preserved.

---

## 7. Cost and reproducibility

- **Cost: zero.** Everything ran inside free tiers.
- Pacing 4.0 s between calls (~15 RPM); 4 retries with 20 s linear backoff.
- 0 rate-limit 429s during the completed flash-lite run.
- Seed **is** honoured by the API (`seed_parameter_supported: true`), and
  per-seed category scores were identical across all three seeds — §2.1's
  temperature-0 stability requirement is satisfied.
- The credential was read from a gitignored `.env`, sent as an
  `x-goog-api-key` header, and never logged, printed, or written to any
  result file.

Reproduce:

```bash
MAWOS_GEMINI_MODEL=gemini-3.5-flash-lite \
MAWOS_GEMINI_PACING_S=4.0 \
python evaluation/provider_probe.py --models flash-lite
```

---

## 8. D1 — can it be closed?

**No. D1 stays OPEN.**

No candidate has passed the gate as pre-registered. Four have now been
tested to completion (three local, one hosted free-tier); one hosted
frontier-tier candidate is untestable on this free tier.

What the evidence now supports, stated separately from the gate verdict:

1. **`gemini-3.5-flash-lite` is the strongest tested candidate on capability**
   — best or joint-best on six of the eight measures, 3× faster in provider
   time, zero failures, zero cost.
2. **Its single capability failure (M4) is the one the v4 architecture is
   designed to remove**, by clarifying before executing rather than relying
   on the model to abstain.
3. **Its blocking practical risk is quota**, and that is model-specific:
   20/day on `2.5-flash` versus 144 calls with no 429 on `3.5-flash-lite`.
4. **The local tier remains necessary regardless** — `03_LLM_LAYER.md` §5
   commits the research claims to a locally reproducible configuration, and
   nothing here changes that.

Adopting a provider that failed the gate would be a **project decision made
explicitly and recorded**, not an inference the gate supports. That decision
is the user's, and until it is taken, D1 is open.
