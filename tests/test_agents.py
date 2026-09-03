"""Unit tests for deterministic agent logic (v2)."""
import asyncio
import datetime as dt

from backend.app import config
from backend.app.agents.attendance import overall_percentage
from backend.app.agents.finance import fees_cleared
from backend.app.models import AttendanceSummary, FeeRecord, HallTicket


def _upload(agents, db, records):
    return asyncio.run(
        agents["attendance_agent"].upload_attendance(db, "test", records))


def _mk_records(usn, subject, n_days, n_present, start=None):
    start = start or dt.date(2026, 1, 5)
    recs, d, made = [], start, 0
    while made < n_days:
        if d.weekday() < 5:
            recs.append({"usn": usn, "subject_code": subject,
                         "date": d.isoformat(), "present": made < n_present})
            made += 1
        d += dt.timedelta(days=1)
    return recs


def test_attendance_percentage_and_shortage(agents, db):
    result = _upload(agents, db, _mk_records("4MT23AI002", "23AI51", 20, 12))
    assert result["accepted"] == 20
    assert overall_percentage(db, "4MT23AI002") == 60.0
    summary = db.query(AttendanceSummary).filter_by(
        usn="4MT23AI002", subject_code="23AI51").first()
    assert summary.percentage == 60.0 and summary.shortage is True


def test_duplicate_attendance_rejected(agents, db):
    recs = _mk_records("4MT23AI001", "23AI51", 5, 5)
    assert _upload(agents, db, recs)["accepted"] == 5
    second = _upload(agents, db, recs)
    assert second["accepted"] == 0
    assert all(r["reason"] == "duplicate entry" for r in second["rejected"])


def test_fee_fine_and_clearance(agents, db):
    fin = agents["finance_agent"]
    today = dt.date.today()
    fee = db.query(FeeRecord).filter_by(usn="4MT23AI002",
                                        status="pending").first() \
        or db.query(FeeRecord).filter_by(usn="4MT23AI002").first()
    fin.refresh_status(db, "4MT23AI002", today=today)
    db.refresh(fee)
    days_late = (today - (fee.due_date
                          + dt.timedelta(days=config.FEE_GRACE_DAYS))).days
    assert fee.status == "overdue"
    assert fee.fine == days_late * config.FEE_LATE_FINE_PER_DAY
    assert fees_cleared(db, "4MT23AI002") is False
    assert fees_cleared(db, "4MT23AI001") is True


def test_exam_eligibility(agents, db):
    elig = agents["eligibility_agent"]
    blocked = elig.evaluate_hall_ticket(db, "4MT23AI002")   # 60% attendance + overdue fee
    db.commit()
    assert blocked["eligible"] is False
    assert any("attendance" in r for r in blocked["reasons"])
    assert any("fees" in r for r in blocked["reasons"])
    ok = elig.evaluate_hall_ticket(db, "4MT23AI001")        # 100% attendance, paid
    db.commit()
    assert ok["eligible"] is True
    assert db.query(HallTicket).filter_by(usn="4MT23AI001").first().eligible


def test_scholarship_rule_prefilter(agents, db):
    result = agents["eligibility_agent"].evaluate_scholarship(db, "4MT23AI002")
    db.commit()
    assert result["status"] == "not_eligible"
    assert len(result["reasons"]) >= 2
