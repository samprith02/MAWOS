"""Agent-level tests for Placement Agent business logic: drive validation,
shortlist idempotency, hard-filter correctness, and outcome tracking."""
import datetime as dt

import pytest

from backend.app.models import Student


@pytest.fixture()
def year4_students(db):
    """Two final-year (year=4) test students. Placement logic only evaluates
    year=4 students, and conftest.py's base_data only seeds year=3 students,
    so these are added here rather than in the shared fixture."""
    existing = (db.query(Student)
                  .filter(Student.usn.in_(["4MT22AI901", "4MT22AI902"]))
                  .all())
    if len(existing) < 2:
        db.add_all([
            Student(usn="4MT22AI901", name="Eligible Finalist",
                    dept_code="AIML", year=4, semester=8, section="A",
                    cgpa=8.5, backlogs=0, family_income=300000),
            Student(usn="4MT22AI902", name="Low CGPA Finalist",
                    dept_code="AIML", year=4, semester=8, section="A",
                    cgpa=5.0, backlogs=1, family_income=300000),
        ])
        db.commit()
    return ("4MT22AI901", "4MT22AI902")


def _make_drive(agents, db, **overrides):
    """Builds a test drive with min_attendance=0.0 so hard-filter results
    don't depend on attendance data we haven't uploaded for test students."""
    data = {"company": "TestCo", "role": "SWE", "package_lpa": 8.0,
            "min_cgpa": 6.0, "max_backlogs": 0, "min_attendance": 0.0,
            "drive_date": dt.date.today() + dt.timedelta(days=30),
            "departments": "ALL", "status": "OPEN",
            "requires_fee_clearance": False}
    data.update(overrides)
    return agents["placement_agent"].create_drive(db, data)


def test_create_drive_rejects_negative_cgpa(agents, db):
    with pytest.raises(ValueError):
        agents["placement_agent"].create_drive(db, {
            "company": "BadCo", "role": "X", "package_lpa": 5,
            "drive_date": dt.date.today() + dt.timedelta(days=10),
            "min_cgpa": -1,
        })


def test_create_drive_rejects_missing_required_fields(agents, db):
    with pytest.raises(ValueError):
        agents["placement_agent"].create_drive(db, {"company": "BadCo"})


def test_shortlist_generation_is_idempotent(agents, db, year4_students):
    drive = _make_drive(agents, db, company="IdemCo")
    result = agents["placement_agent"].generate_shortlist(db, drive.id)
    assert result["candidates_evaluated"] >= 2

    # Re-running without regenerate=True must be rejected
    with pytest.raises(PermissionError):
        agents["placement_agent"].generate_shortlist(db, drive.id)

    # regenerate=True must be allowed
    result2 = agents["placement_agent"].generate_shortlist(
        db, drive.id, regenerate=True)
    assert result2["drive_id"] == drive.id


def test_shortlist_reflects_hard_filter(agents, db, year4_students):
    eligible_usn, ineligible_usn = year4_students
    drive = _make_drive(agents, db, company="FilterCo", min_cgpa=6.0)
    agents["placement_agent"].generate_shortlist(db, drive.id)

    shortlist = {e["usn"]: e for e in
                 agents["placement_agent"].get_shortlist(db, drive.id)}
    assert shortlist[eligible_usn]["eligible"] is True
    assert shortlist[ineligible_usn]["eligible"] is False
    assert any("CGPA" in r for r in shortlist[ineligible_usn]["reasons"])


def test_outcome_blocks_second_accepted_offer(agents, db, year4_students):
    usn, _ = year4_students
    drive_a = _make_drive(agents, db, company="OfferCo A")
    drive_b = _make_drive(agents, db, company="OfferCo B")

    agents["placement_agent"].record_outcome(db, drive_a.id, usn,
                                             "OFFER_ACCEPTED")
    with pytest.raises(PermissionError):
        agents["placement_agent"].record_outcome(db, drive_b.id, usn,
                                                 "OFFER_ACCEPTED")

    # allow_multiple_offers=True should override the block
    outcome = agents["placement_agent"].record_outcome(
        db, drive_b.id, usn, "OFFER_ACCEPTED", allow_multiple_offers=True)
    assert outcome.outcome_status == "OFFER_ACCEPTED"
