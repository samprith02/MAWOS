"""The graph must compile and must bound re-planning at N=1 (D9)."""
from backend.app.graph.build import build_graph
from backend.app.graph.state import MAX_REPLANS, TurnState


def test_replan_depth_is_one():
    """D9 fixes re-plan depth at N=1. A deeper value is a decision that
    requires a recorded measurement, not a code edit."""
    assert MAX_REPLANS == 1


def test_state_declares_the_required_keys():
    required = {"messages", "actor", "turn_id", "plan",
                "outcomes", "pending", "answer", "replans"}
    assert required <= set(TurnState.__annotations__)


def test_graph_compiles_without_a_provider():
    """No credential must not prevent the graph from building -- degradation
    is visible, not fatal."""
    g = build_graph()
    assert g is not None
