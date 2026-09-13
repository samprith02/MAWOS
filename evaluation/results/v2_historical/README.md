# v2 historical results — as originally reported

**These files are the numbers MAWOS v2 actually published.** They were
produced by `evaluation/evaluate.py` under the v2 code, before the P0
evaluation protocol existed. They are preserved here unmodified.

They are **not** regenerated, and they must never be overwritten by a
regenerated run. The distinction this directory exists to protect:

| Directory | What it is |
|---|---|
| `v2_historical/` | what v2 originally reported, produced by v2's own harness |
| `v2_frozen/` | the same system re-measured under `evaluation/PROTOCOL.md` |

Conflating the two would make it impossible to say later whether a
difference came from the system or from the measuring instrument. Any
future claim about v2 must state which of the two it cites.

## What is only available here

`v2_frozen/` regenerates the deterministic lexicon and the greedy
scheduler. It does **not** yet contain the v2 LLM tier — that needs a live
Ollama run and is scheduled before the final experimental lock.

Until then, these files are the only record of:

- **§1.2** LLM tool-selection tier, `qwen2.5:3b-instruct`: 70.4% overall,
  83.3% standard, 44.4% hard, 4474 ms/query — **single run, no seed
  variance**, which is one of the reasons it is being re-measured.
- **§1.2b** the persona/tool-space condition reporting a 14.8% drop. This
  number is **confounded** — persona and tool space were varied together,
  so it cannot support a causal claim. It is retained as the historical
  record and as the motivation for the 2x2 factorial in
  `docs/RESEARCH_PLAN_V3.md` §3.1, not as evidence.
- §2–§5 attendance verification, cascade latency, the modeled manual
  comparison, and the ML model tables.

## Provenance

Generated 2026-08-03/04 by v2 (`evaluate.py`, `ablation.py`,
`failure_injection.py`, `scalability.py`) at commit `46a0c6e`.
Moved into this directory at P0 (2026-08-15) without edits.
