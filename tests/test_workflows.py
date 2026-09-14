"""Timetable solver + cascade + tool permissions.

R1: `test_admissions_pipeline` was removed with the admissions module
(docs/v4/02_SCOPE.md DO-NOT-BUILD; 04_DATA_MODEL.md 4.4).
"""
import asyncio
import datetime as dt
from collections import Counter

from backend.app.models import (
    FeeRecord, Notification, Student, TimetableSlot, User, WorkflowEvent,
)
from tests.fixtures.mini_institution import (  # noqa: E402
    STUDENT_OK, STUDENT_RISK, SUBJECT_LAB, SUBJECT_THEORY)


def test_timetable_generation_is_conflict_free(agents, db):
    result = agents["timetable_agent"].generate(db, "AIML")
    assert result["ok"] and result["unplaced"] == 0
    slots = db.query(TimetableSlot).all()
    # subject slot counts match credits (4 + 3)
    per_subject = Counter(s.subject_code for s in slots)
    assert per_subject[SUBJECT_THEORY] == 4 and per_subject[SUBJECT_LAB] == 3
    # no faculty double-booking
    bookings = Counter((s.faculty_id, s.day, s.period) for s in slots)
    assert max(bookings.values()) == 1
    # CSV export renders
    csv = agents["timetable_agent"].csv_export(db, "AIML", 3, "A")
    assert "Timetable,AIML Year 3 Section A" in csv


def test_full_cascade_under_one_workflow(agents, db):
    records = []
    d, made = dt.date(2026, 2, 2), 0
    while made < 10:
        if d.weekday() < 5:
            records.append({"usn": STUDENT_RISK, "subject_code": SUBJECT_LAB,
                            "date": d.isoformat(), "present": made < 3})
            made += 1
        d += dt.timedelta(days=1)
    result = asyncio.run(agents["attendance_agent"].upload_attendance(
        db, "cascade-test", records))
    events = db.query(WorkflowEvent).filter_by(
        workflow_id=result["workflow_id"]).all()
    topics = {e.topic for e in events}
    assert {"attendance.uploaded", "attendance.updated", "exam.updated",
            "scholarship.updated", "placement.updated",
            "notification.sent"} <= topics
    assert max(e.elapsed_ms for e in events) < 2000
    note = (db.query(Notification).filter_by(usn=STUDENT_RISK)
              .filter(Notification.title.contains("shortage")).first())
    assert note is not None


def test_tool_permissions_lock_students_to_self(agents, db):
    from backend.app.agents import tools
    student1 = db.query(User).filter_by(username=STUDENT_OK).first()
    # v5 CHANGE (was: silent coercion to the caller's own USN).
    # A student asking for another student's record is now DENIED outright.
    # v3 returned the caller's OWN data under the requested USN, which in an
    # LLM-driven system is a grounding hazard: the model would faithfully
    # report the wrong student's name against the right student's numbers.
    # The denial is also logged as a GuardDecision, so the attempt is
    # countable -- a silent coercion never was.
    denied_other = tools.execute(db, agents, student1, "get_attendance",
                                 {"usn": STUDENT_RISK})
    assert denied_other.get("reason_code") == "OUT_OF_SCOPE"
    # the student CAN still read their own record
    own = tools.execute(db, agents, student1, "get_attendance",
                        {"usn": STUDENT_OK})
    assert own.get("usn") == STUDENT_OK
    # and role-gated tools still refuse
    denied = tools.execute(db, agents, student1, "get_institution_analytics", {})
    # v5 CHANGE: the resume brief's own text asserted the OLD pre-guard
    # message ("not permitted"); guard.authorise's actual denial detail is
    # "role '<role>' may not use <capability>" (backend/app/guard.py
    # _decide). Assert the reason_code -- the stable, documented contract
    # (guard.REASON_NOT_PERMITTED) -- rather than a message string that no
    # longer matches.
    assert denied.get("reason_code") == "NOT_PERMITTED"
    assert "may not use" in denied.get("error", "")
