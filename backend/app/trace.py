"""Per-turn trace persistence.

`TraceRecord` is the evaluation instrument, not a log. A step that is not
recorded cannot be measured, and a number that cannot be regenerated may
not be reported (CLAUDE.md).
"""
from __future__ import annotations

import json

from .models import TraceRecord

KINDS = ("plan", "delegate", "tool", "guard", "gate",
         "clarify", "confirm", "synthesise")


def record(db, turn_id: str, step: int, kind: str, actor: str,
           verdict: str = "", payload: dict | None = None,
           latency_ms: float = 0.0) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown trace kind {kind!r}; expected one of {KINDS}")
    db.add(TraceRecord(turn_id=turn_id, step=step, kind=kind, actor=actor,
                       verdict=verdict, latency_ms=latency_ms,
                       payload=json.dumps(payload or {}, default=str)))


def steps_for(db, turn_id: str) -> list[TraceRecord]:
    return (db.query(TraceRecord)
              .filter_by(turn_id=turn_id)
              .order_by(TraceRecord.step)
              .all())
