"""P1 — timetable solver: compact greedy seed + simulated annealing.

Pure and DB-free on purpose: the agent in `agents/timetable.py` reads
`TeachingAssignment` rows and hands this module plain tuples, so the
solver can be run 10 seeds at a time without touching SQLite.

What was wrong with v2
----------------------
The frozen v2 solver (`evaluation/baselines/scheduler_v2.py`) optimises
**hard feasibility only**. It drops each subject into a randomly ordered
free cell, so a schedule with holes at 09:00 and 12:15 scores exactly as
well as a compact one — it has no score at all. Measured over 10 seeds on
the shipped institution: 80.8 of 200 section-days start after first
period, and 223 idle gaps sit inside days.

The objective
-------------
`evaluation/benchmark/schedule_metrics.objective`, frozen at P0 and shared
with the baseline so that "we improved the scheduler" cannot be an
artefact of two different definitions of "gap". This module re-implements
the same arithmetic **incrementally**, because the full metric is
O(slots) and annealing needs ~10^5 evaluations. `verify_against_frozen()`
checks the two agree; if they ever diverge the incremental version is
wrong by definition, since the frozen one is the instrument.

Representation
--------------
A section-day's occupancy is a 6-bit mask, so gaps, late starts and loads
are table lookups rather than list scans.

Two structural decisions
------------------------
**Every section-day keeps at least one class.** Not for pedagogy — the
frozen metric divides by the number of *non-empty* section-days, so a
solver that empties a Friday shrinks the denominator and scores better
without scheduling better. v2 never does this (all 200 section-days are
occupied), so allowing it would break comparability too. The invariant
blocks the exploit and keeps the incremental cost exactly equal to the
frozen one. This is a defect in the objective, found by trying to
optimise it, and it is recorded rather than quietly patched — the metric
is frozen.

**The seed builds a perfectly compact shape first, then fills it.** Each
section's daily loads are the most even split of its credits (18 → 4,4,4,
3,3 in a random day order) and its cells are periods 0..load-1. That
shape has zero gaps and zero late starts *by construction*, so the search
starts on the good side of the two dominant penalties and spends its
budget on teacher conflicts instead of digging out of holes it made
itself. Cells that cannot be filled without double-booking a teacher
overflow to a later period, and that is exactly where annealing works.
"""
import math
import random
from collections import defaultdict

N_DAYS, N_PERIODS = 5, 6

#: Mirrors schedule_metrics.objective's defaults. Kept here so the solver
#: is self-contained; the equality is asserted by verify_against_frozen().
DEFAULT_WEIGHTS = {"idle_gap": 5.0, "late_start": 4.0, "load_sigma": 2.0,
                   "subject_repeat": 2.0, "faculty_gap": 1.0}


class Unplaceable(RuntimeError):
    """The seed could not place every period. The caller should restart."""


# --------------------------------------------------------------- mask tables
def _build_tables():
    n = 1 << N_PERIODS
    pop, gap, late = [0] * n, [0] * n, [0] * n
    for m in range(n):
        bits = [p for p in range(N_PERIODS) if m & (1 << p)]
        pop[m] = len(bits)
        gap[m] = (bits[-1] - bits[0] + 1) - len(bits) if len(bits) > 1 else 0
        late[m] = 1 if bits and bits[0] != 0 else 0
    return pop, gap, late


POP, GAP, LATE = _build_tables()


def _pstdev5(loads) -> float:
    """Population sd of five day-loads.

    Inlined rather than calling statistics.pstdev, which on 3.12 routes
    through exact Fraction arithmetic and dominates the annealing loop.
    Agreement with the frozen metric is checked to 1e-9 relative.
    """
    mean = (loads[0] + loads[1] + loads[2] + loads[3] + loads[4]) / N_DAYS
    var = sum((x - mean) ** 2 for x in loads) / N_DAYS
    return math.sqrt(var)


# ------------------------------------------------------------------ the state
class Schedule:
    """A complete assignment plus the incremental cost of it.

    `demands` is a list of (section_key, subject_code, faculty_id), one
    entry per period to be taught — a 4-credit subject appears four times.
    """

    def __init__(self, demands, weights=None, blocked=None):
        self.w = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.items = list(demands)
        #: (faculty_id, day) -> period mask of commitments *outside* the
        #: scope being solved. Scoped regeneration (one department) must
        #: not double-book a teacher against the departments it is not
        #: touching. These bits gate feasibility but are deliberately
        #: excluded from the cost: the frozen metric only sees in-scope
        #: slots, and keeping the two identical is worth more than
        #: charging the solver for gaps it cannot close. Institution-wide
        #: generation — the case E4 measures — has none of them.
        self.blocked: dict[tuple[int, int], int] = dict(blocked or {})
        self.sections = sorted({s for s, _, _ in self.items})
        self.sec_index = {s: i for i, s in enumerate(self.sections)}

        self.pos: list[tuple[int, int] | None] = [None] * len(self.items)
        self.cell: dict[tuple[int, int, int], int] = {}
        self.sec_mask = [[0] * N_DAYS for _ in self.sections]
        self.fac_mask: dict[tuple[int, int], int] = defaultdict(int)
        self.subj_count: dict[tuple[int, int, str], int] = defaultdict(int)
        self._undo: list[tuple[int, int, int]] = []

    # -------------------------------------------------------- cost fragments
    def _sec_day_cost(self, si: int, d: int) -> float:
        m = self.sec_mask[si][d]
        return self.w["idle_gap"] * GAP[m] + self.w["late_start"] * LATE[m]

    def _fac_day_cost(self, fid: int, d: int) -> float:
        return self.w["faculty_gap"] * GAP[self.fac_mask[(fid, d)]]

    def _subj_cost(self, si: int, d: int, subj: str) -> float:
        return (self.w["subject_repeat"]
                if self.subj_count[(si, d, subj)] > 1 else 0.0)

    def _sigma_cost(self, si: int) -> float:
        """The load-balance term, algebraically identical to the frozen one.

        frozen: w * mean_over_sections(pstdev(loads)) * n_section_days.
        With every section-day occupied, n_section_days = 5 * n_sections,
        so each section contributes w * 5 * pstdev(loads_s).
        """
        masks = self.sec_mask[si]
        loads = (POP[masks[0]], POP[masks[1]], POP[masks[2]],
                 POP[masks[3]], POP[masks[4]])
        return self.w["load_sigma"] * N_DAYS * _pstdev5(loads)

    def cost(self) -> float:
        """Full recomputation. Used to seed the loop and to check drift."""
        total = 0.0
        for si in range(len(self.sections)):
            total += self._sigma_cost(si)
            for d in range(N_DAYS):
                total += self._sec_day_cost(si, d)
        total += self.w["subject_repeat"] * sum(
            1 for v in self.subj_count.values() if v > 1)
        total += self.w["faculty_gap"] * sum(
            GAP[m] for m in self.fac_mask.values())
        return total

    # ------------------------------------------------------------ primitives
    def free_for(self, item: int, d: int, p: int) -> bool:
        sec, _subj, fid = self.items[item]
        if self.sec_mask[self.sec_index[sec]][d] & (1 << p):
            return False
        if self.blocked.get((fid, d), 0) & (1 << p):
            return False
        return not (self.fac_mask[(fid, d)] & (1 << p))

    def teacher_busy(self, fid: int, d: int, p: int) -> bool:
        bit = 1 << p
        return bool((self.fac_mask[(fid, d)] | self.blocked.get((fid, d), 0))
                    & bit)

    def place(self, item: int, d: int, p: int) -> None:
        sec, subj, fid = self.items[item]
        si = self.sec_index[sec]
        self.cell[(si, d, p)] = item
        self.pos[item] = (d, p)
        self.sec_mask[si][d] |= 1 << p
        self.fac_mask[(fid, d)] |= 1 << p
        self.subj_count[(si, d, subj)] += 1

    def lift(self, item: int) -> tuple[int, int]:
        sec, subj, fid = self.items[item]
        si = self.sec_index[sec]
        d, p = self.pos[item]
        del self.cell[(si, d, p)]
        self.pos[item] = None
        self.sec_mask[si][d] &= ~(1 << p)
        self.fac_mask[(fid, d)] &= ~(1 << p)
        self.subj_count[(si, d, subj)] -= 1
        return d, p

    def day_load(self, si: int, d: int) -> int:
        return POP[self.sec_mask[si][d]]

    # ------------------------------------------------------- move application
    def apply(self, moves) -> float:
        """Apply [(item, day, period), ...] and return the exact cost delta.

        Every item must already be placed. All are lifted before any is
        re-placed, so a swap never sees itself as an occupant.
        """
        secs, facs, subjs, loads = set(), set(), set(), set()
        for item, d, _p in moves:
            sec, subj, fid = self.items[item]
            si = self.sec_index[sec]
            d0, _p0 = self.pos[item]
            for dd in (d0, d):
                secs.add((si, dd))
                facs.add((fid, dd))
                subjs.add((si, dd, subj))
            loads.add(si)

        before = self._fragment(secs, facs, subjs, loads)
        self._undo = [(item, *self.pos[item]) for item, _d, _p in moves]
        for item, _d, _p in moves:
            self.lift(item)
        for item, d, p in moves:
            self.place(item, d, p)
        return self._fragment(secs, facs, subjs, loads) - before

    def undo(self) -> None:
        for item, _d, _p in self._undo:
            self.lift(item)
        for item, d, p in self._undo:
            self.place(item, d, p)

    def restore(self, cells: dict) -> None:
        for item in range(len(self.items)):
            if self.pos[item] is not None:
                self.lift(item)
        for (_si, d, p), item in cells.items():
            self.place(item, d, p)

    def _fragment(self, secs, facs, subjs, loads) -> float:
        total = 0.0
        for si, d in secs:
            total += self._sec_day_cost(si, d)
        for fid, d in facs:
            total += self._fac_day_cost(fid, d)
        for si, d, subj in subjs:
            total += self._subj_cost(si, d, subj)
        for si in loads:
            total += self._sigma_cost(si)
        return total

    # ------------------------------------------------------------------ export
    def slots(self) -> list[dict]:
        out = []
        for (si, d, p), item in self.cell.items():
            (dept, year, sec), subj, fid = self.items[item]
            out.append(dict(dept_code=dept, year=year, section=sec,
                            day=d, period=p, subject_code=subj,
                            faculty_id=fid, room=f"{dept}-{year}{sec}"))
        return out


# --------------------------------------------------------------- greedy seed
def _load_pattern(credits: int, rng: random.Random) -> list[int]:
    """The most even split of `credits` over five days, in random day order."""
    base, rem = divmod(credits, N_DAYS)
    pattern = [base + 1] * rem + [base] * (N_DAYS - rem)
    rng.shuffle(pattern)
    return pattern


def _match(items, cells, sched: Schedule, rng: random.Random) -> dict:
    """Maximum bipartite matching of items to cells, by augmenting paths.

    Pure greedy strands items whenever a busy teacher takes the last cell
    they could have used. A section is only ~18 items, so an exact
    maximum matching is cheap and removes a whole class of avoidable
    overflow — which is what the gaps in the final schedule are made of.
    """
    cand = {}
    for it in items:
        options = [c for c in cells if sched.free_for(it, *c)]
        rng.shuffle(options)
        cand[it] = options

    taken: dict[tuple[int, int], int] = {}

    def augment(it, seen) -> bool:
        for c in cand[it]:
            if c in seen:
                continue
            seen.add(c)
            if c not in taken or augment(taken[c], seen):
                taken[c] = it
                return True
        return False

    for it in sorted(items, key=lambda i: len(cand[i])):
        augment(it, set())
    return {it: c for c, it in taken.items()}


def greedy_seed(demands, rng: random.Random, weights=None,
                blocked=None) -> Schedule:
    """A compact, fully placed, hard-feasible starting schedule."""
    sched = Schedule(demands, weights, blocked)
    by_section = defaultdict(list)
    for i, (sec, _subj, _fid) in enumerate(sched.items):
        by_section[sec].append(i)

    # Sections carrying the busiest teachers go first: they have the least
    # room to manoeuvre once the grid starts filling up.
    fac_load = defaultdict(int)
    for _sec, _subj, fid in sched.items:
        fac_load[fid] += 1
    order = sorted(by_section, key=lambda s: -max(
        fac_load[sched.items[i][2]] for i in by_section[s]))

    for sec in order:
        si = sched.sec_index[sec]
        items = by_section[sec]
        pattern = _load_pattern(len(items), rng)
        target = [(d, p) for d in range(N_DAYS) for p in range(pattern[d])]

        for it, (d, p) in _match(items, target, sched, rng).items():
            sched.place(it, d, p)

        # Overflow: whatever the compact shape could not take goes to the
        # cheapest legal cell anywhere in the section.
        for it in items:
            if sched.pos[it] is not None:
                continue
            fid = sched.items[it][2]
            best, best_delta = None, None
            for d in range(N_DAYS):
                for p in range(N_PERIODS):
                    if not sched.free_for(it, d, p):
                        continue
                    before = sched._sec_day_cost(si, d) + \
                        sched._fac_day_cost(fid, d)
                    sched.place(it, d, p)
                    delta = (sched._sec_day_cost(si, d)
                             + sched._fac_day_cost(fid, d) - before)
                    sched.lift(it)
                    if best_delta is None or delta < best_delta:
                        best, best_delta = (d, p), delta
            if best is None:
                raise Unplaceable(f"no legal cell for item {it} in {sec}")
            sched.place(it, *best)
    return sched


# -------------------------------------------------------------- the annealer
def _try_relocate(sched: Schedule, si: int, item: int, rng, tries=6):
    """Move one class to an empty cell in the same section."""
    d0, p0 = sched.pos[item]
    fid = sched.items[item][2]
    for _ in range(tries):
        d = rng.randrange(N_DAYS)
        p = rng.randrange(N_PERIODS)
        if (d, p) == (d0, p0) or sched.sec_mask[si][d] & (1 << p):
            continue
        # Never empty a section-day; see the module docstring.
        if d != d0 and sched.day_load(si, d0) <= 1:
            continue
        if sched.teacher_busy(fid, d, p):
            continue
        return sched.apply([(item, d, p)])
    return None


def _try_swap(sched: Schedule, si: int, a: int, rng, tries=6):
    """Exchange two classes' cells within one section.

    Day loads are unchanged by a swap, so no day can be emptied. Teacher
    feasibility: each must be free at the other's cell. If the two share a
    teacher the swap is always legal, since the only occupancy in question
    is the pair's own.
    """
    da, pa = sched.pos[a]
    fa = sched.items[a][2]
    for _ in range(tries):
        d = rng.randrange(N_DAYS)
        p = rng.randrange(N_PERIODS)
        b = sched.cell.get((si, d, p))
        if b is None or b == a:
            continue
        fb = sched.items[b][2]
        if fa != fb:
            if sched.teacher_busy(fa, d, p):
                continue    # someone else's class already has fa there
            if sched.teacher_busy(fb, da, pa):
                continue
        return sched.apply([(a, d, p), (b, da, pa)])
    return None


def anneal(sched: Schedule, rng: random.Random, iters: int = 120_000,
           t0: float = 2.5, t1: float = 0.02, trace_every: int = 0) -> dict:
    """Metropolis with geometric cooling over two hard-feasible moves.

    Both moves keep every period placed and every hard constraint
    satisfied, so the search never spends effort repairing feasibility —
    only the soft objective moves, which is what makes the delta
    arithmetic worth doing.
    """
    cur = sched.cost()
    best, best_cells = cur, dict(sched.cell)
    ratio = (t1 / t0) ** (1.0 / max(iters, 1))
    temp = t0
    accepted = 0
    trace = []

    by_section = defaultdict(list)
    for i, (sec, _s, _f) in enumerate(sched.items):
        by_section[sched.sec_index[sec]].append(i)
    section_ids = list(by_section)

    for step in range(iters):
        temp *= ratio
        si = rng.choice(section_ids)
        item = rng.choice(by_section[si])
        delta = (_try_relocate(sched, si, item, rng) if rng.random() < 0.5
                 else _try_swap(sched, si, item, rng))
        if delta is None:
            continue
        if delta <= 0 or rng.random() < math.exp(-delta / temp):
            cur += delta
            accepted += 1
            if cur < best - 1e-9:
                best, best_cells = cur, dict(sched.cell)
        else:
            sched.undo()
        if trace_every and step % trace_every == 0:
            trace.append({"step": step, "temp": round(temp, 4),
                          "cost": round(cur, 2), "best": round(best, 2)})

    sched.restore(best_cells)
    return {"cost": best, "accepted": accepted, "iterations": iters,
            "acceptance_rate": accepted / max(iters, 1), "trace": trace}


# ------------------------------------------------------------------ front door
def solve(demands, seed: int = 0, iters: int = 120_000, weights=None,
          restarts: int = 3, trace_every: int = 0,
          blocked=None) -> tuple[Schedule, dict]:
    """Greedy seed then anneal. Returns the schedule and solver telemetry."""
    import time
    t0 = time.perf_counter()
    rng = random.Random(seed)
    sched = None
    attempts = 0
    for attempts in range(1, restarts + 1):
        try:
            sched = greedy_seed(demands, rng, weights, blocked)
            break
        except Unplaceable:
            continue
    if sched is None:
        raise Unplaceable(f"seed failed {restarts} times at seed {seed}")

    seed_ms = round((time.perf_counter() - t0) * 1000, 1)
    seed_cost = sched.cost()
    info = anneal(sched, rng, iters=iters, trace_every=trace_every)
    info.update({
        "seed": seed,
        "seed_cost": seed_cost,
        "seed_attempts": attempts,
        "seed_ms": seed_ms,
        "final_cost": sched.cost(),
        "improvement": seed_cost - sched.cost(),
        "solve_ms": round((time.perf_counter() - t0) * 1000, 1),
        "slots_placed": len(sched.cell),
        "slots_required": len(sched.items),
    })
    return sched, info


def verify_against_frozen(sched: Schedule) -> tuple[float, float]:
    """Incremental cost vs `schedule_metrics.objective`. Must agree.

    Imported lazily so the running server never depends on `evaluation/`.
    """
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from evaluation.benchmark import schedule_metrics

    class _Row:
        __slots__ = ("dept_code", "year", "section", "day", "period",
                     "faculty_id", "subject_code")

        def __init__(self, d):
            for k in self.__slots__:
                setattr(self, k, d[k])

    rows = [_Row(s) for s in sched.slots()]
    frozen = schedule_metrics.objective(schedule_metrics.compute(rows), sched.w)
    return sched.cost(), frozen
