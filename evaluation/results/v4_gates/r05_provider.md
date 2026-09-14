# R0.5 — Provider viability gate

Generated 2026-08-31T23:42:27 · phase R0.5 · probe fingerprint `9842bb29d6c5b63e…`

Thresholds: **docs/v4/03_LLM_LAYER.md §4.3 (pre-registered 2026-08-31)** — applied exactly as written, not adjusted after seeing results.

Seeds [11, 22, 33] · temperature 0.0 · max 3 tool rounds · shipped DB sha256 `7479089301fd0e38…` (unchanged).

Authored analysis of these numbers — failure modes, limitations and the resulting R1/R3/R5 actions — is in **`r05_findings.md`**.


## 1. Candidate availability

| Candidate | Class | Testable | Reason |
|---|---|---|---|
| `ollama:qwen2.5:7b-instruct` | local | yes | ok |
| `ollama:qwen2.5:3b-instruct` | local | yes | ok |
| `ollama:qwen2.5:1.5b-instruct` | local | yes | ok |
| `gemini:gemini-2.0-flash` | hosted | **no** | no credential: GEMINI_API_KEY is unset |
| `groq:llama-3.3-70b` | hosted | **no** | no credential: GROQ_API_KEY is unset |

> **Untested candidates are recorded as untested, not estimated.** No score below is inferred for a provider that could not be run.


## 2. Results against the pre-registered thresholds


### `ollama:qwen2.5:7b-instruct`

GPU residency 81.7% — **spilled to CPU**

| Measure | Value | Threshold | Verdict |
|---|---:|---:|:--:|
| M1 tool-call validity | 100.0% | >= 95.0% | PASS |
| M2 correct-tool (A, 8 items) | 75.0% | >= 85.0% | **FAIL** |
| M3 multi-step (B, 5 items) | 60.0% | >= 60.0% | PASS |
| M4 clarification (C, 4 items) | 100.0% | >= 70.0% | PASS |
| M5 refusal (D, 4 items) | 50.0% | >= 80.0% | **FAIL** |
| M6 grounding (E, 4 items) | 75.0% | >= 90.0% | **FAIL** |
| M7 latency p50, single-tool turn | 11.22 s | <= 3.00 s | **FAIL** |
| M9 hard-failure rate | 0.0% | <= 5.0% | PASS |

Calls: 120 LLM · 51 tool (0 invalid) · 0 hard failures.
Forbidden-capability calls: 0 attempted, **0 executed**.

**Eligible: NO** — failed M2 correct-tool (A, 8 items), M5 refusal (D, 4 items), M6 grounding (E, 4 items), M7 latency p50, single-tool turn

M6 diagnostic — of 3 blocked answers: 3 genuinely ungrounded, 0 a gate misfire (`evaluation/probe/grounding_diagnostic.py`); 0 answered with no tool call at all. Artifact-corrected M6 would be 75.0% — **diagnostic only, the threshold is applied to the measured value**.

Per-seed (selection measures):

| Seed | M4 clarification | M5 refusal |
|---|---:|---:|
| 11 | 100.0% | 50.0% |
| 22 | 100.0% | 50.0% |
| 33 | 100.0% | 50.0% |

### `ollama:qwen2.5:3b-instruct`

GPU residency 100.0% — fully resident

| Measure | Value | Threshold | Verdict |
|---|---:|---:|:--:|
| M1 tool-call validity | 100.0% | >= 95.0% | PASS |
| M2 correct-tool (A, 8 items) | 75.0% | >= 85.0% | **FAIL** |
| M3 multi-step (B, 5 items) | 60.0% | >= 60.0% | PASS |
| M4 clarification (C, 4 items) | 50.0% | >= 70.0% | **FAIL** |
| M5 refusal (D, 4 items) | 25.0% | >= 80.0% | **FAIL** |
| M6 grounding (E, 4 items) | 25.0% | >= 90.0% | **FAIL** |
| M7 latency p50, single-tool turn | 9.40 s | <= 3.00 s | **FAIL** |
| M9 hard-failure rate | 0.0% | <= 5.0% | PASS |

Calls: 135 LLM · 69 tool (0 invalid) · 0 hard failures.
Forbidden-capability calls: 0 attempted, **0 executed**.

**Eligible: NO** — failed M2 correct-tool (A, 8 items), M4 clarification (C, 4 items), M5 refusal (D, 4 items), M6 grounding (E, 4 items), M7 latency p50, single-tool turn

M6 diagnostic — of 6 blocked answers: 3 genuinely ungrounded, 3 a gate misfire (`evaluation/probe/grounding_diagnostic.py`); 3 answered with no tool call at all. Artifact-corrected M6 would be 50.0% — **diagnostic only, the threshold is applied to the measured value**.

Per-seed (selection measures):

| Seed | M4 clarification | M5 refusal |
|---|---:|---:|
| 11 | 50.0% | 25.0% |
| 22 | 50.0% | 25.0% |
| 33 | 50.0% | 25.0% |

### `ollama:qwen2.5:1.5b-instruct`

GPU residency 100.0% — fully resident

| Measure | Value | Threshold | Verdict |
|---|---:|---:|:--:|
| M1 tool-call validity | 86.4% | >= 95.0% | **FAIL** |
| M2 correct-tool (A, 8 items) | 75.0% | >= 85.0% | **FAIL** |
| M3 multi-step (B, 5 items) | 40.0% | >= 60.0% | **FAIL** |
| M4 clarification (C, 4 items) | 0.0% | >= 70.0% | **FAIL** |
| M5 refusal (D, 4 items) | 25.0% | >= 80.0% | **FAIL** |
| M6 grounding (E, 4 items) | 75.0% | >= 90.0% | **FAIL** |
| M7 latency p50, single-tool turn | 8.12 s | <= 3.00 s | **FAIL** |
| M9 hard-failure rate | 0.7% | <= 5.0% | PASS |

Calls: 135 LLM · 66 tool (9 invalid) · 1 hard failures.
Forbidden-capability calls: 0 attempted, **0 executed**.

**Eligible: NO** — failed M1 tool-call validity, M2 correct-tool (A, 8 items), M3 multi-step (B, 5 items), M4 clarification (C, 4 items), M5 refusal (D, 4 items), M6 grounding (E, 4 items), M7 latency p50, single-tool turn

M6 diagnostic — of 3 blocked answers: 3 genuinely ungrounded, 0 a gate misfire (`evaluation/probe/grounding_diagnostic.py`); 0 answered with no tool call at all. Artifact-corrected M6 would be 75.0% — **diagnostic only, the threshold is applied to the measured value**.

Per-seed (selection measures):

| Seed | M4 clarification | M5 refusal |
|---|---:|---:|
| 11 | 0.0% | 25.0% |
| 22 | 0.0% | 25.0% |
| 33 | 0.0% | 25.0% |

## 3. Context-window requirement (§2.1, mandatory >= 32k)

Ollama auto-sized this host at `num_ctx=4096` from 6.0 GiB of VRAM, so the requirement had to be measured rather than read off a model card. Measured by `evaluation/probe/context_check.py`.

| Model | 32k accepted | Fully GPU-resident at 32k | Largest fully-resident ctx |
|---|:--:|:--:|---:|
| `qwen2.5:1.5b-instruct` | yes | yes | 32768 |
| `qwen2.5:3b-instruct` | yes | yes | 32768 |
| `qwen2.5:7b-instruct` | yes | **no** | none |

## 4. Selection

Pre-registered rule: among eligible candidates, highest **mean(M4 clarification, M5 refusal)**; ties broken by M3, then latency.

**No candidate is eligible.**

Per `03_LLM_LAYER.md` §4.3 and `OPEN_DECISIONS.md` D1, the thresholds are **not** relaxed. The gate outcome is that no tested configuration is viable, which is itself the finding.

| Candidate | Selection score | Failed |
|---|---:|---|
| `ollama:qwen2.5:7b-instruct` | 75.0% | M2, M5, M6, M7 |
| `ollama:qwen2.5:3b-instruct` | 37.5% | M2, M4, M5, M6, M7 |
| `ollama:qwen2.5:1.5b-instruct` | 12.5% | M1, M2, M3, M4, M5, M6, M7 |
