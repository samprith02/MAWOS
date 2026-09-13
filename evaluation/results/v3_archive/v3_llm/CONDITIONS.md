# Inference-condition equivalence: v2 historical vs v3 frozen capture

P0.5's realised curve was computed from v2's historical 3B run. The fresh
capture replaces it. That substitution is only legitimate if both runs
were produced under the same inference conditions, so this compares them.

**Part 1 below was written before any fresh accuracy data existed.** Part 2
is the empirical confirmation, completed after the sweep.

## Part 1 — static comparison (outcome-blind)

v2: `evaluation/evaluate.py::eval_intent_routing_llm(role_mode="matched")`
v3: `evaluation/capture_llm.py::one_call`

| Condition | v2 | v3 | Same? |
|---|---|---|---|
| Persona per query | `ROLE_FOR_INTENT`, default student | `task.asker_role`, generated **from** `ROLE_FOR_INTENT` | yes |
| Tool schemas | `toolreg.schemas_for_role(user.role)` | identical call | yes |
| System prompt | `SYSTEM_PROMPT.format(role, name, detail)` | identical, imported not restated | yes |
| `detail` field | USN, else dept | identical | yes |
| Message structure | system + user, one exchange | identical | yes |
| Scoring | first tool selected, strict | identical | yes |
| Temperature | 0.1 | 0.1 | yes |
| Warm-up | one call outside the timed loop | one discarded call per (model, seed) block | yes, v3 stricter |
| **Seed** | **not set** — Ollama chooses | **0, 1, 2 explicit** | **no** |
| Request timeout | `OLLAMA_TIMEOUT_S * 4` = 32 s | `* 8` = 64 s | no |
| Runs | 1 | 3 | no |

**The three differences, and why none invalidates the substitution:**

*Seed.* v2 set none, so its single run sampled an arbitrary seed. v3 fixes
0/1/2 for reproducibility. At temperature 0.1 decoding is near-greedy, so
the sampling distributions are close — but this is precisely why v2's
single run cannot carry a variance claim and v3's three seeds can. The
change is the point of re-measuring, not a confound.

*Timeout.* Only binds if a call would otherwise time out. v2 reported
**0 call failures**, so no v2 call approached 32 s and the longer v3
timeout cannot alter any result. It exists to protect the 7B, which is
slower under offload.

*Run count.* One versus three. This is the provenance gap being closed.

## Part 2 — empirical confirmation

The check: the fresh 3B mean selection accuracy against v2's historical
**70.4%** (single run, `qwen2.5:3b-instruct`, role-matched).

If the fresh mean sits within seed variance of 70.4%, the conditions are
confirmed equivalent and the fresh per-query vector may replace the
reconstruction in P0.5. A large divergence means something changed that
Part 1 did not capture, and must be explained before any result is
interpreted.

**Result: equivalence is NOT confirmed.** The divergence is large, and it
is concentrated in one tier and one behaviour.

| | v2 historical | v3 fresh (3 seeds) | Δ |
|---|---|---|---|
| Selection accuracy | 70.4% | **76.9% ± 2.0%** | +6.5 |
| Standard tier | 83.3% | **83.8%** (84.7/81.9/84.7) | +0.5 |
| **Colloquial tier** | **44.4%** | **62.9%** (66.7/58.3/63.9) | **+18.5** |
| **Answered with no tool call** | **23** | **10** (9/12/9) | **−13** |
| Call failures | 0 | 0 | — |

The standard tier reproduces almost exactly (83.3% → 83.8%, inside seed
variance). **The entire divergence is the colloquial tier**, and its
mechanism is visible in the last row: the fresh model **abstains less than
half as often**. Thirteen queries that v2's run answered with no tool call
now produce a tool call, and most of them produce the right one.

### What changed

Part 1 confirms the prompt, schemas, persona mapping, message structure,
scoring and temperature are identical. That leaves:

1. **Ollama version.** v2 ran 11 days earlier on an unrecorded version;
   this run is pinned at **0.32.5**. Ollama's tool-calling path — chat
   template handling and constrained decoding for tool emission — changes
   between releases and directly governs *whether a model emits a tool
   call at all*. A shift concentrated entirely in abstention is exactly the
   signature of a tool-emission change, not a reasoning change.
2. **Explicit seeds.** Implausible as a cause: a seed cannot produce a
   systematic 13-query shift in one direction while leaving the standard
   tier untouched.

**This cannot be resolved retroactively** — v2 did not record its Ollama
version. That is now a protocol requirement (§10) rather than an
assumption.

### Consequences

- **The fresh capture is the valid measurement.** Three seeds, known
  runtime, recorded residency, zero failures.
- **v2's 70.4% is not comparable to it** and must not be differenced
  against v3 numbers. It stays in `v2_historical/` as what v2 reported,
  which is precisely why the two directories are kept apart.
- **P0.5's realised curve understated the router.** It used the historical
  per-query vector and reported +1.9% at best. Recomputed on fresh 3B
  data, the hybrid reaches **94.8% against the lexicon's 89.8%, +5.0**.
  The P0.5 *decision* (proceed) is unchanged; its *effect size* was
  pessimistic because the runtime beneath it had moved.
- **v2's headline conclusion survives, with a smaller margin.** The LLM
  tier still loses to the lexicon on routing — 76.9% vs 89.8% — so the
  direction the project reports is intact. But the gap narrows from
  −19.4 to −12.9 points, and part of v2's reported deficit was runtime,
  not model.
