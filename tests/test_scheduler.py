"""P1 solver — invariants that must hold on every seed.

These are correctness tests, not quality tests. E4
(`evaluation/scheduler_eval.py`) measures how *good* the schedules are;
this file checks that they are legal, complete, and scored by the same
arithmetic the frozen instrument uses.
"""
import random

import pytest

from backend.app import scheduler
from evaluation.benchmark import schedule_metrics as sm


def toy(n_sections=6, n_faculty=8, credits=18, seed=0):
    """A small instance with the same shape as the real one: 5 subjects
    per section summing to 18 periods, teachers shared across sections."""
    rng = random.Random(seed)
    split = [4, 4, 4, 3, 3]
    assert sum(split) == credits
    demands = []
    for s in range(n_sections):
        key = ("XX", 1 + s // 2, chr(ord("A") + s % 2))
        for j, c in enumerate(split):
            fid = rng.randrange(n_faculty)
            for _ in range(c):
                demands.append((key, f"SUB{j}", fid))
    return demands


class Row:
    __slots__ = ("dept_code", "year", "section", "day", "period",
                 "faculty_id", "subject_code")

    def __init__(self, d):
        for k in self.__slots__:
            setattr(self, k, d[k])


@pytest.fixture(scope="module")
def solved():
    dem = toy()
    return [scheduler.solve(dem, seed=s, iters=4000) for s in range(3)]


def test_every_period_is_placed(solved):
    for sched, info in solved:
        assert info["slots_placed"] == info["slots_required"]
        assert all(p is not None for p in sched.pos)


def test_hard_constraints_hold(solved):
    for sched, _ in solved:
        m = sm.compute([Row(s) for s in sched.slots()])
        assert m["faculty_conflicts"] == 0
        assert m["section_conflicts"] == 0


def test_no_section_day_is_emptied(solved):
    """The frozen metric divides by *non-empty* section-days, so emptying
    one is a way to score better without scheduling better. The solver
    forbids it; this is the check that it actually does."""
    for sched, _ in solved:
        m = sm.compute([Row(s) for s in sched.slots()])
        assert m["section_days"] == len(sched.sections) * scheduler.N_DAYS


def test_incremental_cost_equals_the_frozen_metric(solved):
    """The whole comparison rests on this. If the solver's own arithmetic
    drifts from `schedule_metrics.objective`, then 'we improved the
    scheduler' is measuring two different things."""
    for sched, _ in solved:
        incremental, frozen = scheduler.verify_against_frozen(sched)
        assert incremental == pytest.approx(frozen, rel=1e-9)


def test_annealing_improves_on_the_seed(solved):
    for _sched, info in solved:
        assert info["final_cost"] < info["seed_cost"]


def test_weights_are_the_frozen_defaults():
    """The solver keeps its own copy so it does not import `evaluation/`
    at runtime. They must not diverge."""
    probe = {"idle_gaps_total": 1, "late_start_days": 1, "section_days": 1,
             "daily_load_sigma_mean": 1.0, "subject_repeat_days": 1,
             "faculty_idle_gaps": 1}
    assert sm.objective(probe) == sum(scheduler.DEFAULT_WEIGHTS.values())


def test_blocked_cells_are_respected():
    """Scoped regeneration must not double-book a teacher against the
    departments it is not touching."""
    dem = toy(n_sections=4, n_faculty=8)
    fid = dem[0][2]
    # Two whole mornings unavailable. Blocking more than this over-
    # constrains a toy instance and the seed legitimately gives up.
    blocked = {(fid, d): 0b000111 for d in (0, 1)}
    sched, _ = scheduler.solve(dem, seed=1, iters=2000, blocked=blocked)
    for s in sched.slots():
        if s["faculty_id"] == fid and (fid, s["day"]) in blocked:
            assert not (blocked[(fid, s["day"])] & (1 << s["period"]))
