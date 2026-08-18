"""Differential test: our cost model against the official validator.

    python evaluation/itc2007/crosscheck.py            # 300 random cases
    python evaluation/itc2007/crosscheck.py -n 2000    # more

This is the whole reason P1b is trustworthy. `ctt.cost` is a hand
transcription of eight C++ functions, and a transcription error would not
announce itself: it would quietly produce an ITC penalty that looks
plausible and is not comparable to anything. So instead of trusting the
port, we generate random instances and random solutions - deliberately
including infeasible ones, empty ones, over-full ones and duplicate
teachers - and require that both implementations agree on
every one of the eight components, not merely on the total.

The validator is not vendored. `build.py` fetches `validator.cc` from the
competition site and records its sha256, so the binary this compares
against has provenance rather than being a file someone pasted in.
"""
from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.itc2007 import ctt  # noqa: E402
from evaluation.itc2007.build import validator_path  # noqa: E402

_FIELDS = [
    ("Violations of Lectures", "lectures"),
    ("Violations of Conflicts", "conflicts"),
    ("Violations of Availability", "availability"),
    ("Violations of RoomOccupation", "room_occupation"),
    ("Cost of RoomCapacity", "room_capacity"),
    ("Cost of MinWorkingDays", "min_working_days"),
    ("Cost of CurriculumCompactness", "curriculum_compactness"),
    ("Cost of RoomStability", "room_stability"),
]


def random_instance(rng: random.Random) -> ctt.Instance:
    """Small but adversarial: shared teachers, courses in several
    curricula at once, rooms far too small, and unavailability that
    overlaps what the solution does.

    periods_per_day is never 1. That is not a convenience: with ppd == 1
    every period satisfies `p % ppd == 0`, so CostsOnCurriculumCompactness
    takes its lookahead branch on the final period and reads one element
    past the end of `curriculum_period_lectures[g]`. The official
    validator's answer there is undefined behaviour, so it cannot serve as
    ground truth, and no competition instance has ppd == 1 (the comp set
    uses 4 to 6). Verified structurally: for ppd >= 2 the last period of
    each day satisfies `p % ppd == ppd-1` and the lookbehind branch is
    taken instead, which is always in range.
    """
    ncourses = rng.randint(2, 7)
    nrooms = rng.randint(1, 3)
    days = rng.randint(1, 4)
    ppd = rng.choice([2, 3, 4, 5, 6])
    teachers = ["T%d" % k for k in range(rng.randint(1, 3))]
    courses = [
        ctt.Course("C%d" % k, rng.choice(teachers), rng.randint(1, 5),
                   rng.randint(1, 4), rng.randint(1, 60))
        for k in range(ncourses)
    ]
    rooms = [ctt.Room("R%d" % k, rng.randint(1, 50)) for k in range(nrooms)]

    curricula: dict[str, list[int]] = {}
    for g in range(rng.randint(0, 3)):
        size = rng.randint(1, ncourses)
        curricula["G%d" % g] = rng.sample(range(ncourses), size)

    periods = days * ppd
    unavailable = set()
    for _ in range(rng.randint(0, periods)):
        unavailable.add((rng.randrange(ncourses), rng.randrange(periods)))

    return ctt.Instance(name="R%d" % rng.randrange(10 ** 6), days=days,
                        periods_per_day=ppd, courses=courses, rooms=rooms,
                        curricula=curricula, unavailable=unavailable)


def random_solution(inst: ctt.Instance, rng: random.Random) -> dict:
    """Deliberately not a valid solution: over- and under-scheduled courses
    are the cases where Lectures and RoomOccupation actually fire."""
    tt: dict[tuple[int, int], int] = {}
    for c in range(len(inst.courses)):
        want = inst.courses[c].lectures + rng.randint(-2, 2)
        want = max(0, min(want, inst.periods))
        for p in rng.sample(range(inst.periods), want):
            tt[(c, p)] = rng.randint(1, len(inst.rooms))
    return tt


def write_instance(inst: ctt.Instance) -> str:
    """Serialise back to .ctt so the validator sees the same instance."""
    L = []
    add = L.append
    add("Name: %s" % inst.name)
    add("Courses: %d" % len(inst.courses))
    add("Rooms: %d" % len(inst.rooms))
    add("Days: %d" % inst.days)
    add("Periods_per_day: %d" % inst.periods_per_day)
    add("Curricula: %d" % len(inst.curricula))
    add("Constraints: %d" % len(inst.unavailable))
    add("")
    add("COURSES:")
    for c in inst.courses:
        add("%s %s %d %d %d" % (c.name, c.teacher, c.lectures,
                                c.min_working_days, c.students))
    add("")
    add("ROOMS:")
    for r in inst.rooms:
        add("%s %d" % (r.name, r.capacity))
    add("")
    add("CURRICULA:")
    for name, members in inst.curricula.items():
        add("%s %d %s" % (name, len(members),
                          " ".join(inst.courses[m].name for m in members)))
    add("")
    add("UNAVAILABILITY_CONSTRAINTS:")
    for c, p in sorted(inst.unavailable):
        add("%s %d %d" % (inst.courses[c].name,
                          p // inst.periods_per_day,
                          p % inst.periods_per_day))
    add("")
    add("END.")
    return chr(10).join(L) + chr(10)


def run_validator(exe: Path, inst_path: Path, sol_path: Path) -> dict:
    out = subprocess.run([str(exe), str(inst_path), str(sol_path)],
                         capture_output=True, text=True, timeout=60)
    got = {}
    for label, key in _FIELDS:
        m = re.search(re.escape(label) + r"[^:]*:\s*(-?\d+)", out.stdout)
        if not m:
            raise RuntimeError("validator did not report %r%s%s"
                               % (label, chr(10), out.stdout + out.stderr))
        got[key] = int(m.group(1))
    return got


def compare(exe: Path, inst: ctt.Instance, tt: dict, tmp: Path) -> list[str]:
    inst_path = tmp / "case.ctt"
    sol_path = tmp / "case.out"
    inst_path.write_text(write_instance(inst), encoding="ascii")
    sol_path.write_text(ctt.render_solution(inst, tt), encoding="ascii")
    theirs = run_validator(exe, inst_path, sol_path)
    ours = ctt.cost(inst, tt).as_dict()
    return ["%s: ours=%d validator=%d" % (k, ours[k], theirs[k])
            for _label, k in _FIELDS if ours[k] != theirs[k]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=300, help="random cases")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    exe = validator_path()
    rng = random.Random(args.seed)
    print("cross-checking evaluation/itc2007/ctt.py against %s"
          % exe.name)
    print("=" * 74)

    failures = 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # The published toy example first: it is the one case with an
        # officially stated answer (Violations = 5, Total Cost = 30).
        toy = ctt.parse((Path(__file__).parent / "fixtures"
                         / "toy.ctt").read_text(encoding="utf-8"))
        toy_tt = {}
        for line in (Path(__file__).parent / "fixtures"
                     / "toy_sol.out").read_text(encoding="utf-8").split(chr(10)):
            if not line.strip():
                continue
            cname, rname, d, p = line.split()
            key = (toy.course_index[cname],
                   int(d) * toy.periods_per_day + int(p))
            toy_tt.setdefault(key, toy.room_index[rname])
        c = ctt.cost(toy, toy_tt)
        ok = (c.violations, c.total) == (5, 30)
        print("  published toy example: violations=%d total=%d  %s"
              % (c.violations, c.total, "ok" if ok else "MISMATCH"))
        failures += 0 if ok else 1

        for i in range(args.n):
            inst = random_instance(rng)
            tt = random_solution(inst, rng)
            diffs = compare(exe, inst, tt, tmp)
            if diffs:
                failures += 1
                print("  case %d MISMATCH" % i)
                for d in diffs:
                    print("      " + d)
                (tmp / "case.ctt").replace(Path.cwd() / "failing_case.ctt")
                (tmp / "case.out").replace(Path.cwd() / "failing_case.out")
                print("      written to failing_case.ctt / .out")
                break

    print("=" * 74)
    if failures:
        print("FAIL - %d mismatch(es). The port is wrong; do not run E4b."
              % failures)
        return 1
    print("%d random cases + the published toy example agree on all eight "
          "components." % args.n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
