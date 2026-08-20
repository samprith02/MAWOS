"""P7 — the figure harness must never invent a figure.

The gate for P7 is "every figure regenerable by one command". That gate is
worthless if a figure whose experiment has not run can still be drawn from
assumed numbers, so the substantive test here is that the three blocked
figures stay blocked and say what they are blocked on. Rendering is
checked on one cheap figure; the full pass is
`python evaluation/figures.py`, which is deliberately not run in the test
suite because it reads every capture in `results/`.
"""
from pathlib import Path

import pytest

from evaluation import figures

ROOT = Path(__file__).resolve().parent.parent
#: F4/F5/F9 are blocked on a future phase (P2/P3/P5) -- structural, not
#: transient. F2/F3/F6/F8 joined them at P2 (2026-08-19): the frozen dev
#: task set moved 108->99 (evaluation/PROTOCOL.md Sec12), which invalidates
#: every existing LLM capture and router-tuning result until a GPU-resident
#: recapture lands (dev_frame() and f6_pareto() now detect this and raise
#: Blocked instead of drawing from a mismatched or CPU-only capture). Move
#: an entry back out once a fresh capture + tune_router.py run replaces it.
BLOCKED = {"F2", "F3", "F4", "F5", "F6", "F8", "F9"}


def test_registry_covers_every_planned_figure():
    assert set(figures.REGISTRY) == {"F%d" % i for i in range(1, 10)}


@pytest.mark.parametrize("key", sorted(BLOCKED))
def test_blocked_figures_refuse_to_draw_and_say_why(key):
    """A blocked figure must raise, not return a placeholder."""
    _slug, fn = figures.REGISTRY[key]
    with pytest.raises(figures.Blocked) as exc:
        fn()
    reason = str(exc.value)
    assert len(reason) > 60, "a blocked figure has to name its experiment"
    assert "Needs " in reason or "Plan " in reason


@pytest.mark.parametrize("key", sorted(set("F%d" % i for i in range(1, 10))
                                       - BLOCKED))
def test_drawable_figures_declare_sources_that_exist(key):
    """Every drawn figure names the files it was regenerated from."""
    _slug, fn = figures.REGISTRY[key]
    figures.style()
    fig, meta = fn()
    try:
        assert meta["sources"], "a figure must declare its provenance"
        for src in meta["sources"]:
            if "*" in src:
                assert list(ROOT.glob(src)), src
            else:
                assert (ROOT / src).exists(), src
        assert meta["note"]
    finally:
        figures.plt.close(fig)


def test_a_figure_actually_renders(tmp_path):
    figures.style()
    fig, _meta = figures.f1_cascade_dag()
    out = tmp_path / "F1.png"
    fig.savefig(out)
    figures.plt.close(fig)
    assert out.stat().st_size > 10_000
