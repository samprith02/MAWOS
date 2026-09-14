"""LangGraph turn state.

One turn = one user utterance and everything the system does in response.
The state is checkpointed, so an interrupted confirmation survives a
restart -- a write proposal is not lost because a process died.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage

#: D9 fixes re-plan depth at N=1. Raising it is a recorded decision backed
#: by a measurement, never a code edit (docs/v4/OPEN_DECISIONS.md D9).
MAX_REPLANS = 1


class TurnState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    actor: str                     # username
    turn_id: str
    plan: list[dict[str, Any]]     # serialised AgentTask list
    outcomes: Annotated[list[dict[str, Any]], operator.add]
    pending: dict[str, Any]        # the write awaiting confirmation, if any
    answer: str
    replans: int
