"""P1b — the ITC-2007 harness must agree with the official scorer.

The heavy differential test against the compiled validator lives in
`evaluation/itc2007/crosscheck.py`, because it needs a C++ compiler and a
network fetch and neither belongs in a unit test run. What is here is
everything that can be checked offline: the published toy example with its
officially stated score, and the invariant that the solver's incremental
bookkeeping never drifts from a full rescore.

If these pass and crosscheck.py passes, an E4b penalty means what the
competition means by it.
"""
from pathlib import Path
import random

import pytest

from evaluation.itc2007 import ctt, solver

FIXTURES = Path(__file__).resolve().parent.parent / "evaluation" / "itc2007" \
    / "fixtures"


@pytest.fixture(scope="module")
def toy():
    return ctt.parse((FIXTURES / "toy.ctt").read_text(encoding="utf-8"))


def read_solution(inst, path):
    tt = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cname, rname, day, per = line.split()
        key = (inst.course_index[cname],
               int(day) * inst.periods_per_day + int(per))
        tt.setdefault(key, inst.room_index[rname])   # repeats skipped, as
    return tt                                        # the validator does


def test_parses_the_published_toy_instance(toy):
    assert toy.name == "ToyExample"
    assert (toy.days, toy.periods_per_day, toy.periods) == (5, 4, 20)
    assert [c.name for c in toy.courses] == ["SceCosC", "ArcTec", "TecCos",
                                             "Geotec"]
    assert toy.total_lectures == 16
    assert len(toy.unavailable) == 8
    # TecCos cannot be scheduled in the third period of Thursday, which is
    # the example the competition's own input-format page spells out.
    assert not toy.available(toy.course_index["TecCos"], 3 * 4 + 2)


def test_conflicts_come_from_curricula_and_from_teachers(toy):
    i = toy.course_index
    # Cur1 = SceCosC, ArcTec, TecCos
    assert i["ArcTec"] in toy.conflict[i["SceCosC"]]
    # Cur2 = TecCos, Geotec
    assert i["Geotec"] in toy.conflict[i["TecCos"]]
    # No shared curriculum and no shared teacher.
    assert i["Geotec"] not in toy.conflict[i["SceCosC"]]


def test_reproduces_the_officially_stated_toy_score(toy):
    """The competition publishes this solution and calls it 'pretty bad'.

    Its score is stated on the site, so this is the one case where an
    outside authority fixes the answer: Violations = 5, Total Cost = 30.
    """
    tt = read_solution(toy, FIXTURES / "toy_sol.out")
    c = ctt.cost(toy, tt)
    assert (c.violations, c.total) == (5, 30)
    assert (c.lectures, c.conflicts, c.availability, c.room_occupation) \
        == (0, 3, 0, 2)
    assert (c.room_capacity, c.min_working_days, c.curriculum_compactness,
            c.room_stability) == (8, 15, 4, 3)


def test_round_trips_through_the_output_format(toy):
    tt = read_solution(toy, FIXTURES / "toy_sol.out")
    again = {}
    for line in ctt.render_solution(toy, tt).splitlines():
        cname, rname, day, per = line.split()
        again[(toy.course_index[cname],
               int(day) * toy.periods_per_day + int(per))] = \
            toy.room_index[rname]
    assert again == tt


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_incremental_cost_never_drifts_from_a_full_rescore(toy, seed):
    """The solver's counters are the only thing E4b's speed depends on and
    the easiest thing to get quietly wrong."""
    rng = random.Random(seed)
    sol = solver.seed(toy, rng)
    for _ in range(400):
        c = rng.randrange(len(toy.courses))
        if not sol.at[c]:
            continue
        p = rng.choice(list(sol.at[c]))
        target = rng.randrange(toy.periods)
        if target != p and target in sol.at[c]:
            continue
        sol.unplace(c, p)
        sol.place(c, target, rng.randrange(1, len(toy.rooms) + 1))
        assert sol.cost_parts() == ctt.cost(toy, sol.assignment())


def test_the_seed_places_every_lecture(toy):
    sol = solver.seed(toy, random.Random(0))
    assert sol.cost_parts().lectures == 0
    assert sum(len(d) for d in sol.at) == toy.total_lectures


def test_annealing_finds_a_feasible_toy_timetable(toy):
    """A smoke test, not a result: the toy instance is four courses.

    It earns its place by exercising parse -> seed -> anneal -> score in
    one line, so a break anywhere in that chain fails here rather than
    silently producing a plausible number in E4b.
    """
    res = solver.anneal(toy, seed_value=0, steps=20_000)
    assert res.cost.violations == 0
    assert res.objective < res.seed_objective
