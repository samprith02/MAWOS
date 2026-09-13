"""E4 — P1 scheduler evaluation: 10 seeds, weight ablation, convergence.

    python evaluation/scheduler_eval.py
    python evaluation/scheduler_eval.py --quick     # 3 seeds, short anneal

Writes `evaluation/results/v3_scheduler/e4.{json,md}`.

Comparator
----------
The v2 greedy baseline is **not re-run here**. It was measured once at P0
over 10 seeds and frozen in `results/v2_frozen/baseline.json`; regenerating
it and calling it the same experiment is exactly the substitution
PROTOCOL.md forbids. This script reads those numbers and compares against
them.

Both solvers are scored by the same frozen instrument,
`evaluation/benchmark/schedule_metrics`, which is hashed in
`evaluation/FROZEN.sha256` — so the comparison cannot drift by way of a
redefined "gap".

Database safety
---------------
Read-only. `TeachingAssignment` rows are read to build the demand list and
nothing is ever written, so the shipped DB's deliberate state survives.
CLAUDE.md: do not run this with the server up.

What is being claimed
---------------------
That an objective function plus local search fixes two specific defects
the v2 solver had no way to see. This is applied engineering with a
measured before/after, **not** a scheduling contribution — the plan
retracted that (§4.4). Simulated annealing for timetabling is decades
old; the result here is that it is worth the ~10x solve time on this
instance, and by how much.
"""
import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app import scheduler                       # noqa: E402
from backend.app.database import SessionLocal           # noqa: E402
from backend.app.models import TeachingAssignment       # noqa: E402
from evaluation.benchmark import schedule_metrics as sm  # noqa: E402

OUT_DIR = ROOT / "evaluation" / "results" / "v3_scheduler"
FROZEN = ROOT / "evaluation" / "results" / "v2_frozen" / "baseline.json"
SEEDS = list(range(10))
ITERS = 120_000

#: The metrics that carry the claim, in report order.
HEADLINE = ["late_start_days", "idle_gaps_total", "daily_load_sigma_mean",
            "subject_repeat_days", "faculty_idle_gaps", "longest_block_mean",
            "placement_rate", "faculty_conflicts", "section_conflicts",
            "objective"]


class Row:
    """Duck-types a TimetableSlot for the frozen metric module."""
    __slots__ = ("dept_code", "year", "section", "day", "period",
                 "faculty_id", "subject_code")

    def __init__(self, d):
        for k in self.__slots__:
            setattr(self, k, d[k])


def demands() -> tuple[list, int]:
    db = SessionLocal()
    try:
        out = []
        for a in db.query(TeachingAssignment).all():
            for _ in range(a.subject.credits):
                out.append(((a.dept_code, a.year, a.section),
                            a.subject_code, a.faculty_id))
        return out, len(out)
    finally:
        db.close()


def measure(sched, required: int) -> dict:
    m = sm.compute([Row(s) for s in sched.slots()], slots_required=required)
    m["objective"] = sm.objective(m)
    return m


def band(values) -> dict:
    return {"mean": statistics.mean(values),
            "median": statistics.median(values),
            "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values)}


def separation(p1_objectives, base) -> dict:
    """How far apart the two solvers are, without inventing v2's per-seed data.

    `baseline.json` stored v2's objective as a band (mean, sd, min, max),
    not ten individual values, so a paired or rank test against P1's ten
    runs is not available — and fabricating ten draws from the band to
    feed a U test would be exactly the kind of number PROTOCOL forbids.

    What the frozen data does support is a range comparison, and on this
    instance that settles it: v2's *best* seed against P1's *worst*. When
    the ranges do not come within an order of magnitude, a p-value adds
    nothing a reader could not read off the two intervals.
    """
    v2_best, p1_worst = base["objective"]["min"], max(p1_objectives)
    return {
        "v2_range": [base["objective"]["min"], base["objective"]["max"]],
        "p1_range": [min(p1_objectives), max(p1_objectives)],
        "v2_best_vs_p1_worst_ratio": v2_best / p1_worst,
        "ranges_disjoint": v2_best > p1_worst,
        "test_omitted_because":
            "v2 per-seed objectives were not stored at P0, only the band; "
            "a rank test would require fabricating them, and the ranges are "
            "disjoint by roughly an order of magnitude regardless",
    }


def run_seeds(dem, required, seeds, iters, weights=None, trace_seed=None):
    runs, traces = [], {}
    for s in seeds:
        every = max(iters // 120, 1) if s == trace_seed else 0
        sched, info = scheduler.solve(dem, seed=s, iters=iters,
                                      weights=weights, trace_every=every)
        m = measure(sched, required)
        inc, frozen = scheduler.verify_against_frozen(sched)
        if not math.isclose(inc, frozen, rel_tol=1e-9):
            sys.exit(f"seed {s}: incremental cost {inc} != frozen {frozen}")
        m["solve_ms"] = info["solve_ms"]
        m["seed_ms"] = info["seed_ms"]
        m["seed_attempts"] = info["seed_attempts"]
        m["seed_cost"] = info["seed_cost"]
        m["acceptance_rate"] = info["acceptance_rate"]
        runs.append(m)
        if info["trace"]:
            traces[s] = info["trace"]
    return runs, traces


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="3 seeds and a short anneal, for smoke tests")
    args = ap.parse_args()
    seeds = SEEDS[:3] if args.quick else SEEDS
    iters = 20_000 if args.quick else ITERS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dem, required = demands()
    base = json.loads(FROZEN.read_text(encoding="utf-8"))["scheduler"]["bands"]

    print("E4 — P1 scheduler vs frozen v2 greedy")
    print("=" * 78)
    print(f"{required} periods over {len({d[0] for d in dem})} sections · "
          f"{len(seeds)} seeds · {iters:,} annealing steps")
    print(f"comparator: results/v2_frozen/baseline.json (frozen at P0, "
          f"not re-run)")

    t0 = time.perf_counter()
    runs, traces = run_seeds(dem, required, seeds, iters, trace_seed=seeds[0])
    bands = {k: band([r[k] for r in runs])
             for k in HEADLINE + ["solve_ms", "seed_ms", "seed_attempts"]}

    print(f"\n{'metric':30} {'v2 greedy':>18} {'P1 SA':>18} {'change':>12}")
    print("-" * 80)
    for k in HEADLINE:
        b, p = base.get(k), bands[k]
        if b is None:
            continue
        if b["mean"] == 0:
            chg = "—" if p["mean"] == 0 else f"+{p['mean']:.2f}"
        else:
            chg = f"{(p['mean'] - b['mean']) / b['mean']:+.1%}"
        print(f"{k:30} {b['mean']:11.2f} ±{b['std']:5.2f} "
              f"{p['mean']:11.2f} ±{p['std']:5.2f} {chg:>12}")
    sm_ = bands["solve_ms"]
    print(f"{'solve_ms (min)':30} {base['solve_ms']['mean']:11.0f} "
          f"±{base['solve_ms']['std']:5.0f} "
          f"{sm_['min']:11.0f}  [{sm_['min']:.0f}-{sm_['max']:.0f}] "
          f"{(sm_['min'] / base['solve_ms']['mean']):>10.1f}x")
    print(f"  Minimum, not mean. Every run does the same {iters:,} steps "
          f"after an identical seed")
    print(f"  phase ({bands['seed_ms']['median']:.0f} ms median, "
          f"{bands['seed_attempts']['max']:.0f} attempt(s) max), yet wall "
          f"clock ranges {sm_['min']:.0f}-{sm_['max']:.0f} ms")
    print("  across identical work. Contention only ever adds time, so the "
          "minimum is the")
    print("  least-contaminated estimate and the spread is a property of "
          "the host, not the")
    print("  solver. Measured with a 2 GB Ollama model resident — CLAUDE.md "
          "records that")
    print("  this machine's timings shift 3-4x under residency.")

    # --- hard feasibility must survive
    for k in ("faculty_conflicts", "section_conflicts"):
        assert bands[k]["max"] == 0, f"{k} nonzero — solver is broken"
    assert bands["placement_rate"]["min"] == 1.0, "periods went unplaced"
    print("\nhard constraints hold in every seed; placement rate 1.000")

    # --- separation, reported without a fabricated test
    sep = separation([r["objective"] for r in runs], base)
    print(f"\nobjective ranges — v2 [{sep['v2_range'][0]:.0f}, "
          f"{sep['v2_range'][1]:.0f}] vs P1 [{sep['p1_range'][0]:.1f}, "
          f"{sep['p1_range'][1]:.1f}]")
    print(f"  disjoint: {sep['ranges_disjoint']}; v2's best seed is "
          f"{sep['v2_best_vs_p1_worst_ratio']:.1f}x P1's worst")
    print("  no rank test: v2's per-seed objectives were not stored at P0,")
    print("  and fabricating them to produce a p-value would be worse than")
    print("  omitting it")

    # --- how close to the floor?
    floor = _floor(dem)
    print(f"\nobjective floor for this instance: {floor:.1f} "
          f"(perfect compaction; the load-balance term cannot reach zero "
          f"because 18 periods do not divide evenly into 5 days)")
    print(f"P1 reaches {bands['objective']['mean']:.1f}, "
          f"{bands['objective']['mean'] - floor:.1f} above it; "
          f"v2 is {base['objective']['mean'] - floor:.1f} above it")

    # --- weight ablation
    print("\nablation — each weight zeroed in the solver, scored by the "
          "full frozen objective")
    print(f"  {'zeroed':16} {'objective':>11} {'gaps':>7} {'late':>7} "
          f"{'repeat':>7} {'facgap':>7}")
    abl_seeds = seeds[:3]
    ablation = {}
    for name in scheduler.DEFAULT_WEIGHTS:
        w = {name: 0.0}
        ar, _ = run_seeds(dem, required, abl_seeds, iters, weights=w)
        ab = {k: band([r[k] for r in ar]) for k in HEADLINE}
        ablation[name] = ab
        print(f"  {name:16} {ab['objective']['mean']:10.1f} "
              f"{ab['idle_gaps_total']['mean']:7.1f} "
              f"{ab['late_start_days']['mean']:7.1f} "
              f"{ab['subject_repeat_days']['mean']:7.1f} "
              f"{ab['faculty_idle_gaps']['mean']:7.1f}")
    full3, _ = run_seeds(dem, required, abl_seeds, iters)
    f3 = {k: band([r[k] for r in full3]) for k in HEADLINE}
    print(f"  {'(none)':16} {f3['objective']['mean']:10.1f} "
          f"{f3['idle_gaps_total']['mean']:7.1f} "
          f"{f3['late_start_days']['mean']:7.1f} "
          f"{f3['subject_repeat_days']['mean']:7.1f} "
          f"{f3['faculty_idle_gaps']['mean']:7.1f}")

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "instance": {"periods": required,
                     "sections": len({d[0] for d in dem}),
                     "faculty": len({d[2] for d in dem})},
        "solver": {"seeds": seeds, "iterations": iters,
                   "weights": scheduler.DEFAULT_WEIGHTS,
                   "t0": 2.5, "t1": 0.02},
        "comparator": "results/v2_frozen/baseline.json (frozen at P0)",
        "v2_bands": {k: base[k] for k in base},
        "p1_bands": bands,
        "objective_floor": floor,
        "separation": sep,
        "ablation": {k: {m: v[m] for m in HEADLINE}
                     for k, v in ablation.items()},
        "ablation_reference": f3,
        "ablation_seeds": abl_seeds,
        "convergence_trace": traces,
        "per_seed": runs,
    }
    (OUT_DIR / "e4.json").write_text(json.dumps(payload, indent=2),
                                     encoding="utf-8")
    _write_md(payload, base, bands, floor, ablation, f3)
    print(f"\nwrote {OUT_DIR / 'e4.json'} and e4.md "
          f"({time.perf_counter() - t0:.0f} s)")


def _floor(dem) -> float:
    """Best objective any schedule could reach on this instance.

    Gaps, late starts, subject repeats and faculty gaps can all in
    principle be zero. The load-balance term cannot: a section's periods
    must split across five days, and 18 does not divide by 5, so the best
    possible daily-load sd is that of (4,4,4,3,3).
    """
    from collections import Counter
    per_section = Counter(sec for sec, _s, _f in dem)
    sigmas = []
    for credits in per_section.values():
        base_, rem = divmod(credits, scheduler.N_DAYS)
        loads = [base_ + 1] * rem + [base_] * (scheduler.N_DAYS - rem)
        sigmas.append(statistics.pstdev(loads))
    w = scheduler.DEFAULT_WEIGHTS["load_sigma"]
    return w * statistics.mean(sigmas) * scheduler.N_DAYS * len(per_section)


def _write_md(payload, base, bands, floor, ablation, f3) -> None:
    L = [
        "# E4 — P1 scheduler (greedy seed + simulated annealing)",
        "",
        f"Generated {payload['generated']}. "
        f"{payload['instance']['periods']} periods, "
        f"{payload['instance']['sections']} sections, "
        f"{payload['instance']['faculty']} teachers. "
        f"{len(payload['solver']['seeds'])} seeds, "
        f"{payload['solver']['iterations']:,} annealing steps.",
        "",
        "The v2 comparator is **read from the P0 freeze, not re-run**. Both "
        "solvers are scored by the same frozen metric module, which is "
        "hashed in `evaluation/FROZEN.sha256`.",
        "",
        "## Read the floor first, not the percentages",
        "",
        f"The best objective *any* schedule could reach on this instance is "
        f"**{floor:.1f}**. Idle gaps, late starts, subject repeats and "
        f"teacher gaps can all in principle be zero; the load-balance term "
        f"cannot, because a section's 18 periods do not divide evenly into "
        f"five days and the best attainable daily-load sd is that of "
        f"(4,4,4,3,3).",
        "",
        f"- **P1 lands {bands['objective']['mean'] - floor:.1f} above the "
        f"floor** ({bands['objective']['mean']:.1f} vs {floor:.1f}).",
        f"- **v2 is {base['objective']['mean'] - floor:.1f} above it** "
        f"({base['objective']['mean']:.1f}).",
        "",
        "That is the honest summary. The per-metric percentages below are "
        "large partly because v2 was not optimising these quantities at "
        "all, and one of them needs an explicit caveat — see *Why idle gaps "
        "reach zero*.",
        "",
        "| Metric | v2 greedy | P1 SA | Change |",
        "|---|---:|---:|---:|",
    ]
    for k in HEADLINE + ["solve_ms"]:
        b, p = base.get(k), bands.get(k)
        if b is None or p is None:
            continue
        if k == "solve_ms":
            chg = f"{p['min'] / b['mean']:.0f}–{p['max'] / b['mean']:.0f}× slower"
        elif b["mean"] == 0:
            chg = "—" if p["mean"] == 0 else f"+{p['mean']:.2f}"
        else:
            chg = f"{(p['mean'] - b['mean']) / b['mean']:+.1%}"
        cell = (f"{p['min']:.0f}–{p['max']:.0f}" if k == "solve_ms"
                else f"{p['mean']:.2f} ± {p['std']:.2f}")
        L.append(f"| {k} | {b['mean']:.2f} ± {b['std']:.2f} | {cell} | "
                 f"{chg} |")
    L += [
        "",
        "## Why idle gaps reach zero",
        "",
        f"Idle gaps come out at {bands['idle_gaps_total']['mean']:.2f} ± "
        f"{bands['idle_gaps_total']['std']:.2f}. **That is mostly "
        f"construction, not search.** The greedy seed lays each section out "
        f"as periods 0..load−1 on every day, which is gap-free and "
        f"late-start-free before a single annealing step runs; gaps only "
        f"appear where a teacher conflict forces an overflow, and the "
        f"objective then penalises them more heavily than anything else "
        f"(weight 5.0). A solver designed to produce compact days producing "
        f"compact days is not a discovery.",
        "",
        f"The number that is not built in is the **distance to the floor**: "
        f"{bands['objective']['mean'] - floor:.1f} points, made up of "
        f"{bands['late_start_days']['mean']:.2f} late starts, "
        f"{bands['subject_repeat_days']['mean']:.2f} subject repeats and "
        f"{bands['faculty_idle_gaps']['mean']:.2f} teacher gaps that the "
        f"search could not remove. Those are the residual, and they are "
        f"where a better solver would show up.",
        "",
        f"**A trade-off the objective does not price.** Compaction lengthens "
        f"the longest unbroken run of classes from "
        f"{base['longest_block_mean']['mean']:.2f} to "
        f"{bands['longest_block_mean']['mean']:.2f} periods. With 18 periods "
        f"over five gap-free days that is arithmetic, not a choice — but no "
        f"term in the frozen objective charges for it, so if four classes "
        f"back-to-back is worse than one mid-morning gap, this objective "
        f"cannot say so.",
        "",
        "## Ablation — each weight zeroed in the solver",
        "",
        "Scored by the **full** frozen objective, so removing a term shows "
        "up as the damage it was preventing.",
        "",
        "| Zeroed | Objective | Idle gaps | Late starts | Repeats | Teacher gaps |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    L.append(f"| *(none)* | {f3['objective']['mean']:.1f} | "
             f"{f3['idle_gaps_total']['mean']:.1f} | "
             f"{f3['late_start_days']['mean']:.1f} | "
             f"{f3['subject_repeat_days']['mean']:.1f} | "
             f"{f3['faculty_idle_gaps']['mean']:.1f} |")
    for name, ab in ablation.items():
        L.append(f"| {name} | {ab['objective']['mean']:.1f} | "
                 f"{ab['idle_gaps_total']['mean']:.1f} | "
                 f"{ab['late_start_days']['mean']:.1f} | "
                 f"{ab['subject_repeat_days']['mean']:.1f} | "
                 f"{ab['faculty_idle_gaps']['mean']:.1f} |")
    L += [
        "",
        "## What this is and is not",
        "",
        "Simulated annealing for timetabling is decades old and the plan "
        "(§4.4) retracted scheduling as a contribution. This is applied "
        "engineering with a measured before/after: the claim is that "
        "v2 had no objective function at all, that adding one fixes the "
        "two defects users actually complained about, and that it costs "
        f"{bands['solve_ms']['min'] / base['solve_ms']['mean']:.0f}× the "
        "solve time to do so — once, at generation.",
    ]
    (OUT_DIR / "e4.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
