# MAWOS — working notes for Claude

B.E. final-year research prototype (Dept. of AI&ML, MITE, Group 12).
Framing: **event-driven multi-agent workflow orchestration engine for
universities**. The contribution is the orchestration engine, not the agent
count. Ten agents, chosen by institutional function.

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
- **Cite v2 and v3 numbers separately.** README, ARCHITECTURE and RESULTS.md
  still carry v2 figures; P8 rewrites them. Until then, say which run a
  number came from.
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
