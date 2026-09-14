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
    """Authorise every planned task before anything runs. A denial becomes a
    Refusal outcome; it never becomes an exception and never silently
    disappears."""
    from ..agents.tools import write_tool_names
    from ..contracts import Refusal
    from ..database import SessionLocal
    from ..guard import authorise
    from ..models import User

    writes = set(write_tool_names())
    refusals, allowed, needs_confirm = [], [], False
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=state["actor"]).one()
        for task in state.get("plan", []):
            v = authorise(db, user, task["capability"], task.get("args", {}),
                          turn_id=state.get("turn_id"))
            if not v.allowed:
                refusals.append(Refusal(agent=task.get("agent", ""),
                                        reason_code=v.reason_code,
                                        detail=v.detail).model_dump())
                continue
            allowed.append(task)
            if task["capability"] in writes:
                needs_confirm = True
        db.commit()
    finally:
        db.close()

    pending = dict(state.get("pending") or {})
    pending["write"] = needs_confirm
    return {"plan": allowed, "outcomes": refusals, "pending": pending}


def after_guard(state: TurnState) -> str:
    if not state.get("plan"):
        return "synthesize"
    return "confirm" if state.get("pending", {}).get("write") else "execute"


def confirm(state: TurnState) -> dict:
    """Pause for a human. The value passed to Command(resume=...) becomes
    this call's return value (LangGraph HITL)."""
    from langgraph.types import interrupt

    proposal = [{"capability": t["capability"], "args": t.get("args", {})}
                for t in state.get("plan", [])]
    decision = interrupt({"action": "confirm_write", "proposed": proposal,
                          "message": "Apply these changes?"})
    if not (decision or {}).get("approve"):
        return {"plan": [], "answer": "Cancelled. Nothing was changed."}
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
