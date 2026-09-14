"""Turn nodes. Kept small and individually testable -- the graph's value is
that each step is inspectable, which is lost if a node does three things.
"""
from __future__ import annotations

from .state import MAX_REPLANS, TurnState


def plan(state: TurnState) -> dict:
    """Ask the model for a plan. With no provider, emit an empty plan so the
    turn degrades to the deterministic tier rather than failing."""
    return {"plan": state.get("plan") or [], "replans": state.get("replans", 0)}


def after_plan(state: TurnState) -> str:
    return "clarify" if state.get("pending", {}).get("question") else "guard"


def clarify(state: TurnState) -> dict:
    q = state.get("pending", {}).get("question", "")
    return {"answer": q}


def guard_step(state: TurnState) -> dict:
    return {}


def after_guard(state: TurnState) -> str:
    if not state.get("plan"):
        return "synthesize"
    return "confirm" if state.get("pending", {}).get("write") else "execute"


def confirm(state: TurnState) -> dict:
    return {}


def execute_step(state: TurnState) -> dict:
    return {}


def observe(state: TurnState) -> dict:
    return {}


def after_observe(state: TurnState) -> str:
    if state.get("replans", 0) < MAX_REPLANS and not state.get("outcomes"):
        return "plan"
    return "synthesize"


def synthesize(state: TurnState) -> dict:
    return {"answer": state.get("answer", "")}
