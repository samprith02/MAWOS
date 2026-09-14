# 01 — Target Architecture, Agent Boundaries, Delegation Contract

Covers R0 requirements **1** (target architecture), **3** (agent boundaries and the
criterion), and **4** (communication / delegation contract).

---

## 1. The architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION      chat · dashboards · live solver · agent trace     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  REST + NDJSON stream
┌───────────────────────────────▼──────────────────────────────────────┐
│  GATEWAY           FastAPI · JWT · role scoping · rate limits        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│  ORCHESTRATOR      the only LLM-bearing component                    │
│                    resolve -> clarify -> plan -> execute -> observe  │
│                            -> re-plan (bounded) -> synthesise        │
│  owns: conversation memory · plan state · clarification              │
│        · confirmation · final answer                                 │
└───┬──────────────────────────────────────────────────────────────┬───┘
    │  delegation:  Task(goal, context, constraints)               │
    │  response:    Result | NeedInfo | Refusal                    │
┌───▼──────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────────▼───┐
│ SCHEDULING   │ │ ATTENDANCE │ │ COMPLIANCE   │ │ COMMS              │
│ constrained  │ │ continuous │ │ deterministic│ │ communication      │
│ search       │ │ monitoring │ │ rules        │ │ policy             │
│              │ │            │ │              │ │ (SHOULD-tier)      │
└───┬──────────┘ └─────┬──────┘ └──────┬───────┘ └────────┬───────────┘
    │                  │               │                  │
┌───▼──────────────────▼───────────────▼──────────────────▼───────────┐
│  GUARD LAYER       role · scope · write-authority · confirmation     │
│  deterministic · non-bypassable · every call, every action           │
└───────────────────────────────┬──────────────────────────────────────┘
┌───────────────────────────────▼──────────────────────────────────────┐
│  EVENT BUS         topic pub/sub · per-hop audit · fault isolation   │
└───────────────────────────────┬──────────────────────────────────────┘
┌───────────────────────────────▼──────────────────────────────────────┐
│  RECORDS SERVICE (not an agent)  +  SHARED CONTEXT STORE (Postgres)  │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.1 The three load-bearing ideas

**(a) Delegation, not method calls.** The Orchestrator sends a goal and receives one of three
outcomes. An agent that can answer *"I need the section"* or *"that is infeasible because
F12 is committed at that hour"* is an agent. One that returns a dict is a service. This is
the single change that fixes v3's query path, where
`agents["academic_agent"].student_profile(db, usn)` was a method call on a dict entry.

**(b) The guard is deterministic and cannot be bypassed.** The LLM proposes; the guard
disposes. Authorisation is never delegated to the prompt. This is inherited from v3, where
role checks already live in `tools.execute()` rather than in the system message — a correct
decision that v4 generalises from reads to writes.

**(c) Everything is traced.** Plan, delegation, tool call, guard verdict, provenance check —
all persisted under one `conversation_turn_id`. This is simultaneously the debugging story,
the explainability feature, and the evaluation instrument. The claims in
`07_CONTRIBUTION.md` are measurable *only because* this exists.

---

## 2. Layer responsibilities

| Layer | Owns | Explicitly does not own |
|---|---|---|
| Presentation | rendering, streaming display, confirmation UI | any authorisation decision |
| Gateway | authentication, role attachment, rate limiting | business rules |
| Orchestrator | language understanding, planning, delegation, clarification, synthesis, conversation memory | domain rules, data access, authorisation |
| Domain agents | one reasoning modality each (§3.2) | cross-domain coordination, user-facing language |
| Guard layer | role, scope, write-authority, confirmation state | domain semantics |
| Event bus | delivery, ordering within a cascade, audit, fault isolation | any decision about content |
| Records service | CRUD and queries over institutional entities | policy of any kind |
| Context store | durable state: institution, conversations, traces | logic |

**Rule:** authorisation appears in exactly one layer. If a role check appears in an agent, a
tool, or a prompt, that is a defect.

---

## 3. What qualifies as an agent

### 3.1 The criterion

A component is an **agent** if and only if it satisfies **all three** clauses:

> **(a) Persistent policy** — it owns state or policy that outlives a single request.
>
> **(b) Autonomous activation** — it acts on events without being directly invoked.
>
> **(c) Goal-level response** — it can accept a delegated *goal* and answer with a result,
> a request for missing information, or a reasoned refusal.

Clause (c) is new in v4 and is the one that matters. v3 used clauses (a) and (b) only, which
is why its agents were genuine on the event path and a facade on the query path: a component
can subscribe to a topic and still be nothing but a function when spoken to.

**Applying the criterion is mandatory and public.** Components that fail it are named as
failing it. Inflating the agent count is a worse outcome than a small one — v3's P2 already
cut 10 to 4 under a stated criterion, and re-inflating that would undo the project's one
honest architectural correction.

### 3.2 The boundary rule

> **Agents are separated by the *kind of reasoning* they perform, not by the domain they
> cover or the database table they read.**

This is why the answer is four and not ten. Each agent runs a materially different internal
mechanism — search, monitoring, rule evaluation, communication policy — and adding a new
*feature* usually extends an existing agent rather than creating one. Exam-hall allocation
is constrained search, so it belongs to Scheduling; it does not justify an Examinations
agent.

Stated negatively: **a new database table is never a reason for a new agent.**

### 3.3 The agents

| Agent | Reasoning modality | Owns | (a) | (b) | (c) |
|---|---|---|---|---|---|
| **Orchestrator** | language + planning | intent, plan, delegation, clarification, confirmation, synthesis, conversation memory | yes — conversation + plan state | yes — resumes pending confirmations | yes |
| **Scheduling** | constrained search / optimisation | timetable, room allocation, substitutions, what-if and counterfactuals, scoped re-solve | yes — current timetable + solver config | yes — `faculty.unavailable`, `assignment.changed` | yes — "infeasible because…" |
| **Attendance & Monitoring** | continuous monitoring + threshold detection | validated intake, recomputation, shortage and streak detection, proactive scans | yes — summaries, thresholds | yes — `attendance.uploaded` + its own scan loop | yes — rejects bad records with per-record reasons |
| **Compliance** | deterministic rule evaluation with reason codes | hall-ticket eligibility, scholarship status, placement eligibility, fee-driven blocks | yes — persisted verdicts + reasons | yes — `attendance.updated`, `fees.updated` | yes |
| **Comms** *(SHOULD-tier)* | communication policy | whether, whom, when and how loudly to notify — dedup, priority, digest, suppression | yes — delivery history, suppression state | yes — subscribes broadly | yes — can decline to notify |

### 3.4 Components that fail the criterion — named

| Component | Fails | Correct label |
|---|---|---|
| **Records** (students, faculty, subjects, marks, fees CRUD) | (a) no policy, (b) no activation, (c) no goal-level response | **service** |
| **Comms in MVRS** (template dispatch, as in v3) | (c) — five hardcoded templates make no decision | **bus subscriber** until promoted in R4 |
| **Guard layer** | (b) — purely reactive, by design | **policy layer** |
| **Event bus** | (a), (c) — infrastructure | **infrastructure** |
| **Solver** (`scheduler.py`) | (a), (b), (c) — a pure function | **library used by the Scheduling agent** |

### 3.5 Alternatives evaluated

| Structure | Verdict |
|---|---|
| **0 domain agents** (orchestrator + tools) | Rejected. This is what v3's query path actually is. Honest, but discards the working event-path cascade and the project's identity |
| **2 agents** (Orchestrator + Scheduling) | Rejected. Defensible on the grounds that Scheduling has the only genuinely hard autonomy — but Attendance and Compliance already satisfy all three clauses *in existing code* (proactive scan; persisted verdict state; reasoned record rejection). Demoting working agents to tell a leaner story is dishonesty in the other direction |
| **3 domain agents** (fold Comms into Compliance) | **Accepted as MVRS.** Comms is the marginal agent. It ships as a bus subscriber and is promoted only if the MUST tier lands early |
| **4 domain agents** | **Accepted as target.** "Should this person be told" is orthogonal to "is this person eligible"; merging them is v2's 10-agent error running backwards |
| **6+ agents** (split by module) | Rejected. Exactly what P2 cut. A new table is not a new agent |
| **Peer-to-peer negotiation** | Rejected. University workflows are hierarchical, and a single orchestrator keeps the audit trail linear — which the permission claim depends on. Agent-to-agent coupling belongs on the event bus |

**Open:** promoting Comms to a full agent is not locked. See `OPEN_DECISIONS.md` §D3.

---

## 4. Two communication channels, and when to use which

| | **Delegation** (synchronous) | **Events** (asynchronous) |
|---|---|---|
| Direction | Orchestrator to agent | any agent to any subscriber |
| Shape | `Task` in, `Result / NeedInfo / Refusal` out | fire-and-forget topic publish |
| Used for | goal-directed work the user is waiting on | propagating a state change |
| Caller knows the callee? | yes, by name | no |
| Failure | returned to the caller | isolated, logged as `agent.error` under the same `workflow_id` |
| Example | "regenerate AIML year-3 timetable avoiding Tuesday for F12" | `attendance.updated` triggers Compliance re-evaluation, then a Comms alert |

**Rule:** if a user is waiting for the outcome, delegate. If the outcome is a consequence
that other parts of the institution need to know about, publish.

**Agents never delegate to each other.** Cross-agent work happens either through the
Orchestrator (which owns the plan) or through the bus (which owns propagation). This keeps
every multi-agent interaction reconstructible from exactly one of two logs.

---

## 5. The delegation contract

```python
@dataclass(frozen=True)
class Task:
    goal: str                # what to achieve, in domain terms
    context: dict            # entities already resolved by the orchestrator
    constraints: dict        # limits the agent must respect
    actor: Actor             # who is asking — carried for the guard, never for logic
    turn_id: str             # ties every downstream record to one conversation turn
    dry_run: bool = False    # plan/preview only; no writes
```

Exactly three response types:

```python
@dataclass(frozen=True)
class Result:
    data: dict               # the payload; the only thing the LLM may ground on
    summary: str             # one line, for the plan trace — never shown verbatim
    effects: list[Effect]    # writes performed or proposed, for audit + confirmation
    confidence: str          # "exact" | "approximate" — set by the agent, not the LLM

@dataclass(frozen=True)
class NeedInfo:
    missing: list[str]       # field names the agent needs
    question: str            # a human-readable question the orchestrator may relay
    partial: dict | None     # anything already computed, so work is not thrown away

@dataclass(frozen=True)
class Refusal:
    reason_code: str         # INFEASIBLE | NOT_PERMITTED | OUT_OF_SCOPE | PRECONDITION_FAILED
    explanation: str         # why, in domain terms
    evidence: dict           # the facts supporting the refusal — must be verifiable
```

### 5.1 Contract rules

1. **An agent never raises for an expected outcome.** Infeasibility, missing information and
   lack of permission are `Refusal` / `NeedInfo`, not exceptions. Exceptions are bugs.
2. **`Refusal.evidence` must be checkable.** "Infeasible" alone is not a refusal; "F12 is
   committed to CSE-3B at Tue-P1 and no other qualified faculty is free" is.
3. **`NeedInfo` is a first-class success.** Asking is the correct behaviour when information
   is missing and not inferable. It is measured as its own benchmark category
   (`06_BENCHMARK.md`) and is never counted as failure.
4. **`Result.data` is the only grounding source.** The provenance gate checks the final
   answer against exactly these payloads. Anything not in a `Result` is ungrounded.
5. **Agents never see the raw user message.** The Orchestrator translates. This keeps
   prompt-injected text inside institutional records from reaching an agent as an
   instruction.
6. **`dry_run` must be honoured.** Every write-capable agent supports preview, because the
   confirmation step needs to show consequences before they happen.
7. **`actor` is for the guard, never for logic.** An agent must not branch on role; that is
   the guard's job, in one place.

---

## 6. The orchestration loop

```
1. RESOLVE      entities against conversation memory + caller identity
2. CLARIFY      if a required entity is missing and not inferable -> ask, stop the turn
3. PLAN         ordered steps; each = delegate | call-tool | ask-user
4. EXECUTE      guard-check every step; a write step requires prior confirmation
5. OBSERVE      reason over Results; re-plan (bounded, N <= 1 in MVRS)
6. SYNTHESISE   compose the answer -> provenance gate -> attach trace
```

### 6.1 Rules

- **Clarification stops the turn.** It does not guess and continue.
- **Re-planning is bounded.** N <= 1 in MVRS. Raising it is measurement-gated
  (`OPEN_DECISIONS.md` §D9).
- **A write is never executed in the same turn it is proposed.** The plan produces a proposed
  `Effect`; the user confirms; the next turn executes. This is what makes "the model never
  executed an unauthorised action" a property of the architecture rather than of the model.
- **Every step emits a trace record**, including steps the guard blocked. Blocked attempts
  are the primary signal for claim 1 in `07_CONTRIBUTION.md` — they must never be silently
  dropped.
- **Degradation is visible.** If the loop cannot complete, the response says which tier
  answered and why. Silent fallback to a lower tier is a defect — v3 did this, in
  `orchestrator.handle_chat`'s degradation path.

### 6.2 What is deliberately not in the loop

No autonomous goal generation, no self-directed background tasks, no tool creation, no
reflection loops beyond the single bounded re-plan. The claim in `07_CONTRIBUTION.md` is
about *bounded* autonomy; an unbounded loop would make the boundary unmeasurable.

---

## 7. The guard layer

Every tool call and every agent action passes through one deterministic check:

| Check | Question | Failure |
|---|---|---|
| **Role** | may this role use this capability at all? | `NOT_PERMITTED` |
| **Scope** | is the target inside the actor's scope? (a student is locked to themselves; an HOD to their department) | `NOT_PERMITTED` |
| **Write authority** | may this actor mutate this entity? | `NOT_PERMITTED` |
| **Confirmation** | for a write: has this exact effect been confirmed this conversation? | `PRECONDITION_FAILED` |

Properties the design must preserve:

1. **Deterministic.** No model output influences a verdict.
2. **Non-bypassable.** There is no code path from the Orchestrator to a tool that skips it.
3. **Logged on both outcomes.** An allowed call and a blocked attempt produce the same record
   shape, differing only in verdict — otherwise the attempt rate cannot be measured.
4. **Fails closed.** An unknown capability, an unknown role, or an unparseable target is
   denied.
5. **Independent of the prompt.** Removing the system prompt entirely must not change any
   verdict. This is testable, and will be a test.

---

## 8. Conversation memory

Per conversation, persisted — not in process memory, because it must survive restart and be
inspectable in the trace UI:

| Field | Purpose |
|---|---|
| `turns[]` | role, content, timestamp — the dialogue |
| `resolved_entities` | e.g. `{student: "...", section: "3A", semester: 5}` — what "she" or "that section" refers to |
| `pending_clarification` | the question asked and the field it fills |
| `pending_confirmation` | the proposed `Effect` awaiting a yes/no |
| `plan_state` | the current plan and which steps completed |
| `tier` | which LLM tier served each turn |

**Retention.** Conversations are institutional records and are scoped to their owner like any
other. They are subject to the same guard checks — a student cannot read another student's
conversation.

**Bound.** History sent to the model is truncated to a token budget, oldest turns dropped
first. `resolved_entities` is never dropped, because losing it is precisely what makes an
assistant feel amnesiac.

---

## 9. What v3 code carries forward unchanged

| Asset | File | Why it survives |
|---|---|---|
| Event bus + per-hop audit | `backend/app/bus.py` | Real pub/sub with fault isolation; every hop persisted with `workflow_id` and `elapsed_ms` |
| Executor-level role checks | `backend/app/agents/tools.py` | Correct placement; v4 generalises it from reads to writes |
| Provenance gate | `backend/app/provenance.py` | Deterministic, dependency-free, and more valuable as the LLM does more |
| Solver core | `backend/app/scheduler.py` | Bitmask state, incremental cost verified to 1e-9 against the frozen metric, exact bipartite matching in the seed |
| Frozen objective | `evaluation/benchmark/schedule_metrics.py` | Cross-validated against the official ITC-2007 validator on 1,900 pairs |
| Attendance intake + cascade | `backend/app/agents/attendance.py` | Validation with per-record reasons, recomputation, proactive scan |
| Evaluation protocol | `evaluation/PROTOCOL.md`, `freeze_manifest.py` | Instrument versioning, seed variance, changelog discipline |
