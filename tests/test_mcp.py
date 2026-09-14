"""Guard parity: the same attack must produce the same verdict whether the
internal planner or an external MCP client drives the tools. A divergence
is a finding, not a bug to hide."""
from backend.app import mcp_server
from backend.app.agents import tools as toolreg
from backend.app.models import User


def test_mcp_exposes_only_role_permitted_tools(db, base_data):
    student_tools = set(mcp_server.mcp_tool_names("student"))
    assert "mark_attendance" not in student_tools
    assert "get_attendance" in student_tools


def test_mcp_denial_matches_internal_denial(db, agents, base_data):
    """Same actor, same capability, same verdict -- via both paths."""
    student = db.query(User).filter_by(role="student").first()
    internal = toolreg.execute(db, agents, student, "mark_attendance", {})
    external = mcp_server.call_as(db, agents, student, "mark_attendance", {})
    assert internal["reason_code"] == external["reason_code"]
    assert ("error" in internal) == ("error" in external)


def test_mcp_cannot_bypass_the_guard(db, agents, base_data):
    from backend.app.models import AttendanceRecord
    student = db.query(User).filter_by(role="student").first()
    before = db.query(AttendanceRecord).count()
    mcp_server.call_as(db, agents, student, "mark_attendance",
                       {"section": "A", "subject_code": "X", "absentees": []})
    assert db.query(AttendanceRecord).count() == before
