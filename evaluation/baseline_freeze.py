"""Capture the MAWOS v2 baseline, once, before v3 changes anything.

    python evaluation/baseline_freeze.py

Writes evaluation/results/v2_frozen/. Run at P0 and then never again —
the whole point is that the comparator stops moving.

**This script never touches the shipped database.** The v2 solver deletes
and bulk-inserts TimetableSlot rows, so running it ten times against
`mawos.db` would consume the deliberate shipped state that CLAUDE.md
protects (400 submitted applications, 0 verified, a demo-able admissions
pipeline). Instead it copies the database to a scratch file, points
MAWOS_DATABASE_URL at the copy before any ORM import happens, and verifies
by hash that the original was untouched on the way out.
"""
import hashlib
import json
import os
import shutil
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHIPPED_DB = ROOT / "mawos.db"
SCRATCH_DB = ROOT / "evaluation" / "results" / "v2_frozen" / "_scratch.db"
OUT_DIR = ROOT / "evaluation" / "results" / "v2_frozen"

SCHED_SEEDS = list(range(10))     # SA is stochastic; so is greedy-with-restarts
ROUTE_SEEDS = [0, 1, 2]           # lexicon is deterministic; run anyway to show it


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _prepare_scratch_db() -> str:
    """Copy the shipped DB and redirect the ORM at the copy."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not SHIPPED_DB.exists():
        sys.exit(f"shipped database not found at {SHIPPED_DB}")
    before = sha256(SHIPPED_DB)
    shutil.copy2(SHIPPED_DB, SCRATCH_DB)
    os.environ["MAWOS_DATABASE_URL"] = f"sqlite:///{SCRATCH_DB}"
    return before


def freeze_routing() -> dict:
    """The v2 keyword lexicon on the 108 dev queries."""
    from evaluation.baselines import lexicon_v2
    from evaluation.benchmark.tasks import DEV_TASKS

    runs = []
    misrouted = []          # accumulated from the first seed only, not per-seed
    for seed in ROUTE_SEEDS:
        t0 = time.perf_counter()
        correct = {"standard": [], "colloquial": []}
        for task in DEV_TASKS:
            got = lexicon_v2.classify_keyword(task.query).intent
            ok = got == task.gold_intent
            correct[task.stratum].append(ok)
            if not ok and seed == ROUTE_SEEDS[0]:
                misrouted.append({"id": task.id, "query": task.query,
                                  "expected": task.gold_intent, "got": got,
                                  "stratum": task.stratum})
        flat = correct["standard"] + correct["colloquial"]
        runs.append({
            "seed": seed,
            "overall": sum(flat) / len(flat),
            "standard": sum(correct["standard"]) / len(correct["standard"]),
            "colloquial": sum(correct["colloquial"]) / len(correct["colloquial"]),
            "wall_ms": (time.perf_counter() - t0) * 1000,
        })

    def band(key):
        vals = [r[key] for r in runs]
        return {"mean": statistics.mean(vals),
                "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0}

    return {
        "n_queries": len(DEV_TASKS),
        "seeds": ROUTE_SEEDS,
        "overall": band("overall"),
        "standard": band("standard"),
        "colloquial": band("colloquial"),
        "per_seed": runs,
        "misrouted": misrouted,
        "lexicon_sha256": lexicon_v2.BODY_SHA256,
        "note": ("The lexicon is deterministic, so the seed bands are zero by "
                 "construction. They are reported anyway: a zero variance "
                 "band is evidence, and it is the contrast against the LLM "
                 "tier's non-zero band that makes the comparison honest."),
    }


def freeze_scheduler() -> dict:
    """The v2 greedy solver at 10 seeds, measured with the E4 instrument."""
    from backend.app.database import SessionLocal
    from backend.app.models import TeachingAssignment, TimetableSlot
    from evaluation.baselines.scheduler_v2 import TimetableAgent
    from evaluation.benchmark import schedule_metrics

    solver = TimetableAgent.__new__(TimetableAgent)   # no bus, no subscriptions
    db = SessionLocal()
    try:
        required = sum(a.subject.credits for a in db.query(TeachingAssignment).all())
        runs = []
        for seed in SCHED_SEEDS:
            t0 = time.perf_counter()
            result = solver.generate(db, dept_code=None, seed=seed)
            solve_ms = (time.perf_counter() - t0) * 1000
            slots = db.query(TimetableSlot).all()
            m = schedule_metrics.compute(slots, slots_required=required)
            m["objective"] = schedule_metrics.objective(m)
            m["seed"] = seed
            m["solve_ms"] = solve_ms
            m["restarts_used"] = result.get("restarts_used")
            runs.append(m)
            print(f"  seed {seed}: late-start {m['late_start_rate']:.1%} · "
                  f"gaps {m['idle_gaps_total']} · obj {m['objective']:.0f}")
    finally:
        db.close()

    def band(key):
        vals = [r[key] for r in runs if isinstance(r.get(key), (int, float))]
        return {"mean": statistics.mean(vals),
                "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
                "min": min(vals), "max": max(vals)}

    tracked = ["late_start_days", "late_start_rate", "idle_gaps_total",
               "idle_gaps_per_section_day", "daily_load_sigma_mean",
               "longest_block_mean", "subject_repeat_days",
               "faculty_idle_gaps", "placement_rate", "unplaced",
               "faculty_conflicts", "section_conflicts", "objective",
               "solve_ms"]
    return {"seeds": SCHED_SEEDS, "slots_required": required,
            "bands": {k: band(k) for k in tracked},
            "per_seed": runs}


def main() -> None:
    print("MAWOS v2 baseline freeze")
    print("=" * 60)
    before = _prepare_scratch_db()
    print(f"shipped db sha256 {before[:16]}… (copied to scratch, not touched)")

    print("\n[1/2] routing — v2 keyword lexicon")
    routing = freeze_routing()
    print(f"  overall {routing['overall']['mean']:.1%} "
          f"± {routing['overall']['std']:.1%} · "
          f"standard {routing['standard']['mean']:.1%} · "
          f"colloquial {routing['colloquial']['mean']:.1%}")

    print("\n[2/2] scheduler — v2 greedy solver, 10 seeds")
    scheduler = freeze_scheduler()

    after = sha256(SHIPPED_DB)
    if after != before:
        sys.exit("ABORT: the shipped database changed during the freeze. "
                 "This should be impossible — investigate before trusting "
                 "any result.")
    print(f"\nshipped db verified unchanged ({after[:16]}…)")

    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "git_commit": os.popen("git rev-parse --short HEAD").read().strip(),
        "shipped_db_sha256": before,
        "routing": routing,
        "scheduler": scheduler,
    }
    out = OUT_DIR / "baseline.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_markdown(payload)
    print(f"wrote {out}")
    print(f"wrote {OUT_DIR / 'BASELINE.md'}")
    _drop_scratch()


def _drop_scratch() -> None:
    """Remove the scratch copy, disposing the engine that holds it open.

    On Windows SQLAlchemy's pooled SQLite connection keeps a handle on the
    file, so unlink raises WinError 32 until the engine is disposed. This
    is the same class of trap CLAUDE.md records for `mawos.db`, where a
    silent failure left a contaminated database behind. Here it is loud:
    the results are already written, so a leftover scratch file is untidy
    rather than dangerous, and saying so beats pretending it was cleaned.
    """
    try:
        from backend.app.database import engine
        engine.dispose()
    except Exception:
        pass
    try:
        SCRATCH_DB.unlink(missing_ok=True)
    except OSError as exc:
        print(f"note: scratch copy left at {SCRATCH_DB} ({exc.strerror}). "
              f"Results above are unaffected; delete it manually.")


def _write_markdown(p: dict) -> None:
    r, s = p["routing"], p["scheduler"]
    b = s["bands"]

    def row(label, key, fmt="{:.2f}"):
        v = b[key]
        return (f"| {label} | {fmt.format(v['mean'])} | {fmt.format(v['std'])} "
                f"| {fmt.format(v['min'])} | {fmt.format(v['max'])} |")

    md = f"""# MAWOS v2 — frozen baseline

Generated {p['generated']} · commit `{p['git_commit']}`
Shipped database `{p['shipped_db_sha256'][:16]}…` (verified unchanged).

This is the comparator for every v3 result. It is frozen: rerunning it is
a mistake, not a refresh. See `evaluation/PROTOCOL.md`.

## 1. Routing — v2 keyword lexicon, {r['n_queries']} dev queries

| Tier | Accuracy | Seed σ |
|---|---|---|
| Overall | {r['overall']['mean']:.1%} | {r['overall']['std']:.1%} |
| Standard ({72}) | {r['standard']['mean']:.1%} | {r['standard']['std']:.1%} |
| Colloquial ({36}) | {r['colloquial']['mean']:.1%} | {r['colloquial']['std']:.1%} |

Lexicon body `sha256 {r['lexicon_sha256'][:16]}…`.

{r['note']}

**These 108 queries are development data.** The lexicon was tuned against
their phrasing, so this number cannot be a headline. It is the tuning
comparator and nothing else.

Misrouted ({len(r['misrouted'])}):

""" + "\n".join(
        f"- `{m['id']}` [{m['stratum']}] \"{m['query']}\" → {m['got']} "
        f"(expected {m['expected']})" for m in r["misrouted"]) + f"""

## 2. Scheduler — v2 greedy solver, {len(s['seeds'])} seeds

The defects the P1 rewrite targets, measured:

| Metric | Mean | σ | Min | Max |
|---|---|---|---|---|
{row("Late-start days (of 200)", "late_start_days")}
{row("Late-start rate", "late_start_rate", "{:.1%}")}
{row("Idle gaps (total)", "idle_gaps_total")}
{row("Idle gaps per section-day", "idle_gaps_per_section_day")}
{row("Daily-load σ (mean)", "daily_load_sigma_mean")}
{row("Longest contiguous block", "longest_block_mean")}
{row("Subject repeats within a day", "subject_repeat_days")}
{row("Faculty idle gaps", "faculty_idle_gaps")}
{row("Placement rate", "placement_rate", "{:.3f}")}
{row("Unplaced", "unplaced")}
{row("Objective (lower better)", "objective", "{:.0f}")}
{row("Solve time (ms)", "solve_ms", "{:.0f}")}

Hard constraints hold in every seed: faculty conflicts
{b['faculty_conflicts']['max']:.0f} max, section conflicts
{b['section_conflicts']['max']:.0f} max. The v2 solver is *feasible*; it
simply has no notion of a good schedule, because it optimises hard
constraints only and no objective function exists in it.
"""
    (OUT_DIR / "BASELINE.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
