# Runtime fingerprint — P6 sweep

PROTOCOL.md §10.1 requires every LLM result file to carry the Ollama
version, quantisation, context length, temperature, seeds and measured
GPU residency. §10.1 was written **after** the P6 sweep had already run,
because the sweep is what exposed the need for it — see `CONDITIONS.md`.

`capture_llm.py` now records these inline, so future files are compliant
by construction. This sidecar supplies them for the three P6 captures
rather than editing the frozen result files, which are not touched after
they are written.

**These values were read from the live daemon on 2026-08-15, the same day
and the same machine as the sweep, with nothing reinstalled in between.**
That is weaker evidence than an inline capture — it is a re-read, not a
record — and it is labelled as such. It is exactly the weakness §10.1
exists to remove going forward.

| | |
|---|---|
| Ollama version | **0.32.5** |
| Context length | Ollama default, unmodified, identical across all three models |
| Temperature | 0.1 |
| Seeds | 0, 1, 2 |
| Interleaved | yes — models rotate inside the seed loop (§10) |
| Warm-ups | one per (model, seed) block, discarded |

| Model | Family | Parameters | Quantisation | GPU-resident |
|---|---|---|---|---|
| qwen2.5:1.5b-instruct | qwen2 | 1.5B | Q4_K_M | 100% |
| qwen2.5:3b-instruct | qwen2 | 3.1B | Q4_K_M | 100% |
| qwen2.5:7b-instruct | qwen2 | 7.6B | Q4_K_M | **81.7% — ineligible** |

Residency is measured, not re-read: it comes from `/api/ps` during the
run and is stored inside each capture file. See `ELIGIBILITY.md` for the
determination and for why `num_ctx` was **not** reduced to make the 7B
fit.
