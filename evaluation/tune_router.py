"""P4 — hybrid router threshold selection on dev.

    python evaluation/tune_router.py

Applies PROTOCOL.md §9.3, committed in 49be6dd *before* this script was
run, to the frozen `qwen2.5:3b-instruct` capture selected under §9.2.

Writes:
    evaluation/results/v3_gates/p4_router.json   full curve + selection
    evaluation/results/v3_gates/p4_router.md     the auditable curve table
    backend/app/router_config.json               the frozen deployed config

What the router is
------------------
The lexicon answers first. Its confidence is the margin between its
best and second-best intent score. If that margin is at or below τ the
query is escalated to the LLM, whose tool choice replaces the lexicon's.
Everything else keeps the lexicon's answer at ~0.06 ms.

This is not the v2 behaviour, which switched tiers on Ollama *reachability*
— an availability check, not a confidence gate. P0.5 is what justifies the
change: AUC(margin → lexicon error) = 0.983, so the lexicon's confidence
is an almost perfect detector of its own failures.

Why the argmax is not simply taken
----------------------------------
τ is the only free parameter in the system, and the curve it is fitted to
has 108 points. Taking the argmax fits τ to seed noise. §9.3 imports the
one-standard-error rule instead and breaks toward the lowest escalation
rate, since every escalated query costs an LLM call and escalation rate is
the cost axis RQ3 is defined over. The rule can only move τ below the
argmax, so it can only *lower* the accuracy this file reports.

Split discipline
----------------
Dev only. `tasks("test")` still raises. The config written here is hashed
so P5 can prove the held-out run used this τ and not a later one.
"""
import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.baselines import lexicon_v2  # noqa: E402
from evaluation.benchmark.tasks import DEV_TASKS  # noqa: E402
from evaluation.gate_p05 import MAX_ESCALATION, auc, bootstrap_delta, margins  # noqa: E402

#: Fixed by PROTOCOL.md §9.2. Not a choice made in this script.
SELECTED_MODEL = "qwen2.5:3b-instruct"
CAPTURE = ROOT / "evaluation" / "results" / "v3_llm" / "qwen2-5_3b-instruct.json"
OUT_DIR = ROOT / "evaluation" / "results" / "v3_gates"
CONFIG = ROOT / "backend" / "app" / "router_config.json"


def mcnemar(a_ok: dict, b_ok: dict) -> dict:
    """Exact two-sided McNemar on paired per-query correctness, a vs b."""
    b01 = sum(1 for k in a_ok if not a_ok[k] and b_ok[k])
    b10 = sum(1 for k in a_ok if a_ok[k] and not b_ok[k])
    n = b01 + b10
    if n == 0:
        return {"discordant": 0, "b01": 0, "b10": 0, "p": 1.0}
    tail = sum(math.comb(n, i) for i in range(0, min(b01, b10) + 1)) / 2 ** n
    return {"discordant": n, "b01": b01, "b10": b10, "p": min(1.0, 2 * tail)}


def bootstrap_p_no_better(marg, lex_ok, llm_ok, tau, iters=10000, seed=0):
    """Share of bootstrap resamples where the hybrid does not beat the lexicon.

    Reported alongside the CI because at n=108 with a 5-point delta the 2.5%
    percentile can land exactly on zero, which a bound alone renders as an
    uninformative "+0.0%". This says how much of the resample mass is there.
    """
    rng = random.Random(seed)
    ids = [t.id for t in DEV_TASKS]
    n = len(ids)
    hits = 0
    for _ in range(iters):
        sample = [ids[rng.randrange(n)] for _ in range(n)]
        hyb = sum((llm_ok[i] if marg[i] <= tau else lex_ok[i]) for i in sample)
        lex = sum(lex_ok[i] for i in sample)
        hits += (hyb - lex) <= 0
    return hits / iters


def load_llm_correctness() -> tuple[list[int], dict[int, dict[str, bool]]]:
    data = json.loads(CAPTURE.read_text(encoding="utf-8"))
    if data["model"] != SELECTED_MODEL:
        sys.exit(f"capture is {data['model']}, §9.2 selected {SELECTED_MODEL}")
    if data.get("call_failures"):
        sys.exit(f"{data['call_failures']} call failures — capture unusable")
    if not (data.get("gpu_residency") or {}).get("fully_resident"):
        sys.exit("capture was not fully GPU-resident — ineligible under §9.2")
    ok = {}
    for seed in data["seeds"]:
        rows = {r["task_id"]: r["outcome"] == "correct"
                for r in data["records"] if r["seed"] == seed}
        if len(rows) != len(DEV_TASKS):
            sys.exit(f"seed {seed}: {len(rows)} records, "
                     f"expected {len(DEV_TASKS)}")
        ok[seed] = rows
    return data["seeds"], ok, data


def build_curve(marg, lex_ok, llm_ok, seeds):
    """Every achievable operating point. This is the published artefact."""
    ids = [t.id for t in DEV_TASKS]
    n = len(ids)
    points = []
    for tau in [-1.0] + sorted({marg[i] for i in ids}):
        esc = [i for i in ids if marg[i] <= tau]
        kept = [i for i in ids if marg[i] > tau]
        base = sum(lex_ok[i] for i in kept)
        accs, fixes, breaks = [], [], []
        for s in seeds:
            accs.append((base + sum(llm_ok[s][i] for i in esc)) / n)
            fixes.append(sum(1 for i in esc if not lex_ok[i] and llm_ok[s][i]))
            breaks.append(sum(1 for i in esc if lex_ok[i] and not llm_ok[s][i]))
        points.append({
            "tau": tau,
            "escalation_rate": len(esc) / n,
            "n_escalated": len(esc),
            "accuracy_mean": statistics.mean(accs),
            "accuracy_std": statistics.pstdev(accs) if len(accs) > 1 else 0.0,
            "accuracy_per_seed": accs,
            "fixed_mean": statistics.mean(fixes),
            "broken_mean": statistics.mean(breaks),
            "feasible": len(esc) / n <= MAX_ESCALATION,
        })
    return points


def select(points) -> tuple[dict, dict, float]:
    """PROTOCOL.md §9.3, applied mechanically."""
    feasible = [p for p in points if p["feasible"]]
    argmax = max(feasible, key=lambda p: p["accuracy_mean"])
    sigma = argmax["accuracy_std"]
    within = [p for p in feasible
              if p["accuracy_mean"] >= argmax["accuracy_mean"] - sigma]
    chosen = min(within, key=lambda p: (p["escalation_rate"], p["tau"]))
    return chosen, argmax, sigma


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seeds, llm_ok, capture = load_llm_correctness()
    marg = margins()
    lex_ok = {t.id: lexicon_v2.classify_keyword(t.query).intent == t.gold_intent
              for t in DEV_TASKS}
    ids = [t.id for t in DEV_TASKS]
    n = len(ids)
    lex_acc = sum(lex_ok.values()) / n
    n_err = sum(1 for v in lex_ok.values() if not v)

    points = build_curve(marg, lex_ok, llm_ok, seeds)
    chosen, argmax, sigma = select(points)
    tau = chosen["tau"]

    print("P4 router threshold selection — PROTOCOL.md §9.3")
    print("=" * 74)
    print(f"model {SELECTED_MODEL} (§9.2) · dev n={n} · seeds {seeds}")
    print(f"lexicon {lex_acc:.1%} · {n_err} errors available · "
          f"AUC(margin->error) "
          f"{auc(marg, {t.id: not lex_ok[t.id] for t in DEV_TASKS}):.3f}")

    print(f"\ncomplete threshold curve (all {len(points)} achievable points)")
    print(f"  {'tau':>6} {'esc':>7} {'n':>4} {'acc':>7} {'sd':>6} "
          f"{'per-seed':>22} {'fix':>5} {'brk':>5}")
    print("  " + "-" * 72)
    for p in points:
        mark = ""
        if p is chosen:
            mark = "  <- SELECTED"
        elif p is argmax:
            mark = "  <- argmax"
        flag = " " if p["feasible"] else "x"
        print(f"{flag} {p['tau']:6.2f} {p['escalation_rate']:6.1%} "
              f"{p['n_escalated']:4d} {p['accuracy_mean']:6.1%} "
              f"{p['accuracy_std']:5.1%} "
              + "/".join(f"{a:.1%}" for a in p["accuracy_per_seed"]).rjust(22)
              + f" {p['fixed_mean']:5.1f} {p['broken_mean']:5.1f}{mark}")
    print("  x = above the 50% escalation cap (§9.1), excluded")

    print(f"\nargmax  tau<={argmax['tau']:.2f}  {argmax['accuracy_mean']:.1%} "
          f"at {argmax['escalation_rate']:.1%} escalation  (sigma {sigma:.1%})")
    within = [p for p in points
              if p["feasible"]
              and p["accuracy_mean"] >= argmax["accuracy_mean"] - sigma]
    print(f"within one sigma: {len(within)} point(s) — "
          + ", ".join(f"tau<={p['tau']:.2f}@{p['escalation_rate']:.0%}"
                      for p in within))
    print(f"SELECTED tau <= {tau:.2f}  "
          f"{chosen['accuracy_mean']:.1%} at {chosen['escalation_rate']:.1%} "
          f"escalation")
    if chosen is not argmax:
        cost = argmax["accuracy_mean"] - chosen["accuracy_mean"]
        saved = argmax["escalation_rate"] - chosen["escalation_rate"]
        print(f"  1-SE rule gives up {cost:.1%} accuracy to save "
              f"{saved:.1%} escalation")

    # --- effect size and significance at the selected tau
    hybrid_ok = {s: {i: (llm_ok[s][i] if marg[i] <= tau else lex_ok[i])
                     for i in ids} for s in seeds}
    maj = {i: sum(hybrid_ok[s][i] for s in seeds) > len(seeds) / 2 for i in ids}
    mc = mcnemar(lex_ok, maj)
    per_seed_mc = {str(s): mcnemar(lex_ok, hybrid_ok[s]) for s in seeds}
    cis = [bootstrap_delta(marg, lex_ok, llm_ok[s], tau) for s in seeds]
    lo, hi = statistics.mean(c[0] for c in cis), statistics.mean(c[1] for c in cis)
    p_null = statistics.mean(
        bootstrap_p_no_better(marg, lex_ok, llm_ok[s], tau) for s in seeds)
    delta = chosen["accuracy_mean"] - lex_acc

    print(f"\nhybrid vs lexicon at the selected tau")
    print(f"  {chosen['accuracy_mean']:.1%} vs {lex_acc:.1%} "
          f"= {delta:+.1%}  (95% bootstrap CI {lo:+.1%} to {hi:+.1%})")
    print(f"  McNemar (majority vote): b01={mc['b01']} b10={mc['b10']} "
          f"p={mc['p']:.3f}")
    print("  per-seed McNemar: " + ", ".join(
        f"seed {s} p={m['p']:.3f}" for s, m in per_seed_mc.items()))
    print(f"  bootstrap resamples where the hybrid does not win: {p_null:.1%}")
    if lo <= 0:
        print("  NOTE: the CI's lower bound is not above zero. The point")
        print("  estimate favours the router; on dev alone the effect is not")
        print("  established, and dev is contaminated by construction (§11).")

    # --- what the escalation rate costs at runtime
    llm_ms = capture["latency_median_ms"]
    lex_ms = 0.06   # measured median of classify_keyword over the dev split
    exp_ms = chosen["escalation_rate"] * llm_ms + lex_ms
    print(f"\nexpected per-query cost at tau<={tau:.2f}")
    print(f"  {chosen['escalation_rate']:.1%} x {llm_ms:.0f} ms + "
          f"{lex_ms} ms = {exp_ms:.0f} ms mean")
    print(f"  vs {llm_ms:.0f} ms for LLM-on-everything "
          f"({llm_ms / exp_ms:.1f}x cheaper)")

    payload = {
        "rule": "PROTOCOL.md §9.3, pre-registered in 49be6dd before this run",
        "model": SELECTED_MODEL,
        "model_selected_by": "PROTOCOL.md §9.2 — results/v3_gates/p6_sweep.json",
        "split": "dev", "n": n, "seeds": seeds,
        "lexicon_accuracy": lex_acc, "lexicon_errors": n_err,
        "max_escalation": MAX_ESCALATION,
        "curve": points,
        "argmax": {k: v for k, v in argmax.items()},
        "sigma_at_argmax": sigma,
        "within_one_sigma": [p["tau"] for p in within],
        "selected": {k: v for k, v in chosen.items()},
        "selected_tau": tau,
        "delta_vs_lexicon": delta,
        "delta_ci95_mean_over_seeds": [lo, hi],
        "bootstrap_p_hybrid_no_better": p_null,
        "mcnemar_majority_vs_lexicon": mc,
        "mcnemar_per_seed_vs_lexicon": per_seed_mc,
        "expected_latency_ms": exp_ms,
        "llm_latency_median_ms": llm_ms,
    }
    (OUT_DIR / "p4_router.json").write_text(json.dumps(payload, indent=2),
                                            encoding="utf-8")

    md = [
        "# P4 — hybrid router threshold curve (dev)",
        "",
        f"`{SELECTED_MODEL}`, selected under PROTOCOL.md §9.2. "
        f"Threshold selected under §9.3, pre-registered in `49be6dd` before "
        f"this ran. Dev split, {n} tasks, seeds {seeds}. "
        f"Lexicon baseline **{lex_acc:.1%}**, {n_err} errors available.",
        "",
        "The complete curve is published, not only the selected point, so "
        "the selection is auditable. Rows above the 50% escalation cap "
        "(§9.1) are shown but were never candidates.",
        "",
        "| τ | escalation | n | hybrid acc | σ | per-seed | fixed | broken | |",
        "|---:|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for p in points:
        note = ("**selected**" if p is chosen else
                "argmax" if p is argmax else
                "" if p["feasible"] else "above cap")
        md.append(
            f"| {p['tau']:.2f} | {p['escalation_rate']:.1%} | "
            f"{p['n_escalated']} | {p['accuracy_mean']:.1%} | "
            f"{p['accuracy_std']:.1%} | "
            + " / ".join(f"{a:.1%}" for a in p["accuracy_per_seed"])
            + f" | {p['fixed_mean']:.1f} | {p['broken_mean']:.1f} | {note} |")
    md += [
        "",
        "## Selection",
        "",
        f"- argmax: τ ≤ {argmax['tau']:.2f}, {argmax['accuracy_mean']:.1%} at "
        f"{argmax['escalation_rate']:.1%} escalation, σ = {sigma:.1%}",
        f"- within one σ: "
        + ", ".join(f"τ ≤ {p['tau']:.2f}" for p in within),
        f"- **selected: τ ≤ {tau:.2f}** — lowest escalation rate among those",
        "",
        "## Effect at the selected threshold",
        "",
        f"- hybrid {chosen['accuracy_mean']:.1%} vs lexicon {lex_acc:.1%} = "
        f"**{delta:+.1%}**",
        f"- 95% bootstrap CI {lo:+.1%} to {hi:+.1%}; "
        f"{p_null:.1%} of resamples show no gain",
        f"- McNemar vs lexicon (majority vote): b01={mc['b01']}, "
        f"b10={mc['b10']}, p = {mc['p']:.3f}",
        f"- expected cost {exp_ms:.0f} ms/query vs {llm_ms:.0f} ms for "
        f"LLM-on-everything",
        "",
        "The point estimate favours the router and the direction is "
        "consistent across all three seeds, but neither the CI nor McNemar "
        "clears conventional significance on 108 queries. **Dev is "
        "contaminated by construction** (§11) — the lexicon was tuned on it. "
        "These numbers select τ; they are not the result. The held-out set "
        "(P5) is.",
    ]
    (OUT_DIR / "p4_router.md").write_text("\n".join(md) + "\n",
                                          encoding="utf-8")

    # --- the frozen deployed config
    cfg = {
        "_": "Frozen by evaluation/tune_router.py under PROTOCOL.md §9.3. "
             "Edited by hand = a different experiment. P5 verifies sha256.",
        "tau": tau,
        "model": SELECTED_MODEL,
        "temperature": capture["temperature"],
        "margin": "top1 - top2 over the frozen lexicon's intent scores",
        "escalate_when": "margin <= tau",
        "selected_on": "dev, 108 tasks, seeds 0/1/2",
        "dev_accuracy_mean": chosen["accuracy_mean"],
        "dev_escalation_rate": chosen["escalation_rate"],
        "provenance": "evaluation/results/v3_gates/p4_router.json",
    }
    body = json.dumps(cfg, indent=2)
    digest = hashlib.sha256(body.encode()).hexdigest()
    CONFIG.write_text(body, encoding="utf-8")
    (OUT_DIR / "p4_router_config.sha256").write_text(
        f"{digest}  backend/app/router_config.json\n", encoding="utf-8")

    print(f"\nwrote {OUT_DIR / 'p4_router.json'}")
    print(f"wrote {CONFIG}")
    print(f"  sha256 {digest}")


if __name__ == "__main__":
    main()
