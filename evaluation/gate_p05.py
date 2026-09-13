"""P0.5 — router viability gate.

    python evaluation/gate_p05.py

A cheap go/no-go test on whether the confidence-gated hybrid router (P4)
is worth building at all, run *before* building it. Thresholds are
pre-registered in evaluation/PROTOCOL.md §9.1 and are not revisable here.

The question
------------
The hybrid router escalates only low-confidence queries to the LLM. That
is worth doing iff the lexicon's confidence actually predicts its own
errors. If the lexicon is equally confident when right and when wrong,
no escalation policy can help: you would be escalating at random, and the
best available strategy is to pick one tier and stay there.

Three things are computed, in increasing order of how decisive they are:

**Oracle ceiling** — assume a perfect LLM that answers every escalated
query correctly. This needs no LLM data at all; it is a structural
property of the margin ranking. It answers: *at what escalation rate
would a flawless LLM have to be invoked to fix the lexicon's errors?* If
that rate is high, the router is pointless even with a perfect model,
because you are effectively just running the LLM on everything.

**AUC** — the descriptive summary of the same fact: does margin rank
errors below correct answers?

**Realised curve** — the oracle replaced by the LLM's actual per-query
correctness. This is the criterion of record.

Data provenance
---------------
The realised curve needs per-query LLM correctness. The frozen LLM
baseline does not exist yet (it needs a live Ollama run, scheduled before
the final experimental lock). This script therefore reconstructs the
vector from `results/v2_historical/RESULTS.md` §1.2, which lists all 32
misrouted queries verbatim. All 32 map onto frozen task IDs.

That reconstruction is **one run, one seed, one model** — v2 never
measured seed variance. So the realised curve here is *provisional*. The
oracle ceiling and the AUC are not: they depend only on the frozen
lexicon and the frozen tasks, and will not move.
"""
import json
import random
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.baselines import lexicon_v2  # noqa: E402
from evaluation.benchmark.tasks import DEV_TASKS  # noqa: E402

OUT_DIR = ROOT / "evaluation" / "results" / "v3_gates"
HISTORICAL = ROOT / "evaluation" / "results" / "v2_historical" / "RESULTS.md"

#: Pre-registered in PROTOCOL.md §9.1. Not revisable after seeing data.
MAX_ESCALATION = 0.50
AUC_NO_SIGNAL = 0.60
AUC_STRONG = 0.70
LEXICON_SEED_BAND = 0.0      # measured in v2_frozen: the lexicon is deterministic


def margins() -> dict[str, float]:
    """Top-1 minus top-2 lexicon score, per task.

    Pre-registered definition: the absolute gap between the best and
    second-best intent score. A query that matches no pattern at all
    scores zero everywhere and therefore gets margin 0 — maximally
    uncertain, which is correct: those are the queries the lexicon
    silently dumps into `profile_query`.

    Computed here by re-scoring against the frozen `_LEXICON` rather than
    by modifying it. P0 artefacts are read, never edited.
    """
    out = {}
    for task in DEV_TASKS:
        q = task.query.lower()
        scores = []
        for intent, patterns in lexicon_v2._LEXICON.items():
            s = sum(w for pat, w in patterns if re.search(pat, q))
            scores.append(s)
        scores.sort(reverse=True)
        out[task.id] = scores[0] - scores[1]
    return out


def llm_correctness() -> tuple[dict[str, bool], str]:
    """Per-task LLM correctness, reconstructed from the v2 historical run."""
    txt = HISTORICAL.read_text(encoding="utf-8")
    section = txt.split("## 1.2 Intent routing")[1].split("## 1.2b")[0]
    rows = re.findall(r"^- \[(standard|hard)\] '(.+?)' -> (\S+) \(expected (\S+)\)",
                      section, re.M)
    by_query = {t.query: t.id for t in DEV_TASKS}
    missed = set()
    for _tier, query, _got, _want in rows:
        if query not in by_query:
            raise RuntimeError(f"historical misroute does not map to a frozen "
                               f"task: {query!r}")
        missed.add(by_query[query])
    correct = {t.id: t.id not in missed for t in DEV_TASKS}
    note = (f"reconstructed from v2_historical/RESULTS.md §1.2 "
            f"({len(rows)} misroutes, single run, single seed, "
            f"qwen2.5:3b-instruct)")
    return correct, note


def auc(scores: dict[str, float], is_error: dict[str, bool]) -> float:
    """P(a random error scores higher than a random non-error).

    Predictor is -margin: low confidence should indicate error. Rank-based
    Mann-Whitney, ties given half credit. Implemented directly to avoid a
    scipy/sklearn dependency for ten lines of arithmetic.
    """
    pos = [-scores[k] for k, e in is_error.items() if e]
    neg = [-scores[k] for k, e in is_error.items() if not e]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def curve(marg, lex_ok, llm_ok=None):
    """Hybrid accuracy at every achievable escalation threshold.

    Escalation is threshold-based (`margin <= tau`), not top-k, because
    that is what a deployed router actually does: you set a threshold, not
    a quota. Ties therefore escalate together, which is the honest set of
    operating points.
    """
    ids = [t.id for t in DEV_TASKS]
    n = len(ids)
    points = []
    for tau in [-1.0] + sorted({marg[i] for i in ids}):
        escalated = [i for i in ids if marg[i] <= tau]
        kept = [i for i in ids if marg[i] > tau]
        hits = sum(lex_ok[i] for i in kept)
        hits += len(escalated) if llm_ok is None else sum(llm_ok[i] for i in escalated)
        points.append({"tau": tau,
                       "escalation_rate": len(escalated) / n,
                       "accuracy": hits / n})
    return points


def bootstrap_delta(marg, lex_ok, llm_ok, tau, iters=10000, seed=0):
    """Bootstrap CI on (hybrid - lexicon) accuracy at a fixed tau."""
    rng = random.Random(seed)
    ids = [t.id for t in DEV_TASKS]
    n = len(ids)
    deltas = []
    for _ in range(iters):
        sample = [ids[rng.randrange(n)] for _ in range(n)]
        hyb = sum((llm_ok[i] if marg[i] <= tau else lex_ok[i]) for i in sample)
        lex = sum(lex_ok[i] for i in sample)
        deltas.append((hyb - lex) / n)
    deltas.sort()
    return deltas[int(0.025 * iters)], deltas[int(0.975 * iters)]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    marg = margins()
    lex_ok = {t.id: lexicon_v2.classify_keyword(t.query).intent == t.gold_intent
              for t in DEV_TASKS}
    llm_ok, provenance = llm_correctness()
    n = len(DEV_TASKS)

    lex_acc = sum(lex_ok.values()) / n
    llm_acc = sum(llm_ok.values()) / n

    print("P0.5 router viability gate")
    print("=" * 62)
    print(f"tasks {n} (dev) · lexicon {lex_acc:.1%} · "
          f"LLM {llm_acc:.1%} [{provenance}]")

    # --- margin distribution sanity
    errs = [marg[t.id] for t in DEV_TASKS if not lex_ok[t.id]]
    oks = [marg[t.id] for t in DEV_TASKS if lex_ok[t.id]]
    print(f"\nmargin | errors  median {statistics.median(errs):.2f} "
          f"(n={len(errs)})")
    print(f"       | correct median {statistics.median(oks):.2f} (n={len(oks)})")

    # --- secondary criterion
    a = auc(marg, {t.id: not lex_ok[t.id] for t in DEV_TASKS})
    band = ("no signal" if a < AUC_NO_SIGNAL else
            "weak — simulation decides" if a < AUC_STRONG else
            "consistent with proceeding")
    print(f"\nAUC(margin -> lexicon error) = {a:.3f}  [{band}]")

    # --- oracle ceiling: needs no LLM data
    oracle = curve(marg, lex_ok, llm_ok=None)
    feasible_o = [p for p in oracle if p["escalation_rate"] <= MAX_ESCALATION]
    best_o = max(feasible_o, key=lambda p: p["accuracy"])
    full_fix = next((p for p in oracle if p["accuracy"] >= 1.0 - 1e-9), None)
    print(f"\noracle ceiling (perfect LLM on escalated queries)")
    print(f"  best below {MAX_ESCALATION:.0%} escalation: "
          f"{best_o['accuracy']:.1%} at {best_o['escalation_rate']:.1%} "
          f"(tau<={best_o['tau']:.2f})")
    if full_fix:
        print(f"  escalation needed to fix every lexicon error: "
              f"{full_fix['escalation_rate']:.1%}")

    # --- primary criterion
    real = curve(marg, lex_ok, llm_ok=llm_ok)
    feasible = [p for p in real if p["escalation_rate"] <= MAX_ESCALATION]
    best = max(feasible, key=lambda p: p["accuracy"])
    threshold = lex_acc + LEXICON_SEED_BAND
    passes = best["accuracy"] > threshold
    lo, hi = bootstrap_delta(marg, lex_ok, llm_ok, best["tau"])

    print(f"\nrealised curve (v2 3B correctness)")
    print(f"  best below {MAX_ESCALATION:.0%} escalation: "
          f"{best['accuracy']:.1%} at {best['escalation_rate']:.1%} "
          f"(tau<={best['tau']:.2f})")
    print(f"  lexicon-only: {lex_acc:.1%} · required > {threshold:.1%}")
    print(f"  delta {best['accuracy'] - lex_acc:+.1%} "
          f"(95% CI {lo:+.1%} to {hi:+.1%})")

    print("\n" + "=" * 62)
    print(f"PRE-REGISTERED DECISION: P4 {'PROCEEDS' if passes else 'ABANDONED'}")
    if not passes:
        print("  No escalation policy below 50% beats the lexicon. Per")
        print("  PROTOCOL.md §9.1 the router is abandoned, not retuned.")

    payload = {
        "n": n, "lexicon_accuracy": lex_acc, "llm_accuracy": llm_acc,
        "llm_provenance": provenance,
        "auc_margin_predicts_error": a, "auc_band": band,
        "margin_median_error": statistics.median(errs),
        "margin_median_correct": statistics.median(oks),
        "oracle_best_under_cap": best_o,
        "oracle_full_fix_escalation": full_fix["escalation_rate"] if full_fix else None,
        "realised_best_under_cap": best,
        "delta_vs_lexicon": best["accuracy"] - lex_acc,
        "delta_ci95": [lo, hi],
        "decision": "proceed" if passes else "abandon",
        "thresholds": {"max_escalation": MAX_ESCALATION,
                       "auc_no_signal": AUC_NO_SIGNAL,
                       "auc_strong": AUC_STRONG,
                       "lexicon_seed_band": LEXICON_SEED_BAND},
        "oracle_curve": oracle, "realised_curve": real,
        "per_task": [{"id": t.id, "margin": marg[t.id],
                      "lexicon_correct": lex_ok[t.id],
                      "llm_correct": llm_ok[t.id], "stratum": t.stratum}
                     for t in DEV_TASKS],
    }
    out = OUT_DIR / "p05_gate.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
