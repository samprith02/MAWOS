"""Write tools must be (a) marked, (b) guarded, and (c) unable to execute
when the guard denies -- the guard is non-bypassable, so a denial must
stop the write, not merely annotate it."""
from backend.app.agents import tools as toolreg
from backend.app.models import AttendanceRecord, User


def test_three_write_tools_are_registered():
    assert set(toolreg.write_tool_names()) == {
        "mark_attendance", "apply_timetable_change", "issue_eligibility_override"}


def test_write_tools_are_staff_only():
    for name in toolreg.write_tool_names():
        assert "student" not in toolreg.TOOLS[name]["roles"]


def test_student_write_attempt_is_blocked_and_writes_nothing(db, agents, base_data):
    student = db.query(User).filter_by(role="student").first()
    before = db.query(AttendanceRecord).count()
    out = toolreg.execute(db, agents, student, "mark_attendance",
                          {"section": "A", "subject_code": "X", "absentees": []})
    assert "error" in out
    assert out["reason_code"] == "NOT_PERMITTED"
    assert db.query(AttendanceRecord).count() == before


def test_read_tools_are_not_marked_as_writes():
    assert toolreg.TOOLS["get_attendance"].get("writes") is not True
