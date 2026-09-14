# 07 — Research Contribution and Claims

Covers R0 requirement **9**.

---

## 1. The contribution, in one paragraph

> MAWOS contributes an end-to-end architecture and a measurement instrument for **bounded LLM
> autonomy over a real institutional system**: the model plans and delegates across
> autonomous agents, but every action passes a deterministic policy guard, every write
> requires human confirmation, every numeric claim is mechanically checked against the tool
> output that produced it, and the entire chain is traced. **No individual mechanism is
> novel** — permission enforcement, numeric provenance checking, and constraint-based
> timetabling are all prior art, and this project implements and cites them rather than
> claiming them. The contribution is the **composition plus the instrument**: a task
> benchmark that separates *attempted* from *executed* unauthorised actions, and that
> quantifies how much task capability the same architecture retains as the underlying model
> degrades from a hosted API to a locally runnable one.

**Why this is the right claim for this system.** It is measurable from the implementation, it
*requires* the multi-agent architecture to exist rather than merely to be described, and the
domain is not decorative — permissions genuinely matter in a university, where a student
reading another student's fee record is a real harm rather than a contrived one.

---

## 2. Claims we will defend

### Claim 1 — Guard placement, not model choice, determines safety

**Statement.** In this architecture, unauthorised actions execute at rate zero by
construction, while the rate at which the model *attempts* them is non-trivial and varies by
model. Safety is therefore a property of where the boundary is enforced, not of which model
sits inside it.

**Evidence required:** the ~20-item adversarial suite plus category-5 benchmark items,
reporting **attempt rate** and **executed rate** as two separate numbers
(`06_BENCHMARK.md` §5).

**Produced by:** `evaluation/` adversarial run · `GuardDecision` records · the trace.

**Honest framing.** The executed rate is expected to be 0, and a 0 is not a headline — it is a
tautology of the design, and this project's rules forbid headlining a perfect figure. The
**headline is the attempt rate**: *"the model attempted an unauthorised action in X% of
adversarial items; the guard executed none of them."* That sentence is informative, is not
100%, and makes the architectural point precisely.

**Falsified if:** any unauthorised action executes (a critical defect that blocks R5), or if
the attempt rate is ~0 across all tested models — in which case the guard is not doing
observable work and the claim reduces to a design note.

---

### Claim 2 — Quantified capability degradation across model tiers

**Statement.** The same architecture, the same benchmark, run under a hosted model and a
locally runnable one, quantifies the task capability an institution gives up by refusing to
send student data to a third party.

**Evidence required:** the full benchmark run at Tier 1 and Tier 2, per-category, 3 seeds,
mean ± std.

**Produced by:** `evaluation/` benchmark run × 2 providers.

**Why it matters here.** Your project guide objected to cloud-API dependence. This turns that
objection into a measured result rather than a constraint to be argued around, and the answer
is directly useful to any institution facing the same decision. It is also the reason
`03_LLM_LAYER.md` §5 commits to stating the primary claims under the local configuration.

**Status:** **SHOULD-tier.** It needs a second full run. If time or budget does not allow it,
this claim is **dropped and the limitation is stated** — see `OPEN_DECISIONS.md` §D5. It is
the highest-value item in the postponed set for exactly this reason.

**Falsified if:** the gap falls inside seed variance — which would itself be a useful result,
since it would say a local model suffices for this class of work.

---

### Claim 3 — Numeric grounding under multi-step answers

**Statement.** A deterministic extract-and-match provenance gate reduces ungrounded numeric
claims in multi-step, multi-tool answers at a measurable and acceptable false-block cost.

**Evidence required:** ungrounded-claim rate with the gate on and off; false-block rate on
answers that were in fact correct; per-turn gate latency.

**Produced by:** `backend/app/provenance.py` (exists) + the R5 benchmark run.

**What is new versus v3.** v3's P3 measured this on **synthetic corruption of single-tool
answers** — one real number per answer replaced by a fabricated one — reaching a 100% catch
rate at a 23.5% false-block rate. Those conditions do not transfer. Multi-tool answers mix
numbers from several payloads, restate values with different rounding, and combine them
arithmetically; the false-block rate under those conditions is genuinely unknown
(`OPEN_DECISIONS.md` §D10).

**Honest framing.** The catch rate on synthetic corruption is 100% and **must not be
headlined**. The interesting and reportable quantity is the false-block rate on real
multi-step answers, and the trade-off curve between them.

**Falsified if:** the false-block rate makes the assistant unusable, or claims routinely
escape by paraphrase (e.g. "about four-fifths" for 82%) — a known scope limit of a numeric
matcher that must be stated rather than discovered.

---

### Claim 4 — Verified explanation in constrained scheduling

**Statement.** The system can answer *why* a timetable is the way it is, and the answer is
**verified by re-solving** rather than generated as plausible text.

**Evidence required:** for N sampled counterfactual claims ("moving X to Tue-P3 costs +8
objective"), apply the move, rescore against the frozen metric, and report the
**explanation-verification rate**.

**Produced by:** the counterfactual endpoint (`05_TIMETABLE_SCOPE.md` §3.2 item 5) + a
verification harness in `evaluation/`.

**Why it is defensible.** The claim is not that the solver is novel — it is not, and
`RESEARCH_PLAN_V3.md` §0.3 already retracted that. The claim is that the *explanation* is
computed by the same cost function that produced the schedule, using primitives that already
exist (`Schedule.apply` returns an exact delta; `Schedule.undo` reverses it), so it is correct
by construction rather than by persuasion. LLM-generated explanations of optimiser output are
common and usually unverifiable; this one is checkable, and the check is the contribution.

**Falsified if:** verification rates are high only because the counterfactuals are trivial.
Mitigated by sampling counterfactuals across a spread of objective deltas, including moves the
solver rejected.

---

## 3. Claims we will NOT make

Each entry names the prior art that occupies the space, so the write-up positions rather than
overreaches.

| We will not claim | Occupied by | What we say instead |
|---|---|---|
| A novel timetabling algorithm | SA-with-penalisation (*J. Scheduling*, 2022); ITC-2007 track 3 defines curriculum compactness as a standard soft constraint | We implement a standard method and report a measured before/after against a preserved baseline, with the distance to the instance floor stated |
| A novel numeric-grounding mechanism | Proof-Carrying Numbers (arXiv 2509.06902); VeriFin; EG-VAR | We implement a PCN-style gate and cite it. Our contribution is measuring it under multi-step conditions |
| A novel permission model | OrgAccess (arXiv 2505.19165) on whether models *reason* about permissions; Progent on *enforcing* policy on tool calls | We enforce with a conventional guard and measure the attempt/execute split end to end |
| That more agents is better | — | The agent count follows from a stated criterion (`01_ARCHITECTURE.md` §3.1) and is four, not ten. Components failing the criterion are named as failing it |
| Any general claim about LLM agents | — | One institution, one domain, one language, ~70 tasks. Claims are about this system on this benchmark |
| That the system is secure | — | The adversarial suite tests *anticipated* attacks authored by the implementers. It is not a security evaluation |
| Intent-classification accuracy as a headline | — | It measured tool selection, which is not what v4 does. v3's finding stays citable *for its own instrument* |
| That the LLM improves over the deterministic tier at everything | — | v3 measured a keyword lexicon **beating** a 3B model at tool selection (88.9% vs 83.5%). That result stands, is reported, and is part of why the provider floor is set where it is |
| An ML contribution | — | **There is no ML model in v4.** The two v3 models were trained on labels our own rules generated. Deterministic rules where the domain is deterministic, constrained search where the problem is combinatorial, an LLM only for language and planning — that is a design position, stated as one |

---

## 4. Supporting results (reported, not claimed as contributions)

| Result | Where it comes from |
|---|---|
| Event-driven propagation latency and fault isolation across a multi-hop cascade | `bus.py` audit records, already instrumented |
| Timetable improvement over the frozen v2 baseline | `evaluation/scheduler_eval.py`, 10 seeds, existing |
| Cost-model agreement with the official ITC-2007 validator on 1,900 pairs | `evaluation/itc2007/crosscheck.py`, existing |
| Provider selection under pre-registered thresholds | `evaluation/provider_probe.py` (R0.5) |
| Replay recovery after a failed subscriber | SHOULD-tier (bus outbox) |

---

## 5. The honest ceiling

v3's plan included a section with this name, and keeping it is part of the project's culture.

**What v4 realistically is:** one solid applied-systems result (claim 1), one genuinely useful
practitioner-facing measurement (claim 2), two competent engineering results with honest
evaluation (claims 3 and 4), built on an architecture that is defensible rather than
fashionable. That is a strong B.E. final-year project and a plausible workshop-tier paper.

**What it is not:** a novel mechanism. Every component has prior art, and §3 says so
explicitly.

**What would raise the ceiling** — and is deliberately out of scope: multiple institutions,
multiple domains, a real deployment with real users, or a formal treatment of the guard's
completeness. Each is a separate project.

**The rule that keeps this honest**, carried forward verbatim from `CLAUDE.md`:

> Never headline a 100% figure. Report results in the direction the data points. Cite which
> instrument produced each number. Never present a number that `evaluation/` cannot
> regenerate. A null result is a result.
