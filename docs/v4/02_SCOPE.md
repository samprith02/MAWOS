# 02 — Scope: MVRS and the Build Boundary

Covers R0 requirements **2** (final MVRS scope) and **11** (MUST / SHOULD / NICE /
DO-NOT-BUILD boundaries).

**This document governs every other document.** Where another file describes a capability,
its tier here decides whether it gets built.

---

## 1. The Minimum Viable Research System

> **MVRS = a system where an LLM plans and delegates real work across at least three
> autonomous agents; every action is guarded and traced; at least one workflow writes to the
> institution under human confirmation; and a task benchmark measures the result — running
> on a deployed instance.**

That is a strong, defensible final-year project **on its own**. Everything past it is upside,
not obligation.

### 1.1 MVRS by dimension

| Dimension | MVRS minimum | Deliberately excluded from MVRS |
|---|---|---|
| **Agents** | Orchestrator + **3** domain agents: Scheduling, Attendance & Monitoring, Compliance | Comms as a policy agent (ships as a bus subscriber) |
| **ERP modules** | Attendance · Timetable · Records/Marks · Eligibility (hall ticket) · Fees (rules only) | Admissions, placements ML, scholarship ML, general requests module |
| **Workflows** | **One** write-bearing multi-agent cascade, end to end, with confirmation | Leave requests, re-evaluation requests, room booking |
| **AI capability** | Conversation memory · plan → delegate → observe · bounded re-plan (N=1) · clarification · guard layer · write confirmation · provenance gate · full trace | Streaming tokens, proactive LLM behaviour, re-plan depth > 1 |
| **Timetable** | Existing greedy + SA, **plus** rooms, generalised unavailability, counterfactual scoring | Lab blocks, load caps, MRV backtracking, capacity, breaks |
| **Evaluation** | ~70-task outcome-checked suite · ~20-item adversarial guard suite · grounding rate · **one** provider · 3 seeds | Second-provider degradation run, full factorial |
| **UI** | Existing vanilla SPA **plus three panels**: chat with clarification/confirmation, agent trace, solver stream | Next.js rewrite |
| **Deployment** | Runs on Postgres · containerised · deployed once to a free host with a live URL · visible degradation banner | Multi-region, CI/CD pipeline, monitoring stack |

### 1.2 The MVRS demonstration

One cascade, entirely composed of parts that already exist, newly driven by a plan:

> A faculty member asks the assistant to mark today's attendance for a section, naming two
> absentees. The Orchestrator resolves the section from conversation context, finds the
> subject is missing, **asks**. Given it, it plans: validate → write → observe. The guard
> confirms the faculty member owns that subject-section assignment. The proposed write is
> shown; the user confirms. **Attendance** validates and recomputes; **Compliance**
> re-evaluates hall-ticket eligibility for the affected students; **Comms** alerts the two
> now in shortage. The assistant reports what changed, grounded in tool output, with the
> full trace attached.

Every hop of that cascade exists in v3 today. What is new: an LLM planned it, a guard
authorised it, a human confirmed the write, and the whole chain is one inspectable trace.

---

## 2. The build boundary

### 2.1 MUST HAVE — MVRS collapses without these

**Foundations**
- Fictional institution identity as configuration (`institution.yaml`); zero hardcoded
  institution names anywhere in code
- Deterministic, seeded, scale-parameterised data generator
- New schema: rooms, teacher availability, conversations, traces, one request type
- Postgres-capable configuration + Alembic migrations
- Small hand-built fixtures with fully known ground truth

**LLM layer**
- Provider abstraction (no provider-specific code above the interface)
- **R0.5 provider viability probe** with thresholds pre-registered before any run
- Three-tier fallback ladder with a visible active-tier indicator
- Deterministic tier that degrades to a structured action or a UI control — never to a
  confident guess

**Agent runtime**
- Persisted conversation memory (turns, resolved entities, pending states, plan state)
- Plan → delegate → observe loop with bounded re-plan (N = 1)
- Typed delegation contract: `Task` → `Result | NeedInfo | Refusal`
- Clarification as a first-class outcome that stops the turn
- Deterministic, non-bypassable guard layer logging both allowed and blocked outcomes
- At least **3 write tools** with a human confirmation turn
- Provenance gate wired into the new synthesis step
- Full per-turn trace persisted and renderable

**Timetable**
- Room as a real decision variable (clash + type)
- Generalised teacher unavailability
- Counterfactual scoring endpoint (apply → rescore → undo)

**Workflows**
- One end-to-end write cascade spanning at least three agents

**Evaluation**
- ~70-task benchmark with gold **outcomes** and category labels
- Deterministic outcome checker
- ~20-item adversarial guard suite
- Runs with seed variance reported

**Deployment**
- Deployed instance on Postgres with a live URL
- Real JWT secret required in production; rate limiting; CORS configuration

**Removals** (these are MUST-tier work, not optional tidying)
- Real institution identity (name, principal, USN prefix, email domain, crest)
- Admissions module
- `fl/` federated-learning PoC
- Scholarship CART model and placement RF model

### 2.2 SHOULD HAVE — materially strengthens the project

Build only after every MUST is green.

| Item | Value |
|---|---|
| Comms promoted to a policy agent (dedup, priority, digest, suppression) | The 4th agent; makes "decides not to act" demonstrable |
| Second provider run → the degradation claim | **Highest research value of the postponed set** (`07_CONTRIBUTION.md` claim 2) |
| Requests & Approvals as a general module (leave, correction, re-evaluation) | Richer multi-agent demonstration than the attendance cascade |
| Bus outbox + replay | Closes v3's documented at-most-once weakness; makes recovery measurable |
| Min-conflicts repair fallback when the greedy seed fails | Cheap insurance once rooms land |
| Multi-period contiguous lab blocks | The most realistic missing timetable feature; needs a new annealer move type |
| Teacher max-per-day / max-per-week caps | Cheap counters, but they add constraint interaction |
| Timetable diagnosis ("why does Wednesday start at P2?") | Complements the counterfactual |
| Streaming token output in chat | Perceived quality; no correctness impact |
| Benchmark expansion to ~120 tasks | Tighter confidence intervals per stratum |

### 2.3 NICE TO HAVE — only with genuine slack

Next.js frontend rewrite · CP-SAT oracle in `evaluation/` (proven optimum on small
instances) · ITC-2007 E4b (still blocked on instance files) · room capacity constraints ·
break/lunch slot modelling · proactive agent behaviour beyond the existing scans · 3-seed ×
2-provider full factorial · conversation export · admin analytics dashboards.

### 2.4 DO NOT BUILD

| Item | Why not |
|---|---|
| **Admissions pipeline** | 400 records, a 4-stage batch pipeline, zero agent interaction, large UI surface. Its only chat-facing tool was already retired at v3's P2 |
| **Federated learning (`fl/`)** | Unused PoC with no path to being real |
| **Any new ML model** | The two existing ones are circular (trained on labels our own rules generated). Adding more repeats the mistake the guide already flagged |
| **A third-party agent framework** (LangChain, CrewAI, AutoGen) | They hide exactly the orchestration this project claims as its contribution. Plain Python plus the provider interface keeps it inspectable and measurable |
| **RAG over documents** | No corpus exists, and it imports a whole retrieval-evaluation burden for no claim |
| **Fine-tuning** | Cost, reproducibility, and it answers no question we are asking |
| **Voice / mobile / real payments / plugin system** | Demo theatre with no research content |
| **Peer-to-peer agent negotiation** | Hierarchical domain; a central orchestrator keeps the audit trail linear, which the permission claim depends on |
| **A second search algorithm on speculation** | MRV backtracking is gated on a pre-registered failure threshold, not on intuition (`05_TIMETABLE_SCOPE.md` §4) |
| **Re-inflating the agent count** | v3's P2 cut 10 to 4 under a stated criterion. Undoing that would discard the project's one honest architectural correction |

---

## 3. Scope rules

1. **The MUST column is the contract.** If time collapses, ship exactly it. A complete MVRS
   beats a half-finished superset.
2. **Nothing is promoted from SHOULD to MUST without removing something.** Scope is
   conserved.
3. **A NICE-tier item may never block a MUST-tier item**, including for review deadlines.
4. **Cutting is recorded, not silent.** Anything dropped is written into
   `07_CONTRIBUTION.md` as a stated limitation, in keeping with the project's rule that a
   null or reduced result is still a result.
5. **DO-NOT-BUILD is not a maybe.** Reversing an entry requires a dated entry in
   `OPEN_DECISIONS.md` §4 with the reason.

---

## 4. Effort shape (relative, not calendar)

Rough proportions of remaining implementation effort, for planning conversations:

| Phase | Share | Note |
|---|---|---|
| R1 foundations | ~20% | Schema + generator + Postgres; everything is downstream |
| R3 agent runtime | ~30% | The contribution. Highest value per unit effort |
| R2 timetable | ~15% | Four small additions to working code |
| R4 writes + cascade | ~10% | Mostly wiring existing pieces through the guard |
| R5 benchmark + evaluation | ~15% | Authoring is external; the checker is ours |
| R6 UI additions | ~5% | Three panels on the existing SPA |
| R7 deployment | ~5% | |

If the true available time is materially less than this shape implies, the correct response
is to cut **SHOULD-tier items first, in the order listed in `09_ROADMAP.md` §4** — never to
half-build a MUST.
