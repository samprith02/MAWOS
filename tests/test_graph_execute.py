"""`execute_step` must actually run tools (Critical 2) and each proposed
action -- allowed or refused -- must land exactly one `GuardDecision` row,
never two and never zero (Important 3)."""
from langgraph.checkpoint.memory import InMemorySaver

from backend.app.graph.build import build_graph
from backend.app.models import GuardDecision
from tests.fixtures.mini_institution import HOD_USER, STUDENT_OK


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


def test_execute_step_actually_runs_the_tool(db, agents, base_data):
    """Critical 2: a no-op `execute_step` returns `{}`, which looks like a
    valid (if empty) turn. This asserts real tool output comes back through
    `outcomes`, which a `{}` return cannot produce."""
    g = build_graph(checkpointer=InMemorySaver())
    state = {"actor": HOD_USER, "turn_id": "t-exec-1",
             "plan": [{"capability": "get_attendance",
                       "args": {"usn": STUDENT_OK},
                       "agent": "attendance_agent", "actor": HOD_USER}],
             "pending": {}}
    result = g.invoke(state, config=_cfg("t-exec-1"))
    outcomes = result.get("outcomes", [])
    assert len(outcomes) == 1
    assert outcomes[0]["kind"] == "result"
    assert outcomes[0]["ok"] is True
    assert outcomes[0]["source_tool"] == "get_attendance"
    assert outcomes[0]["data"]["usn"] == STUDENT_OK


def test_single_allowed_task_produces_exactly_one_guard_decision_row(
        db, agents, base_data):
    """Important 3: `guard_step` used to call `guard.authorise` (which
    logs), and once `execute_step` stopped being a no-op, `tools.execute`
    called `authorise` again for the same task -- two rows per allowed
    action. `guard_step` must now decide without logging (`guard.decide`)
    and let `execute()` write the only row for anything it actually runs.
    This FAILS (asserting == 2) if `guard_step` goes back to calling
    `authorise` directly."""
    g = build_graph(checkpointer=InMemorySaver())
    before = db.query(GuardDecision).count()
    state = {"actor": HOD_USER, "turn_id": "t-exec-2",
             "plan": [{"capability": "get_attendance",
                       "args": {"usn": STUDENT_OK},
                       "agent": "attendance_agent", "actor": HOD_USER}],
             "pending": {}}
    g.invoke(state, config=_cfg("t-exec-2"))
    after = db.query(GuardDecision).count()

    assert after - before == 1
    row = db.query(GuardDecision).order_by(GuardDecision.id.desc()).first()
    assert row.verdict == "allowed"
    assert row.capability == "get_attendance"
    assert row.turn_id == "t-exec-2"


def test_a_refused_task_also_produces_exactly_one_guard_decision_row(
        db, agents, base_data):
    """The other half of Important 3: a refused item never reaches
    `execute`, so `guard_step` itself must log it -- exactly once, not
    zero times (which would make the attempt vanish) and not via
    `authorise` (which would be redundant with nothing, but is the
    tempting wrong fix)."""
    g = build_graph(checkpointer=InMemorySaver())
    before = db.query(GuardDecision).count()
    state = {"actor": STUDENT_OK, "turn_id": "t-exec-3",
             "plan": [{"capability": "mark_attendance",
                       "args": {}, "agent": "attendance_agent",
                       "actor": STUDENT_OK}],
             "pending": {}}
    g.invoke(state, config=_cfg("t-exec-3"))
    after = db.query(GuardDecision).count()

    assert after - before == 1
    row = db.query(GuardDecision).order_by(GuardDecision.id.desc()).first()
    assert row.verdict == "denied"
    assert row.capability == "mark_attendance"
