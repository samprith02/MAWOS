# MAWOS v2 — an event-driven multi-agent workflow orchestration engine for universities

B.E. Final-Year Research Prototype · Dept. of AI&ML, MITE · Group 12

MAWOS models a **real institution** — 5 departments × 4 years × 2 sections
(1,200 students, 75 faculty, 100 subjects, 180,000 attendance records, an
admissions intake of 400 applicants) — and runs it through a **multi-agent
system**: ten agents, each owning an institutional domain, coordinating over
an instrumented event bus, with an **LLM-driven orchestrator** that calls
role-scoped tools rather than answering from a script.

The research contribution is the **orchestration engine**, not the agent count:
`intent → tool selection (LLM) → permission-checked execution → grounded answer`
on the query path, and
`attendance upload → attendance → {exam, scholarship, placement, notification}`
on the propagation path — where **every hop is measured** under a workflow ID.

---

## Quickstart

```bash
pip install -r requirements.txt
python ml/calibrate.py       # estimate distributions from the real UCI dataset
python ml/train.py           # generate calibrated data + train CART & RF
python run.py                # -> http://localhost:8000
```

First launch seeds the institution and solves the timetable (720 slots,
40 sections, 0 teacher conflicts, ~70 ms). Roughly 60 s of one-time setup.

### Turning the LLM brain on (important)

MAWOS is LLM-first by design, but degrades to a deterministic classifier when
no model is reachable. **The portal shows which mode is live** — the header
badge reads `AI · LLM` or `AI · fallback mode`.

```bash
winget install Ollama.Ollama
ollama pull qwen2.5:3b-instruct
```

If `winget` downloads and then hangs without installing (it blocks on a UAC
prompt that never appears in a non-interactive shell), skip the installer and
use the portable build instead — no admin rights required:

```bash
# download ollama-windows-amd64.zip from the v0.32.5 GitHub release, then:
unzip ollama-windows-amd64.zip -d %LOCALAPPDATA%\Ollama
%LOCALAPPDATA%\Ollama\ollama.exe serve          # leave running
%LOCALAPPDATA%\Ollama\ollama.exe pull qwen2.5:3b-instruct
```

Both downloads total ~3.4 GB, so allow time on a slow connection. Point MAWOS
at a different model or host with `MAWOS_OLLAMA_MODEL` / `MAWOS_OLLAMA_HOST`.

Restart MAWOS; the badge flips to `AI · LLM` and the assistant begins
selecting tools itself, chaining several per question, and writing answers in
its own words from tool results. No other change is needed — and the two
modes are directly comparable, which is itself one of the experiments.

That comparison is **automated, not asserted**: `evaluation/evaluate.py`
detects Ollama and, when present, replays all 108 labelled queries through the
LLM tool-selection path against the same target tools, then writes a
head-to-head table with the per-tier deltas and the latency each tier costs.
Each query is asked by the role that would really ask it; a second pass re-asks
everything as admin to measure how much tool calling depends on the caller's
permissions. The report's conclusion is derived from the measured signs — and
on this laptop **the LLM loses the routing comparison, so the report says so**.
Use `--no-llm` to score the deterministic tier alone, or
`--no-role-sensitivity` to skip the second pass.

| | LLM mode | Fallback mode |
|---|---|---|
| Understanding | free-form, multi-intent, follow-ups | one intent per query, keyword-scored |
| Tool use | model chooses, may chain 2-3 tools | exactly one mapped tool |
| Answer | composed from tool results | fixed formatter per tool |
| Requires | Ollama + qwen2.5 (~2 GB) | nothing |
| Measured routing accuracy | **70.4%** (83.3% direct / 44.4% indirect) | **89.8%** (100% direct / 69.4% indirect) |
| Latency per query | ~4.5 s | <1 ms |

So switch the LLM on for the *answers*, not for the routing — that is what the
measurement supports, and §1.2b/§1.3 of `evaluation/results/RESULTS.md` carries
the full breakdown with every miss listed.

### Demo accounts (five different portals, not five skins)

| Role | Login | What that role can actually do |
|---|---|---|
| Student | `4MT23AI049` / `student123` | attendance & CIE marks, fees + pay, hall-ticket status, scholarship, placements, personal timetable + CSV download, notices, assistant |
| Faculty | `aiml.f02` / `faculty123` | own teaching assignments, **mark class attendance** (only for assigned subject-sections — enforced server-side), enter internal marks, own teaching timetable |
| HOD | `hod.aiml` / `faculty123` | department analytics, section-wise timetables, **regenerate the department timetable**, fee-defaulter list |
| Principal | `principal` / `principal123` | institution-wide analytics: department comparison, fee collection, placements, admissions funnel |
| Admin | `admin` / `admin123` | **full admissions pipeline** (verify → merit rank → allot seats vs intake → enrol), demo cascade trigger |

Any USN from `4MT23AI001`–`4MT26CV6xx` works as a student login; faculty are
`{dept}.f02`…`{dept}.f15`; HODs are `hod.{dept}` for aiml/cse/ece/me/cv.

---

## The ten agents

| Agent | Kind | Responsibility |
|---|---|---|
| **Orchestrator** | LLM + tools | Tool-calling loop over role-filtered schemas; deterministic fallback |
| **Admission** | workflow | verify → merit rank → seat allotment vs intake & category quota → enrolment (creates student, login, fee, fires cascade) |
| **Timetable** | constraint solver | Randomized-greedy with restarts; globally conflict-free across all 40 sections; CSV export |
| **Academic** | records | students, CIE marks, class rosters, department & institution analytics |
| **Attendance** | rules + proactive | percentages, <75% shortage, absence streaks, autonomous periodic scan |
| **Finance** | rules + proactive | fee structures, ₹50/day fines, payments, defaulters, collection stats |
| **Exam** | rules | schedules; hall-ticket eligibility with reason codes |
| **Scholarship** | rules + CART | rule pre-filter then calibrated decision-tree scoring |
| **Placement** | rules + RF | final-year drive eligibility + success-probability ranking |
| **Notification** | event-driven | turns cascade events into targeted, role-scoped messages |

Dropped from v1: Library, Smart-Event, and the pseudo "Student/Faculty agents"
— students and faculty are *roles with permissions*, not agents. Agents are
chosen by function, never to hit a number.

---

## Measured results (`evaluation/results/`)

| Metric | Result |
|---|---|
| Intent routing, deterministic tier — 108 labelled queries, 12 intents | **89.8%** overall · 100% direct phrasings · **69.4% indirect** · confusion matrix + every miss listed |
| Intent routing, LLM tier — same 108 queries, same target tools | **70.4%** overall · 83.3% direct · 44.4% indirect · 4.5 s/query — **the LLM loses this comparison**, see below |
| Tool calling vs. caller permissions | same queries under one staff persona instead of the natural role: **70.4% → 55.6%**, driven by 23 → 35 refusals to call any tool |
| Attendance computation | 0 mismatches / 1,000 summaries — reported as *deterministic verification*, **not** an AI accuracy claim |
| Cross-agent propagation | avg **466 ms**, p95 **479 ms** (target <2 s) — measured with the LLM resident; ~127 ms with Ollama stopped |
| Timetable solver | **720/720** slots across 40 sections, **0 teacher conflicts**, 1 restart, ~46 ms |
| Ablation — event bus removed | **0** downstream tables auto-update and **4** manual office interventions per upload (vs 0 with the bus, for ~403 ms of extra processing) |
| Ablation — orchestration layer | ~8 ms overhead for classification + permission checks + logging |
| Failure injection | Scholarship Agent crashed mid-cascade → siblings complete, error audited as `agent.error`, replay recovers · **PASS** |
| Scalability | institution 4× larger (1,200→4,800 students), identical workload: latency **did not grow** (0.72×, i.e. within run-to-run noise), memory flat |
| Scholarship CART / Placement RF | 90% / 82% test accuracy — deliberately **not** ~100%, see below |

**Nothing here reports 100%** — including the result we expected to go the
other way. The intent benchmark carries a deliberately hard tier that the
deterministic classifier fails 30% of the time, and the design assumption was
that the LLM would recover exactly that gap. **Measured, it does not:**
qwen2.5:3b-instruct scores 44.4% on the hard tier against the lexicon's 69.4%,
and 70.4% against 89.8% overall, at 4.5 s per query versus under 1 ms.

We report it as measured rather than quietly dropping the experiment. Three
things follow, and they are the honest reading:

1. **A tuned keyword lexicon is a strong baseline** on a closed 12-intent
   domain. It was built against these very phrasings, which is precisely why
   it wins — and why a benchmark a system's own author wrote is evidence about
   the classifier, not proof about language understanding in general.
2. **The LLM's contribution here is composition, not routing** — grounding an
   answer in several tool results and writing it in prose. That is what the
   portal actually uses it for; routing is the part it does worse.
3. **Tool calling is permission-sensitive** (§1.2b): the same model on the same
   queries drops 14.8 points when the persona cannot satisfy the tool's
   arguments, because it correctly refuses to invent a USN. Any single-persona
   tool-calling benchmark understates a role-scoped system.

A larger local model is the obvious next experiment — `MAWOS_OLLAMA_MODEL`
switches it with no code change, and `evaluate.py` will re-score both tiers.

ML training data is calibrated to the
real UCI Student Performance dataset (n=1,044) *including its correlation
structure* via a Gaussian copula, then injected with 3% label noise and
stochastic outcomes, so no model can re-derive a hand-written rule. Full
methodology and threats to validity:
[docs/DATASET_METHODOLOGY.md](docs/DATASET_METHODOLOGY.md).

### Reproduce everything

```bash
python -m pytest tests -q                 # 12 tests: cascade, permissions, solver, admissions, fault isolation
python evaluation/evaluate.py             # routing (both tiers), verification, propagation, manual baseline
python evaluation/evaluate.py --no-llm    # deterministic tier only (skips the 108 live LLM calls)
python evaluation/ablation.py             # is the architecture load-bearing?
python evaluation/failure_injection.py    # fault tolerance
python evaluation/scalability.py          # constant workload vs institution size
python fl/federated_poc.py                # appendix / future work only
```

---

## Project structure

```
backend/app/
  agents/            10 agents, one file each
    orchestrator.py    LLM tool-calling loop + deterministic fallback
    tools.py           typed tool registry with ROLE ENFORCEMENT
    timetable.py       constraint solver + CSV export
    admission.py       admissions pipeline
  bus.py             instrumented pub/sub, workflow IDs, fault isolation
  llm.py             Ollama chat + tool calling; keyword fallback tier
  models.py          shared institutional context store
  seed.py            the synthetic institution
  api/routes.py      role-guarded FastAPI gateway
frontend/static/     five role portals (no build step)
ml/                  UCI calibration -> copula generation -> CART/RF
evaluation/          evaluate · ablation · failure_injection · scalability
fl/                  federated-learning PoC (future work)
docs/                ARCHITECTURE · DATASET_METHODOLOGY · CODE_WALKTHROUGH · PLAN_V2
tests/               pytest suite
```

### PostgreSQL

MAWOS requires PostgreSQL for its application database. Create the `mawos`
database before starting the backend, then configure `MAWOS_DATABASE_URL` in
the root `.env` file. The expected local connection is:

```text
Host: 127.0.0.1
Port: 5432
Database: mawos
Username: postgres
```

Set the password only in `.env`; do not commit it or place it in this README.
The required SQLAlchemy URL uses the `psycopg` driver:

```text
MAWOS_DATABASE_URL=postgresql+psycopg://postgres:<password>@127.0.0.1:5432/mawos
```

On a fresh PostgreSQL database, the backend creates the tables from
`backend/app/models.py` during startup. To migrate the existing SQLite backup
without deleting it, run:

```bash
python scripts/migrate_sqlite_to_postgres.py
```
