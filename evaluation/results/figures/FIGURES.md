# P7 figures

Regenerate all of them with **one command**:

```bash
python evaluation/figures.py          # every figure that has data
python evaluation/figures.py F6 F7    # just these
python evaluation/figures.py --pdf    # vector copies as well
```

Generated 2026-08-25T21:42:31. Do not hand-edit: this file is overwritten on every run.

A figure is listed as blocked when the experiment behind it has not been run. No illustrative or placeholder version of a blocked figure exists anywhere in this repository, and none should be made: every number that reaches a slide has to be regenerable from `evaluation/`.

| Figure | File | Status | Regenerated from |
|---|---|---|---|
| **F1** | `F1_cascade_dag.png` | drawn | `backend/app/bus.py`<br>`backend/app/agents/*.py` |
| **F2** | `F2_routing_accuracy.png` | drawn | `evaluation/results/v3_gates/p6_sweep.json`<br>`evaluation/results/v2_frozen/baseline.json`<br>`evaluation/results/v3_llm/qwen2-5_3b-instruct.json` |
| **F3** | `F3_confusion.png` | drawn | `evaluation/baselines/lexicon_v2.py`<br>`evaluation/benchmark/tasks.py`<br>`evaluation/results/v3_llm/qwen2-5_3b-instruct.json` |
| **F4** | - | **blocked** | - |
| **F5** | - | **blocked** | - |
| **F6** | `F6_pareto.png` | drawn | `evaluation/results/v3_gates/p4_router.json`<br>`evaluation/results/v3_gates/p6_sweep.json`<br>`evaluation/results/v2_frozen/baseline.json` |
| **F7** | `F7_scheduler.png` | drawn | `evaluation/results/v3_scheduler/e4.json`<br>`evaluation/results/v2_frozen/baseline.json` |
| **F8** | `F8_latency_cdf.png` | drawn | `evaluation/results/v3_llm/*.json`<br>`evaluation/results/v2_frozen/baseline.json`<br>`evaluation/results/v3_gates/p6_sweep.json` |
| **F9** | - | **blocked** | - |

## What each drawn figure says

* **F1** - 7/9 agents in cascades, 9 edges, 5 sink topics, depth 2
* **F2** - lexicon 89.8%; best eligible hybrid 94.6%
* **F3** - lexicon 11/99 misrouted; LLM abstained 20, off-registry 0 (3 seeds)
* **F6** - tau=0: 94.6% at 416 ms vs LLM-only 83.5% at 3740 ms
* **F7** - P1 204.2 vs v2 2441, floor 196.0; trace for seed 0 only
* **F8** - 88.9% of queries answered in 0.09 ms; escalated tail median 3865 ms

## What the blocked figures are waiting for

* **F4** - RQ1 is a 2x2 (tool space x persona) and only cells A and D have ever been run - A here in v3, D in v2, and those two runs failed the equivalence check, so they cannot even be differenced. Cells B (full tool space, role-matched persona) and C (role-scoped, single admin persona) are the experiment. P2 is done (the 4-agent conditions exist), but E2 is specified on the held-out split (plan 5), so this still Needs P5 for the data. Plan 3.1.
* **F5** - The PCN-style provenance gate does not exist yet. E3 measures its false-block rate and latency cost against the gate switched off; with no gate there is no on/off to plot. Needs P3. Plan 3.2.
* **F9** - The dose-response sweep over tool-space size (5/9/13/20/30, composition frozen in benchmark/toolspace.py) has not been run. The harness exists, P2 is done and the distractors are frozen; the capture is the missing piece, and E5 is specified on the held-out split (plan 5), so this Needs P5 as well as a capture run. Plan 3.4.

## Reading rules that travel with these figures

1. Every accuracy number here is a **development-set** result (F1 is structural and F7 is a scheduling instance). tau was fitted on the same dev tasks the lexicon was tuned on. F6's hybrid gain motivates held-out evaluation; it does not establish generalisation. P5 decides.
2. The **LLM tier loses** the routing comparison. F2 and F6 are drawn to show that, not to hide it.
3. **v2 and v3 LLM numbers are never differenced.** The two runs failed an equivalence check (PROTOCOL 10.1). The only v2 quantity reused here is the frozen lexicon and greedy scheduler, which are the same instrument in both runs.
4. The **7B is out of competition** (measured GPU residency below 100%). It is hatched in F2, dashed in F8, and absent from F6's frontier.
5. F7's zero idle gaps are **construction, not search** - the greedy seed is gap-free before annealing starts. The figure's real quantity is the distance to the instance floor.
