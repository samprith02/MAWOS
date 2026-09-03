"""P3 -- diagnostic chart for the provenance gate's dev-only engineering pass.

    python evaluation/gate_p3_figure.py

Not a P7 figure (not in evaluation/figures.py's REGISTRY, not F5). F5 is
reserved for RQ2's confirmed held-out result, which needs P3 scaled to the
3-seed convention plus real annotated hallucination data (P5) -- neither
exists yet. This script only plots what `evaluation/gate_p3.py` already
wrote to `p3_provenance.json`: the dev-only, one-seed, synthetic-ground-truth
numbers, captioned as exactly that. Regenerate `p3_provenance.json` first
with `python evaluation/gate_p3.py` (needs live Ollama) if it's stale;
this script itself only reads JSON and never calls the model.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GATES = ROOT / "evaluation" / "results" / "v3_gates"
LLM = ROOT / "evaluation" / "results" / "v3_llm"
OUT = GATES / "p3_diagnostic.png"

C_CATCH = "#1b7f79"
C_BLOCK = "#c8553d"
C_GATE = "#4a5899"
C_LLM = "#8c3b28"


def main() -> None:
    p3 = json.loads((GATES / "p3_provenance.json").read_text(encoding="utf-8"))

    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
        "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
        "axes.edgecolor": "#555555", "axes.grid": True,
        "grid.color": "#dcdcdc", "grid.linewidth": 0.6,
    })
    fig, (axa, axb) = plt.subplots(1, 2, figsize=(10.6, 4.6),
                                    gridspec_kw={"width_ratios": [1, 1.15]})

    catch = p3["catch_rate_on_synthetic_corruption"] * 100
    block = p3["block_rate_on_genuine_answers"] * 100
    n_c = p3["n_corrupted_checked"]
    n_g = p3["n_genuine_checked"]
    bars = axa.bar(["catch rate\n(synthetic corruption)",
                     "block rate\n(genuine answers)"],
                    [catch, block], color=[C_CATCH, C_BLOCK], width=0.55,
                    edgecolor="white", linewidth=0.8)
    for b, v, n in zip(bars, [catch, block], [n_c, n_g]):
        axa.text(b.get_x() + b.get_width() / 2, v + 2, "%.1f%%\n(n=%d)" % (v, n),
                  ha="center", fontsize=8.4, fontweight="bold",
                  color=b.get_facecolor())
    axa.set_ylim(0, 118)
    axa.set_ylabel("rate (%)")
    axa.spines["top"].set_visible(False)
    axa.spines["right"].set_visible(False)
    axa.set_axisbelow(True)
    axa.set_title("A " + chr(8212) + " does the gate catch what it should,\n"
                   "without blocking what it shouldn't", loc="left", fontsize=9.2)

    llm_ms = None
    sweep_path = GATES / "p6_sweep.json"
    if sweep_path.exists():
        sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
        for m in sweep.get("eligible_models", []):
            if m["model"] == p3["model"]:
                llm_ms = m["latency_median_ms"]
                break
    gate_us = p3["mean_gate_overhead_us"]
    if llm_ms:
        labels = ["gate check\n(regex/set, no model call)", "LLM call itself\n(%s)" % p3["model"]]
        vals = [gate_us / 1000.0, llm_ms]
        colors = [C_GATE, C_LLM]
        bars = axb.barh(labels, vals, color=colors, height=0.5,
                         edgecolor="white", linewidth=0.8)
        for b, v in zip(bars, vals):
            axb.text(v * 1.15, b.get_y() + b.get_height() / 2,
                      ("%.3f ms" if v < 1 else "%.0f ms") % v,
                      va="center", fontsize=8.4, fontweight="bold",
                      color=b.get_facecolor())
        axb.set_xscale("log")
        axb.set_xlim(0.0005, max(vals) * 4)
        axb.set_xlabel("time (ms, log scale)")
        axb.set_title("B " + chr(8212) + " gate cost vs. the LLM call it checks",
                       loc="left", fontsize=9.2)
        axb.spines["top"].set_visible(False)
        axb.spines["right"].set_visible(False)
        note_b = ("gate adds %.0fx less time than one LLM call"
                  % (llm_ms / (gate_us / 1000.0)))
    else:
        axb.text(0.5, 0.5, "p6_sweep.json not found --\nrun evaluation/analyze_sweep.py",
                  ha="center", va="center", transform=axb.transAxes, fontsize=9)
        axb.axis("off")
        note_b = "LLM latency reference unavailable"

    fig.text(0.5, -0.05,
              "Dev split (99-task instrument), one seed, %s. Ground truth for "
              "'catch' is synthetic: one real numeric claim per genuine answer "
              "replaced with a fabricated value. This is a dev-only engineering "
              "pass (H2, RESEARCH_PLAN_V3.md 3.2), NOT RQ2's confirmed result -- "
              "real annotated hallucination data and the 3-seed convention are "
              "still pending on P5 (blocked on external authors). Not part of "
              "the P7 figure registry; F5 is reserved for that confirmed result."
              % p3["model"], ha="center", va="top", fontsize=7.2, color="#444444",
              wrap=True)

    GATES.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT)
    plt.close(fig)
    print("wrote %s" % OUT.relative_to(ROOT))
    print("  catch %.1f%% (n=%d), block %.1f%% (n=%d), gate overhead %.1f us/check"
          % (catch, n_c, block, n_g, gate_us))
    if llm_ms:
        print("  " + note_b)


if __name__ == "__main__":
    main()
