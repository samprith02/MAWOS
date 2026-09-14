"""Graph assembly.

Node bodies live in `nodes.py`; this module only wires topology and
persistence, so the shape of the turn stays readable in one screen.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .. import config
from .state import TurnState


def get_checkpointer():
    """Postgres when deployed, in-memory for tests and local SQLite runs."""
    if config.DATABASE_URL.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver
        saver = PostgresSaver.from_conn_string(config.DATABASE_URL)
        saver.setup()
        return saver
    from langgraph.checkpoint.memory import InMemorySaver
    return InMemorySaver()


def build_graph(checkpointer=None):
    from . import nodes

    g = StateGraph(TurnState)
    g.add_node("plan", nodes.plan)
    g.add_node("clarify", nodes.clarify)
    g.add_node("guard", nodes.guard_step)
    g.add_node("confirm", nodes.confirm)
    g.add_node("execute", nodes.execute_step)
    g.add_node("observe", nodes.observe)
    g.add_node("synthesize", nodes.synthesize)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", nodes.after_plan,
                            {"clarify": "clarify", "guard": "guard"})
    g.add_edge("clarify", END)                 # a NeedInfo STOPS the turn
    g.add_conditional_edges("guard", nodes.after_guard,
                            {"confirm": "confirm", "execute": "execute",
                             "synthesize": "synthesize"})
    g.add_edge("confirm", "execute")
    g.add_edge("execute", "observe")
    g.add_conditional_edges("observe", nodes.after_observe,
                            {"plan": "plan", "synthesize": "synthesize"})
    g.add_edge("synthesize", END)

    return g.compile(checkpointer=checkpointer or get_checkpointer())
