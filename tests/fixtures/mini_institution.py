"""A hand-built miniature institution with fully known ground truth.

`docs/v4/04_DATA_MODEL.md` §5.3 makes this MUST-tier, for three reasons that
are not conveniences:

1. The R5 outcome checker asserts against exact expected state, which needs
   an instance small enough to reason about by hand.
2. v3's tests depended on the shipped 30 MB `mawos.db`, which is why
   `CLAUDE.md` carries warnings about not deleting it while the server runs
   and not running the evaluation concurrently. Fixtures remove that coupling.
3. Solver tests need instances where the correct answer is known, not merely
   instances that produce *an* answer.

Every identifier is derived from `data/institution.yaml`, so the fixtures
carry no institution identity of their own and the R1 identity gate cannot
be defeated by a test file.
"""
from __future__ import annotations

import datetime as dt

from data.generator.config import load

_INST = load()
_P = _INST.usn_prefix
_DOMAIN = _INST.email_domain

# ---------------------------------------------------------------- identities
#: Clears every rule: high CGPA, no backlogs, fees paid, good attendance.
STUDENT_OK = f"{_P}23AI001"
#: Fails several: low CGPA, 3 backlogs, unpaid tuition, poor attendance.
STUDENT_RISK = f"{_P}23AI002"
#: Exists but has no records at all — the "empty state" case.
STUDENT_EMPTY = f"{_P}23AI003"
#: Never inserted. Used to test unknown-identifier handling.
STUDENT_UNKNOWN = f"{_P}23AI999"

DEPT = "AIML"
YEAR, SEMESTER, SECTION = 3, 5, "A"

SUBJECT_THEORY = f"{SEMESTER}AI01"
SUBJECT_LAB = f"{SEMESTER}AI02"

ROOM_CLASS = "MAI-C001"
ROOM_LAB = "MAI-L001"

FACULTY_NAME = "Test Prof"

#: Ground truth the tests may rely on.
EXPECTED = {
    STUDENT_OK: {"cgpa": 8.5, "backlogs": 0, "fees_cleared": True},
    STUDENT_RISK: {"cgpa": 5.5, "backlogs": 3, "fees_cleared": False},
}


def build(session, *, today: dt.date | None = None) -> dict:
    """Create the mini institution. Returns the ids the tests need."""
    from backend.app.auth import hash_password
    from backend.app.models import (
        Department, Faculty, FeeRecord, Room, Student, Subject,
        TeachingAssignment, User,
    )

    today = today or dt.date.today()
    session.add(Department(code=DEPT, name="AI & ML", intake=2))
    session.add_all([
        Subject(code=SUBJECT_THEORY, name="Machine Learning", dept_code=DEPT,
                semester=SEMESTER, credits=4, kind="theory", block_size=1),
        Subject(code=SUBJECT_LAB, name="Database Systems", dept_code=DEPT,
                semester=SEMESTER, credits=3, kind="lab", block_size=2),
    ])
    session.add_all([
        Room(code=ROOM_CLASS, name="Main Classroom 1", room_type="classroom",
             capacity=70, building="Main"),
        Room(code=ROOM_LAB, name="Main Lab 1", room_type="lab",
             capacity=40, building="Main"),
    ])

    fac = Faculty(name=FACULTY_NAME, dept_code=DEPT,
                  email=f"{DEPT.lower()}.f01@{_DOMAIN}",
                  qualified_subjects=f"{SUBJECT_THEORY},{SUBJECT_LAB}")
    session.add(fac)
    session.flush()

    session.add_all([
        TeachingAssignment(faculty_id=fac.id, subject_code=SUBJECT_THEORY,
                           dept_code=DEPT, year=YEAR, section=SECTION),
        TeachingAssignment(faculty_id=fac.id, subject_code=SUBJECT_LAB,
                           dept_code=DEPT, year=YEAR, section=SECTION),
    ])

    session.add_all([
        Student(usn=STUDENT_OK, name="Good Student", dept_code=DEPT,
                year=YEAR, semester=SEMESTER, section=SECTION, cgpa=8.5,
                backlogs=0, family_income=300000,
                email=f"{STUDENT_OK.lower()}@{_DOMAIN}"),
        Student(usn=STUDENT_RISK, name="Struggling Student", dept_code=DEPT,
                year=YEAR, semester=SEMESTER, section=SECTION, cgpa=5.5,
                backlogs=3, family_income=900000,
                email=f"{STUDENT_RISK.lower()}@{_DOMAIN}"),
    ])
    session.add_all([
        FeeRecord(usn=STUDENT_RISK, fee_type="tuition", amount_due=85000,
                  due_date=today - dt.timedelta(days=60), status="pending"),
        FeeRecord(usn=STUDENT_OK, fee_type="tuition", amount_due=85000,
                  amount_paid=85000, due_date=today - dt.timedelta(days=60),
                  paid_date=today - dt.timedelta(days=61), status="paid"),
    ])
    session.add_all([
        User(username=STUDENT_OK, password_hash=hash_password("x"),
             role="student", display_name="Good Student", usn=STUDENT_OK,
             dept_code=DEPT),
        User(username=STUDENT_RISK, password_hash=hash_password("x"),
             role="student", display_name="Struggling Student",
             usn=STUDENT_RISK, dept_code=DEPT),
    ])
    session.commit()
    return {"faculty_id": fac.id}
