"""Write tools must be (a) marked, (b) guarded, and (c) unable to execute
when the guard denies -- the guard is non-bypassable, so a denial must
stop the write, not merely annotate it."""
from backend.app.agents import tools as toolreg
from backend.app.models import AttendanceRecord, HallTicket, Student, User
from tests.fixtures.mini_institution import DEPT, SECTION, SEMESTER, YEAR


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


def test_override_on_student_without_hall_ticket_does_not_double_insert(
        db, agents, base_data):
    """Regression test for the autoflush=False double-insert bug found and
    fixed while building EligibilityAgent.override() (backend/app/agents/
    eligibility.py). `SessionLocal` is autoflush=False (backend/app/
    database.py), and `override()` is the only call site in the codebase
    that runs `evaluate_hall_ticket` TWICE in one session (once to capture
    the "before" verdict, once to re-derive "after" post-write). For a
    student with no existing HallTicket row, the first call adds a pending
    (unflushed, unqueryable-without-flush) HallTicket; without the two
    `db.flush()` calls inside `override()`, the second call's query does
    not see that pending row, adds a SECOND HallTicket for the same
    (usn, semester), and the eventual commit throws
    `sqlite3.IntegrityError: UNIQUE constraint failed:
    hall_tickets.usn, hall_tickets.semester`.

    DO NOT remove those two `db.flush()` calls from `override()` to "tidy
    it up" -- this test exists specifically to catch that regression, by
    asserting there is exactly ONE HallTicket row afterwards, not just that
    the call didn't raise.

    A fresh student is created here rather than reusing STUDENT_OK/
    STUDENT_RISK from the shared fixture: test_agents.py::test_exam_eligibility
    already calls and commits evaluate_hall_ticket for both of those, which
    runs earlier in the default collection order, so by the time this test
    ran, both would already have a committed HallTicket row -- silently
    turning this into a no-op test that can't reproduce the bug.
    STUDENT_EMPTY (tests/fixtures/mini_institution.py) looked like the
    right fit ("exists but has no records at all") but is a stale constant
    -- `mini_institution.build()` never actually inserts a Student row for
    it, so `override()` would just return "unknown student" and never
    reach `evaluate_hall_ticket` at all. Verified: `db.get(Student,
    STUDENT_EMPTY)` is None under `base_data`.
    """
    usn = "1VT23AI900"
    assert db.get(Student, usn) is None       # confirms this is a fresh USN
    db.add(Student(usn=usn, name="Fresh No-Ticket Student", dept_code=DEPT,
                   year=YEAR, semester=SEMESTER, section=SECTION, cgpa=5.0,
                   backlogs=1))
    db.commit()
    assert db.query(HallTicket).filter_by(usn=usn).count() == 0

    out = agents["eligibility_agent"].override(
        db, usn=usn, exam="mid-sem", reason="regression coverage",
        decided_by="hod.aiml")

    assert out["applied"] is True
    assert db.query(HallTicket).filter_by(usn=usn).count() == 1
