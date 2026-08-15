# P4 — hybrid router threshold curve (dev)

`qwen2.5:3b-instruct`, selected under PROTOCOL.md §9.2. Threshold selected under §9.3, pre-registered in `49be6dd` before this ran. Dev split, 108 tasks, seeds [0, 1, 2]. Lexicon baseline **89.8%**, 11 errors available.

The complete curve is published, not only the selected point, so the selection is auditable. Rows above the 50% escalation cap (§9.1) are shown but were never candidates.

| τ | escalation | n | hybrid acc | σ | per-seed | fixed | broken | |
|---:|---:|---:|---:|---:|---|---:|---:|---|
| -1.00 | 0.0% | 0 | 89.8% | 0.0% | 89.8% / 89.8% / 89.8% | 0.0 | 0.0 |  |
| 0.00 | 10.2% | 11 | 94.8% | 0.4% | 95.4% / 94.4% / 94.4% | 6.7 | 1.3 | **selected** |
| 0.50 | 12.0% | 13 | 94.8% | 0.4% | 95.4% / 94.4% / 94.4% | 6.7 | 1.3 |  |
| 1.00 | 13.0% | 14 | 93.8% | 0.4% | 94.4% / 93.5% / 93.5% | 6.7 | 2.3 |  |
| 1.50 | 18.5% | 20 | 92.9% | 0.4% | 93.5% / 92.6% / 92.6% | 6.7 | 3.3 |  |
| 2.00 | 28.7% | 31 | 88.9% | 0.8% | 89.8% / 88.0% / 88.9% | 6.7 | 7.7 |  |
| 2.50 | 41.7% | 45 | 86.4% | 2.2% | 88.0% / 83.3% / 88.0% | 6.7 | 10.3 |  |
| 3.00 | 60.2% | 65 | 81.2% | 1.7% | 82.4% / 78.7% / 82.4% | 6.7 | 16.0 | above cap |
| 3.50 | 74.1% | 80 | 80.6% | 1.3% | 81.5% / 78.7% / 81.5% | 6.7 | 16.7 | above cap |
| 4.00 | 76.9% | 83 | 79.0% | 1.6% | 80.6% / 76.9% / 79.6% | 6.7 | 18.3 | above cap |
| 4.50 | 81.5% | 88 | 78.1% | 1.6% | 79.6% / 75.9% / 78.7% | 6.7 | 19.3 | above cap |
| 5.00 | 88.9% | 96 | 78.1% | 1.6% | 79.6% / 75.9% / 78.7% | 6.7 | 19.3 | above cap |
| 5.50 | 94.4% | 102 | 77.2% | 1.6% | 78.7% / 75.0% / 77.8% | 6.7 | 20.3 | above cap |
| 6.00 | 98.1% | 106 | 76.9% | 2.0% | 78.7% / 74.1% / 77.8% | 6.7 | 20.7 | above cap |
| 8.00 | 100.0% | 108 | 76.9% | 2.0% | 78.7% / 74.1% / 77.8% | 6.7 | 20.7 | above cap |

## Selection

- argmax: τ ≤ 0.00, 94.8% at 10.2% escalation, σ = 0.4%
- within one σ: τ ≤ 0.00, τ ≤ 0.50
- **selected: τ ≤ 0.00** — lowest escalation rate among those

## Effect at the selected threshold

- hybrid 94.8% vs lexicon 89.8% = **+4.9%**
- 95% bootstrap CI +0.0% to +10.2% — **includes zero**
- supplementary description only, not a test: 3.8% of resamples show no gain
- McNemar vs lexicon (majority vote): b01=7, b10=1, p = 0.070
- expected cost 348 ms/query vs 3414 ms for LLM-on-everything

**How to state this.** *The confidence-gated hybrid showed a +4.9-point improvement on the development set, motivating held-out evaluation.* Not *"significantly improves"* — the paired McNemar test does not reach conventional significance (p = 0.070) and the bootstrap CI includes zero. The point estimate favours the router and the direction is consistent across all three seeds, but **dev is contaminated by construction** (§11): the lexicon was tuned on these queries. These numbers select τ. They are not the result. The held-out set (P5) is.
