# MAWOS — working notes for Claude

B.E. final-year research prototype (Dept. of AI&ML, MITE, Group 12).
Framing: **event-driven multi-agent workflow orchestration engine for
universities**. The contribution is the orchestration engine, not the agent
count. **4 core agents** as of P2 (2026-08-19) — Orchestrator, Attendance,
Eligibility, Scheduling; `backend/app/agents.CORE_AGENTS` is the queryable
source of truth. Academic/Admission/Finance/Placement/Notification are
still real, still in the registry, still called by tools.py and the REST
routes — just not counted as agents (§7 of `docs/RESEARCH_PLAN_V3.md`).

## Status (updated 2026-08-21 — keep this current every session)

| Phase | What | State |
|---|---|---|
| P0 | Freeze v2 baseline, RQ1 instrumentation, protocol | done |
| P0.5 | Router viability gate | done |
| P1 | Objective-driven scheduler (greedy seed + SA) | done |
| P1b | ITC-2007 external benchmark harness | harness validated (1,900 cases vs official validator); **blocked on instance files**, see `evaluation/itc2007/INSTANCES.md` |
| P2 | Agent reduction 10→4, tool surface held 13→12 | **done** — code, frozen instrument, and all downstream figures/tests on the 99-task set (commit `9ed24c8`, 2026-08-19) |
| P3 | PCN-style provenance gate | **pending** — next unstarted phase |
| P4 | Confidence-gated hybrid router, τ frozen on dev | **done, current** — GPU-resident recapture + `tune_router.py` re-run on the 99-task/12-tool instrument, 2026-08-21: 88.9%/83.5%/94.6%, τ=0 (see below) |
| P5 | Held-out set → dual annotation → single test run | **blocked on external authors — the largest schedule risk** |
| P6 | Model sweep, 1.5B/3B/7B × 3 seeds | **partial** — 3B recaptured GPU-resident on the 99-task set; 1.5B/7B still pre-P2 (108-task), blocked on a laptop GPU driver dropout, see below |
| P7 | Figures F1–F9 | F1/F3/F7 drawn from fresh data; F2/F6/F8 blocked on P6 completing (depend on `p6_sweep.json`); F4/F5/F9 blocked on P3/P5 |
| P8 | Rewrite ARCHITECTURE.md / RESULTS.md to match the evidence | pending — README.md is current as of 2026-08-21; those two still carry v2-era numbers by design until P8 |

**P4 is done and current as of 2026-08-21.** GPU access came back (the
earlier block was a transient host-level driver/session fault, fixed by a
reboot — not a Claude Code sandbox restriction) and a clean, alone
99-task × 3-seed capture ran against `qwen2.5:3b-instruct`: 297 records,
99 unique task IDs matching `DEV_TASKS` exactly, 0 call failures,
`gpu_residency.fully_resident: true`, `mawos.db` hash unchanged
before/after. `tune_router.py` re-ran §9.3's rule against it and selected
τ≤0 again: lexicon 88.9%, LLM-alone 83.5% ± 0.5%, hybrid 94.6% (+5.7 pts,
95% CI [+0.3, +11.8], McNemar p=0.070). `backend/app/router_config.json`
was rewritten and `FROZEN.sha256` regenerated accordingly (PROTOCOL §12
changelog entry dated 2026-08-21). This **supersedes, does not correct**,
the pre-P2 108-task numbers (89.8%/76.9%/94.8%).

**P6 is only partial: the model-selection decision behind P4 is still
inherited from stale evidence.** The 3B was picked by the pre-P2 108-task
sweep; that pick has not been reconfirmed against the 99-task instrument
because `analyze_sweep.py` needs *every* model in `v3_llm/` to match the
current instrument and hard-exits (`RuntimeError`, not a silent skip) the
moment one doesn't — 1.5B and 7B are still the old 108-task captures.
Recapturing them stalled on 2026-08-21: the laptop's NVIDIA kernel driver
(`nvlddmkm`) stopped again mid-session, confirmed via `sc query nvlddmkm`
(`STOPPED`, no intervening reboot) and Ollama's `/api/ps` reporting
`size_vram: 0` for a model that fits easily. `Start-Service nvlddmkm`
requires elevation this tool doesn't have — **needs a host-side fix**
(reboot, or an elevated driver restart) before 1.5B/7B can be recaptured.
`evaluation/results/v3_gates/p6_sweep.json` therefore stays the pre-P2
108-task file; `evaluation/figures.py`'s `sweep_fresh()` check (added
2026-08-21) blocks F2/F6/F8 rather than draw from it, and
`evaluation/results/v3_llm/CONDITIONS.md`-style disclosure now lives
inline in PROTOCOL.md §12 and README's routing section.

Next unstarted phase in work order: **P3**, or completing P6 (1.5B/7B
recapture) once the GPU driver is fixed. P2 and P4 are done; don't
restart that work.

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
  the routing comparison. Under v3's current (99-task, GPU-resident,
  2026-08-21) conditions that is **83.5% vs 88.9%, −5.4 points** (3 seeds,
  `results/v3_llm/`). The pre-P2 108-task v3 run (76.9% vs 89.8%, −12.9)
  and v2's single-run −19.4 are both superseded, **not corrected** — none
  of the three runs may be differenced against another; they failed an
  equivalence check or used a retired instrument (`v3_llm/CONDITIONS.md`,
  PROTOCOL §10.1). Do not re-frame the loss as a win, and do not delete
  the losing configuration from the report.
- **Cite v2 and v3 numbers separately, and cite which v3 instrument.**
  README.md is current to the 99-task/12-tool instrument as of 2026-08-21;
  `docs/ARCHITECTURE.md` and `evaluation/results/v2_historical/RESULTS.md`
  still carry v2-era numbers on purpose — P8 rewrites those. Until then,
  say which run a number came from.
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

- The 99-query routing benchmark and the keyword lexicon it scores were
  written by the same project, so the lexicon is tuned to these phrasings.
  It is evidence about this classifier on this benchmark, not a general
  claim. A held-out set written outside the team is the fix.
- The model sweep is **only partial post-P2** (P6: 1.5B/3B/7B × 3 seeds,
  pre-P2/108-task) — the 3B was selected under a pre-registered rule
  against that older sweep, then reconfirmed via a fresh 99-task
  GPU-resident capture + `tune_router.py` (2026-08-21), but 1.5B/7B
  haven't been recaptured against the 99-task instrument yet, so whether
  3B is still the *right* pick under §9.2 is not yet reconfirmed. It is
  still one family, one temperature, three seeds. The 7B **could not stay
  GPU-resident** on this 6 GB laptop in the pre-P2 sweep (81.7%) and was
  reported out-of-competition; its post-P2 status is unknown until
  recaptured, and it must never share a Pareto frontier with an eligible
  model.
- **τ = 0 was selected on dev, and dev is contaminated by construction** —
  the lexicon was tuned on those 99 queries. The +5.7-point hybrid gain's
  95% CI now excludes zero ([+0.3, +11.8]), but McNemar p = 0.070 is still
  not significant at 0.05. It is not a confirmed result yet; the held-out
  set (P5) decides.
- Data is synthetic (UCI-calibrated, copula, 3% label noise), the bus is
  in-process and at-most-once, and replay recovery is manual.
