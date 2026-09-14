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
