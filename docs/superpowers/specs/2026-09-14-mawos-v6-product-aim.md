# MAWOS v6 — product aim: a smart multi-agent college ERP

**Date:** 2026-09-14
**Supersedes as the driver:** `2026-09-13-mawos-v5-design.md` (v5's *engineering* stands; its
research framing is demoted — see §1)
**Status:** proposed scope, not yet executed

---

## 1. What changed, and the one thing to be honest about

The owner has re-aimed the project:

> "our main aim is just SMART and Advanced Multi agent based college ERP SYSTEM … mainly focus
> on admin type. main feature is like one can query llm agent inside the erp to get any info,
> send any requests, timetable rescheduling when certain teacher is absent"

and has explicitly lifted the research-first constraint:

> "dont strictly depend on research, research is not that important for now … for research we
> can do it completely different"

**Research is demoted from gate to appendix. It is not deleted.** Everything under
`evaluation/` stays — the probe, the gates, PROTOCOL, the D-register, the archived runs. They
remain valid evidence for the report and the viva. What stops is their *authority to block
product work*. A decision no longer waits for a pre-registered measurement; it waits for
someone to try it and see whether it is good.

### The thing to be honest about

Two features the owner asked for repeatedly were blocked **by research decisions, by name**:

| Asked for | Blocked by | Recorded where |
|---|---|---|
| Rooms as a real timetable entity | R2 deferred wholesale | `02_SCOPE.md`, v5 §7.4 cut order |
| MRV / backtracking search | **D2: "do not build"** | `OPEN_DECISIONS.md` D2 |
| The Chronos timetable UI | "borrowed only the visualization idea" | `CLAUDE.md`, P-table note |

The `teacher-erp-with-timetable-simulation/` app was never integrated for a reason nobody
stated out loud: **it is in `.gitignore` (line 51).** It has never been in the repository,
never been pushed, and is invisible to every clone and every agent working from one. It was
not overlooked — it was structurally unreachable.

That is the correct explanation, and it is also the correct criticism: the research framing
converted "the owner asked for this three times" into "D2 says do not build," and nobody
revisited it. Lifting the framing is what unblocks it.

---

## 2. Where MAWOS actually stands — measured, not asserted

Not everything is bad, and the parts that are good are the parts that are hard to rebuild.
Being accurate here decides what gets kept.

### Genuinely strong — keep, do not touch

| Asset | Why it is worth keeping |
|---|---|
| `backend/app/guard.py` | Deterministic authorisation. `tools.execute()` is the **only** call site of any tool function in the whole app, and every call passes the guard, which logs allowed *and* denied in one shape. This is the rare part; most projects cannot say it |
| `backend/app/mcp_server.py` | External LLMs (Claude Desktop, ChatGPT) reach the same tools behind the same guard. Parity-tested |
| `contracts.py` | `AgentTask → AgentResult \| NeedInfo \| Refusal`. Three outcomes, not two — `NeedInfo` is what makes an agent ask instead of guess |
| `trace.py` + `GuardDecision` | Every turn is inspectable and every authorisation is countable |
| Hybrid router | ~90% of queries never touch the LLM. On a free tier that is not a research artefact, it is the thing that keeps the demo inside rate limits |
| The ERP domain | Attendance, fees, marks, eligibility, scholarships, placements, notifications — real workflows, already wired to agents and tools |

### Genuinely thin — this is what "worst" actually refers to

The timetable **solver is not broken**. Measured just now, on the live DB:

```
sections 40 · slots 720/720 placed · unplaced 0 · teacher_conflicts 0
placement_rate 100.0 · objective 604 → 210 · solve_ms 1293
```

It solves. What is missing is everything *around* it:

| Gap | Detail |
|---|---|
| **Rooms are not a decision variable** | `scheduler.py:257` writes `room=f"{dept}-{year}{sec}"` — a derived label. There is no room, no capacity, no lab, no contention |
| **No teacher absence** | Nothing models a teacher being unavailable. The flagship feature has no substrate |
| **Grid is hardcoded** | `N_DAYS, N_PERIODS = 5, 6` with 6-bit occupancy masks. Changing it is a solver rewrite, not config |
| **Data goes stale** | `main.py` generates slots once when the table is empty and never again. The live grid drifts from what the solver would now produce — already documented, never fixed |
| **The UI is nothing** | Vanilla-JS SPA, no build step. Functional; not something to show anyone |
| **LangGraph is not on the request path** | `build_graph()` has zero call sites outside `tests/`; `nodes.plan()` returns an empty plan by construction. `/chat` still runs the v3 loop |

---

## 3. The decision: adopt Chronos as the product shell

`teacher-erp-with-timetable-simulation/` ("Chronos") is 6,022 lines of TypeScript —
Next.js 16 · Drizzle · Postgres · Tailwind 4 · a pure-TS MRV-backtracking + hill-climbing
solver written as a `function*` generator so the same code can stream its decisions to the
browser for live animation, or be drained synchronously by a seeder.

**It already contains what MAWOS spent two months not building:**

| Chronos has | MAWOS status |
|---|---|
| `rooms` as a first-class table and solver dimension | never built (R2 deferred) |
| `teachers.unavailable: number[]`, enforced in the engine at `engine.ts:228` | never built |
| `assignments.locked: boolean` — pin an assignment across a re-solve | never built |
| Configurable `days` / `periodsPerDay` / `breakSlots` | hardcoded 5×6 |
| MRV backtracking + bounded min-conflicts repair + hill-climb polish | **D2 said do not build** |
| Streaming live-trace UI (`SolverSim.tsx`, 798 lines) | a wrapper that replays a trace |
| CRUD for teachers · subjects · rooms · classes · curriculum · settings | partially, in a raw SPA |
| Run history, compare, publish | never built |

`unavailable` + `locked` together are **exactly** the two primitives the flagship feature
needs. This is not a rewrite — it is wiring something that already exists.

### The architecture

This is not a new topology. **v5 §4.1 already planned "Next.js console on Vercel + FastAPI on
Render."** The only change is that Chronos *is* the Next.js app rather than one built from
scratch.

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  Chronos  (Next.js, Vercel) │         │  MAWOS  (FastAPI, Render)    │
│                             │         │                              │
│  • admin ERP screens        │  HTTP   │  • LangGraph turn runtime    │
│  • timetable + simulator    │ ◄─────► │  • deterministic GUARD       │
│  • MRV solver (/api/solve)  │         │  • agents + tool registry    │
│  • rooms/teachers/lessons   │         │  • MCP server                │
│  • chat panel (new)         │         │  • trace + provenance        │
└──────────────┬──────────────┘         └───────────────┬──────────────┘
               │                                        │
               └──────────────► Postgres ◄──────────────┘
                        strict table ownership
```

**Rules that keep two ORMs over one database from becoming a mess:**

1. **One owner per table.** Chronos/Drizzle owns `teachers, subjects, rooms, class_groups,
   lessons, runs, assignments, settings`. MAWOS/SQLAlchemy owns `students, attendance, fees,
   marks, hall_tickets, guard_decisions, trace_records, conversations`.
2. **No cross-ORM writes, ever.** MAWOS never writes a Chronos table and vice versa.
3. **Cross-domain access is HTTP, not SQL.** MAWOS's timetable agent is an HTTP client of
   Chronos's `/api/solve`, `/api/resources/[type]`, `/api/runs`. This is what makes the guard
   still meaningful: a call that crosses the boundary is a *capability*, and capabilities pass
   the guard.
4. Migrations stay independent — `drizzle-kit push` for its tables, Alembic for MAWOS's.

### Why not the alternatives

- **Port the solver to Python.** Throws away the 798-line live-trace UI — the thing actually
  wanted — to gain stack purity nobody is paying for.
- **Rebuild Chronos's screens inside MAWOS's SPA.** Strictly worse on every axis.
- **Keep both solvers.** Two sources of truth for the timetable. No.

MAWOS's `scheduler.py` is **retired from the product** and kept in the repository as the
frozen v3 baseline the archived ITC-2007 benchmark scored. It stops being the thing that
generates the timetable users see.

---

## 4. The flagship feature: absence rescheduling, end to end

This is the demo. It uses every part worth keeping.

```
Admin, in the ERP chat panel:
  "Prof. Rao is out Thursday afternoon — fix the timetable"

 1  PLAN       model turns it into tasks; resolves "Rao" → teacher_id,
               "Thursday afternoon" → slot indices
 2  CLARIFY    ambiguous? ask. ("Thursday of this week or next?")
               → NeedInfo STOPS the turn. It does not guess.
 3  GUARD      apply_timetable_change is a WRITE, roles=(hod, principal, admin).
               Deterministic. Logged whether allowed or denied.
 4  PROPOSE    set teacher.unavailable += those slots
               lock every assignment that must not move
               call Chronos /api/solve in repair mode
               → a DIFF: 3 lessons move, 37 stay, objective 210 → 218
 5  CONFIRM    LangGraph interrupt(). A human sees the diff and approves.
               Checkpointed — a process restart does not lose the proposal.
 6  EXECUTE    publish the run; cascade: affected sections notified,
               attendance expectations updated
 7  TRACE      every step above is persisted and renderable
```

**Why this is a good flagship:** it is a real administrative task, it is impossible without
an agent (natural language → constrained re-solve), it is dangerous enough to justify a guard
and a confirmation, and it produces a *visibly animated* result. It also exercises the
`NeedInfo` path, which is the behaviour the D1 probe measured every candidate model failing.

---

## 5. Wiring LangGraph onto the request path

Scoped as asked. Today `build_graph()` has no caller outside `tests/` and `nodes.plan()`
returns `state.get("plan") or []` — an empty plan by construction.

| # | Task | Detail |
|---|---|---|
| 1 | `plan()` calls the model | Bind role-filtered tool schemas, ask for a task list, parse into `AgentTask[]`. Returns `NeedInfo` when a required argument is genuinely missing rather than defaulting it |
| 2 | `synthesize()` calls the model | Compose the final answer **only** from `outcomes`, then run the existing provenance gate over it |
| 3 | `POST /api/agent/turn` | Runs the graph. `thread_id` = conversation id, so checkpointing is per conversation. Returns either an answer, a clarifying question, or a pending confirmation |
| 4 | `POST /api/agent/confirm` | Resumes an interrupted turn with `Command(resume={"approve": bool})` |
| 5 | Keep the lexicon as a fast path | A high-margin single-read query answers deterministically without entering the graph. This is not legacy — on a free tier it is what keeps ~90% of traffic off the rate limit |
| 6 | Trace endpoint + viewer | `GET /api/agent/trace/{turn_id}` → the Chronos trace panel |

**Migration note.** `/chat` keeps working throughout. The graph lands behind
`/api/agent/turn` and the UI switches when it is better, so there is never a window with no
working assistant.

---

## 6. Data — what is actually wrong with it

The owner's judgement is that the synthetic data is bad. Concretely, what is weak:

| Problem | Fix |
|---|---|
| No rooms, labs or capacity at all | Comes free with Chronos's schema — generate a real room inventory with types and capacities |
| Teacher availability is uniform | Give teachers real unavailability patterns (research day, part-time, shared across departments) — this is what makes rescheduling non-trivial |
| No academic calendar | Terms, holidays, exam weeks, mid-term breaks. Attendance and timetable both currently float in an undated void |
| Attendance is `rng.random() < 0.82` per record | Correlate it: by student, by subject, by weekday, with streaks. Uncorrelated noise makes every analytic look the same |
| Lessons have no structure | Multi-period lab blocks, tutorials, electives with subsets of a class |
| 1 department demoed | 5 departments already generate; give each distinct load so cross-department comparison is interesting |

`data/generator/` stays — it is deterministic, scale-parameterised and feasibility-asserting,
which is genuinely good work. It gets *extended* to Chronos's richer schema, not replaced.

---

## 7. Scope

### Phase A — foundation
- Un-ignore Chronos, bring it into the repository (its own top-level directory)
- One Postgres, table ownership documented, both migration paths working
- Chronos deploys to Vercel; MAWOS stays on Render; `/health` on both

### Phase B — the agent on the request path
- §5 tasks 1–4: `plan()` and `synthesize()` call the model; the two agent endpoints
- Chat panel inside Chronos, talking to MAWOS
- Trace viewer

### Phase C — the flagship
- `reschedule_for_absence` write tool, behind the guard
- Chronos repair-mode solve endpoint (unavailable + locked → diff)
- Diff UI with confirm/reject
- The downstream cascade

### Phase D — depth
- Requests & approvals (leave, room booking, timetable-change requests) as a real module
- Data rework per §6
- Admin analytics that use the richer data

### Will not build
- A second timetable algorithm — Chronos's MRV **is** the second algorithm
- Rewriting MAWOS's ERP CRUD screens before the agent work is done
- Any new research instrument

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Two stacks is more to run | It is also the topology v5 already planned. One command per side; both deploy independently |
| Two ORMs over one DB drift | Strict table ownership; no cross-ORM writes; cross-domain access over HTTP only |
| Chronos is unreviewed 30-minute code | It works, and it is ours. Read the solver before trusting it in a demo; it is 755 lines |
| Free-tier rate limits during a live demo | The lexicon fast path keeps ~90% of traffic off the provider. Warm Render before demoing |
| The re-aim becomes a third rewrite | It is not a rewrite. The guard, tools, agents, MCP and trace are untouched; the *timetable and the shell* are replaced by something that already exists |

---

## 9. Success criterion

> An admin opens the ERP, types *"Prof. Rao is out Thursday afternoon — fix the timetable"*,
> is asked one clarifying question, sees a proposed diff of three moved lessons with the cost
> delta, approves it, watches the solver animate the repair, and can then open the trace and
> see every step — including the guard's authorisation — recorded.

Everything in §7 serves that sentence.
