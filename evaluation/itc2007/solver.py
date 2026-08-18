"""Simulated annealing over the CB-CTT model, sharing P1's search design.

Same shape as `backend/app/scheduler.py`: a cheap constructive seed, then
Metropolis acceptance with geometric cooling over a hard-feasible move
set, with incremental cost so a move costs O(neighbourhood) rather than a
full rescore. Only the objective and the moves differ, because the
problems differ - CB-CTT has rooms, this one does not.

The point of running it here is external comparability, nothing more.
Plan 4.4: *"the scheduler implementation was evaluated against a standard
timetabling benchmark to establish baseline competitiveness"* - never a
contribution, and if the gap to published bests is large that is reported.

Hard violations are weighted, not forbidden. The competition ranks by
distance-to-feasibility first and soft cost second, so `HARD_WEIGHT` is
set far above any reachable soft cost, which makes the scalar objective
agree with the lexicographic one in practice while still letting the
search pass through infeasible states.

`cost()` here must always equal `ctt.cost()` on the same assignment;
`tests/test_itc2007.py` asserts that after random move sequences, which is
the only thing keeping the incremental bookkeeping honest.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import ctt

#: Far above any soft cost seen on the comp set (published bests are in
#: the tens). Makes "one fewer violation" always beat any soft gain.
HARD_WEIGHT = 100_000


class Solution:
    """A CB-CTT assignment with incrementally maintained cost.

    `at[c][p] = room` (1-based, absent = unscheduled). Every course holds
    at most one lecture per period, which matches the validator's own
    representation, so the Lectures component can only be violated by
    scheduling the wrong *number* of lectures - and the moves below never
    change that number, so it stays 0 throughout.
    """

    def __init__(self, inst: ctt.Instance):
        self.inst = inst
        n = len(inst.courses)
        self.at: list[dict[int, int]] = [{} for _ in range(n)]
        self.sched_at: list[set[int]] = [set() for _ in range(inst.periods)]
        self.room_used: dict[tuple[int, int], int] = {}
        self.cpl: list[list[int]] = [[0] * inst.periods
                                     for _ in inst.curricula]
        self.days: list[dict[int, int]] = [{} for _ in range(n)]
        self.rooms_of: list[dict[int, int]] = [{} for _ in range(n)]

        self.conflicts = 0
        self.availability = 0
        self.room_occupation = 0
        self.room_capacity = 0
        self.min_days = 0          # unweighted day shortfall
        self.compact = 0           # unweighted isolated-lecture count
        self.stability = 0         # unweighted extra-room count

        for c in range(n):
            self.min_days += inst.courses[c].min_working_days

    # ---------------------------------------------------------- helpers

    def _compact_at(self, g: int, p: int) -> int:
        """Isolation contribution of one period, mirroring the validator."""
        row = self.cpl[g]
        n = row[p]
        if n == 0:
            return 0
        ppd = self.inst.periods_per_day
        periods = self.inst.periods

        def at(q: int) -> int:
            return row[q] if 0 <= q < periods else 0

        if p % ppd == 0:
            return n if at(p + 1) == 0 else 0
        if p % ppd == ppd - 1:
            return n if at(p - 1) == 0 else 0
        return n if at(p + 1) == 0 and at(p - 1) == 0 else 0

    def _compact_window(self, g: int, p: int) -> int:
        """Contribution of p and its two neighbours inside the same day."""
        ppd = self.inst.periods_per_day
        day = p // ppd
        total = 0
        for q in (p - 1, p, p + 1):
            if 0 <= q < self.inst.periods and q // ppd == day:
                total += self._compact_at(g, q)
        return total

    def _shortfall(self, c: int) -> int:
        want = self.inst.courses[c].min_working_days
        return max(0, want - len(self.days[c]))

    # ------------------------------------------------------------ moves

    def place(self, c: int, p: int, r: int) -> None:
        inst = self.inst
        gs = inst.member_of[c]
        before = [self._compact_window(g, p) for g in gs]

        self.conflicts += len(inst.conflict[c] & self.sched_at[p])
        if not inst.available(c, p):
            self.availability += 1
        n = self.room_used.get((r, p), 0)
        self.room_occupation += max(0, n) - max(0, n - 1)
        self.room_used[(r, p)] = n + 1
        over = inst.courses[c].students - inst.room_capacity(r)
        if over > 0:
            self.room_capacity += over

        self.min_days -= self._shortfall(c)
        d = p // inst.periods_per_day
        self.days[c][d] = self.days[c].get(d, 0) + 1
        self.min_days += self._shortfall(c)

        used = len(self.rooms_of[c])
        self.rooms_of[c][r] = self.rooms_of[c].get(r, 0) + 1
        self.stability += max(0, len(self.rooms_of[c]) - 1) - max(0, used - 1)

        self.at[c][p] = r
        self.sched_at[p].add(c)
        for g in gs:
            self.cpl[g][p] += 1
        for g, was in zip(gs, before):
            self.compact += self._compact_window(g, p) - was

    def unplace(self, c: int, p: int) -> None:
        inst = self.inst
        r = self.at[c][p]
        gs = inst.member_of[c]

        del self.at[c][p]
        self.sched_at[p].discard(c)
        before = []
        for g in gs:
            before.append(self._compact_window(g, p))
        for g in gs:
            self.cpl[g][p] -= 1
        for g, was in zip(gs, before):
            self.compact += self._compact_window(g, p) - was

        self.conflicts -= len(inst.conflict[c] & self.sched_at[p])
        if not inst.available(c, p):
            self.availability -= 1
        n = self.room_used[(r, p)]
        self.room_occupation += max(0, n - 2) - max(0, n - 1)
        if n == 1:
            del self.room_used[(r, p)]
        else:
            self.room_used[(r, p)] = n - 1
        over = inst.courses[c].students - inst.room_capacity(r)
        if over > 0:
            self.room_capacity -= over

        self.min_days -= self._shortfall(c)
        d = p // inst.periods_per_day
        if self.days[c][d] == 1:
            del self.days[c][d]
        else:
            self.days[c][d] -= 1
        self.min_days += self._shortfall(c)

        used = len(self.rooms_of[c])
        if self.rooms_of[c][r] == 1:
            del self.rooms_of[c][r]
        else:
            self.rooms_of[c][r] -= 1
        self.stability += max(0, len(self.rooms_of[c]) - 1) - max(0, used - 1)

    # ------------------------------------------------------------- cost

    def cost_parts(self) -> ctt.Cost:
        lectures = sum(
            abs(len(self.at[c]) - self.inst.courses[c].lectures)
            for c in range(len(self.inst.courses)))
        return ctt.Cost(
            lectures=lectures,
            conflicts=self.conflicts,
            availability=self.availability,
            room_occupation=self.room_occupation,
            room_capacity=self.room_capacity,
            min_working_days=self.min_days * ctt.MIN_WORKING_DAYS_COST,
            curriculum_compactness=self.compact
            * ctt.CURRICULUM_COMPACTNESS_COST,
            room_stability=self.stability * ctt.ROOM_STABILITY_COST,
        )

    def objective(self) -> int:
        c = self.cost_parts()
        return c.violations * HARD_WEIGHT + c.total

    def assignment(self) -> dict[tuple[int, int], int]:
        return {(c, p): r for c, row in enumerate(self.at)
                for p, r in row.items()}


def seed(inst: ctt.Instance, rng: random.Random) -> Solution:
    """Constructive start: every lecture placed, preferring a period the
    course is available in and a room that is free and large enough.

    It is allowed to fail into an infeasible placement rather than
    backtrack. Annealing is what resolves conflicts; a seed that refuses
    to finish would just move the search's job earlier.
    """
    sol = Solution(inst)
    order = sorted(range(len(inst.courses)),
                   key=lambda c: -inst.courses[c].lectures)
    nrooms = len(inst.rooms)
    for c in order:
        need = inst.courses[c].lectures
        periods = [p for p in range(inst.periods) if inst.available(c, p)]
        rng.shuffle(periods)
        periods += [p for p in range(inst.periods) if not inst.available(c, p)]
        placed = 0
        for p in periods:
            if placed == need:
                break
            if p in sol.at[c]:
                continue
            free = [r for r in range(1, nrooms + 1)
                    if (r, p) not in sol.room_used]
            pool = [r for r in free
                    if inst.room_capacity(r) >= inst.courses[c].students]
            r = rng.choice(pool or free or list(range(1, nrooms + 1)))
            sol.place(c, p, r)
            placed += 1
    return sol


@dataclass
class Result:
    cost: ctt.Cost
    objective: int
    assignment: dict
    steps: int
    seed_objective: int
    trace: list[tuple[int, int]]


def anneal(inst: ctt.Instance, seed_value: int = 0, steps: int = 200_000,
           t0: float = 12.0, t1: float = 0.05,
           trace_every: int = 0) -> Result:
    rng = random.Random(seed_value)
    sol = seed(inst, rng)
    start = sol.objective()
    best = start
    best_assignment = sol.assignment()
    nrooms = len(inst.rooms)
    lectures = [(c, p) for c in range(len(inst.courses)) for p in sol.at[c]]
    if not lectures:
        return Result(sol.cost_parts(), start, best_assignment, 0, start, [])

    decay = (t1 / t0) ** (1.0 / max(1, steps))
    temp = t0
    cur = start
    trace: list[tuple[int, int]] = []

    for step in range(steps):
        temp *= decay
        i = rng.randrange(len(lectures))
        c, p = lectures[i]
        if p not in sol.at[c]:            # stale entry after a swap
            continue
        r = sol.at[c][p]

        if rng.random() < 0.75:
            np_ = rng.randrange(inst.periods)
            nr = rng.randrange(1, nrooms + 1)
            if np_ == p and nr == r:
                continue
            if np_ != p and np_ in sol.at[c]:
                continue
            sol.unplace(c, p)
            sol.place(c, np_, nr)
            after = sol.objective()
            if after <= cur or rng.random() < math.exp((cur - after) / temp):
                cur = after
                lectures[i] = (c, np_)
            else:
                sol.unplace(c, np_)
                sol.place(c, p, r)
        else:
            j = rng.randrange(len(lectures))
            c2, p2 = lectures[j]
            if c2 == c or p2 not in sol.at[c2]:
                continue
            r2 = sol.at[c2][p2]
            if (p2 in sol.at[c] and p2 != p) or (p in sol.at[c2] and p != p2):
                continue
            sol.unplace(c, p)
            sol.unplace(c2, p2)
            sol.place(c, p2, r2)
            sol.place(c2, p, r)
            after = sol.objective()
            if after <= cur or rng.random() < math.exp((cur - after) / temp):
                cur = after
                lectures[i] = (c, p2)
                lectures[j] = (c2, p)
            else:
                sol.unplace(c, p2)
                sol.unplace(c2, p)
                sol.place(c, p, r)
                sol.place(c2, p2, r2)

        if cur < best:
            best = cur
            best_assignment = sol.assignment()
        if trace_every and step % trace_every == 0:
            trace.append((step, cur))

    return Result(cost=ctt.cost(inst, best_assignment), objective=best,
                  assignment=best_assignment, steps=steps,
                  seed_objective=start, trace=trace)
