"""Hash the frozen measuring instrument. PROTOCOL.md §1.5.

    python evaluation/freeze_manifest.py            # verify (exit 1 on drift)
    python evaluation/freeze_manifest.py --write    # regenerate the manifest

The files listed below define *what is measured*: the task set and its
gold labels, the distractors, the tool-space construction, the seven RQ1
instrumentation fields, the scheduling metrics, and the two v2 baselines
every v3 number is compared against.

Why this exists. P1 rewrites the scheduler and P7 draws the figures, and
both are natural places to "just fix" a metric definition in passing — a
tweak to how an idle gap is counted would silently move the frozen
baseline that P1 is supposed to beat. The manifest turns that from an
invisible edit into a failing test.

Regenerating is allowed. Regenerating *quietly* is not: `--write` prints
the diff, and PROTOCOL.md §12 needs a dated entry saying why.

Newlines are normalised before hashing so the digests survive git's
autocrlf on Windows.
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "evaluation" / "FROZEN.sha256"

#: Every file that defines what is measured. Not the analysis scripts —
#: those may be fixed and re-run; these may not be touched at all.
FROZEN = [
    "evaluation/benchmark/tasks.py",
    "evaluation/benchmark/distractors.py",
    "evaluation/benchmark/toolspace.py",
    "evaluation/benchmark/instrumentation.py",
    "evaluation/benchmark/schedule_metrics.py",
    "evaluation/baselines/lexicon_v2.py",
    "evaluation/baselines/scheduler_v2.py",
    "backend/app/router_config.json",
]


def digest(rel: str) -> str:
    body = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(body).hexdigest()


def current() -> dict[str, str]:
    return {rel: digest(rel) for rel in FROZEN}


def recorded() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    out = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        h, rel = line.split(None, 1)
        out[rel.strip()] = h
    return out


def drift() -> list[str]:
    now, was = current(), recorded()
    problems = []
    if not was:
        return ["FROZEN.sha256 is missing — run with --write"]
    for rel in FROZEN:
        if rel not in was:
            problems.append(f"{rel}: not in the manifest")
        elif was[rel] != now[rel]:
            problems.append(f"{rel}: MODIFIED\n    was {was[rel]}\n"
                            f"    now {now[rel]}")
    for rel in was:
        if rel not in now:
            problems.append(f"{rel}: in the manifest but no longer frozen")
    return problems


def write() -> None:
    was = recorded()
    now = current()
    lines = [
        "# Frozen measuring instrument — PROTOCOL.md §1.5.",
        "# sha256 of each file with newlines normalised to LF.",
        "# Regenerate with: python evaluation/freeze_manifest.py --write",
        "# A regeneration needs a dated entry in PROTOCOL.md §12.",
        "",
    ]
    for rel in FROZEN:
        lines.append(f"{now[rel]}  {rel}")
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    changed = [r for r in FROZEN if was.get(r) not in (None, now[r])]
    added = [r for r in FROZEN if r not in was]
    for rel in changed:
        print(f"CHANGED {rel}\n  was {was[rel]}\n  now {now[rel]}")
    for rel in added:
        print(f"ADDED   {rel}  {now[rel]}")
    if not changed and not added:
        print("manifest unchanged")
    if changed:
        print("\nA frozen file changed. PROTOCOL.md §12 needs a dated entry,\n"
              "and every result computed before this point was computed\n"
              "against the previous instrument.")
    print(f"\nwrote {MANIFEST}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="regenerate the manifest instead of verifying it")
    if ap.parse_args().write:
        write()
        return
    problems = drift()
    if problems:
        print("FROZEN INSTRUMENT DRIFT — PROTOCOL.md §1.5")
        for p in problems:
            print(f"  {p}")
        sys.exit(1)
    print(f"frozen instrument verified — {len(FROZEN)} files unchanged")


if __name__ == "__main__":
    main()
