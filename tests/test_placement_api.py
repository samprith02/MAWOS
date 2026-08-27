"""API-layer tests for Placement Agent endpoints — role gating and
per-student access restrictions, exercised over real HTTP requests via a
lightweight FastAPI app that mounts only the placement router. This avoids
running main.py's full startup (seed_all(), timetable generation), which
would seed the full synthetic dataset into the isolated test DB."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.placement import router as placement_router
from backend.app.auth import create_token, hash_password
from backend.app.models import User

_test_app = FastAPI()
_test_app.include_router(placement_router)
client = TestClient(_test_app)


@pytest.fixture()
def admin_token(db):
    user = db.query(User).filter_by(username="placement_admin_test").first()
    if user is None:
        user = User(username="placement_admin_test",
                    password_hash=hash_password("x"), role="admin",
                    display_name="Placement Admin Test")
        db.add(user)
        db.commit()
        db.refresh(user)
    return create_token(user)


@pytest.fixture()
def student1_token(db):
    user = db.query(User).filter_by(username="4MT23AI001").first()
    return create_token(user)


def test_non_admin_cannot_create_drive(student1_token):
    response = client.post(
        "/api/placement/drives",
        json={"company": "TestCorp", "role": "SDE", "package_lpa": 10,
              "drive_date": "2026-12-01"},
        headers={"Authorization": f"Bearer {student1_token}"},
    )
    assert response.status_code == 403


def test_admin_can_create_drive(admin_token):
    response = client.post(
        "/api/placement/drives",
        json={"company": "AdminCorp", "role": "SDE", "package_lpa": 10,
              "drive_date": "2026-12-01"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201


def test_student_cannot_view_another_students_eligibility(student1_token):
    response = client.get(
        "/api/placement/drives/1/candidates/4MT23AI002/eligibility",
        headers={"Authorization": f"Bearer {student1_token}"},
    )
    assert response.status_code == 403


def test_student_can_view_own_eligibility(student1_token):
    # drive_id doesn't need to exist for this check — the 403/self-access
    # gate runs before any drive lookup, so a 404 here (not 403) proves the
    # student was allowed through as themselves.
    response = client.get(
        "/api/placement/drives/999999/candidates/4MT23AI001/eligibility",
        headers={"Authorization": f"Bearer {student1_token}"},
    )
    assert response.status_code != 403
