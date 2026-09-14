"""A write must pause for a human. LangGraph's interrupt() is the pause;
the guard decides whether the write may even be PROPOSED."""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.app.graph.build import build_graph
from tests.fixtures.mini_institution import HOD_USER, SECTION, SUBJECT_THEORY


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


def test_write_plan_pauses_for_confirmation(db, agents, base_data):
    g = build_graph(checkpointer=InMemorySaver())
    state = {"actor": HOD_USER, "turn_id": "t1",
             "plan": [{"capability": "mark_attendance",
                       "args": {"section": SECTION,
                                "subject_code": SUBJECT_THEORY,
                                "absentees": []},
                       "agent": "attendance_agent", "actor": HOD_USER}],
             "pending": {"write": True}}
    g.invoke(state, config=_cfg("t1"))
    assert g.get_state(_cfg("t1")).next, "graph should be paused, not finished"
    assert g.get_state(_cfg("t1")).values.get("plan"), \
        "guard emptied the plan; the graph never reached confirm"


def test_rejecting_the_confirmation_performs_no_write(db, agents, base_data):
    """Critical 2: this test used to pass whether or not confirm() rejected
    anything, because `execute_step` was a no-op and NOTHING ever wrote --
    it would have passed even with confirm()'s rejection branch deleted.
    Now that `execute_step` really calls `tools.execute`, this only proves
    the property if the approval half (below) proves a write CAN happen at
    all; together they show the count is unchanged on rejection and
    changed on approval."""
    from backend.app.models import AttendanceRecord
    g = build_graph(checkpointer=InMemorySaver())
    state = {"actor": HOD_USER, "turn_id": "t2",
             "plan": [{"capability": "mark_attendance",
                       "args": {"section": SECTION,
                                "subject_code": SUBJECT_THEORY,
                                "absentees": []},
                       "agent": "attendance_agent", "actor": HOD_USER}],
             "pending": {"write": True}}
    before = db.query(AttendanceRecord).count()
    g.invoke(state, config=_cfg("t2"))
    g.invoke(Command(resume={"approve": False}), config=_cfg("t2"))
    assert db.query(AttendanceRecord).count() == before


def test_approving_the_confirmation_performs_the_write(db, agents, base_data):
    """The other half of Critical 2's property: approval must actually
    reach `tools.execute` and write. Without this half, the rejection test
    above cannot distinguish "nothing writes, ever" from "rejection
    specifically blocked a write" -- a no-op `execute_step` satisfies the
    rejection test alone but fails this one, since count stays unchanged
    either way."""
    from backend.app.models import AttendanceRecord
    g = build_graph(checkpointer=InMemorySaver())
    state = {"actor": HOD_USER, "turn_id": "t3",
             "plan": [{"capability": "mark_attendance",
                       "args": {"section": SECTION,
                                "subject_code": SUBJECT_THEORY,
                                "absentees": []},
                       "agent": "attendance_agent", "actor": HOD_USER}],
             "pending": {"write": True}}
    before = db.query(AttendanceRecord).count()
    g.invoke(state, config=_cfg("t3"))
    result = g.invoke(Command(resume={"approve": True}), config=_cfg("t3"))
    after = db.query(AttendanceRecord).count()

    assert after > before
    outcomes = result.get("outcomes", [])
    assert outcomes, "approval must produce an outcome, not silence"
    assert outcomes[-1]["kind"] == "result"
    assert outcomes[-1]["ok"] is True
    assert outcomes[-1]["source_tool"] == "mark_attendance"
