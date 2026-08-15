"""P6 sweep analysis — applies the pre-registered selection rule.

    python evaluation/analyze_sweep.py

Consumes evaluation/results/v3_llm/*.json and writes
evaluation/results/v3_gates/p6_sweep.{json,md}.

The selection rule is PROTOCOL.md §9.2, committed before any model beyond
the 3B was run. This script implements it mechanically so the choice
cannot drift once the numbers are visible:

    net headroom recovery
        = (lexicon errors the model fixes - lexicon-correct answers it
           breaks) / (total lexicon errors)
      evaluated at the escalation threshold that maximises hybrid accuracy
      under the 50% escalation cap

    tie-break within one seed-sigma: lower median per-query latency
    hard constraint: fully GPU-resident, else ineligible

Why headroom recovery rather than raw accuracy: raw hybrid accuracy is
dominated by the ~90% of queries the lexicon already answers and where
escalation never fires, so it compresses exactly the differences the sweep
exists to measure. P0.5 established the oracle ceiling — a perfect model
reaches 100% at 18.5% escalation — so the honest question is what fraction
of that available correction each model actually recovers.
"""
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.baselines import lexicon_v2  # noqa: E402
from evaluation.benchmark.tasks import DEV_TASKS  # noqa: E402
from evaluation.gate_p05 import MAX_ESCALATION, margins  # noqa: E402

LLM_DIR = ROOT / "evaluation" / "results" / "v3_llm"
OUT_DIR = ROOT / "evaluation" / "results" / "v3_gates"


def mcnemar(a_ok: dict, b_ok: dict) -> dict:
    """Exact McNemar on paired per-query correctness. a vs b."""
    b01 = sum(1 for k in a_ok if not a_ok[k] and b_ok[k])   # b right, a wrong
    b10 = sum(1 for k in a_ok if a_ok[k] and not b_ok[k])   # a right, b wrong
    n = b01 + b10
    if n == 0:
        return {"discordant": 0, "b01": 0, "b10": 0, "p": 1.0}
    # two-sided exact binomial, p = 0.5
    tail = sum(math.comb(n, i) for i in range(0, min(b01, b10) + 1)) / 2 ** n
    return {"discordant": n, "b01": b01, "b10": b10, "p": min(1.0, 2 * tail)}


def evaluate_model(path: Path, marg: dict, lex_ok: dict) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    seeds = data["seeds"]
    n_err = sum(1 for v in lex_ok.values() if not v)
    ids = [t.id for t in DEV_TASKS]
    n = len(ids)

    per_seed = []
    for seed in seeds:
        ok = {r["task_id"]: r["outcome"] == "correct"
              for r in data["records"] if r["seed"] == seed}
        if len(ok) != n:
            raise RuntimeError(f"{path.name} seed {seed}: {len(ok)} records, "
                               f"expected {n}")
        best = None
        for tau in [-1.0] + sorted({marg[i] for i in ids}):
            esc = [i for i in ids if marg[i] <= tau]
            if len(esc) / n > MAX_ESCALATION:
                continue
            hits = sum(ok[i] for i in esc) + sum(lex_ok[i] for i in ids
                                                 if marg[i] > tau)
            cand = {
                "tau": tau, "escalation_rate": len(esc) / n,
                "hybrid_accuracy": hits / n,
                "fixed": sum(1 for i in esc if not lex_ok[i] and ok[i]),
                "broken": sum(1 for i in esc if lex_ok[i] and not ok[i]),
            }
            if best is None or cand["hybrid_accuracy"] > best["hybrid_accuracy"]:
                best = cand
        best["net_headroom_recovery"] = (best["fixed"] - best["broken"]) / n_err
        best["llm_solo_accuracy"] = sum(ok.values()) / n
        best["seed"] = seed
        best["_ok"] = ok
        per_seed.append(best)

    def band(key):
        v = [p[key] for p in per_seed]
        return {"mean": statistics.mean(v),
                "std": statistics.pstdev(v) if len(v) > 1 else 0.0}

    # majority vote across seeds, for the paired significance test
    maj = {i: sum(p["_ok"][i] for p in per_seed) > len(per_seed) / 2
           for i in ids}

    res = data.get("gpu_residency") or {}
    return {
        "model": data["model"],
        "eligible": bool(res.get("fully_resident")),
        "gpu_fraction": res.get("gpu_fraction"),
        "call_failures": data.get("call_failures", 0),
        "llm_solo_accuracy": band("llm_solo_accuracy"),
        "hybrid_accuracy": band("hybrid_accuracy"),
        "net_headroom_recovery": band("net_headroom_recovery"),
        "escalation_rate": band("escalation_rate"),
        "fixed": band("fixed"), "broken": band("broken"),
        "latency_median_ms": data["latency_median_ms"],
        "latency_p95_ms": data["latency_p95_ms"],
        "abstention_rate": data["bands"]["abstention_rate"],
        "declined_despite_exposure": data["bands"]["declined_despite_exposure"],
        "per_seed": [{k: v for k, v in p.items() if k != "_ok"}
                     for p in per_seed],
        "_majority_ok": maj,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(LLM_DIR.glob("*.json"))
    if not files:
        sys.exit(f"no capture files in {LLM_DIR} — run capture_llm.py first")

    marg = margins()
    lex_ok = {t.id: lexicon_v2.classify_keyword(t.query).intent == t.gold_intent
              for t in DEV_TASKS}
    lex_acc = sum(lex_ok.values()) / len(lex_ok)
    n_err = sum(1 for v in lex_ok.values() if not v)

    results = [evaluate_model(f, marg, lex_ok) for f in files]
    results.sort(key=lambda r: -r["net_headroom_recovery"]["mean"])

    # PROTOCOL 9.2 excludes an ineligible model "regardless of accuracy".
    # That exclusion governs every primary analysis, not just the final
    # pick: a partially offloaded model runs in a different computational
    # regime (GPU->CPU RAM->GPU rather than GPU->GPU), so its latency does
    # not lie on the same axis as an eligible model's and must never share
    # a Pareto frontier or a paired significance test with one.
    eligible = [r for r in results if r["eligible"]]
    diagnostic = [r for r in results if not r["eligible"]]

    print("P6 model sweep — PROTOCOL.md §9.2")
    print("=" * 78)
    print(f"lexicon {lex_acc:.1%} · {n_err} errors available · "
          f"oracle ceiling 100% at 18.5% escalation")

    def table(rows, latency: bool):
        hdr = (f"  {'model':24} {'solo':>7} {'hybrid':>8} {'recov':>8} "
               f"{'fix/brk':>9}" + (f" {'med ms':>8}" if latency else ""))
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for r in rows:
            line = (f"  {r['model']:24} {r['llm_solo_accuracy']['mean']:6.1%} "
                    f"{r['hybrid_accuracy']['mean']:7.1%} "
                    f"{r['net_headroom_recovery']['mean']:7.1%} "
                    f"{r['fixed']['mean']:4.1f}/{r['broken']['mean']:<4.1f}")
            if latency:
                line += f" {r['latency_median_ms']:7.0f}"
            print(line)

    print("\nPRIMARY — eligible under the fixed compute budget")
    table(eligible, latency=True)

    if diagnostic:
        print("\nOUT-OF-COMPETITION — partially CPU-offloaded, NON-COMPARABLE")
        print("  Excluded from selection, Pareto analysis and all paired")
        print("  tests. Accuracy is unaffected by offload and is reported;")
        print("  latency is a different regime and is withheld here.")
        table(diagnostic, latency=False)
        for r in diagnostic:
            print(f"  {r['model']}: {r['gpu_fraction']:.1%} GPU-resident, "
                  f"latency non-comparable "
                  f"(median {r['latency_median_ms']:.0f} ms under offload)")

    selected = None
    if eligible:
        top = eligible[0]
        sigma = max(top["net_headroom_recovery"]["std"], 1e-9)
        tied = [r for r in eligible
                if abs(r["net_headroom_recovery"]["mean"]
                       - top["net_headroom_recovery"]["mean"]) <= sigma]
        selected = min(tied, key=lambda r: r["latency_median_ms"])
        print(f"\ntied within one seed-sigma ({sigma:.1%}): "
              + ", ".join(r["model"] for r in tied))
        print(f"SELECTED (§9.2): {selected['model']}")
        if selected is not top:
            print(f"  tie-break on median latency over "
                  f"{top['model']} ({top['latency_median_ms']:.0f} ms)")

    # Paired tests among eligible models only.
    pairs = {}
    for i, a in enumerate(eligible):
        for b in eligible[i + 1:]:
            pairs[f"{a['model']} vs {b['model']}"] = mcnemar(
                a["_majority_ok"], b["_majority_ok"])
    for label, m in pairs.items():
        print(f"  McNemar {label}: b01={m['b01']} b10={m['b10']} p={m['p']:.3f}")

    payload = {
        "rule": "PROTOCOL.md §9.2, pre-registered 2026-08-15",
        "eligibility_record": "results/v3_llm/ELIGIBILITY.md — determined on "
                              "hardware grounds before any accuracy was seen",
        "lexicon_accuracy": lex_acc, "lexicon_errors": n_err,
        "max_escalation": MAX_ESCALATION,
        "eligible_models": [{k: v for k, v in r.items() if k != "_majority_ok"}
                            for r in eligible],
        "out_of_competition": [
            {**{k: v for k, v in r.items() if k != "_majority_ok"},
             "latency_comparable": False,
             "excluded_from": ["selection", "pareto", "paired_tests"]}
            for r in diagnostic],
        "selected": selected["model"] if selected else None,
        "mcnemar_eligible_only": pairs,
    }
    (OUT_DIR / "p6_sweep.json").write_text(json.dumps(payload, indent=2),
                                           encoding="utf-8")
    print(f"\nwrote {OUT_DIR / 'p6_sweep.json'}")


if __name__ == "__main__":
    main()
