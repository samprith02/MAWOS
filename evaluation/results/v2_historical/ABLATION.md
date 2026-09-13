# Ablation Study

## A. Event bus ablation (20 students x 5 subjects per upload)

| | Full system (event-driven) | No bus (siloed baseline) |
|---|---|---|
| Hall tickets auto-updated | 18 | 0 |
| Scholarship assessments auto-updated | 3 | 0 |
| Students' placement lists auto-updated | 14 | 0 |
| Manual interventions to reach consistency | 0 | 4 (exam cell, scholarship cell, placement cell and notification desk must each refresh manually) |
| Upload call time | 483.9 ms (incl. full cascade) | 81.0 ms (state left stale) |

Counts below the student total reflect no-op suppression: rows whose
eligibility state and reason codes were unchanged by the new day's data are
re-evaluated but not rewritten, so their timestamps do not move.

Interpretation: the event bus converts 4 manual
cross-office refreshes into an automatic cascade costing
~403 ms of extra
processing on the upload path. Without it the system is a conventional
siloed ERP: writes succeed but every downstream eligibility table is stale
until a human intervenes.

## B. Orchestration-layer overhead, deterministic tier (20 reps)

| | Full pipeline (classify -> permission-checked tool -> format -> log) | Raw tool call |
|---|---|---|
| Median latency | 9.63 ms | 1.67 ms |

Interpretation: classification, the role-permission layer, response
formatting and decision logging together cost
7.96 ms per query — negligible against the
latency budget. The LLM-vs-fallback quality comparison is a separate
experiment enabled by installing Ollama and re-running evaluate.py.
