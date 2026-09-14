"""Turn nodes. Kept small and individually testable -- the graph's value is
that each step is inspectable, which is lost if a node does three things.
"""
from __future__ import annotations

from .state import MAX_REPLANS, TurnState


def plan(state: TurnState) -> dict:
    """Ask the model for a plan. With no provider, emit an empty plan so the
    turn degrades to the deterministic tier rather than failing.

    Increments `replans` on every entry -- `after_observe` bounds re-entry
    on this counter (D9, N=1). Passing it through unchanged made the bound
    unenforceable (Critical 1): with `execute_step` a no-op, `outcomes`
    never filled, and the graph looped here forever (one allowed
    `get_attendance` task produced 2502 `GuardDecision` rows before
    `GraphRecursionError`)."""
    return {"plan": state.get("plan") or [],
            "replans": state.get("replans", 0) + 1}


def after_plan(state: TurnState) -> str:
    return "clarify" if state.get("pending", {}).get("question") else "guard"


def clarify(state: TurnState) -> dict:
    q = state.get("pending", {}).get("question", "")
    return {"answer": q}


def guard_step(state: TurnState) -> dict:
    """Authorise every planned task before anything runs. A denial becomes a
    Refusal outcome; it never becomes an exception and never silently
    disappears.

    Uses `guard.decide()` (no logging) to sort the plan, then logs a
    `GuardDecision` only for the items it refuses -- those never reach
    `execute_step`, so if this didn't log them the attempt would vanish
    from the record entirely. Allowed items are logged once, by
    `tools.execute` (via `execute_step`), when they actually run. That
    keeps exactly one `GuardDecision` row per proposed action either way
    (Important 3) -- calling `guard.authorise` here too, as before, would
    double-log every allowed item once `execute_step` stopped being a
    no-op."""
    from ..agents.tools import write_tool_names
    from ..contracts import Refusal
    from ..database import SessionLocal
    from ..guard import decide, record_refusal
    from ..models import User
    from .. import trace

    writes = set(write_tool_names())
    refusals, allowed, needs_confirm = [], [], False
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=state["actor"]).one()
        for i, task in enumerate(state.get("plan", [])):
            v = decide(db, user, task["capability"], task.get("args", {}))
            trace.record(db, state.get("turn_id", ""), i,
                         "guard", actor=task["capability"],
                         verdict="allowed" if v.allowed else "denied",
                         payload={"reason_code": v.reason_code})
            if not v.allowed:
                record_refusal(db, user, v, turn_id=state.get("turn_id"))
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
    """Run every task the guard allowed. Each call goes through
    `tools.execute` -- the only call site of a tool's `fn` in this app --
    which authorises (and logs) the call again right before running it;
    `guard_step` already decided this item was allowed and deliberately
    did not log it (Important 3), so this is that item's one log entry.

    Follows `guard_step`'s session handling: open, use, commit, close in
    `finally`."""
    from ..agents import get_agents
    from ..agents.tools import execute as run_tool
    from ..contracts import AgentResult, Refusal
    from ..database import SessionLocal
    from ..models import User
    from .. import trace

    outcomes = []
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=state["actor"]).one()
        agents = get_agents()
        for i, task in enumerate(state.get("plan", [])):
            data = run_tool(db, agents, user, task["capability"],
                            task.get("args", {}), turn_id=state.get("turn_id"))
            if isinstance(data, dict) and "error" in data and "reason_code" in data:
                outcomes.append(Refusal(
                    agent=task.get("agent", ""),
                    reason_code=data["reason_code"],
                    detail=data.get("error", "")).model_dump())
                verdict = "denied"
            else:
                outcomes.append(AgentResult(
                    agent=task.get("agent", ""), data=data,
                    source_tool=task["capability"]).model_dump())
                verdict = "ok"
            trace.record(db, state.get("turn_id", ""), i, "tool",
                        actor=task["capability"], verdict=verdict,
                        payload={"args": task.get("args", {})})
        db.commit()
    finally:
        db.close()
    return {"outcomes": outcomes}


def observe(state: TurnState) -> dict:
    return {}


def after_observe(state: TurnState) -> str:
    """Re-plan at most once (D9, N=1). `plan()` increments `replans` on
    every entry, so the first entry leaves it at 1; while that is still
    `<= MAX_REPLANS` (1) and nothing came back, go around once more. The
    second entry leaves it at 2, which fails the bound, so the turn always
    terminates: two `plan` entries, one re-plan, N=1."""
    if state.get("replans", 0) <= MAX_REPLANS and not state.get("outcomes"):
        return "plan"
    return "synthesize"


def synthesize(state: TurnState) -> dict:
    return {"answer": state.get("answer", "")}
