"""P3 -- provenance gate dev-only engineering validation (RQ2, §3.2).

    python evaluation/gate_p3.py

What this measures
-------------------
H2: "a deterministic extract-and-match gate reduces ungrounded numeric
claims at acceptable false-block and latency cost." Two things, on the
99-task dev split, restricted to the tools whose answers actually carry
numbers (`get_attendance`, `get_fees`, `get_marks`, `get_dept_analytics`,
`get_student_overview`, `get_placements` -- 54 of the 99 dev tasks):

  * **Catch rate** -- for each genuine answer, one real numeric claim is
    replaced with a fabricated value (a synthetic hallucination with a
    known-ungrounded label) and re-checked. This is the gate's recall on
    a case it is guaranteed to be wrong about.
  * **Block rate on genuine answers** -- every real (uncorrupted) answer
    is also checked. Any block here is inspected by hand (printed to
    `p3_provenance.md`) and classified as either a real catch (the model
    stated a number the tools never returned) or a false block (a real,
    grounded number the extractor/matcher missed) -- this script cannot
    tell the two apart automatically, so it reports both counts and
    leaves the classification auditable rather than asserting one.

Why this is not the full 3-seed convention every other P-phase uses:
this is a first engineering pass at whether the gate mechanism works at
all, with ground truth controlled by synthetic corruption rather than
real annotated hallucinations (which do not exist yet -- P5 is still
blocked on external authors). One seed, temperature 0.1 (near-
deterministic), same model PROTOCOL §9.2 selected. Scaling this to 3
seeds is cheap to add once the mechanism itself is validated.

Tools here are read-only (verified by inspection before this script was
written) but this still runs against a throwaway copy of `mawos.db`,
never the shipped one -- same caution `capture_llm.py` takes by hashing
the shipped DB, just structurally guaranteed here instead.
"""
import asyncio
import json
import re
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHIPPED_DB = ROOT / "mawos.db"
SCRATCH_DB = ROOT / "evaluation" / "results" / "v3_gates" / "_p3_scratch.db"
OUT_DIR = ROOT / "evaluation" / "results" / "v3_gates"

NUMERIC_TOOLS = {"get_attendance", "get_fees", "get_marks",
                 "get_dept_analytics", "get_student_overview", "get_placements"}


def _corrupt(text: str, provenance) -> str | None:
    """Replace the first numeric claim in `text` with a fabricated value.

    Returns None if there is nothing to corrupt with.
    """
    nums = provenance.extract_numbers(text)
    if not nums:
        return None
    victim = nums[0]
    fake = victim + 1000.0 if victim < 500 else victim / 7.0 + 3.14159
    pattern = re.compile(re.escape(f"{victim:g}"))
    new_text, n = pattern.subn(f"{fake:g}", text, count=1)
    return new_text if n else None


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(SHIPPED_DB, SCRATCH_DB)
    import os
    os.environ["MAWOS_DATABASE_URL"] = f"sqlite:///{SCRATCH_DB}"

    from backend.app import config, provenance
    from backend.app.agents import get_agents, tools as toolreg
    from backend.app.database import SessionLocal
    from backend.app.models import User
    from evaluation.benchmark.tasks import DEV_TASKS

    config.PROVENANCE_GATE_ENABLED = False  # capture raw text; check() still runs

    db = SessionLocal()
    try:
        agents = get_agents()
        orch = agents["orchestrator_agent"]

        from backend.app import llm as llm_mod
        if not llm_mod.check_ollama(force=True):
            sys.exit("Ollama is not reachable at "
                      f"{config.OLLAMA_HOST} -- start it first (see CLAUDE.md).")

        users = {}
        student = db.query(User).filter_by(username="4MT23AI049").first()
        if student:
            users["student"] = student
        for role in ("faculty", "hod", "principal", "admin"):
            u = db.query(User).filter_by(role=role).first()
            if u:
                users[role] = u

        tasks = [t for t in DEV_TASKS if t.gold_tool in NUMERIC_TOOLS]
        missing = {t.asker_role for t in tasks} - set(users)
        if missing:
            sys.exit(f"no benchmark user for role(s): {missing}")

        print(f"P3 gate dev validation: {len(tasks)} numeric-answer dev tasks "
              f"(of {len(DEV_TASKS)}), model {config.OLLAMA_MODEL}, seed 0")

        genuine, corrupted, skipped, gate_overhead_ms = [], [], [], []
        for i, t in enumerate(tasks, 1):
            user = users.get(t.asker_role) or users["student"]
            resp = await orch._handle_llm(db, user, t.query)
            if resp is None:
                skipped.append({"task_id": t.id, "reason": "llm_unavailable_or_gave_up"})
                continue
            gate = resp.get("provenance")
            if gate is None:
                skipped.append({"task_id": t.id, "reason": "no_tool_called"})
                continue

            tool_results = [toolreg.execute(db, agents, user, tu["name"], tu["args"])
                            for tu in resp["tools_used"]]

            t0 = time.perf_counter()
            regrounded = provenance.check(resp["text"], tool_results)
            gate_overhead_ms.append((time.perf_counter() - t0) * 1000)
            assert regrounded["blocked"] == gate["blocked"], t.id  # sanity: reproducible

            genuine.append({
                "task_id": t.id, "query": t.query, "gold_tool": t.gold_tool,
                "text": resp["text"],
                "tools_used": [tu["name"] for tu in resp["tools_used"]],
                "blocked": gate["blocked"], "claims_checked": gate["claims_checked"],
                "ungrounded": gate["ungrounded"],
            })

            grounded_set = provenance.grounded_numbers(tool_results)
            c_text = _corrupt(resp["text"], provenance)
            if c_text is None:
                continue
            c_check = provenance.check(c_text, tool_results)
            corrupted.append({
                "task_id": t.id, "text": c_text, "blocked": c_check["blocked"],
                "ungrounded": c_check["ungrounded"],
            })
            if i % 10 == 0:
                print(f"  {i}/{len(tasks)}", flush=True)

        n_g, n_c = len(genuine), len(corrupted)
        blocked_genuine = [g for g in genuine if g["blocked"]]
        caught_corrupted = [c for c in corrupted if c["blocked"]]
        block_rate_genuine = len(blocked_genuine) / n_g if n_g else 0.0
        catch_rate = len(caught_corrupted) / n_c if n_c else 0.0
        mean_overhead_us = statistics.mean(gate_overhead_ms) * 1000 if gate_overhead_ms else 0.0

        print(f"\ngenuine answers checked: {n_g}  ({len(skipped)} skipped -- "
              f"see report for reasons)")
        print(f"  blocked on genuine (uncorrupted) answers: "
              f"{len(blocked_genuine)}/{n_g} = {block_rate_genuine:.1%}")
        print(f"corrupted answers checked: {n_c}")
        print(f"  caught (correctly blocked): {len(caught_corrupted)}/{n_c} "
              f"= {catch_rate:.1%}")
        print(f"gate overhead: {mean_overhead_us:.1f} us/check "
              "(pure regex/set arithmetic, no model call)")

        payload = {
            "rule": "dev-only engineering pass, H2 (RESEARCH_PLAN_V3.md §3.2)",
            "model": config.OLLAMA_MODEL, "split": "dev", "seed": 0,
            "n_numeric_dev_tasks": len(tasks),
            "n_genuine_checked": n_g, "n_corrupted_checked": n_c,
            "n_skipped": len(skipped), "skipped": skipped,
            "block_rate_on_genuine_answers": block_rate_genuine,
            "catch_rate_on_synthetic_corruption": catch_rate,
            "mean_gate_overhead_us": mean_overhead_us,
            "genuine_records": genuine,
            "corrupted_records": corrupted,
            "blocked_genuine_for_manual_review": blocked_genuine,
        }
        (OUT_DIR / "p3_provenance.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")

        md = [
            "# P3 -- provenance gate dev-only engineering validation",
            "",
            f"`{config.OLLAMA_MODEL}`, dev split, seed 0 -- **one seed, not the "
            "3-seed convention** (see this file's module docstring for why). "
            f"{n_g} genuine answers checked, {len(skipped)} tasks skipped "
            "(no tool called, or the LLM path gave up).",
            "",
            "## Headline numbers",
            "",
            f"- **Catch rate on synthetic corruption: {catch_rate:.1%}** "
            f"({len(caught_corrupted)}/{n_c}) -- one real numeric claim per "
            "answer replaced with a fabricated value; ground truth is "
            "ungrounded by construction.",
            f"- **Block rate on genuine answers: {block_rate_genuine:.1%}** "
            f"({len(blocked_genuine)}/{n_g}) -- not automatically labelled "
            "false-vs-true, see manual review below.",
            f"- Gate overhead: **{mean_overhead_us:.1f} µs/check** -- pure "
            "regex/set arithmetic, no model call; negligible next to LLM "
            "inference latency.",
            "",
            "## Manual review of blocks on genuine (uncorrected) answers",
            "",
            "Each row needs a human read of `text` against `ungrounded` to "
            "decide: a real catch (the model actually stated an invented "
            "number) or a false block (a real, grounded number the "
            "extractor/matcher missed -- e.g. an unusual phrasing).",
            "",
        ]
        if blocked_genuine:
            md.append("| task | ungrounded values | answer text |")
            md.append("|---|---|---|")
            for g in blocked_genuine:
                md.append(f"| {g['task_id']} | {g['ungrounded']} | "
                          f"{g['text'][:200].replace(chr(10), ' ')} |")
        else:
            md.append("None -- every genuine answer in this pass was fully grounded.")
        md += [
            "",
            "## How to state this",
            "",
            "*A dev-only engineering pass of the provenance gate mechanism "
            f"catches {catch_rate:.0%} of synthetically injected ungrounded "
            f"numeric claims at a {block_rate_genuine:.0%} block rate on real "
            "(uncorrupted) answers.* This is not RQ2's confirmed result -- "
            "it validates the mechanism works at all, on synthetic ground "
            "truth, at one seed. A corpus of real annotated hallucinations "
            "and the 3-seed convention are both still pending (tracks with "
            "P5, blocked on external authors).",
        ]
        (OUT_DIR / "p3_provenance.md").write_text("\n".join(md) + "\n", encoding="utf-8")

        print(f"\nwrote {OUT_DIR / 'p3_provenance.json'}")
        print(f"wrote {OUT_DIR / 'p3_provenance.md'}")
    finally:
        db.close()
        from backend.app.database import engine
        engine.dispose()          # release the sqlite file handle (Windows locks it)
        if SCRATCH_DB.exists():
            try:
                SCRATCH_DB.unlink()
            except PermissionError:
                print(f"note: could not remove {SCRATCH_DB} (still locked); "
                      "harmless, delete it by hand if it bothers you")


if __name__ == "__main__":
    asyncio.run(main())
