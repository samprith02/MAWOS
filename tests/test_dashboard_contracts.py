"""API contracts consumed by the Principal and Admin React dashboards."""
from fastapi.testclient import TestClient

from backend.app.auth import hash_password
from backend.app.main import app
from backend.app.models import Department, Faculty, Student, User


def _headers(db, role: str) -> dict[str, str]:
    username = f"dashboard.{role}"
    if db.query(User).filter_by(username=username).first() is None:
        db.add(User(username=username, password_hash=hash_password("x"),
                    role=role, display_name=f"Dashboard {role.title()}"))
        db.commit()
    token = TestClient(app).post("/api/auth/login", json={
        "username": username, "password": "x"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _add_cse_department(db):
    if db.get(Department, "CSE") is None:
        db.add(Department(code="CSE", name="Computer Science", intake=2))
        db.add(Faculty(name="CSE Dashboard Faculty", dept_code="CSE"))
        db.add(Student(usn="4MT23CS950", name="CSE Dashboard Student",
                       dept_code="CSE", year=3, semester=5, section="A",
                       cgpa=8.0, backlogs=0, family_income=300000))
        db.commit()


def test_principal_analytics_contract_has_department_rows_for_multiple_departments(db):
    _add_cse_department(db)
    response = TestClient(app).get("/api/principal/analytics",
                                   headers=_headers(db, "principal"))

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["departments"], list)
    assert {row["dept"] for row in payload["departments"]} >= {"AIML", "CSE"}
    assert all({"dept", "students", "faculty", "shortage_students",
                "avg_attendance", "avg_cgpa", "by_year"} <= row.keys()
               for row in payload["departments"])
    assert {"total_due", "total_collected", "total_outstanding", "by_department"} <= payload["fee_collection"].keys()
    assert {"upcoming_drives", "eligible_finalists", "eligible_finalists_by_dept"} <= payload["placements"].keys()
    assert {"stages", "departments"} <= payload["admissions"].keys()


def test_principal_analytics_contract_allows_no_departments(db, agents, monkeypatch):
    monkeypatch.setattr(agents["academic_agent"], "institution_analytics",
                        lambda _db: {})
    response = TestClient(app).get("/api/principal/analytics",
                                   headers=_headers(db, "principal"))

    assert response.status_code == 200
    assert response.json()["departments"] == []


def test_admin_admissions_contract_uses_descriptive_application_fields(db):
    response = TestClient(app).get("/api/admin/admissions",
                                   headers=_headers(db, "admin"))

    assert response.status_code == 200
    payload = response.json()
    assert {"stages", "departments"} <= payload["funnel"].keys()
    application = payload["applications"][0]
    assert {"applicant_name", "dept_code", "entrance_score", "status",
            "tenth_pct", "twelfth_pct", "allotted_usn"} <= application.keys()
    assert "name" not in application
    assert "dept" not in application
    assert "entrance" not in application
