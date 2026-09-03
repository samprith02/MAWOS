# P4 — hybrid router threshold curve (dev)

`qwen2.5:3b-instruct`, selected under PROTOCOL.md §9.2. Threshold selected under §9.3, pre-registered in `49be6dd` before this ran. Dev split, 99 tasks, seeds [0, 1, 2]. Lexicon baseline **88.9%**, 11 errors available.

The complete curve is published, not only the selected point, so the selection is auditable. Rows above the 50% escalation cap (§9.1) are shown but were never candidates.

| τ | escalation | n | hybrid acc | σ | per-seed | fixed | broken | |
|---:|---:|---:|---:|---:|---|---:|---:|---|
| -1.00 | 0.0% | 0 | 88.9% | 0.0% | 88.9% / 88.9% / 88.9% | 0.0 | 0.0 |  |
| 0.00 | 11.1% | 11 | 94.6% | 0.5% | 93.9% / 94.9% / 94.9% | 7.0 | 1.3 | **selected** |
| 0.50 | 13.1% | 13 | 94.6% | 0.5% | 93.9% / 94.9% / 94.9% | 7.0 | 1.3 |  |
| 1.00 | 14.1% | 14 | 93.6% | 0.5% | 92.9% / 93.9% / 93.9% | 7.0 | 2.3 |  |
| 1.50 | 19.2% | 19 | 93.6% | 0.5% | 92.9% / 93.9% / 93.9% | 7.0 | 2.3 |  |
| 2.00 | 28.3% | 28 | 91.2% | 0.5% | 90.9% / 91.9% / 90.9% | 7.0 | 4.7 |  |
| 2.50 | 40.4% | 40 | 89.9% | 0.0% | 89.9% / 89.9% / 89.9% | 7.0 | 6.0 |  |
| 3.00 | 58.6% | 58 | 86.5% | 0.5% | 86.9% / 85.9% / 86.9% | 7.0 | 9.3 | above cap |
| 3.50 | 71.7% | 71 | 86.5% | 0.5% | 86.9% / 85.9% / 86.9% | 7.0 | 9.3 | above cap |
| 4.00 | 74.7% | 74 | 85.5% | 0.5% | 85.9% / 84.8% / 85.9% | 7.0 | 10.3 | above cap |
| 4.50 | 79.8% | 79 | 84.5% | 0.5% | 84.8% / 83.8% / 84.8% | 7.0 | 11.3 | above cap |
| 5.00 | 87.9% | 87 | 84.5% | 0.5% | 84.8% / 83.8% / 84.8% | 7.0 | 11.3 | above cap |
| 5.50 | 93.9% | 93 | 83.5% | 0.5% | 83.8% / 82.8% / 83.8% | 7.0 | 12.3 | above cap |
| 6.00 | 98.0% | 97 | 83.5% | 0.5% | 83.8% / 82.8% / 83.8% | 7.0 | 12.3 | above cap |
| 8.00 | 100.0% | 99 | 83.5% | 0.5% | 83.8% / 82.8% / 83.8% | 7.0 | 12.3 | above cap |

## Selection

- argmax: τ ≤ 0.00, 94.6% at 11.1% escalation, σ = 0.5%
- within one σ: τ ≤ 0.00, τ ≤ 0.50
- **selected: τ ≤ 0.00** — lowest escalation rate among those

## Effect at the selected threshold

- hybrid 94.6% vs lexicon 88.9% = **+5.7%**
- 95% bootstrap CI +0.3% to +11.8% — **excludes zero**
- supplementary description only, not a test: 3.1% of resamples show no gain
- McNemar vs lexicon (majority vote): b01=7, b10=1, p = 0.070
- expected cost 416 ms/query vs 3740 ms for LLM-on-everything

**How to state this.** *The confidence-gated hybrid showed a +5.7-point improvement on the development set, motivating held-out evaluation.* Not *"significantly improves"* — the paired McNemar test does not reach conventional significance (p = 0.070) even though the bootstrap CI excludes zero. The point estimate favours the router and the direction is consistent across all three seeds, but **dev is contaminated by construction** (§11): the lexicon was tuned on these queries. These numbers select τ. They are not the result. The held-out set (P5) is.
