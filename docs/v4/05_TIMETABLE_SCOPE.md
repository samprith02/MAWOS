# 05 — Timetable Scope

Covers R0 requirement **7**.

**The governing concern:** the timetable engine must be strong enough to be a major MAWOS
capability without becoming a second project. Every decision below is made against that
constraint.

---

## 1. Where the two existing implementations actually stand

| | **MAWOS P1** (`backend/app/scheduler.py`) | **Chronos** (`teacher-erp-.../src/lib/solver/engine.ts`) |
|---|---|---|
| Search | compact greedy seed + simulated annealing, 120k steps | MRV backtracking + forward check + restarts → min-conflicts repair → hill-climb polish |
| Hard constraints | section clash, teacher clash, out-of-scope block mask | **+ rooms (type + capacity), teacher unavailability, teacher max/day + max/week, subject max/day, break slots** |
| Soft objective | 5 terms, frozen at P0, **cross-validated against the official ITC-2007 validator on 1,900 instance/solution pairs across all eight cost components** | ad-hoc; the polish phase optimises a *different* cost function than the search does |
| Cost evaluation | incremental delta, verified equal to the frozen full metric to 1e-9 | full recomputation of a partial cost |
| Explainability | aggregate objective + cost/temperature trace | **per-slot `FailReason`**: `class`/`teacher`/`unavail`/`dayload`/`spread`/`room`/`break` |
| Rigor | 10 seeds vs a preserved v2 baseline; distance-to-floor reported honestly (8.2 above a floor of 196.0) | single run, no seeds, no baseline, no validator |
| Completion | placement rate 1.000 or the solve is rejected | best-effort; can finish with lessons unplaced |
| Live view | replayed seed placements + cost curve | full decision stream over NDJSON driving a real-time UI |

**The two are strong in opposite places.** MAWOS has the better optimiser and the better
evidence; Chronos has the better constraint model and per-slot explainability. The read that
Chronos "works better" is about the *model* and the *UI*, not the algorithm.

**Decision: keep MAWOS's optimiser and frozen metric; adopt Chronos's constraint model and
its per-slot failure reasons; go past both on explanation.**

---

## 2. Minimum constraint model (MUST)

### 2.1 Hard constraints

| Constraint | Status |
|---|---|
| A section has at most one class per (day, period) | **exists** |
| A teacher is in at most one place per (day, period) — checked globally | **exists** |
| A room hosts at most one class per (day, period) | **new** |
| A class is placed only in a room of the required type | **new** |
| A teacher is never placed in an unavailable (day, period) | **~exists** — see §2.3 |
| Every subject receives exactly `credits` periods per week | **exists** |

### 2.2 Soft objective — unchanged

The five frozen terms stay exactly as they are: `idle_gap` (5.0), `late_start` (4.0),
`load_sigma` (2.0), `subject_repeat` (2.0), `faculty_gap` (1.0).

**Not touching the objective is a deliberate constraint on this phase.** The frozen metric is
hashed in `evaluation/FROZEN.sha256`, shared with the preserved v2 baseline, and
cross-validated against the ITC-2007 validator. Changing weights or adding terms would break
comparability with the one baseline that makes "we improved the scheduler" a measurable claim
rather than an assertion.

Whether rooms need a **room-stability** soft term (ITC-2007 track 3 has one) is **open** —
`OPEN_DECISIONS.md` §D7. It is added only if measurement shows room churn is bad without it,
and adding it would be a documented instrument change.

### 2.3 Why exactly these two additions and nothing more

**Rooms.** No real timetable omits them, and their absence is precisely what forced v3 to
descope ITC-2007 track 3 (`RESEARCH_PLAN_V3.md` §0.2(b): *"MAWOS has no room model —
`room` is a cosmetic f-string"*). The cost is genuinely small, for a structural reason:
**a room is a resource with multiplicity.** A teacher is unique, so a teacher clash kills a
slot outright; a slot only fails on rooms when *every* room of the required type is busy.
With a sensibly sized inventory, rooms constrain the search far more weakly than teachers
already do. Implementation is one additional mask dictionary in `Schedule` plus a room
selection step — not a new search problem.

**Unavailability.** This is **roughly 80% already built.** `Schedule.__init__` already carries
`blocked: dict[(faculty_id, day), int]`, a period mask of commitments outside the scope being
solved (`scheduler.py:114`), and `free_for()` and `teacher_busy()` already honour it. What
changes is only the *source* of those bits: today they come from other departments' existing
slots; in v4 they additionally come from `FacultyAvailability` rows. That is a handful of
lines, and it is what makes leave-driven re-solving possible at all.

---

## 3. Minimum algorithm

### 3.1 A correction recorded in full

An earlier draft of this rework recommended a **two-stage MRV-backtracking + SA solver** as
mandatory. **That recommendation is withdrawn.** It was justified by the speculation that
adding rooms would make the greedy seed fail often. Checking the code shows the reasoning is
weak on both sides:

- Rooms are a multiplicity resource (§2.3) and therefore a weak constraint.
- The existing seed is not naive greedy. `_match()` computes an **exact maximum bipartite
  matching** of a section's items to its compact target cells by augmenting paths
  (`scheduler.py:270-298`), explicitly so that *"pure greedy strands items whenever a busy
  teacher takes the last cell they could have used"*. It then overflows leftovers to the
  cheapest legal cell, and `solve()` restarts up to 3 times on `Unplaceable`.

Building a second complete search algorithm before observing the first one fail is exactly
the scope creep this document exists to prevent. The decision is therefore **gated on
measurement** (§4).

### 3.2 The pipeline

| # | Piece | Status | Effort |
|---|---|---|---|
| 1 | Compact greedy seed + exact maximum bipartite matching | **exists** | — |
| 2 | Simulated annealing, incremental delta cost, geometric cooling | **exists** | — |
| 3 | Room dimension in feasibility and state | new | small |
| 4 | Generalised unavailability source | ~exists | tiny |
| 5 | **Counterfactual scoring** (apply → rescore → undo) | new | tiny |
| 6 | Per-slot failure reasons | new | small |
| 7 | Min-conflicts repair fallback on `Unplaceable` | new | ~60 lines · **SHOULD** |
| 8 | MRV / backtracking feasibility stage | not built | **gated — §4** |

**On (5):** counterfactual scoring is nearly free because the primitives already exist.
`Schedule.apply(moves)` returns the exact cost delta and `Schedule.undo()` reverses it
(`scheduler.py:200-230`). A counterfactual is: apply the hypothetical move, read the delta,
undo. The answer is therefore **computed, not generated** — this is what makes the
explanation claim (`07_CONTRIBUTION.md` claim 4) checkable rather than plausible.

**On (6):** borrow Chronos's `FailReason` enum directly. When a candidate cell is rejected,
record *which* constraint rejected it. This is the input to both the live trace and the
diagnosis feature.

### 3.3 Which classical techniques are genuinely necessary

| Technique | Verdict | Reason |
|---|---|---|
| **Simulated annealing** | **Necessary** | It is the optimiser, it is validated against the frozen metric, and it is what produced the measured v2→P1 improvement. Keep |
| **Greedy construction seed** | **Necessary** | The construction phase. Already produces a gap-free, late-start-free layout by design — honestly reported in `e4.md` as construction rather than search |
| **Maximum bipartite matching** | **Necessary** | Already present; removes a whole class of avoidable overflow |
| **Min-conflicts repair** | **SHOULD** | Cheap insurance once rooms land. Borrow Chronos's Phase 3 |
| **MRV / forward-checking / backtracking** | **Gated on §4** | Not built on speculation |
| **Hill-climbing polish** | **Not needed** | SA already accepts improving moves; a separate polish phase optimising a different cost is Chronos's weakness, not a feature |

---

## 4. The pre-registered MRV trigger

> **Build the MRV/backtracking feasibility stage if and only if, on the R1-generated
> institution with rooms and unavailability enabled, the greedy seed fails to produce a
> complete hard-feasible assignment in more than 5% of attempts over 10 seeds — after
> restarts and after min-conflicts repair have both been applied.**

- **Instrumented in:** R2, as part of `evaluation/scheduler_eval.py`.
- **Recorded in:** `evaluation/results/v4_scheduler/seed_failure.json`.
- **If the trigger fires:** MRV is promoted to MUST and the decision is logged in
  `OPEN_DECISIONS.md` §4 with the measurement.
- **If it does not fire:** MRV is **not built**, and the reason is recorded so a later phase
  cannot quietly add it.

The threshold is fixed now, before the measurement exists.

---

## 5. Postponement tiers

| Feature | Tier | Note |
|---|---|---|
| Counterfactual / what-if scoring | **MUST** | The explanation contribution; nearly free |
| Room clash + room type | **MUST** | |
| Generalised unavailability | **MUST** | |
| Per-slot failure reasons | **MUST** | Feeds trace and diagnosis |
| Min-conflicts repair fallback | SHOULD | |
| Diagnosis ("why does Wednesday start at P2?") | SHOULD | Trace-back over the blocking masks |
| Multi-period contiguous lab blocks | SHOULD | Needs a new annealer move (block relocate) and a seed change — genuine work. Schema field lands in R1 so the schema does not change twice |
| Teacher max-per-day / max-per-week | SHOULD | Two counters; adds constraint interaction |
| Room capacity | NICE | Needs per-section headcount; adds little given typed rooms |
| Break / lunch slots | NICE | The existing 6-period grid already implies a lunch gap between P3 and P4 |
| Subject max-per-day as a **hard** constraint | NICE | Already priced as a soft penalty |
| Room-stability soft term | **OPEN** — §D7 | Would change the frozen instrument |
| CP-SAT oracle in `evaluation/` | NICE | See §6 |
| ITC-2007 E4b | NICE | Unblocked by rooms, but still blocked on instance files |

---

## 6. Rejected approaches

### 6.1 Port Chronos's engine wholesale — rejected

It has no verified cost model, no seed-variance reporting, and no baseline; and its polish
phase optimises a different objective than its search, so its reported `score` is not the
quantity the search minimised. Adopting it would discard the single externally validated
artefact this project owns — a cost model that agrees with the **official ITC-2007
validator on 1,900 pairs**. Take its constraint model and its `FailReason` enum; leave its
search.

### 6.2 Replace everything with OR-Tools CP-SAT — rejected as the production solver

It would very likely beat both, and that is precisely the problem: it reduces the timetable to
a library call, deleting the measurable algorithmic work, and it adds a heavy dependency to a
deployment that must run on a free tier.

**But it is the right tool for one job.** As a NICE-tier addition inside `evaluation/` only,
CP-SAT can prove an optimum on small instances, letting the project report **how far the SA
lands from a proven optimum** rather than only from an estimated floor. That is a genuinely
strong evaluation move at zero production risk — and it is off the critical path.

### 6.3 Change the objective weights — rejected

The five weights are frozen, hashed, and shared with the preserved v2 baseline. Re-tuning them
would make the before/after comparison an artefact of two different definitions of "gap" —
the exact failure mode `scheduler.py`'s own docstring says the frozen metric exists to
prevent.

---

## 7. Regression gate for R2

The timetable is a *capability*, so it must not get worse while gaining constraints.

**R2 does not close until:**

1. `evaluation/scheduler_eval.py` shows the room-aware solver is **no worse** than current P1
   on the frozen objective for the existing constraint set, over 10 seeds, mean ± std.
2. Placement rate remains 1.000; teacher conflicts and section conflicts remain 0.
3. **Room conflicts are 0** and every class sits in a room of its required type.
4. **No teacher is scheduled into an unavailable slot.**
5. `evaluation/itc2007/crosscheck.py` still passes — the cost model has not drifted.
6. `verify_against_frozen()` still agrees with the frozen metric to 1e-9.
7. Seed-failure rate is recorded against the §4 trigger, whether or not it fires.

Because the frozen metric and the preserved v2 baseline both still exist, a regression here is
**detectable rather than arguable**. That is the property worth protecting.

---

## 8. What this deliberately gives up

Stated plainly so it appears in the write-up rather than being discovered by an examiner:

- **No claim of algorithmic novelty.** SA for timetabling is decades old; v3 already retracted
  that claim (`RESEARCH_PLAN_V3.md` §0.3), and v4 does not revive it.
- **The constraint model remains smaller than ITC-2007 track 3**, which also has room
  stability, curriculum compactness, and min-working-days. v4 adds rooms and availability; it
  does not claim parity.
- **Idle gaps reaching zero is mostly construction, not search** — the seed lays out compact
  days by design. `e4.md` already says this, and v4 keeps saying it. The number that is not
  built in is the distance to the instance floor.
- **Lab blocks are the most realistic missing feature** and are SHOULD-tier, so the MVRS
  timetable may ship without them.
