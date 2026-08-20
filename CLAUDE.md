# MAWOS — working notes for Claude

B.E. final-year research prototype (Dept. of AI&ML, MITE, Group 12).
Framing: **event-driven multi-agent workflow orchestration engine for
universities**. The contribution is the orchestration engine, not the agent
count. **4 core agents** as of P2 (2026-08-19) — Orchestrator, Attendance,
Eligibility, Scheduling; `backend/app/agents.CORE_AGENTS` is the queryable
source of truth. Academic/Admission/Finance/Placement/Notification are
still real, still in the registry, still called by tools.py and the REST
routes — just not counted as agents (§7 of `docs/RESEARCH_PLAN_V3.md`).

## Status (updated 2026-08-19 — keep this current every session)

| Phase | What | State |
|---|---|---|
| P0 | Freeze v2 baseline, RQ1 instrumentation, protocol | done |
| P0.5 | Router viability gate | done |
| P1 | Objective-driven scheduler (greedy seed + SA) | done |
| P1b | ITC-2007 external benchmark harness | harness validated (1,900 cases vs official validator); **blocked on instance files**, see `evaluation/itc2007/INSTANCES.md` |
| P2 | Agent reduction 10→4, tool surface held 13→12 | **code + frozen instrument done** (commit `9ed24c8`, 2026-08-19); **recapture blocked** — see below |
| P3 | PCN-style provenance gate | **pending** — not started |
| P4 | Confidence-gated hybrid router, τ frozen on dev | **stale** — pre-P2 numbers (89.8%/76.9%/94.8%, τ=0) described a 108-task, 13-tool instrument that no longer exists; do not cite them as current |
| P5 | Held-out set → dual annotation → single test run | **blocked on external authors — the largest schedule risk** |
| P6 | Model sweep, 1.5B/3B/7B × 3 seeds | **stale** — same reason as P4; needs a fresh GPU-resident sweep against the 99-task set |
| P7 | Figures F1–F9 | harness done; F2/F3/F6/F8 depend on the stale P4/P6 data and will read old numbers until recaptured; F1/F7 unaffected |
| P8 | Rewrite ARCHITECTURE.md / RESULTS.md to match the evidence | pending — README.md was brought current 2026-08-19; those two still carry v2-era numbers by design until P8 |

**P2 recapture is blocked on GPU access, not on anything in the repo.**
Ollama in this environment sees CPU only (`nvidia-smi` fails with
"insufficient permissions"; Ollama's own log drops the discrete GPU and
falls back to `cpu`) — a sandboxing restriction, not a laptop problem
(PROTOCOL.md's hardware section measured this same RTX 4050 on
2026-08-15). `evaluation/tune_router.py` hard-exits on a non-GPU-resident
capture by design (PROTOCOL §9.2) — that gate is correct and must not be
weakened to force a number out of it. The real fix is running
`capture_llm.py` + `tune_router.py` + `analyze_sweep.py` + `figures.py`
from an environment with real GPU access; nothing else about P2 is
blocked.

A CPU-only diagnostic 3B capture ran anyway (2026-08-20, 99 tasks, 3
seeds) for a sanity read — `evaluation/results/v3_llm/
qwen2-5_3b-instruct.json`, `gpu_residency.fully_resident: false`, **do not
cite as a P4/P6 result**: selection accuracy 81.5% ± 1.0% (seeds 82.8% /
80.8% / 80.8%), abstention 11.1%, latency not comparable to any GPU
number. **This run ended with an ABORT its own integrity check raised**:
`mawos.db`'s hash changed mid-run because `ablation.py` and
`failure_injection.py` were run concurrently with it (both write to that
DB; `capture_llm.py` doesn't, but checks the file anyway as a tripwire
against the harness itself ever executing a tool). `one_call()` never
calls `toolreg.execute`, so the recorded selections are not touched by
those unrelated writes — verified: 297 records, 99 unique task IDs
matching `DEV_TASKS` exactly, 0 call failures. The data is very likely
clean; the process that produced it wasn't, and that's disclosed rather
than quietly reconciled. A real GPU-resident recapture must be run
without anything else touching `mawos.db` at the same time.

Next unstarted phase in work order: **P3**, or the GPU-resident recapture
above once available. P2's code is done; don't restart that work.

## Run it

```bash
%LOCALAPPDATA%\Ollama\ollama.exe serve     # FIRST — portable install, not a service
python run.py                              # -> http://localhost:8000
```

`llm.py` caches the Ollama availability check at startup, so the header badge
only flips to `AI · hybrid router` if Ollama was already serving when MAWOS
booted. Without it the system still works — the lexicon answers everything,
including the low-margin queries it would normally escalate, and the badge
says `AI · lexicon only`.

**Routing is v3 now.** `backend/app/router.py` gates on the lexicon's own
confidence (margin ≤ τ, τ = 0 frozen in `router_config.json`), not on whether
Ollama is reachable. ~90% of queries never touch the LLM by design, so the
lexicon is the *primary* tier — do not call it a "fallback" in code, UI or
docs. Config is hashed; hand-editing τ makes it a different experiment
(PROTOCOL §9.3).

Logins: `4MT23AI049`/`student123`, `aiml.f02`/`faculty123`, `hod.aiml`/
`faculty123`, `principal`/`principal123`, `admin`/`admin123`.

## Rules that matter here

- **Never headline a 100% figure.** Anywhere. This project was rebuilt
  specifically because v1 looked too clean to be real.
- **Report results in the direction the data points.** The LLM tier *loses*
  the routing comparison. Under v3's controlled conditions that is **76.9%
  vs 89.8%, −12.9 points** (3 seeds, `results/v3_llm/`). v2's −19.4 is
  superseded, **not corrected** — the two runs failed an equivalence check
  and must never be differenced (`v3_llm/CONDITIONS.md`, PROTOCOL §10.1).
  Do not re-frame the loss as a win, and do not delete the losing
  configuration from the report.
- **Cite v2 and v3 numbers separately.** README.md was brought current to
  v3 on 2026-08-19; `docs/ARCHITECTURE.md` and `evaluation/results/
  v2_historical/RESULTS.md` still carry v2-era numbers on purpose — P8
  rewrites those. Until then, say which run a number came from.
- **Never present a number you cannot regenerate** from `evaluation/`.
- Label attendance accuracy as *deterministic verification*, never "AI
  accuracy"; label the manual-workflow comparison as a *modeled estimate*.
- Design decisions in the docs are deliberate viva defences. Don't casually
  change them — if something looks wrong, say so rather than silently
  "fixing" it.

## Gotchas that have cost real time

- **Stop the server before deleting `mawos.db`.** A running server holds the
  file, so `Remove-Item -ErrorAction SilentlyContinue` fails *silently* and
  leaves a contaminated DB. Reseed helper: `scratchpad/reseed.py`.
- **Don't run `evaluate.py` while the server is up** — both write the same
  SQLite file.
- **Shipped DB state is deliberate**: 400 submitted applications, 0 verified,
  so the admissions pipeline can be demoed live. Don't consume it by running
  verify/merit/allot against the shipped DB.
- **Cascade latency is not comparable across runs** with and without Ollama
  resident: ~127 ms idle vs ~466 ms with a 2 GB model loaded. The cascade path
  never calls the LLM; it is pure resource contention. State the condition.
- **Installing Ollama on this laptop**: `winget install Ollama.Ollama` hangs
  after downloading (blocks on a UAC prompt that can't appear in a
  non-interactive shell), and its temp file is preallocated to full size so it
  looks complete while still downloading — a mid-flight copy matches the
  remote byte-for-byte but fails `Get-AuthenticodeSignature` with
  `HashMismatch`. Use the portable zip instead; verify the signature.

## Evaluation

```bash
python -m pytest tests -q                 # 44 tests
python evaluation/gate_p05.py             # P0.5 router viability gate
python evaluation/capture_llm.py          # frozen-protocol LLM capture (live Ollama)
python evaluation/analyze_sweep.py        # P6 model selection, PROTOCOL 9.2
python evaluation/tune_router.py          # P4 threshold selection, PROTOCOL 9.3
python evaluation/scheduler_eval.py       # E4: P1 solver vs frozen v2 greedy
python evaluation/freeze_manifest.py      # verify the frozen instrument (PROTOCOL 1.5)
python evaluation/evaluate.py             # v2 harness: both routing tiers
python evaluation/evaluate.py --no-llm    # skip the 108 live LLM calls
python evaluation/ablation.py             # is the architecture load-bearing?
python evaluation/failure_injection.py    # fault isolation + replay
python evaluation/scalability.py          # constant workload vs institution size
python evaluation/figures.py              # P7: every figure, one command
python evaluation/itc2007/build.py        # fetch+build the official ITC validator
python evaluation/itc2007/crosscheck.py   # P1b: our CB-CTT cost model vs that validator
python evaluation/itc2007/run_e4b.py      # E4b (needs instances -- see INSTANCES.md)
```

`evaluate.py::_verdict` derives §1.3's conclusion from the *sign* of the
measured deltas, so the report cannot claim the LLM helps when it doesn't.
Keep it that way.

## Known weak points (say these before an examiner does)

- The 108-query routing benchmark and the keyword lexicon it scores were
  written by the same project, so the lexicon is tuned to these phrasings.
  It is evidence about this classifier on this benchmark, not a general
  claim. A held-out set written outside the team is the fix.
- The model sweep is **done** (P6: 1.5B/3B/7B × 3 seeds) and the 3B was
  selected under a pre-registered rule. It is still one family, one
  temperature, three seeds. The 7B **could not stay GPU-resident** on this
  6 GB laptop (81.7%) and is reported out-of-competition — its accuracy is
  valid, its latency is not comparable, and it must never share a Pareto
  frontier with an eligible model.
- **τ = 0 was selected on dev, and dev is contaminated by construction** —
  the lexicon was tuned on those 108 queries. The +4.9-point hybrid gain has
  a CI whose lower bound sits on zero and McNemar p = 0.070. It is not a
  result yet; the held-out set (P5) decides.
- Data is synthetic (UCI-calibrated, copula, 3% label noise), the bus is
  in-process and at-most-once, and replay recovery is manual.
