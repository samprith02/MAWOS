# MAWOS v5 — Design Spec

**Written 2026-09-13. Supersedes the *stack and scope* of `docs/v4/`, not its aim.**
**Status: awaiting owner review. No implementation has begun.**

---

## 0. What this document is, and what it is not

This is **not** a third re-aiming. v4's research question is unchanged:

> bounded LLM autonomy over a real institutional system — the model plans and delegates
> across agents, a deterministic guard authorises every action, writes require confirmation,
> and the whole chain is traced and measured.

`docs/v4/07_CONTRIBUTION.md` stands. `docs/v4/01_ARCHITECTURE.md` stands. `evaluation/PROTOCOL.md`
stands. Every working rule in `CLAUDE.md` stands verbatim.

Four things change, and each has a stated cause:

| # | Change | Cause |
|---|---|---|
| 1 | Orchestration runs on **LangGraph** instead of a hand-rolled loop | Hand-rolled orchestration is neither a research contribution nor a hiring signal. The contribution is the guard/provenance layer *above* it |
| 2 | The provider is **hosted**, not local | R0.5 measured it: no local model passed. Local also cannot be deployed on any free host — see §4.3 |
| 3 | A new external surface: an **MCP server** | Puts an untrusted external LLM behind the same guard. A second experiment, not decoration |
| 4 | Licence constraint: **permissive only** | The owner intends to fold this into an existing startup. Copyleft dependencies are disqualifying |

Plus one hard constraint that governs everything below: **10 days to a demonstration**, not to
final submission. The target is "how far did you get, shown running on a public URL."

---

## 1. Why not adopt an open-source ERP

Recorded because it will be asked, in the viva and by investors.

| Candidate | Licence | Verdict |
|---|---|---|
| ERPNext / Frappe Education | **GPLv3** | Rejected |
| Samarth eGov | Not published; no locatable public repository | Rejected |
| openSIS, Gibbon, RosarioSIS | GPL-family | Rejected |
| Fedena community edition | Stale (Rails 2.x era) | Rejected |

**The licence argument is decisive on its own.** GPLv3 is copyleft: distributing modified code
obliges you to distribute the source under GPLv3. Hosted-only SaaS is a loophole (network use
is not distribution), but Indian colleges overwhelmingly procure **on-premise** installs, and
on-premise *is* distribution. Adopting ERPNext would mean handing every customer the full
modified source. That constrains the business model from day one.

Two secondary reasons, recorded for completeness:

- **No ERP ships a dataset.** Real student records are PII and are never published. Every
  candidate ships an empty schema. MAWOS already has `data/generator/` — deterministic,
  seeded, scale-parameterised, feasibility-asserting. That is the asset the ERPs lack.
- **Adoption destroys the differentiators.** The SA timetable solver (cross-validated against
  the official ITC-2007 validator), the generator, the R1 schema, and 63 passing tests do not
  survive a migration to PHP or to Frappe's framework.

The chosen stack is permissive end to end: LangGraph (MIT), LangChain (MIT), FastAPI (MIT),
SQLAlchemy (MIT), Pydantic (MIT), PostgreSQL (PostgreSQL Licence), MCP Python SDK (MIT),
Next.js (MIT), shadcn/ui (MIT).

---

## 2. Architecture

### 2.1 The shape

```
                       ┌──────────────────────────────┐
   Next.js console ───▶│                              │
   (chat · trace ·     │        FastAPI service       │
    solver stream)     │                              │
                       │  ┌────────────────────────┐  │
   MCP client      ───▶│  │   LangGraph runtime    │  │
   (Claude Desktop,    │  │  plan → clarify →      │  │
    ChatGPT)           │  │  guard → confirm →     │  │
                       │  │  execute → observe →   │  │
                       │  │  synthesize            │  │
                       │  └───────────┬────────────┘  │
                       │              │               │
                       │   ┌──────────▼───────────┐   │
                       │   │  GUARD (deterministic)│  │ ◀── non-bypassable
                       │   └──────────┬───────────┘   │
                       │              │               │
                       │   ┌──────────▼───────────┐   │
                       │   │ Agents: Orchestrator │   │
                       │   │ Scheduling · Attend. │   │
                       │   │ · Compliance         │   │
                       │   └──────────┬───────────┘   │
                       └──────────────┼───────────────┘
                                      ▼
                          Postgres (domain + checkpoints + traces)
```

**The load-bearing claim:** both entry points — the internal planner and the external MCP
client — reach tools *only* through the same deterministic guard. An external LLM gets no
privilege the internal one lacks. That is testable, and §6 tests it.

### 2.2 What LangGraph provides, and what we build

Drawing this line precisely matters, because "we used a framework" and "we contributed
nothing" must not be the same sentence.

| LangGraph gives us | We build |
|---|---|
| Graph state machine, conditional edges | The specific node topology and its re-plan bound (N=1) |
| `PostgresSaver` checkpointing, thread IDs | Mapping conversation identity onto threads |
| `interrupt()` / `Command(resume=…)` HITL | **The guard that decides *whether* a write may even be proposed** |
| Streaming, subgraphs | The provenance gate over synthesis |
| Tool binding | The typed `Task → Result \| NeedInfo \| Refusal` contract |

Verified against current docs (LangGraph 1.0.x): `interrupt()` raised inside a node or tool
pauses the run; `stream.interrupted` / `stream.interrupts` expose the payload; the value passed
to `Command(resume=…)` becomes the return value of `interrupt()`. `PostgresSaver.from_conn_string(...)`
plus `.setup()` provisions the checkpoint tables. The framework's own canonical example is a
human-approved write tool — the exact primitive v4 requires.

**Nothing above the guard is provider-specific or framework-specific.** The guard, the
provenance gate, and the delegation contract are ours and would survive swapping LangGraph out.

### 2.3 Agents

Unchanged from `docs/v4/01_ARCHITECTURE.md`: **Orchestrator + Scheduling + Attendance &
Monitoring + Compliance**. Comms ships as a bus subscriber, not an agent (D3 stays open;
promotion requires the measurement, not the deadline).

---

## 3. The LLM provider — closing D1 honestly

### 3.1 The problem with just picking Groq

D1 is an open, pre-registered decision. Its thresholds were fixed *before* any run, and
`docs/v4/OPEN_DECISIONS.md` states plainly: if nothing is eligible, **thresholds are not
relaxed**. Wiring in whichever provider is convenient and back-filling a justification is
precisely the failure mode the register exists to prevent.

So D1 is closed by **measurement, on day 1**, before the provider touches the agent runtime.

### 3.2 Candidates and why they are affordable now

| Provider | Free allowance | Card? | Role |
|---|---|---|---|
| **Groq** | 14,400 req/day · 30 RPM | No | **Primary candidate** |
| OpenRouter | 50/day (1,000/day after $10) | No | Secondary |
| GitHub Models | 50/day high-tier · 150/day mini | No | Tertiary |
| Gemini | 20/day | No | Excluded — broke the 2026-09-01 run |
| SambaNova | 20/day | No | Excluded — same wall |
| Cerebras | Free tier ended 2026-07-16 | Yes | Excluded |
| Cloudflare Workers AI | ~15–25 generations/day | No | Excluded |

The probe is ~150 requests per candidate. Groq's daily allowance covers the **entire benchmark
(~70 tasks × 3 seeds ≈ 210 calls) roughly 68 times over.** Cost is no longer a live constraint.

### 3.3 Required before the re-run

**D14 must be re-registered first.** It records that M7 measures client-side pacing rather than
provider latency — defective, but standing. Against hosted providers M7 becomes a *network*
measurement, so the defect now materially changes the verdict. Per D1's clause (b), the fix is a
**dated re-registration entry written before the run that uses it**, not an adjustment after
seeing results.

Order of operations, and it is not negotiable:
1. Re-register M7 (dated entry, stated justification) — **before** any hosted run
2. Run the probe: Groq · OpenRouter · GitHub Models
3. Apply the pre-registered selection rule as written
4. Record the outcome, whatever it is, in `evaluation/results/v5_gates/`
5. **Only then** wire the winner into the runtime

If nothing passes again, that is a finding and it gets reported as one. The architecture — which
clarifies *before* executing — is itself the mitigation for the exact failure Gemini exhibited
(calling a tool against a silent default, then asking).

---

## 4. Deployment

### 4.1 Topology

| Layer | Host | Free? |
|---|---|---|
| Next.js console | Vercel | Yes |
| FastAPI + LangGraph + MCP | Render web service (Docker) | Yes — 512 MB |
| Postgres | Render PG (Neon as fallback) | Yes |
| LLM | Groq API | Yes |

### 4.2 Rejected hosts, with reasons

- **Vercel for the backend** — free-tier functions time out at 10 s. One agent turn (plan, tool
  calls, LLM round-trips, synthesis) exceeds that. Vercel's Python runtime is also not built for
  long-running FastAPI. Frontend only.
- **Zoho Catalyst** — real (25k GB-seconds/month free), but serverless functions suit a stateful
  LangGraph app poorly, documentation for this use case is thin, and it carries no hiring signal.
  Not worth the learning cost in 10 days.
- **Railway** — $1/month credit after the first month; insufficient for always-on.
- **Fly.io** — free tier withdrawn for new users; card required.
- **Koyeb** — free Postgres, but compute now starts at $29/month.

### 4.3 Why local inference is not a fallback

Recorded because it was the assumed safety net and it is not one. **No free host provides a
GPU.** Render's free tier is 512 MB RAM; a 3B model needs 2–3 GB to load and would run at a few
tokens/second on free CPU, if it did not OOM first. "Local LLM + Docker + deploy" does not yield
a deployed system — it yields a laptop-only system, which fails the deployment requirement
outright. Local inference is the *undeployable* option, not the safe one.

### 4.4 Operational notes

- Render free services spin down when idle (~50 s cold start). **Warm the service before any
  demo.** Do not discover this live.
- `GROQ_API_KEY` lives in the host's environment. `.gitignore` already excludes `.env` and
  `.env.*` while permitting `.env.example`. No key enters git, ever.
- Deploy a thin slice on **day 3–4**, not day 9. Deployment discovers problems; discover them early.

---

## 5. Data

**No change of policy — the work is already done, and this section records that.**

A grep of `backend/`, `data/`, and `frontend/` for the real institution name, the owner's name,
the real USN prefix, the real email domain, and the real city returns **zero hits** — except
`data/generator/config.py:107`, which is the ban list that *rejects* them.

`data/institution.yaml` defines a wholly fictional institution: *Vidyut Institute of Engineering
& Technology* (VIET), USN prefix `1VT`, domain `viet.edu.in`, city "Kadamba". D12 leaves the name
to the owner; changing it is one edit plus a reseed.

No real personal data appears anywhere, and none is needed — no ML model is trained in v5, so the
data exists only to exercise workflows.

**Correction to a standing assumption:** the timetable problems were **not** a dataset defect.
`backend/app/main.py` generates `timetable_slots` only once, when the table is empty, and never
regenerates — so the grid drifts from what the current solver would produce. That is stale rows,
not bad data and not a solver regression. The dataset work that *does* matter is R2's addition of
**rooms as a real decision variable** and **generalised teacher unavailability**, already
specified in `docs/v4/05_TIMETABLE_SCOPE.md`.

---

## 6. Evaluation

Scaled to 10 days; the protocol is unchanged.

| Instrument | Size | Purpose |
|---|---|---|
| Task benchmark | ~70 tasks, gold **outcomes**, category labels | Primary result |
| Adversarial guard suite | ~20 items | Claim 1 (guard placement) |
| **MCP guard parity suite** | ~10 items | **New** — same attacks via MCP; must produce identical guard decisions |
| Provider degradation run | 3 providers × the benchmark | Claim 2 |

**The MCP parity suite is the new experiment.** Every adversarial item is replayed through the
MCP surface with an external client driving. The claim under test: *guard decisions are
identical regardless of which LLM drives the tools.* A divergence is a finding worth reporting,
not a bug to hide.

**Blind authorship — a standing blocker, now unblocked.** `docs/v4/06_BENCHMARK.md` §6 requires
task authors blind to the implementation; this has blocked P5 since v3. Two teammates who are
**not** building the agent layer will author the benchmark **without reading the agent code**.
This is recorded honestly as *"teammates, partially blind"* — not as external authorship. It is a
material improvement over self-authorship and is not equivalent to independence.

Carried forward without exception: never headline a 100% figure; report in the direction the data
points; cite which instrument produced every number; never present a number that cannot be
regenerated from `evaluation/`.

---

## 7. Scope for 10 days

### 7.1 MUST — the demonstration collapses without these

- LangGraph runtime: plan → clarify → guard → confirm → execute → observe → synthesize
- `PostgresSaver` checkpointing; conversation identity mapped to thread IDs
- Typed delegation contract: `Task → Result | NeedInfo | Refusal`
- Deterministic, non-bypassable guard logging **both** allowed and blocked outcomes
- **3 write tools** gated by `interrupt()` confirmation, named here so the plan need not guess:
  1. `mark_attendance(section, subject, date, absentees[])` — Attendance agent
  2. `apply_timetable_change(section, slot, new_assignment)` — Scheduling agent, counterfactual-scored before it is proposed
  3. `issue_eligibility_override(student, exam, reason)` — Compliance agent, the highest-privilege write and therefore the sharpest guard test
- One end-to-end write cascade spanning ≥ 3 agents (the `02_SCOPE.md` §1.2 attendance cascade)
- MCP server exposing the same guarded tools
- D1 closed by measurement, with M7 re-registered first
- Deployed on a public URL, on Postgres
- Per-turn trace persisted and renderable

### 7.2 SHOULD — build only when every MUST is green

- Next.js console (chat · trace viewer · solver stream)
- Rooms as a decision variable + generalised unavailability
- Provider degradation run across all three candidates
- MCP guard parity suite
- GitHub Actions running pytest

### 7.3 WILL NOT BUILD in these 10 days

- Comms promoted to a fourth agent (D3 needs a measurement, not a deadline)
- MRV/backtracking second search stage (D2 says do not build)
- Multi-period lab blocks · load caps · capacity
- Requests & Approvals as a general module
- Bus outbox + replay
- RAG over policy documents — *no workflow currently needs it; adding it for stack optics is
  exactly the trap this project keeps avoiding*
- Any rewrite of the existing SPA's CRUD screens

### 7.4 Cut order if days are lost

1. Next.js console — the existing SPA carries the demo
2. Provider degradation run — drops to one provider, and Claim 2 is reported as not attempted
3. Rooms — R2 defers wholesale

**Never cut:** deployment · the guard layer · the trace · D1's honest closure.

---

## 8. Day plan

| Day | Owner (Claude Code) | Teammate A (ChatGPT) | Teammates B + C |
|---|---|---|---|
| 0 | ✅ R1 committed · Groq key · this spec | read spec | read spec |
| 1 | Re-register M7 → run probe → **close D1** | Next.js scaffold | benchmark categories |
| 2 | LangGraph skeleton + state + checkpointer | console layout | task authoring |
| 3 | Guard wired; typed contract | trace viewer | task authoring |
| 4 | **Deploy thin slice** · 3 write tools + `interrupt()` | wire to API | task authoring |
| 5 | Write cascade end to end | solver stream | gold outcomes |
| 6 | MCP server | polish | outcome checker |
| 7 | MCP parity suite | polish | dry-run benchmark |
| 8 | Benchmark run × providers | — | figures |
| 9 | Results, docs, `CLAUDE.md` sync | demo rehearsal | slides |
| 10 | Buffer · demo video · viva prep | | |

Teammates B and C do **not** read `backend/app/agents/` or the LangGraph code at any point —
that is what preserves partial blindness in §6.

---

## 9. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| D1 fails again on all three hosted candidates | Medium | It is a reportable finding. The architecture clarifies before executing, which is the mitigation for the observed failure. Fall back to best-scoring with the gap recorded explicitly |
| Render cold start ruins the live demo | **High** | Warm before demo; record a backup video on day 9 |
| LangGraph migration eats more than 3 days | Medium | Guard, tools, and agents are unchanged — only the planner is replaced. If it overruns, the existing router keeps the demo alive |
| Unattended cloud agents drift | **High** | Every task carries tests as its acceptance criterion. Architecture decisions stay in attended sessions |
| Blind authorship leaks | Medium | B and C never open the agent code. If it leaks, say so in the write-up |
| 10 days is simply not enough | **High** | §7.4 cut order exists precisely for this. The target is "how far we got," not completeness |

---

## 10. Open decisions after this spec

| ID | Decision | State |
|---|---|---|
| D1 | LLM provider | **Closes day 1, by measurement** |
| D14 | M7 measures client pacing | **Re-register before the run** |
| D2 | MRV second stage | Do not build |
| D3 | Comms as 4th agent | Stays open — needs a measurement |
| D4 | Frontend rewrite | **Partially resolved:** no rewrite of CRUD screens; the *new* console is Next.js. Recorded as a scope decision, not a measured one |
| D12 | Institution name | Owner's call; placeholder stands |

The four things a session must never quietly decide (`OPEN_DECISIONS.md` §1) remain in force.
D4's partial resolution above **is** a decision made explicitly and recorded, which is the
register's requirement.

---

## 11. Success criterion

> A public URL where a faculty member asks the assistant, in English, to mark today's
> attendance for a section; it asks a clarifying question; a deterministic guard authorises
> the write; a human confirms it; three agents execute the cascade; eligibility is
> recomputed; and the full trace is inspectable — **and the same tools, behind the same
> guard, are reachable from Claude Desktop over MCP.**

Everything in §7.1 serves that sentence. Everything in §7.3 does not.
