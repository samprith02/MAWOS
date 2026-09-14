"""The graph must compile and must bound re-planning at N=1 (D9)."""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.app.graph import nodes
from backend.app.graph.build import build_graph
from backend.app.graph.state import MAX_REPLANS, TurnState
from tests.fixtures.mini_institution import HOD_USER, SECTION, SUBJECT_THEORY


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


def test_replan_depth_is_one():
    """D9 fixes re-plan depth at N=1. A deeper value is a decision that
    requires a recorded measurement, not a code edit."""
    assert MAX_REPLANS == 1


def test_plan_increments_replans_on_every_entry():
    """Critical 1: plan() used to pass `replans` through unchanged, so
    `after_observe`'s bound could never trip and the graph looped forever
    whenever outcomes stayed empty. It must increment every entry."""
    first = nodes.plan({})
    assert first["replans"] == 1
    second = nodes.plan({"replans": first["replans"]})
    assert second["replans"] == 2


def test_after_observe_allows_exactly_one_replan_then_stops():
    """The exact trace this fix must produce (brief, Critical 1): 1st plan
    -> replans=1 -> observe -> 1<=1 and no outcomes -> re-plan -> replans=2
    -> observe -> 2<=1 is false -> synthesize. Two plan entries, one
    re-plan, N=1."""
    assert nodes.after_observe({"replans": 1, "outcomes": []}) == "plan"
    assert nodes.after_observe({"replans": 2, "outcomes": []}) == "synthesize"
    # An outcome ends the turn immediately, even on the very first pass.
    assert nodes.after_observe({"replans": 1, "outcomes": [{"kind": "result"}]}) \
        == "synthesize"


def test_state_declares_the_required_keys():
    required = {"messages", "actor", "turn_id", "plan",
                "outcomes", "pending", "answer", "replans"}
    assert required <= set(TurnState.__annotations__)


def test_graph_compiles_without_a_provider():
    """No credential must not prevent the graph from building -- degradation
    is visible, not fatal."""
    g = build_graph()
    assert g is not None


def test_graph_terminates_when_a_turn_produces_no_outcomes(
        monkeypatch, db, agents, base_data):
    """Integration-level trace for D9's exact bound: a rejected write
    reaches `execute_step` with an empty plan (confirm() clears it), so no
    outcome is ever appended, and the turn re-plans once before
    terminating -- exactly the "two plan entries, one re-plan, N=1" trace.

    NOTE, found while doing the deliberate-break check the brief asks for:
    with `execute_step` correctly implemented (Critical 2), this specific
    scenario terminates in exactly 2 `plan` entries EVEN IF Critical 1's
    increment/bound fix is reverted -- because the second `plan` entry
    still carries an empty `state["plan"]` (confirm's rejection cleared
    it), and `after_guard`'s own `if not state.get("plan"): return
    "synthesize"` bypasses `execute`/`observe` (and therefore the replans
    check) entirely on that second pass, independent of the counter. So
    this test, alone, does NOT fail if Critical 1's fix is reverted --
    verified empirically, see final-fix-report.md. It stays here because
    it is still a real, useful end-to-end trace of the D9 bound; the tests
    that actually regression-test Critical 1's fix are the two directly
    above (`test_plan_increments_replans_on_every_entry` and
    `test_after_observe_allows_exactly_one_replan_then_stops`), which DO
    fail when the increment or the `<=` bound is reverted."""
    calls = {"n": 0}
    original_plan = nodes.plan

    def counting_plan(state):
        calls["n"] += 1
        return original_plan(state)

    monkeypatch.setattr(nodes, "plan", counting_plan)
    g = build_graph(checkpointer=InMemorySaver())
    state = {"actor": HOD_USER, "turn_id": "t-replan-1",
             "plan": [{"capability": "mark_attendance",
                       "args": {"section": SECTION,
                                "subject_code": SUBJECT_THEORY,
                                "absentees": []},
                       "agent": "attendance_agent", "actor": HOD_USER}],
             "pending": {"write": True}}
    g.invoke(state, config=_cfg("t-replan-1"))
    result = g.invoke(Command(resume={"approve": False}),
                      config=_cfg("t-replan-1"))

    assert result.get("answer") == "Cancelled. Nothing was changed."
    assert calls["n"] <= MAX_REPLANS + 1
    assert calls["n"] >= 2, "this scenario is supposed to trigger one re-plan"
