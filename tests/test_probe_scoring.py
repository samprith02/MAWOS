"""D14 constraint 1: re-registering M7 must change no completed verdict.

docs/v4/OPEN_DECISIONS.md D14 allows the re-registration only if it is
verified to leave every already-published eligibility outcome intact.
This test is the executable form of that constraint.
"""
import json
from collections import defaultdict
from pathlib import Path

import pytest

from evaluation.provider_probe import eligibility, score

RESULTS = Path(__file__).resolve().parent.parent / "evaluation" / "results" / "v4_gates"
COMPLETED = ["r05_provider.json", "r05_provider_20260901.json"]


def _runs():
    """(filename, provider, records, published_scores) per completed run."""
    out = []
    for fname in COMPLETED:
        path = RESULTS / fname
        if not path.exists():
            continue
        blob = json.loads(path.read_text(encoding="utf-8"))
        by_provider = defaultdict(list)
        for key, rec in (blob.get("records") or {}).items():
            by_provider[key.split("|")[0]].append(rec)
        for provider, recs in by_provider.items():
            published = ((blob.get("results") or {})
                         .get(provider, {})
                         .get("scores"))
            if published and recs:
                out.append((fname, provider, recs, published))
    return out


def test_completed_runs_exist():
    assert _runs(), "no completed probe runs found to verify against"


@pytest.mark.parametrize("fname,provider,records,published", _runs())
def test_m7_redefinition_changes_no_verdict(fname, provider, records, published):
    fresh = score(records)
    was = eligibility(published)["eligible"]
    now = eligibility(fresh)["eligible"]
    assert now == was, (
        f"{provider} in {fname}: eligibility flipped {was} -> {now} "
        f"under the re-registered M7. D14 constraint 1 forbids this."
    )
