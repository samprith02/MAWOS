"""E4b — the SA core against ITC-2007 track 3.

    python evaluation/itc2007/run_e4b.py                 # every instance
    python evaluation/itc2007/run_e4b.py comp01 comp02
    python evaluation/itc2007/run_e4b.py --seeds 3 --steps 200000

Reads `.ctt` files from `evaluation/itc2007/instances/` (see INSTANCES.md
— they are not in the repository and could not be downloaded
automatically), runs the annealer for the configured number of seeds, and
**passes every reported solution through the official validator**. A
penalty this harness prints has been agreed by the competition's own
binary, not only by our port of it.

What this is allowed to claim, from plan 4.4: *the scheduler
implementation was evaluated against a standard timetabling benchmark to
establish baseline competitiveness.* Never a contribution. If the gap to
published bests is large, that is the result and it gets reported as the
result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.itc2007 import ctt, solver          # noqa: E402
from evaluation.itc2007.build import validator_path  # noqa: E402

HERE = Path(__file__).resolve().parent
INSTANCES = HERE / "instances"
BESTS = INSTANCES / "BESTS.json"
OUT = ROOT / "evaluation" / "results" / "v3_itc2007"


def validate(exe: Path, inst_path: Path, inst: ctt.Instance,
             assignment: dict) -> tuple[int, int, str]:
    """Run the official validator; return (violations, total, warnings)."""
    with tempfile.TemporaryDirectory() as td:
        sol = Path(td) / "sol.out"
        sol.write_text(ctt.render_solution(inst, assignment), encoding="ascii")
        proc = subprocess.run([str(exe), str(inst_path), str(sol)],
                              capture_output=True, text=True, timeout=300)
    viol = total = None
    for line in proc.stdout.splitlines():
        if line.startswith("Summary:"):
            for part in line.split(","):
                if "Violations" in part:
                    viol = int(part.split("=")[1])
                elif "Total Cost" in part:
                    total = int(part.split("=")[1])
    if total is None:
        raise RuntimeError("validator produced no summary:" + chr(10)
                           + proc.stdout + proc.stderr)
    return viol or 0, total, proc.stderr.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="instance stems, e.g. comp01")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--steps", type=int, default=400_000)
    args = ap.parse_args()

    files = sorted(INSTANCES.glob("*.ctt"))
    if args.names:
        files = [f for f in files if f.stem in set(args.names)]
    if not files:
        print("No .ctt instances in %s" % INSTANCES.relative_to(ROOT))
        print()
        print("E4b cannot run without them, and this harness will not "
              "invent numbers to fill the gap.")
        print("See evaluation/itc2007/INSTANCES.md for why the automatic "
              "download failed and the three ways to supply them.")
        print()
        print("Everything else is ready and verified:")
        print("  python evaluation/itc2007/build.py       # official "
              "validator, hash-checked")
        print("  python evaluation/itc2007/crosscheck.py  # our cost model "
              "vs that validator")
        return 2

    exe = validator_path()
    bests = json.loads(BESTS.read_text(encoding="utf-8")) if BESTS.exists() \
        else {}
    OUT.mkdir(parents=True, exist_ok=True)

    print("E4b — ITC-2007 track 3, %d instance(s), %d seeds, %d steps"
          % (len(files), args.seeds, args.steps))
    if not bests:
        print("No instances/BESTS.json — reporting our penalties only; the "
              "comparison to published bests is pending a sourced table.")
    print("=" * 78)
    print("  %-10s %7s %8s %8s %8s %9s %8s" % ("instance", "lects", "best",
                                               "median", "worst", "published",
                                               "sec/seed"))
    print("  " + "-" * 74)

    rows = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        inst = ctt.parse(text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        totals, viols, times = [], [], []
        for s in range(args.seeds):
            t0 = time.perf_counter()
            res = solver.anneal(inst, seed_value=s, steps=args.steps)
            times.append(time.perf_counter() - t0)
            v, total, warn = validate(exe, path, inst, res.assignment)
            if warn:
                print("  !! validator warnings on %s seed %d: %s"
                      % (path.stem, s, warn.splitlines()[0]))
            if (v, total) != (res.cost.violations, res.cost.total):
                raise SystemExit(
                    "our cost model and the official validator disagree on "
                    "%s seed %d: ours=(%d,%d) validator=(%d,%d). Stop and "
                    "run crosscheck.py."
                    % (path.stem, s, res.cost.violations, res.cost.total,
                       v, total))
            viols.append(v)
            totals.append(total)

        feasible = [t for t, v in zip(totals, viols) if v == 0]
        pub = bests.get(path.stem, {}).get("best")
        rows.append({
            "instance": path.stem, "sha256": digest,
            "courses": len(inst.courses), "rooms": len(inst.rooms),
            "periods": inst.periods, "lectures": inst.total_lectures,
            "seeds": args.seeds, "steps": args.steps,
            "violations": viols, "totals": totals,
            "feasible_seeds": len(feasible),
            "best": min(feasible) if feasible else None,
            "median": statistics.median(feasible) if feasible else None,
            "worst": max(feasible) if feasible else None,
            "published_best": pub,
            "seconds_per_seed": statistics.median(times),
        })
        r = rows[-1]
        print("  %-10s %7d %8s %8s %8s %9s %8.1f"
              % (r["instance"], r["lectures"],
                 r["best"] if r["best"] is not None else "infeas",
                 r["median"] if r["median"] is not None else "-",
                 r["worst"] if r["worst"] is not None else "-",
                 pub if pub is not None else "-", r["seconds_per_seed"]))

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "validator_sha256_source": "see evaluation/itc2007/build.py",
        "seeds": args.seeds, "steps": args.steps,
        "published_bests_available": bool(bests),
        "rows": rows,
    }
    (OUT / "e4b.json").write_text(json.dumps(payload, indent=2),
                                  encoding="utf-8")
    print("=" * 78)
    infeasible = [r["instance"] for r in rows if r["feasible_seeds"] == 0]
    if infeasible:
        print("No feasible solution found on: %s. Reported as found, not "
              "hidden." % ", ".join(infeasible))
    print("wrote %s" % (OUT / "e4b.json").relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
