"""Timetable quality metrics — the E4 measuring instrument.

FROZEN AT P0. Do not edit without a dated entry in evaluation/PROTOCOL.md.

Shared deliberately between the frozen v2 greedy baseline and the P1
simulated-annealing solver. If each solver reported its own metrics, "we
improved the scheduler" could be an artefact of two different definitions
of "gap", and nobody would be able to tell from the results table.

Terminology, fixed here once:

  **section-day**  one (dept, year, section, weekday) pair — a single
                   class group's single day. 40 sections x 5 days = 200.
  **idle gap**     an unfilled period lying *between* two filled periods
                   on the same section-day. Free periods before the first
                   or after the last class are not gaps; they are a late
                   start or an early finish, counted separately.
  **late start**   a section-day whose first class is not period 0.

The distinction matters because it is the difference between a student
waiting around mid-morning and a student going home early. The v2 solver
produces both and penalises neither.
"""
import statistics
from collections import defaultdict

N_DAYS, N_PERIODS = 5, 6


def _by_section_day(slots):
    """(dept, year, section, day) -> sorted list of period indices."""
    grid = defaultdict(list)
    for s in slots:
        grid[(s.dept_code, s.year, s.section, s.day)].append(s.period)
    return {k: sorted(v) for k, v in grid.items()}


def _gaps(periods: list[int]) -> int:
    """Unfilled periods strictly between the first and last class."""
    if len(periods) < 2:
        return 0
    return (periods[-1] - periods[0] + 1) - len(periods)


def compute(slots, slots_required: int | None = None) -> dict:
    """Quality metrics for a set of TimetableSlot rows.

    `slots` needs `.dept_code .year .section .day .period .faculty_id
    .subject_code`.
    """
    grid = _by_section_day(slots)
    n_section_days = len(grid)
    if n_section_days == 0:
        return {"error": "no slots"}

    gap_counts = [_gaps(p) for p in grid.values()]
    late_starts = sum(1 for p in grid.values() if p and p[0] != 0)
    loads = [len(p) for p in grid.values()]

    # within-section spread of daily load, averaged over sections
    per_section = defaultdict(list)
    for (dept, year, sec, _day), periods in grid.items():
        per_section[(dept, year, sec)].append(len(periods))
    sigmas = [statistics.pstdev(v) for v in per_section.values() if len(v) > 1]

    # longest run of consecutive filled periods, per section-day
    runs = []
    for periods in grid.values():
        best = run = 1 if periods else 0
        for a, b in zip(periods, periods[1:]):
            run = run + 1 if b == a + 1 else 1
            best = max(best, run)
        runs.append(best)

    # a subject taught more than once on the same section-day
    subj_day = defaultdict(int)
    for s in slots:
        subj_day[(s.dept_code, s.year, s.section, s.day, s.subject_code)] += 1
    repeats = sum(1 for v in subj_day.values() if v > 1)

    # faculty idle gaps, same definition applied per teacher-day
    fac = defaultdict(list)
    for s in slots:
        fac[(s.faculty_id, s.day)].append(s.period)
    fac_gaps = sum(_gaps(sorted(v)) for v in fac.values())

    # hard constraints — must be zero
    fac_seen, sec_seen = defaultdict(int), defaultdict(int)
    for s in slots:
        fac_seen[(s.faculty_id, s.day, s.period)] += 1
        sec_seen[(s.dept_code, s.year, s.section, s.day, s.period)] += 1
    fac_clash = sum(v - 1 for v in fac_seen.values() if v > 1)
    sec_clash = sum(v - 1 for v in sec_seen.values() if v > 1)

    out = {
        "section_days": n_section_days,
        "slots_placed": len(list(slots)),
        # --- the two defects the rewrite targets
        "late_start_days": late_starts,
        "late_start_rate": late_starts / n_section_days,
        "idle_gaps_total": sum(gap_counts),
        "idle_gaps_per_section_day": sum(gap_counts) / n_section_days,
        "idle_gap_distribution": {g: gap_counts.count(g)
                                  for g in sorted(set(gap_counts))},
        # --- balance and shape
        "daily_load_sigma_mean": (sum(sigmas) / len(sigmas)) if sigmas else 0.0,
        "daily_load_min": min(loads),
        "daily_load_max": max(loads),
        "longest_block_mean": sum(runs) / len(runs),
        "subject_repeat_days": repeats,
        "faculty_idle_gaps": fac_gaps,
        # --- hard constraints
        "faculty_conflicts": fac_clash,
        "section_conflicts": sec_clash,
    }
    if slots_required:
        out["placement_rate"] = len(list(slots)) / slots_required
        out["unplaced"] = slots_required - len(list(slots))
    return out


def objective(metrics: dict, weights: dict | None = None) -> float:
    """Scalar soft-constraint cost. Lower is better.

    Weights are the P1 tuning surface and are ablated in E4. The defaults
    here encode the priority order stated in the plan: a student waiting
    mid-morning (idle gap) and a student called in for a late start are
    the two complaints that motivated the rewrite, so they dominate.
    """
    w = {"idle_gap": 5.0, "late_start": 4.0, "load_sigma": 2.0,
         "subject_repeat": 2.0, "faculty_gap": 1.0, **(weights or {})}
    return (w["idle_gap"] * metrics["idle_gaps_total"]
            + w["late_start"] * metrics["late_start_days"]
            + w["load_sigma"] * metrics["daily_load_sigma_mean"] * metrics["section_days"]
            + w["subject_repeat"] * metrics["subject_repeat_days"]
            + w["faculty_gap"] * metrics["faculty_idle_gaps"])
