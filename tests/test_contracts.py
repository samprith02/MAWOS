"""Clarification is a first-class outcome, not an error string. A turn that
returns NeedInfo STOPS -- that is the behaviour whose absence made Gemini
fail M4 (it called a tool against a silent default, then asked)."""
import pytest
from pydantic import ValidationError

from backend.app.contracts import AgentResult, AgentTask, NeedInfo, Refusal


def test_task_requires_capability_and_actor():
    t = AgentTask(capability="get_attendance", args={"usn": "X"},
                  actor="stud1", agent="attendance_agent")
    assert t.capability == "get_attendance"
    assert t.args == {"usn": "X"}


def test_task_rejects_missing_capability():
    with pytest.raises(ValidationError):
        AgentTask(args={}, actor="stud1", agent="attendance_agent")


def test_result_carries_provenance_payload():
    r = AgentResult(agent="attendance_agent", data={"pct": 71.0},
                    source_tool="get_attendance")
    assert r.ok is True
    assert r.source_tool == "get_attendance"


def test_need_info_carries_the_question_and_field():
    n = NeedInfo(agent="attendance_agent", question="Which subject?",
                 field="subject_code")
    assert n.ok is False
    assert n.field == "subject_code"


def test_refusal_carries_a_reason_code():
    f = Refusal(agent="attendance_agent", reason_code="NOT_PERMITTED",
                detail="role 'student' may not use mark_attendance")
    assert f.ok is False
    assert f.reason_code == "NOT_PERMITTED"
