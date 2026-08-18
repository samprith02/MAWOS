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
BLOCKED = {"F4", "F5", "F9"}


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
    assert "Needs P" in reason or "Plan " in reason


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
