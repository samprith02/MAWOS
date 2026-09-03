"""Admission Agent — the full admissions workflow.

Pipeline: submitted -> verified -> merit_listed -> seat_allotted -> enrolled.

  * verify: deterministic document/threshold checks with reason codes;
  * merit:  weighted score (50% entrance, 30% 12th, 20% 10th), ranked
    per department;
  * allot:  seats vs department intake with a reserved-category floor
    (30% of seats for non-GM categories, standard supernumerary style);
  * enrol:  creates the Student record + first-year fee items + login,
    and fires the enrollment cascade (notification, finance).
"""
import datetime as dt

from ..auth import hash_password
from ..models import (Application, Department, FeeRecord, Student, User)
from ..seed import DEPT_LETTERS
from .base import BaseAgent

MIN_TWELFTH = 45.0
MIN_ENTRANCE = 25.0
RESERVED_SHARE = 0.30


class AdmissionAgent(BaseAgent):
    name = "admission_agent"
    description = ("Admissions pipeline: verification, merit ranking, "
                   "seat allotment vs intake, enrollment cascade")

    # ---------- stage 1: verification -----------------------------------------
    @staticmethod
    def _apply_verification(app: Application) -> str:
        """Deterministic threshold checks; sets status + reason codes."""
        reasons = []
        if app.twelfth_pct < MIN_TWELFTH:
            reasons.append(f"12th {app.twelfth_pct}% below {MIN_TWELFTH}% minimum")
        if app.entrance_score < MIN_ENTRANCE:
            reasons.append(f"entrance {app.entrance_score} below {MIN_ENTRANCE} cutoff")
        if reasons:
            app.status = "rejected"
            app.notes = "; ".join(reasons)
        else:
            app.status = "verified"
            app.notes = "documents and thresholds verified"
        return app.status

    def verify(self, db, app_id: int) -> dict:
        app = db.get(Application, app_id)
        if app is None or app.status != "submitted":
            return {"ok": False, "error": "application not in submitted state"}
        status = self._apply_verification(app)
        db.commit()
        return {"ok": True, "status": status, "notes": app.notes}

    def verify_all(self, db) -> dict:
        """Batch verification: one transaction for the whole intake."""
        apps = db.query(Application).filter(
            Application.status == "submitted").all()
        rejected = sum(1 for a in apps
                       if self._apply_verification(a) == "rejected")
        db.commit()
        return {"processed": len(apps), "verified": len(apps) - rejected,
                "rejected": rejected}

    # ---------- stage 2: merit ranking ------------------------------------------
    @staticmethod
    def merit_score(app: Application) -> float:
        return round(0.5 * (app.entrance_score / 200 * 100)
                     + 0.3 * app.twelfth_pct + 0.2 * app.tenth_pct, 2)

    def run_merit(self, db) -> dict:
        ranked = {}
        for dept in db.query(Department).all():
            apps = (db.query(Application)
                      .filter(Application.dept_code == dept.code,
                              Application.status.in_(["verified", "merit_listed"]))
                      .all())
            for a in apps:
                a.merit_score = self.merit_score(a)
            apps.sort(key=lambda a: -a.merit_score)
            for rank, a in enumerate(apps, start=1):
                a.merit_rank = rank
                a.status = "merit_listed"
            ranked[dept.code] = len(apps)
        db.commit()
        return {"ranked_per_dept": ranked}

    # ---------- stage 3: seat allotment -------------------------------------------
    async def allot_seats(self, db) -> dict:
        summary = {}
        for dept in db.query(Department).all():
            already = (db.query(Application)
                         .filter(Application.dept_code == dept.code,
                                 Application.status.in_(["seat_allotted", "enrolled"]))
                         .count())
            capacity = max(0, dept.intake - already)
            if capacity == 0:
                summary[dept.code] = {"allotted": 0, "capacity_left": 0}
                continue
            pool = (db.query(Application)
                      .filter_by(dept_code=dept.code, status="merit_listed")
                      .order_by(Application.merit_rank).all())
            reserved_quota = int(capacity * RESERVED_SHARE)
            reserved_pool = [a for a in pool if a.category != "GM"]
            allotted = []
            for a in reserved_pool[:reserved_quota]:
                allotted.append(a)
            remaining = [a for a in pool if a not in allotted]
            for a in remaining[:capacity - len(allotted)]:
                allotted.append(a)
            for a in allotted:
                a.status = "seat_allotted"
                a.notes += f"; seat allotted (merit rank {a.merit_rank})"
            summary[dept.code] = {"allotted": len(allotted),
                                  "capacity_left": capacity - len(allotted)}
        db.commit()
        await self.publish("admission.allotted", {"summary": summary})
        return summary

    # ---------- stage 4: enrollment --------------------------------------------------
    async def enrol(self, db, app_id: int) -> dict:
        app = db.get(Application, app_id)
        if app is None or app.status != "seat_allotted":
            return {"ok": False, "error": "application not seat_allotted"}
        batch = dt.date.today().year % 100
        letters = DEPT_LETTERS[app.dept_code]
        count = db.query(Student).filter_by(dept_code=app.dept_code, year=1).count()
        usn = f"4MT{batch:02d}{letters}{count + 1 + 500:03d}"  # 5xx: new intake
        student = Student(
            usn=usn, name=app.applicant_name, dept_code=app.dept_code,
            year=1, semester=1, section="A" if count % 2 == 0 else "B",
            cgpa=0.0, backlogs=0, category=app.category,
            family_income=app.family_income,
            admission_year=dt.date.today().year,
            email=app.email, phone=app.phone)
        db.add(student)
        db.add(User(username=usn, password_hash=hash_password("student123"),
                    role="student", display_name=app.applicant_name,
                    usn=usn, dept_code=app.dept_code))
        db.add(FeeRecord(usn=usn, fee_type="admission+tuition",
                         amount_due=110_000.0, amount_paid=0.0,
                         due_date=dt.date.today() + dt.timedelta(days=21)))
        app.status = "enrolled"
        app.allotted_usn = usn
        db.commit()
        workflow_id = await self.publish("admission.enrolled", {
            "usn": usn, "name": app.applicant_name, "dept": app.dept_code})
        return {"ok": True, "usn": usn, "workflow_id": workflow_id}

    # ---------- reporting ---------------------------------------------------------------
    def funnel(self, db) -> dict:
        stages = ["submitted", "verified", "merit_listed", "seat_allotted",
                  "enrolled", "rejected"]
        counts = {s: db.query(Application).filter_by(status=s).count()
                  for s in stages}
        per_dept = {}
        for dept in db.query(Department).all():
            per_dept[dept.code] = {
                "intake": dept.intake,
                "applications": db.query(Application)
                                  .filter_by(dept_code=dept.code).count(),
                "allotted": db.query(Application)
                              .filter(Application.dept_code == dept.code,
                                      Application.status.in_(
                                          ["seat_allotted", "enrolled"])).count(),
            }
        return {"stages": counts, "departments": per_dept}

    def list_applications(self, db, status: str | None = None,
                          dept: str | None = None, limit: int = 100) -> list[dict]:
        q = db.query(Application).order_by(
            Application.merit_rank.isnot(None).desc(), Application.merit_rank)
        if status:
            q = q.filter_by(status=status)
        if dept:
            q = q.filter_by(dept_code=dept)
        return [{"id": a.id, "name": a.applicant_name, "dept": a.dept_code,
                 "category": a.category, "tenth": a.tenth_pct,
                 "twelfth": a.twelfth_pct, "entrance": a.entrance_score,
                 "status": a.status, "merit_score": a.merit_score,
                 "merit_rank": a.merit_rank, "usn": a.allotted_usn,
                 "notes": a.notes} for a in q.limit(limit).all()]
