"""Live-trace wrapper around the P1 scheduler, for UI visualisation only.

`scheduler.py` is frozen research instrumentation (P1, benchmarked against
ITC-2007 in P1b) and stays untouched — this module never imports its
private state, only reuses its public primitives (`Schedule`, `_match`,
`_load_pattern`, `anneal`, `Unplaceable`). The one thing it duplicates is
the ~45-line body of `greedy_seed`, so that each placement can emit an
event for the browser to animate; the annealing phase is not duplicated
at all — it calls the real, unmodified `scheduler.anneal()`, whose
`trace_every` argument already exists and only appends to a list, so
passing it changes no RNG draw and no cost value the frozen path relies
on.

If this ever drifts from `greedy_seed`, `verify_against_frozen` still
only checks `scheduler.py`'s own output — this module's result is
therefore checked the same way any other caller of `scheduler.solve`
would be, by feeding its final `Schedule` through the identical cost
function.
"""
import random
import time
from collections import defaultdict

from . import scheduler


def _traced_seed(demands, rng: random.Random, weights, blocked, events: list):
    """Same algorithm as `scheduler.greedy_seed`, instrumented for replay."""
    sched = scheduler.Schedule(demands, weights, blocked)
    by_section = defaultdict(list)
    for i, (sec, _subj, _fid) in enumerate(sched.items):
        by_section[sec].append(i)

    fac_load = defaultdict(int)
    for _sec, _subj, fid in sched.items:
        fac_load[fid] += 1
    order = sorted(by_section, key=lambda s: -max(
        fac_load[sched.items[i][2]] for i in by_section[s]))

    def _emit(it, d, p):
        sec, subj, fid = sched.items[it]
        events.append({"type": "place", "section": "-".join(map(str, sec)),
                       "subject": subj, "faculty_id": fid, "day": d, "period": p})

    for sec in order:
        si = sched.sec_index[sec]
        items = by_section[sec]
        pattern = scheduler._load_pattern(len(items), rng)
        target = [(d, p) for d in range(scheduler.N_DAYS) for p in range(pattern[d])]

        for it, (d, p) in scheduler._match(items, target, sched, rng).items():
            sched.place(it, d, p)
            _emit(it, d, p)

        for it in items:
            if sched.pos[it] is not None:
                continue
            fid = sched.items[it][2]
            best, best_delta = None, None
            for d in range(scheduler.N_DAYS):
                for p in range(scheduler.N_PERIODS):
                    if not sched.free_for(it, d, p):
                        continue
                    before = sched._sec_day_cost(si, d) + sched._fac_day_cost(fid, d)
                    sched.place(it, d, p)
                    delta = (sched._sec_day_cost(si, d)
                             + sched._fac_day_cost(fid, d) - before)
                    sched.lift(it)
                    if best_delta is None or delta < best_delta:
                        best, best_delta = (d, p), delta
            if best is None:
                raise scheduler.Unplaceable(f"no legal cell for item {it} in {sec}")
            sched.place(it, *best)
            _emit(it, *best)
    return sched


def solve_with_trace(demands, seed: int = 7, iters: int = 120_000,
                      weights=None, restarts: int = 3, blocked=None,
                      anneal_trace_every: int = 200) -> dict:
    """Regenerate a timetable and return the real event trace alongside it.

    The write path (Schedule -> slots) and the final numbers are produced
    by the exact same `scheduler.anneal` used everywhere else; only the
    seed phase is re-run through the traced variant above so the browser
    has something to animate before annealing starts.
    """
    t0 = time.perf_counter()
    rng = random.Random(seed)
    sched, seed_events, attempts = None, None, 0
    for attempts in range(1, restarts + 1):
        try:
            events: list = []
            sched = _traced_seed(demands, rng, weights, blocked, events)
            seed_events = events
            break
        except scheduler.Unplaceable:
            continue
    if sched is None:
        raise scheduler.Unplaceable(f"seed failed {restarts} times at seed {seed}")

    seed_ms = round((time.perf_counter() - t0) * 1000, 1)
    seed_cost = sched.cost()
    info = scheduler.anneal(sched, rng, iters=iters, trace_every=anneal_trace_every)

    return {
        "seed": seed, "seed_cost": seed_cost, "seed_attempts": attempts,
        "seed_ms": seed_ms, "seed_events": seed_events,
        "anneal_trace": info["trace"],
        "final_cost": sched.cost(), "improvement": seed_cost - sched.cost(),
        "solve_ms": round((time.perf_counter() - t0) * 1000, 1),
        "slots_placed": len(sched.cell), "slots_required": len(sched.items),
        "sched": sched,
    }
