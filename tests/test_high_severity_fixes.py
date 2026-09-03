import datetime as dt

from fastapi.testclient import TestClient

from backend.app.agents.attendance import overall_percentage
from backend.app.agents.finance import fees_cleared
from backend.app.auth import hash_password
from backend.app.main import app
from backend.app.models import (
    AttendanceRecord, Department, Faculty, FeeRecord, MarksRecord, Student,
    Subject, TeachingAssignment, User,
)


def _ensure_scope_fixture(db):
    if db.get(Department, "CSE") is None:
        db.add(Department(code="CSE", name="Computer Science", intake=2))
    if db.get(Subject, "23CS51") is None:
        db.add(Subject(code="23CS51", name="Data Structures", dept_code="CSE",
                       semester=5, credits=4))
    if db.get(Student, "4MT23AI901") is None:
        db.add(Student(usn="4MT23AI901", name="Assigned Student",
                       dept_code="AIML", year=3, semester=5, section="A",
                       cgpa=8.0, backlogs=0, family_income=300000))
    if db.get(Student, "4MT23CS901") is None:
        db.add(Student(usn="4MT23CS901", name="Foreign Student",
                       dept_code="CSE", year=3, semester=5, section="A",
                       cgpa=8.0, backlogs=0, family_income=300000))
    faculty = db.query(Faculty).filter_by(name="Test Prof").first()
    if db.query(User).filter_by(username="scope.faculty").first() is None:
        db.add(User(username="scope.faculty", password_hash=hash_password("x"),
                    role="faculty", display_name="Scope Faculty",
                    faculty_id=faculty.id, dept_code="AIML"))
    db.commit()


def _login(username: str) -> dict:
    client = TestClient(app)
    token = client.post("/api/auth/login",
                        json={"username": username, "password": "x"}).json()["token"]
    return {"Authorization": "Bearer " + token}


def test_faculty_roster_requires_assigned_class(db):
    _ensure_scope_fixture(db)
    client = TestClient(app)
    headers = _login("scope.faculty")

    assigned = client.get("/api/faculty/roster/AIML/3/A", headers=headers)
    assert assigned.status_code == 200
    assert any(s["usn"] == "4MT23AI901" for s in assigned.json()["roster"])

    unassigned = client.get("/api/faculty/roster/CSE/3/A", headers=headers)
    assert unassigned.status_code == 403
    assert "4MT23CS901" not in unassigned.text


def test_faculty_marks_require_assigned_subject_section_and_do_not_write(db):
    _ensure_scope_fixture(db)
    client = TestClient(app)
    headers = _login("scope.faculty")
    db.add(MarksRecord(usn="4MT23CS901", subject_code="23CS51",
                       internal=1, marks=12, entered_by="seed"))
    db.commit()

    denied = client.post("/api/faculty/marks", headers=headers, json={
        "subject_code": "23CS51", "internal": 1,
        "entries": [{"usn": "4MT23CS901", "marks": 49}],
    })
    assert denied.status_code == 403
    db.expire_all()
    unchanged = db.query(MarksRecord).filter_by(
        usn="4MT23CS901", subject_code="23CS51", internal=1).first()
    assert unchanged.marks == 12
    assert unchanged.entered_by == "seed"

    allowed = client.post("/api/faculty/marks", headers=headers, json={
        "subject_code": "23AI51", "internal": 3,
        "entries": [{"usn": "4MT23AI901", "marks": 46}],
    })
    assert allowed.status_code == 200
    assert allowed.json()["accepted"] == 1
    written = db.query(MarksRecord).filter_by(
        usn="4MT23AI901", subject_code="23AI51", internal=3).first()
    assert written is not None
    assert written.marks == 46
    assert written.entered_by == "scope.faculty"


def _student_with_attendance(db, usn: str):
    if db.get(Student, usn) is None:
        db.add(Student(usn=usn, name=usn, dept_code="AIML", year=3,
                       semester=5, section="A", cgpa=8.5, backlogs=0,
                       family_income=300000))
        today = dt.date.today()
        for i in range(10):
            db.add(AttendanceRecord(usn=usn, subject_code="23AI51",
                                    date=today - dt.timedelta(days=i + 1),
                                    present=True, uploaded_by="test"))
        db.commit()
    assert overall_percentage(db, usn) == 100.0


def test_future_due_unpaid_fee_blocks_hall_ticket_and_scholarship(agents, db):
    usn = "4MT23AI902"
    _student_with_attendance(db, usn)
    db.add(FeeRecord(usn=usn, fee_type="tuition", amount_due=1000,
                     amount_paid=0, due_date=dt.date.today() + dt.timedelta(days=10),
                     status="pending"))
    db.commit()

    hall_ticket = agents["eligibility_agent"].evaluate_hall_ticket(db, usn)
    scholarship = agents["eligibility_agent"].evaluate_scholarship(db, usn)

    assert fees_cleared(db, usn) is False
    assert hall_ticket["eligible"] is False
    assert any("fees" in r for r in hall_ticket["reasons"])
    assert scholarship["status"] == "not_eligible"
    assert any("fees" in r for r in scholarship["reasons"])


def test_partial_and_zero_balance_fee_clearance(db):
    partial = "4MT23AI903"
    paid = "4MT23AI904"
    zero_paid = "4MT23AI905"
    zero_pending = "4MT23AI906"
    for usn in (partial, paid, zero_paid, zero_pending):
        _student_with_attendance(db, usn)
    today = dt.date.today()
    db.add_all([
        FeeRecord(usn=partial, fee_type="tuition", amount_due=1000,
                  amount_paid=400, due_date=today + dt.timedelta(days=10),
                  status="pending"),
        FeeRecord(usn=paid, fee_type="tuition", amount_due=1000,
                  amount_paid=1000, due_date=today, paid_date=today,
                  status="PAID"),
        FeeRecord(usn=zero_paid, fee_type="waiver", amount_due=0,
                  amount_paid=0, due_date=today, paid_date=today,
                  status="paid"),
        FeeRecord(usn=zero_pending, fee_type="waiver", amount_due=0,
                  amount_paid=0, due_date=today, status="pending"),
    ])
    db.commit()

    assert fees_cleared(db, partial) is False
    assert fees_cleared(db, paid) is True
    assert fees_cleared(db, zero_paid) is True
    assert fees_cleared(db, zero_pending) is False
