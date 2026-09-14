"""The trace is simultaneously the debugging story, the explainability
feature and the evaluation instrument -- so every step must land in order."""
import pytest

from backend.app import trace


def test_steps_are_returned_in_order(db, base_data):
    for i, kind in enumerate(["plan", "guard", "tool", "synthesise"]):
        trace.record(db, "turn-x", i, kind, actor="orchestrator_agent")
    db.commit()
    got = trace.steps_for(db, "turn-x")
    assert [r.kind for r in got] == ["plan", "guard", "tool", "synthesise"]
    assert [r.step for r in got] == [0, 1, 2, 3]


def test_unknown_kind_is_rejected(db, base_data):
    with pytest.raises(ValueError):
        trace.record(db, "turn-y", 0, "not-a-kind", actor="x")


def test_payload_roundtrips_as_json(db, base_data):
    trace.record(db, "turn-z", 0, "tool", actor="get_attendance",
                 payload={"pct": 71.0})
    db.commit()
    assert trace.steps_for(db, "turn-z")[0].payload_dict() == {"pct": 71.0}
