"""Regression coverage for the read-only student dashboard contract."""
import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app import config
from backend.app.agents import get_agents
from backend.app.auth import hash_password
from backend.app.main import app
from backend.app.models import FeeRecord, PlacementDrive, PlacementShortlist, Student, User


READ_ONLY_USN = "4MT23AI908"
WRITE_FLOW_USN = "4MT23AI909"


def _create_dashboard_student(db):
    if db.get(Student, READ_ONLY_USN) is not None:
        return
    today = dt.date.today()
    db.add(Student(usn=READ_ONLY_USN, name="Read Only Finalist", dept_code="AIML",
                   year=4, semester=8, section="A", cgpa=8.4, backlogs=0,
                   family_income=300000))
    db.add(User(username=READ_ONLY_USN, password_hash=hash_password("x"),
                role="student", display_name="Read Only Finalist",
                usn=READ_ONLY_USN, dept_code="AIML"))
    db.add(FeeRecord(usn=READ_ONLY_USN, fee_type="tuition", amount_due=1000,
                     amount_paid=0, due_date=today - dt.timedelta(
                         days=config.FEE_GRACE_DAYS + 3), fine=0,
                     status="pending"))
    db.add(PlacementDrive(company="Read Only Systems", role="Engineer",
                          package_lpa=6.0, min_cgpa=7.0, max_backlogs=0,
                          min_attendance=0, drive_date=today + dt.timedelta(days=7),
                          departments="AIML"))
    db.commit()


def _dashboard_headers():
    client = TestClient(app)
    response = client.post("/api/auth/login", json={
        "username": READ_ONLY_USN, "password": "x"})
    assert response.status_code == 200
    return client, {"Authorization": f"Bearer {response.json()['token']}"}


def _fee_snapshot(db, usn):
    return [(fee.id, fee.amount_due, fee.amount_paid, fee.fine, fee.status,
             fee.due_date, fee.paid_date)
            for fee in db.query(FeeRecord).filter_by(usn=usn).order_by(FeeRecord.id)]


def test_student_dashboard_is_read_only_and_idempotent(db, monkeypatch):
    _create_dashboard_student(db)
    client, headers = _dashboard_headers()
    before_fees = _fee_snapshot(db, READ_ONLY_USN)
    before_shortlists = db.query(PlacementShortlist).filter_by(usn=READ_ONLY_USN).count()
    commits, flushes = [], []
    original_commit, original_flush = Session.commit, Session.flush

    def track_commit(session, *args, **kwargs):
        commits.append(session)
        return original_commit(session, *args, **kwargs)

    def track_flush(session, *args, **kwargs):
        flushes.append(session)
        return original_flush(session, *args, **kwargs)

    monkeypatch.setattr(Session, "commit", track_commit)
    monkeypatch.setattr(Session, "flush", track_flush)

    first = client.get("/api/student/dashboard", headers=headers)
    second = client.get("/api/student/dashboard", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["profile"]["usn"] == READ_ONLY_USN
    assert body["fees"]["items"] == [{
        "id": before_fees[0][0], "type": "tuition", "amount_due": 1000.0,
        "fine": 3 * config.FEE_LATE_FINE_PER_DAY, "status": "overdue",
        "due_date": str(before_fees[0][5]),
    }]
    assert commits == []
    assert flushes == []
    db.expire_all()
    assert _fee_snapshot(db, READ_ONLY_USN) == before_fees
    assert db.query(PlacementShortlist).filter_by(usn=READ_ONLY_USN).count() == before_shortlists


def test_fee_state_synchronisation_remains_an_explicit_write_service(db):
    if db.get(Student, WRITE_FLOW_USN) is None:
        db.add(Student(usn=WRITE_FLOW_USN, name="Fee Write Flow", dept_code="AIML",
                       year=3, semester=5, section="A", cgpa=8.0, backlogs=0,
                       family_income=300000))
        db.add(FeeRecord(usn=WRITE_FLOW_USN, fee_type="tuition", amount_due=1000,
                         amount_paid=0, due_date=dt.date.today() - dt.timedelta(
                             days=config.FEE_GRACE_DAYS + 2), fine=0,
                         status="pending"))
        db.commit()

    changed = get_agents()["finance_agent"].refresh_status(db, WRITE_FLOW_USN)

    assert changed == 1
    db.expire_all()
    fee = db.query(FeeRecord).filter_by(usn=WRITE_FLOW_USN).one()
    assert fee.status == "overdue"
    assert fee.fine == 2 * config.FEE_LATE_FINE_PER_DAY
