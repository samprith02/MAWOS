# R0.5 — Provider viability gate

Generated 2026-09-14T07:36:21 · phase R0.5 · probe fingerprint `7b2888d1f813014b…`

Thresholds: **docs/v4/03_LLM_LAYER.md §4.3 (pre-registered 2026-08-31); M7 re-registered 2026-09-01 per §2.3.1 — a future run using it is a NEW INSTRUMENT and may not be differenced against the 2026-08-31 results** — applied exactly as written, not adjusted after seeing results.

Seeds [11, 22, 33] · temperature 0.0 · max 3 tool rounds · shipped DB sha256 `133c5a1163587cb4…` (unchanged).

Authored analysis of these numbers — failure modes, limitations and the resulting R1/R3/R5 actions — is in **`r05_findings.md`**.


## 1. Candidate availability

| Candidate | Class | Testable | Reason |
|---|---|---|---|
| `groq:qwen3.8-27b` | hosted | yes | ok |
| `groq:gpt-oss-20b` | hosted | yes | ok |

## 2. Results against the pre-registered thresholds


### `groq:qwen3.8-27b`

| Measure | Value | Threshold | Verdict |
|---|---:|---:|:--:|
| M1 tool-call validity | 100.0% | >= 95.0% | PASS |
| M2 correct-tool (A, 8 items) | 100.0% | >= 85.0% | PASS |
| M3 multi-step (B, 5 items) | 73.3% | >= 60.0% | PASS |
| M4 clarification (C, 4 items) | 0.0% | >= 70.0% | **FAIL** |
| M5 refusal (D, 4 items) | 66.7% | >= 80.0% | **FAIL** |
| M6 grounding (E, 4 items) | 75.0% | >= 90.0% | **FAIL** |
| M7 latency p50, single-tool turn | 2.91 s | <= 6.00 s | PASS |
| M9 hard-failure rate | 9.6% | <= 5.0% | **FAIL** |

Calls: 135 LLM · 74 tool (0 invalid) · 13 hard failures.
Forbidden-capability calls: 0 attempted, **0 executed**.

**Eligible: NO** — failed M4 clarification (C, 4 items), M5 refusal (D, 4 items), M6 grounding (E, 4 items), M9 hard-failure rate

M6 diagnostic — of 0 blocked answers: 0 genuinely ungrounded, 0 a gate misfire (`evaluation/probe/grounding_diagnostic.py`); 3 answered with no tool call at all. Artifact-corrected M6 would be 75.0% — **diagnostic only, the threshold is applied to the measured value**.

Per-seed (selection measures):

| Seed | M4 clarification | M5 refusal |
|---|---:|---:|
| 11 | 0.0% | 100.0% |
| 22 | 0.0% | 100.0% |
| 33 | 0.0% | 0.0% |

### `groq:gpt-oss-20b`

| Measure | Value | Threshold | Verdict |
|---|---:|---:|:--:|
| M1 tool-call validity | 100.0% | >= 95.0% | PASS |
| M2 correct-tool (A, 8 items) | 75.0% | >= 85.0% | **FAIL** |
| M3 multi-step (B, 5 items) | 80.0% | >= 60.0% | PASS |
| M4 clarification (C, 4 items) | 75.0% | >= 70.0% | PASS |
| M5 refusal (D, 4 items) | 75.0% | >= 80.0% | **FAIL** |
| M6 grounding (E, 4 items) | 100.0% | >= 90.0% | PASS |
| M7 latency p50, single-tool turn | 3.05 s | <= 6.00 s | PASS |
| M9 hard-failure rate | 0.0% | <= 5.0% | PASS |

Calls: 138 LLM · 66 tool (0 invalid) · 0 hard failures.
Forbidden-capability calls: 0 attempted, **0 executed**.

**Eligible: NO** — failed M2 correct-tool (A, 8 items), M5 refusal (D, 4 items)

M6 diagnostic — of 0 blocked answers: 0 genuinely ungrounded, 0 a gate misfire (`evaluation/probe/grounding_diagnostic.py`); 0 answered with no tool call at all. Artifact-corrected M6 would be 100.0% — **diagnostic only, the threshold is applied to the measured value**.

Per-seed (selection measures):

| Seed | M4 clarification | M5 refusal |
|---|---:|---:|
| 11 | 75.0% | 75.0% |
| 22 | 75.0% | 75.0% |
| 33 | 75.0% | 75.0% |

## 4. Selection

Pre-registered rule: among eligible candidates, highest **mean(M4 clarification, M5 refusal)**; ties broken by M3, then latency.

**No candidate is eligible.**

Per `03_LLM_LAYER.md` §4.3 and `OPEN_DECISIONS.md` D1, the thresholds are **not** relaxed. The gate outcome is that no tested configuration is viable, which is itself the finding.

| Candidate | Selection score | Failed |
|---|---:|---|
| `groq:gpt-oss-20b` | 75.0% | M2, M5 |
| `groq:qwen3.8-27b` | 33.3% | M4, M5, M6, M9 |
