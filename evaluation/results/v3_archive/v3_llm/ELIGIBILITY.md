# P6 model eligibility determination

**Determined 2026-08-15, before any accuracy data existed.**

This record exists to establish that eligibility was decided on
**hardware and protocol grounds only**, never on outcomes. It was written
while the sweep was still running and no per-model accuracy had been
observed. Eligibility that is settled after seeing results is not
eligibility, it is selection.

The governing rule is `evaluation/PROTOCOL.md` §9.2, committed in
`1afd766` before any model beyond the 3B had been run:

> A model is eligible only if it runs **fully GPU-resident**, verified via
> `ollama ps` reporting 100% GPU. A partially offloaded model measures the
> offload rather than the model (§10) and is excluded regardless of
> accuracy.

## Measurements

Hardware: RTX 4050 Laptop, 6141 MiB VRAM. Context length 4096 for every
model — Ollama's default, unmodified, identical across conditions.

| Model | Total | In VRAM | GPU % | Verdict |
|---|---|---|---|---|
| qwen2.5:1.5b-instruct | 1.2 GB | 1.2 GB | **100%** | eligible |
| qwen2.5:3b-instruct | 2.16 GB | 2.16 GB | **100%** | eligible |
| qwen2.5:7b-instruct | 5.12 GB | 4.19 GB | **81.7%** | **INELIGIBLE** |

The 7B's Q4 weights fit in 6141 MiB; weights **plus KV cache** do not.
0.93 GB spills to system RAM.

## Consequences

**1.5B and 3B are the primary experiment.** Both satisfy the fixed local
compute budget that RQ3 is defined over.

**7B is an out-of-competition diagnostic.** It is measured and reported,
but excluded from:

- the §9.2 model selection,
- every Pareto / accuracy-latency analysis,
- every primary hypothesis test,
- every paired significance comparison against an eligible model.

The exclusion is not merely "extra latency". Offloading changes the
computational regime — GPU→GPU for the eligible models, GPU→CPU RAM→GPU
for the 7B — so a 7B latency figure is **not on the same axis** as an
eligible one and must never be plotted with them.

What the 7B *can* answer, and will be reported as answering: *does
increasing model size look promising if the deployment constraint is
violated?* Accuracy is unaffected by offload, so its accuracy figures are
valid; only its latency is non-comparable.

## Two things deliberately not done

**`num_ctx` was not reduced for the 7B.** Shrinking its context to make it
fit would have produced 1.5B@4096 / 3B@4096 / 7B@2048, confounding model
size with context capacity. §9.2 freezes conditions across the sweep for
exactly this reason.

**§9.2 was not relaxed.** The rule was written before the measurement and
is not revisable because a model we wanted turned out not to fit.

## Finding

This is a measured result, not a design decision:

> A nominally 7B Q4 model **cannot remain GPU-resident** on a 6141 MiB
> laptop GPU at context 4096.

The practical ceiling for this experiment lies between 3B and 7B. That
retroactively confirms the plan's rejection of 14B (§6) on stronger
grounds than estimation — if the 7B already spills, the 14B was never
viable.
