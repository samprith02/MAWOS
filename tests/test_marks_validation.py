"""Atomic validation for faculty CIE marks sheets."""
from fastapi.testclient import TestClient

from backend.app.auth import hash_password
from backend.app.main import app
from backend.app.models import Faculty, MarksRecord, User

USN_ONE = "4MT23AI001"
USN_TWO = "4MT23AI002"
SUBJECT = "23AI51"


def _headers(db, username="marks.faculty"):
    faculty = db.query(Faculty).filter_by(name="Test Prof").first()
    if username == "marks.unassigned":
        faculty = db.query(Faculty).filter_by(name="Unassigned Marks Faculty").first()
        if faculty is None:
            faculty = Faculty(name="Unassigned Marks Faculty", dept_code="AIML")
            db.add(faculty)
            db.flush()
    if db.query(User).filter_by(username=username).first() is None:
        db.add(User(username=username, password_hash=hash_password("x"),
                    role="faculty", display_name="Marks Faculty",
                    faculty_id=faculty.id, dept_code="AIML"))
        db.commit()
    token = TestClient(app).post("/api/auth/login", json={
        "username": username, "password": "x"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _clear_internal(db, internal):
    db.query(MarksRecord).filter(
        MarksRecord.usn.in_([USN_ONE, USN_TWO]),
        MarksRecord.subject_code == SUBJECT,
        MarksRecord.internal == internal,
    ).delete(synchronize_session=False)
    db.commit()


def _post_marks(db, payload, username="marks.faculty"):
    return TestClient(app).post("/api/faculty/marks", json=payload,
                                headers=_headers(db, username))


def test_marks_policy_exposes_the_cie_maximum(db):
    response = TestClient(app).get("/api/faculty/marks-policy",
                                   headers=_headers(db))

    assert response.status_code == 200
    assert response.json()["assessments"] == [
        {"internal": 1, "label": "CIE-1", "max_marks": 50.0},
        {"internal": 2, "label": "CIE-2", "max_marks": 50.0},
        {"internal": 3, "label": "CIE-3", "max_marks": 50.0},
    ]


def test_missing_mark_rejects_the_complete_sheet(db):
    _clear_internal(db, 1)
    response = _post_marks(db, {"subject_code": SUBJECT, "internal": 1,
                                 "entries": [{"usn": USN_ONE}]})

    assert response.status_code == 422
    assert db.query(MarksRecord).filter_by(
        usn=USN_ONE, subject_code=SUBJECT, internal=1).first() is None


def test_null_mark_rejects_the_complete_sheet(db):
    _clear_internal(db, 1)
    response = _post_marks(db, {"subject_code": SUBJECT, "internal": 1,
                                 "entries": [{"usn": USN_ONE, "marks": None}]})

    assert response.status_code == 422
    assert db.query(MarksRecord).filter_by(
        usn=USN_ONE, subject_code=SUBJECT, internal=1).first() is None


def test_explicit_zero_mark_is_accepted(db):
    _clear_internal(db, 1)
    response = _post_marks(db, {"subject_code": SUBJECT, "internal": 1,
                                 "entries": [{"usn": USN_ONE, "marks": 0}]})

    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "rejected": []}
    assert db.query(MarksRecord).filter_by(
        usn=USN_ONE, subject_code=SUBJECT, internal=1).first().marks == 0


def test_negative_and_excessive_marks_are_rejected(db):
    for mark in (-1, 51):
        _clear_internal(db, 1)
        response = _post_marks(db, {"subject_code": SUBJECT, "internal": 1,
                                     "entries": [{"usn": USN_ONE, "marks": mark}]})
        assert response.status_code == 422
        assert db.query(MarksRecord).filter_by(
            usn=USN_ONE, subject_code=SUBJECT, internal=1).first() is None


def test_invalid_row_writes_nothing_and_preserves_existing_marks(db):
    _clear_internal(db, 2)
    db.add(MarksRecord(usn=USN_ONE, subject_code=SUBJECT, internal=2,
                       marks=17, entered_by="seed"))
    db.commit()

    response = _post_marks(db, {"subject_code": SUBJECT, "internal": 2,
                                 "entries": [
                                     {"usn": USN_ONE, "marks": 45},
                                     {"usn": USN_TWO, "marks": -1},
                                 ]})

    assert response.status_code == 422
    db.expire_all()
    existing = db.query(MarksRecord).filter_by(
        usn=USN_ONE, subject_code=SUBJECT, internal=2).first()
    assert existing.marks == 17
    assert existing.entered_by == "seed"
    assert db.query(MarksRecord).filter_by(
        usn=USN_TWO, subject_code=SUBJECT, internal=2).first() is None


def test_duplicate_student_rejects_the_complete_sheet(db):
    _clear_internal(db, 3)
    response = _post_marks(db, {"subject_code": SUBJECT, "internal": 3,
                                 "entries": [
                                     {"usn": USN_ONE, "marks": 20},
                                     {"usn": USN_ONE, "marks": 30},
                                 ]})

    assert response.status_code == 422
    assert db.query(MarksRecord).filter_by(
        usn=USN_ONE, subject_code=SUBJECT, internal=3).first() is None


def test_fully_valid_marks_sheet_is_accepted(db):
    _clear_internal(db, 3)
    response = _post_marks(db, {"subject_code": SUBJECT, "internal": 3,
                                 "entries": [
                                     {"usn": USN_ONE, "marks": 12},
                                     {"usn": USN_TWO, "marks": 48},
                                 ]})

    assert response.status_code == 200
    assert response.json() == {"accepted": 2, "rejected": []}
    written = {row.usn: row.marks for row in db.query(MarksRecord).filter_by(
        subject_code=SUBJECT, internal=3).all()}
    assert written[USN_ONE] == 12
    assert written[USN_TWO] == 48


def test_unassigned_faculty_cannot_submit_marks(db):
    response = _post_marks(db, {"subject_code": SUBJECT, "internal": 1,
                                 "entries": [{"usn": USN_ONE, "marks": 25}]},
                           username="marks.unassigned")

    assert response.status_code == 403
