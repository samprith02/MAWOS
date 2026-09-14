"""MCP surface.

Exposes MAWOS's capabilities to an external client (Claude Desktop,
ChatGPT) through exactly the same guarded path the internal planner uses.
`call_as` delegates to `tools.execute`, which calls `guard.authorise` --
there is no second authorisation path, and adding one would invalidate the
guard-parity claim this module exists to test.

Note on the `mcp` SDK version installed here (2.2.0): `FastMCP` was renamed
to `MCPServer` and moved to `mcp.server.mcpserver` (the `mcp.server.fastmcp`
import path raises `ModuleNotFoundError` with a migration pointer). The
`add_tool(fn, name=..., description=...)` call used below has the same
signature under the new name, so only the import/class name changed.
"""
from __future__ import annotations

from .agents import get_agents
from .agents import tools as toolreg
from .database import SessionLocal
from .models import User


def mcp_tool_names(role: str) -> list[str]:
    return [t["name"] for t in toolreg.TOOLS.values() if role in t["roles"]]


def call_as(db, agents, user, name: str, args: dict) -> dict:
    """The single external entry point. Deliberately a thin delegation."""
    return toolreg.execute(db, agents, user, name, args or {})


def build_mcp_server(actor_username: str):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("mawos")
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=actor_username).one()
        role = user.role
    finally:
        db.close()

    for spec in list(toolreg.TOOLS.values()):
        if role not in spec["roles"]:
            continue

        def _make(tool_name: str):
            def _call(**kwargs) -> dict:
                session = SessionLocal()
                try:
                    actor = session.query(User).filter_by(
                        username=actor_username).one()
                    out = call_as(session, get_agents(), actor, tool_name, kwargs)
                    session.commit()
                    return out
                finally:
                    session.close()
            return _call

        server.add_tool(_make(spec["name"]), name=spec["name"],
                        description=spec["description"])
    return server
