"""Diagnostic split for measure 6 (grounding), R0.5.

M6 is scored by `backend/app/provenance.check` exactly as it ships, and the
pre-registered threshold is applied to that number unchanged. This module
does **not** alter the score. It answers a separate question the R0.5 run
raised: *of the answers the gate blocked, how many were the model inventing
a number, and how many were the gate itself misfiring?*

The misfire found on 2026-08-31
-------------------------------
`provenance._NUMBER_RE` begins with `\\s*`, so a match can start at the
whitespace **before** a numeral. `extract_numbers` then computes the start
of the current line with `text.rfind("\\n", 0, start)`, but `start` is now
the newline itself, so the search looks before it and the line-start lands
on the *previous* line. The markdown-ordered-list filter
(`after == "." and text[line_start:start].strip() == ""`) therefore does
not fire, and a list marker is scored as a numeric claim.

It only manifests when the character preceding that whitespace is neither
`\\w` nor `.` -- the lookbehind `(?<![\\w.])` otherwise rejects the
whitespace-leading match and the regex retries at the digit, where the
filter works. In practice a colon does it:

    "...details of each item:\\n\\n1. Tuition: ..."   -> 1.0 scored as a claim
    "...Status - Overdue.\\n2. Exam: ..."             -> correctly filtered

This is recorded, not fixed. `provenance.py` is v3 code under
`evaluation/FROZEN.sha256` discipline and R0.5 is a provider gate, not a
gate-repair phase. It is logged against `docs/v4/OPEN_DECISIONS.md` D10,
which already anticipated that P3's 23.5% false-block rate -- measured on
synthetic single-tool corruption -- would not transfer to richer answers.

Consequence for reading the results: **M6 as reported is a lower bound on
model grounding.**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app import provenance  # noqa: E402

#: Same pattern, without the leading `\s*` that breaks the line-start maths.
_FIXED_RE = re.compile(r"(?<![\w.])₹?(\d[\d,]*(?:\.\d+)?)\s*%?")


def extract_numbers_fixed(text: str) -> list[float]:
    """`provenance.extract_numbers` with the list-marker filter working."""
    out = []
    for m in _FIXED_RE.finditer(text):
        start, end = m.start(), m.end()
        raw = m.group(1)
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        if before == "-" and "." not in raw and "," not in raw:
            continue
        if (before == "(" and after == ")" and len(raw) <= 2
                and "." not in raw and "," not in raw):
            continue
        line_start = text.rfind("\n", 0, start) + 1
        if after == "." and text[line_start:start].strip() == "":
            continue
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def classify(record: dict) -> str:
    """gate_artifact | genuine | mixed | not_blocked."""
    gate = record.get("provenance")
    if not gate or not gate["blocked"]:
        return "not_blocked"
    text = record.get("final_text") or ""
    grounded = set()
    # Rebuild the grounded set the same way the gate does, from the payloads
    # the gate itself saw. We only have the final text here, so instead we
    # ask a narrower question: would the corrected extractor still have
    # produced these claims at all?
    claims_fixed = set(extract_numbers_fixed(text))
    ungrounded = [u for u in gate["ungrounded"]]
    survives = [u for u in ungrounded if u in claims_fixed]
    if not survives:
        return "gate_artifact"
    if len(survives) < len(ungrounded):
        return "mixed"
    return "genuine"


def summarise(records: list[dict]) -> dict:
    e = [r for r in records if r["category"] == "E_numeric"]
    blocked = [r for r in e if r.get("provenance") and r["provenance"]["blocked"]]
    kinds = {"gate_artifact": 0, "genuine": 0, "mixed": 0}
    detail = []
    for r in blocked:
        k = classify(r)
        kinds[k] = kinds.get(k, 0) + 1
        detail.append({"item_id": r["item_id"], "seed": r["seed"], "kind": k,
                       "ungrounded": r["provenance"]["ungrounded"]})
    n = len(e)
    # Match `provider_probe.score`'s definition exactly: an item with no tool
    # call has no gate result and counts as ungrounded, not as a gate artifact.
    passed = sum(1 for r in e
                 if r.get("provenance") and not r["provenance"]["blocked"])
    no_tool = sum(1 for r in e if not r.get("provenance"))
    corrected = passed + kinds["gate_artifact"]
    return {
        "n_numeric_items": n,
        "m6_as_measured": passed / n if n else 0.0,
        "no_tool_called": no_tool,
        "blocked": len(blocked),
        "blocked_kinds": kinds,
        "m6_artifact_corrected": corrected / n if n else 0.0,
        "detail": detail,
        "note": ("m6_as_measured is the pre-registered score and is what the "
                 "threshold is applied to. m6_artifact_corrected is a "
                 "diagnostic only -- it shows what the score would be if the "
                 "list-marker misfire documented in this module were fixed."),
    }
