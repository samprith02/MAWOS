# 03 — LLM Layer: Requirements, Fallback Ladder, and the R0.5 Provider Probe

Covers R0 requirement **5**.

> **No provider is chosen in this document.** A provider is adopted only after the R0.5
> probe in §4 runs against thresholds pre-registered in §4.3, and the decision is recorded
> in `OPEN_DECISIONS.md` §D1. Naming a default here would be exactly the drift this phase
> exists to prevent.

---

## 1. What the layer must do

The architecture in `01_ARCHITECTURE.md` asks the model to do four things and nothing else:

1. Understand a request in context and resolve its entities.
2. Decide whether information is missing, and if so **ask** rather than guess.
3. Produce an ordered plan of delegations and tool calls.
4. Compose a final answer grounded strictly in `Result.data`.

It is *not* asked to authorise anything, enforce anything, compute anything numeric, or
remember anything durably. Those belong to the guard, the agents, and the store. This
narrowness is deliberate: it is what keeps the boundary in "bounded autonomy" measurable,
and it is what makes a smaller model viable at all.

---

## 2. Capability requirements

### 2.1 Mandatory — a provider failing any of these is disqualified

| Requirement | Why it is mandatory |
|---|---|
| **Native function/tool calling** emitting well-formed arguments against a JSON schema | Without it the whole architecture needs a fragile text-parsing shim, and tool-call validity stops being measurable |
| **Multi-turn tool-result feedback** (a `tool`-role message the model reads) | The observe → re-plan step is impossible without it |
| **Multiple tool calls within one logical turn** (parallel or sequential) | Multi-step tasks are a benchmark category; single-call-per-turn models cannot express them |
| **Context window ≥ 32k tokens** | Tool schemas + conversation history + tool payloads accumulate quickly; a department analytics payload alone is substantial |
| **Stable behaviour at temperature 0** across repeat runs | Seed-variance reporting is meaningless if the model is unstable at its own floor |
| **Instruction adherence: asks rather than guesses** | This is benchmark category 4 and a headline metric — not a nicety |
| **Instruction adherence: declines rather than attempts** | This is benchmark category 5/6 and feeds claim 1 |

### 2.2 Desirable, not disqualifying

| Capability | Why it is not mandatory |
|---|---|
| **Structured / JSON-schema-constrained output** | Convenient for the plan object, but the plan can be captured as an `emit_plan` **tool call** instead. If tool calling is solid, this adds nothing load-bearing |
| **Streaming** | Not required for correctness — required only for perceived quality. Ship without it; add in R6 (`02_SCOPE.md` SHOULD tier) |
| **Long context beyond 32k** | Useful, but the memory bound in `01_ARCHITECTURE.md` §8 exists precisely so the system does not depend on it |
| **Vision, code execution, web access** | Unused by this architecture |

### 2.3 Operational requirements

| Requirement | Target |
|---|---|
| Latency, single-tool turn | p50 ≤ **6 s** — *re-registered 2026-09-01, see §2.3.1* |
| Latency, per LLM call | p50 ≤ **3 s** — *new diagnostic, §2.3.1* |
| Latency, 3-step plan | p50 ≤ **15 s** — *re-registered 2026-09-01* |
| Benchmark affordability | a full run (~70 tasks × 3 seeds × ~6 calls ≈ 1,300 calls) completes within a free tier or a trivial cost cap |
| Failure legibility | rate limits and truncation are **signalled**, not silently degraded — a silently truncated tool call is worse than an error |
| Reproducibility | the same request at temperature 0 yields the same tool selection across runs, or the instability is quantified |

#### 2.3.1 M7 re-registration — dated 2026-09-01, post-hoc, and bounded

**This is a post-hoc threshold change, which this project's protocol normally
forbids** (`PROTOCOL.md` §1 rule 8). It is permitted here only under the four
constraints below, all of which are met and all of which are checkable.

**What was wrong.** §2.3 originally read "p50 < 3 s single-tool turn".
`01_ARCHITECTURE.md` §6 then defined a turn as *select tool → execute →
compose answer*, which is **two LLM calls**, not one. The threshold was
therefore inconsistent with the architecture it gates, and no value of model
quality could satisfy it: 3 s per turn implies ~1.5 s per call.

**What R0.5 measured** (2026-08-31, `r05_findings.md` §4): 21 of 24
single-tool items used 2 LLM calls; tool execution against SQLite is
negligible, so **100% of wall-clock time is LLM time**.

**The re-derivation**, stated in the architecture's own terms:

| Quantity | Budget | Derivation |
|---|---|---|
| Per LLM call | p50 ≤ 3.0 s | the original per-call intuition, now named explicitly |
| Single-tool turn | p50 ≤ **6.0 s** | 2 calls × 3.0 s |
| 3-step plan | p50 ≤ **15.0 s** | ~4–5 calls × 3.0 s |

**The four constraints that make this admissible:**

1. **It cannot rescue anything.** Verified against the completed run: if M7
   were deleted outright, the eligible set is still empty — 1.5B fails 6 other
   mandatory measures, 3B fails 4, 7B fails 3. At the new 6.0 s value all
   three *still* fail M7 (8.12 / 9.40 / 11.22 s). The change alters **no**
   verdict of 2026-08-31.
2. **The completed run is not re-scored.** `r05_provider.{json,md}` stand
   exactly as produced, scored against 3 s.
3. **It applies only to future runs**, which are a **new instrument**. Numbers
   from a future run may never be differenced against the 2026-08-31 numbers.
4. **The motivation is structural, not empirical.** The threshold contradicted
   the architecture's own definition of a turn — a specification defect that
   would have been correct to fix before any provider was run, had it been
   noticed.

**A per-call diagnostic is added** because it is architecture-independent: a
turn's call count is a design choice, but per-call latency is a property of
the model and the hardware. R0.5's per-call p50 was 3.79 s (1.5B), 4.16 s
(3B), 5.36 s (7B) — all above the 3.0 s budget, so this framing does not
flatter the local models either.

### 2.4 Minimum acceptable model capability

**Determined by the probe, not asserted here.** One honest prior, recorded so the probe's
outcome is interpretable rather than surprising:

> This project's own v3 P6 sweep found `qwen2.5:3b-instruct` scoring **83.5%** on tool
> selection against a keyword lexicon's **88.9%** — a 3B model losing to regex on the
> *easiest* of the four tasks the v4 architecture requires. Small models characteristically
> fail the two adherence requirements in §2.1: they guess instead of asking, and attempt
> instead of declining.

The expectation is therefore that the usable floor lands around **7B-class or better**, and
the probe exists to confirm or refute that rather than to assume it. If a smaller model
passes, that is a finding and it is reported.

---

## 3. The fallback ladder

Mandatory in the architecture **regardless of which provider is chosen**.

```
   ┌──────────────┐  unavailable   ┌──────────────┐  unavailable   ┌───────────────────┐
   │  Tier 1      │ ─────────────► │  Tier 2      │ ─────────────► │  Tier 3           │
   │  hosted LLM  │                │  local LLM   │                │  deterministic    │
   └──────────────┘                └──────────────┘                └───────────────────┘
   full planning,                  reduced planning,               no planning:
   clarification,                  same guard, same                resolve to a known
   multi-step                      tools, same gate                action or hand over
                                                                   the UI control
```

### 3.1 Rules

1. **The active tier is always visible.** A banner names it. A degraded answer that looks
   identical to a full one is a defect.
2. **The guard, the tools, and the provenance gate are identical at every tier.** Only
   language understanding degrades. Safety must never be a function of which tier answered.
3. **Tier 3 degrades to a structured action, not to a fake conversation.** This is the
   correction of v3's largest UX defect: there, the lexicon confidently answered questions it
   had not understood. Tier 3's correct behaviours are, in order of preference:
   - resolve the request to one unambiguous known action and execute it (guarded as usual);
   - present the corresponding UI control ("here is the attendance panel");
   - say plainly that the assistant is unavailable and what the user can do instead.

   **Never** a confident natural-language answer produced by pattern matching.
4. **Tier transitions are logged** per turn, so degradation frequency is measurable rather
   than anecdotal.
5. **Tier 2 is optional at deployment, mandatory in evaluation.** The deployed instance may
   run Tier 1 → Tier 3 if no local model is hosted, but the evaluation must be runnable at
   Tier 2 so the claims hold under a locally reproducible configuration (§5).

### 3.2 Cost and rate governance

- Per-session token budget, enforced before the call, not after.
- Response cache keyed on `(role, normalised query, data version)` — a repeated question
  about unchanged data need not re-plan.
- Circuit breaker: N consecutive provider failures drops the tier for a cooldown period.
- Every call logs tokens in/out and latency, so §2.3's affordability target is verified from
  data rather than estimated.

---

## 4. R0.5 — the provider viability probe

This mirrors v3's P0.5 router-viability gate, so the pattern is native to the project's
methodology and reviewable the same way.

### 4.1 Purpose

Choose a provider **empirically**, and record the choice as a dated, reproducible decision
rather than a preference.

### 4.2 The instrument

`evaluation/provider_probe.py`, built in R0.5. A fixed **25-item** probe set, frozen before
any provider runs, drawn from the same domain but **disjoint from the R5 benchmark** — a
provider must not be selected on the data its selection will later be judged against.

Composition:

| Items | Purpose |
|---|---|
| 8 | Unambiguous single-tool requests — baseline competence |
| 5 | Genuinely multi-step requests requiring ≥ 2 chained tools |
| 4 | **Deliberately underspecified** — the correct behaviour is to ask |
| 4 | **Out of scope or not permitted** — the correct behaviour is to decline |
| 4 | Numeric-answer requests — grounding is checkable against tool payloads |

### 4.3 Measures and pre-registered thresholds

**These thresholds are fixed now, before any provider has been run.** A provider is
**eligible** only if it meets every mandatory threshold.

| # | Measure | Threshold | Mandatory? |
|---|---|---|---|
| 1 | Tool-call validity rate (well-formed name + schema-valid args) | ≥ 95% | **yes** |
| 2 | Correct-tool rate on the 8 unambiguous items | ≥ 85% | **yes** |
| 3 | Multi-step rate (chains ≥ 2 tools on the 5 multi-step items) | ≥ 60% | **yes** |
| 4 | Clarification rate on the 4 underspecified items (asks, does not guess) | ≥ 70% | **yes** |
| 5 | Refusal rate on the 4 out-of-scope items (declines, does not attempt) | ≥ 80% | **yes** |
| 6 | Grounding rate on the 4 numeric items (every number traceable to tool output) | ≥ 90% | **yes** |
| 7 | Latency p50, single-tool turn | < 3 s | **yes** |
| 8 | Cost for a projected full benchmark run | within free tier, or < a cap set at R0.5 | **yes** |
| 9 | Hard-failure rate over N = 100 calls (rate limit, malformed JSON, timeout) | < 5% | **yes** |

**Selection rule, also pre-registered:** among eligible providers, choose the one with the
highest **(4 + 5) / 2** — the mean of clarification and refusal rates. Ties are broken by
measure 3, then by latency.

**Rationale for that rule, stated in advance so it cannot be reverse-engineered from
results:** measures 1, 2 and 6 are table stakes that any adequate model clears, and
optimising for them selects for the wrong thing — v3 already demonstrated that a regex beats
a small model on tool selection alone. Measures 4 and 5 are what separate an assistant that
feels intelligent from one that feels like a command interface, and they are the two
behaviours the headline claims depend on.

### 4.4 The shortlist

At least one candidate from each class, so the comparison spans the real trade-off:

| Class | Purpose in the comparison |
|---|---|
| A hosted frontier-tier API | Establishes the capability ceiling |
| A free-tier hosted API | Tests whether deployability is achievable at zero cost |
| The existing local models (`qwen2.5:3b`, `qwen2.5:7b`, already pulled) | Establishes the locally reproducible floor — and whether §2.4's prior holds |

Exact vendors are chosen at R0.5 from what is actually available and affordable at that time.
**None is named here.**

### 4.5 Outputs

- `evaluation/results/v4_gates/r05_provider.json` — raw per-item records, all providers
- `evaluation/results/v4_gates/r05_provider.md` — the table, the eligible set, the selection,
  and any threshold missed
- An entry in `evaluation/PROTOCOL.md` §12 recording the decision and its date
- `OPEN_DECISIONS.md` §D1 moved from open to closed, citing the run

### 4.6 Re-running

Providers change. The probe is re-runnable and cheap (25 items). If a provider is changed
later, the probe re-runs and the decision record gains a dated entry — the selection is never
silently edited.

---

## 5. The local-reproducibility commitment

Your project guide has objected to cloud-API dependence. The abstraction answers that
objection rather than sidestepping it, through one commitment:

> **The research claims are stated under the locally reproducible configuration. The hosted
> configuration is reported as the practical upper bound. The gap between them is itself a
> result** (`07_CONTRIBUTION.md`, claim 2).

Consequences that follow, and that R1–R5 must respect:

1. The full benchmark must be **runnable end to end at Tier 2** on the existing hardware. If
   it is not, that is a bug in the architecture, not an acceptable limitation.
2. No claim may depend on a capability only the hosted tier has.
3. For an ERP holding student records, *"no student data leaves the institution"* is a
   genuine architectural argument. State it as such — not as an apology for avoiding an API.

---

## 6. Consequence: v3's routing results are superseded

Changing the primary model **invalidates P4 and P6 as headline numbers**. τ = 0 was selected
for a 3B model under a 99-task single-tool instrument; a stronger model reverses the sign of
that finding, and the v4 benchmark is a different instrument measuring different behaviour.

Under this repository's own rule (`evaluation/PROTOCOL.md` §10.1, `CLAUDE.md`), that makes
them **superseded, not corrected**:

- v3 results are archived at R1 to `evaluation/results/v3_archive/` with a `SUPERSEDED.md`
  naming the instrument that produced each.
- **No v4 number may be differenced against a v3 number.**
- The v3 routing finding remains citable *as a finding about that instrument* — including
  the honest one that a keyword lexicon beat a 3B model at tool selection, which is part of
  why §2.4 sets the expected floor where it does.

This is a cost of the rework, consciously accepted at R0, not a discovery made later.
