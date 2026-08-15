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

> **To be completed after the sweep. Not yet filled in.**

| | v2 historical | v3 fresh (3 seeds) |
|---|---|---|
| Selection accuracy | 70.4% | _pending_ |
| Standard tier | 83.3% | _pending_ |
| Colloquial tier | 44.4% | _pending_ |
| Answered with no tool call | 23 | _pending_ |
| Call failures | 0 | _pending_ |
