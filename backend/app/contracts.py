"""The typed delegation contract: Task -> Result | NeedInfo | Refusal.

Three distinct outcomes, not two. A NeedInfo is not a failure and not an
error string -- it STOPS the turn and asks. That distinction is the whole
point: the R0.5 hosted run failed M4 because the model called a tool
against a silent default and asked afterwards.
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    """One unit of delegated work. Produced by the planner, never trusted."""
    capability: str
    args: dict[str, Any] = Field(default_factory=dict)
    actor: str
    agent: str
    rationale: str = ""


class AgentResult(BaseModel):
    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    agent: str
    data: dict[str, Any] = Field(default_factory=dict)
    #: Which tool produced `data`. The provenance gate checks answers
    #: against this, so it is required rather than decorative.
    source_tool: str


class NeedInfo(BaseModel):
    kind: Literal["need_info"] = "need_info"
    ok: Literal[False] = False
    agent: str
    question: str
    #: The argument that is missing, so the resumed turn can fill exactly it.
    field: str


class Refusal(BaseModel):
    kind: Literal["refusal"] = "refusal"
    ok: Literal[False] = False
    agent: str
    reason_code: str
    detail: str = ""


Outcome = Union[AgentResult, NeedInfo, Refusal]
