"""Placement Agent — final-year drive eligibility (dept + criteria filters)
with calibrated Random Forest success-probability ranking."""
import datetime as dt

import joblib

from .. import config
from ..models import PlacementDrive, PlacementShortlist, Student
from .attendance import overall_percentage
from .base import BaseAgent

_MODEL_PATH = config.ML_MODELS_DIR / "placement_rf.joblib"


class PlacementAgent(BaseAgent):
    name = "placement_agent"
    description = "Final-year drive eligibility + Random Forest ranking"

    def __init__(self, bus):
        super().__init__(bus)
        self.model = None
        if _MODEL_PATH.exists():
            # Safe: artifact produced locally by ml/train.py in this repo.
            self.model = joblib.load(_MODEL_PATH)

    def register_subscriptions(self):
        self.bus.subscribe("attendance.updated", self.name, self.on_upstream_change)

    async def on_upstream_change(self, payload: dict):
        updates = payload.get("updates", payload.get("usns", []))
        db = self.session()
        try:
            drives = self._upcoming_drives(db)
            changed = 0
            for u in updates:
                usn = u["usn"] if isinstance(u, dict) else u
                att = u.get("overall_percentage") if isinstance(u, dict) else None
                changed += self.evaluate_student(db, usn, drives=drives,
                                                 attendance=att)
            db.commit()
        finally:
            db.close()
        usns = [u["usn"] if isinstance(u, dict) else u for u in updates]
        await self.publish("placement.updated", {
            "workflow_id": payload["workflow_id"],
            "_hop": payload.get("_hop", 1),
            "usns": usns, "entries_updated": changed})

    def _upcoming_drives(self, db):
        cutoff = dt.date.today() - dt.timedelta(days=7)
        return (db.query(PlacementDrive)
                  .filter(PlacementDrive.drive_date >= cutoff)
                  .order_by(PlacementDrive.drive_date).all())

    def _drive_evaluation(self, student, drive, attendance: float) -> tuple[bool, float | None, str]:
        """Calculate one shortlist result without changing ORM state."""
        prob = None
        if self.model is not None:
            prob = float(self.model.predict_proba(
                [[student.cgpa, student.backlogs, attendance]])[0][1])
        reasons = []
        allowed = (drive.departments == "ALL"
                   or student.dept_code in drive.departments.split(","))
        if not allowed:
            reasons.append(f"drive not open to {student.dept_code}")
        if student.cgpa < drive.min_cgpa:
            reasons.append(f"CGPA {student.cgpa} < required {drive.min_cgpa}")
        if student.backlogs > drive.max_backlogs:
            reasons.append(f"{student.backlogs} backlogs > allowed {drive.max_backlogs}")
        if attendance < drive.min_attendance:
            reasons.append(f"attendance {attendance}% < {drive.min_attendance}%")
        eligible = not reasons
        if eligible:
            reasons.append("meets all drive criteria")
        return eligible, prob if eligible else None, "; ".join(reasons)

    def evaluate_student(self, db, usn: str, drives=None,
                         attendance: float | None = None) -> int:
        student = db.get(Student, usn)
        if student is None or student.year != 4:   # placements = final years
            return 0
        if attendance is None:
            attendance = overall_percentage(db, usn)
        if drives is None:
            drives = self._upcoming_drives(db)
        existing = {e.drive_id: e for e in
                    db.query(PlacementShortlist).filter_by(usn=usn).all()}
        changed = 0
        for drive in drives:
            eligible, probability, reasons = self._drive_evaluation(
                student, drive, attendance)
            entry = existing.get(drive.id)
            if entry is None:
                entry = PlacementShortlist(drive_id=drive.id, usn=usn,
                                           eligible=eligible)
                db.add(entry)
            entry.eligible = eligible
            entry.ml_probability = probability
            entry.reasons = reasons
            changed += 1
        return changed

    def student_view(self, db, usn: str) -> list[dict]:
        student = db.get(Student, usn)
        if student is None:
            return []
        drives = self._upcoming_drives(db)
        entries = {e.drive_id: e for e in
                   db.query(PlacementShortlist).filter_by(usn=usn).all()}
        calculated = {}
        if student.year == 4:
            attendance = overall_percentage(db, usn)
            calculated = {drive.id: self._drive_evaluation(student, drive, attendance)
                          for drive in drives}
        out = []
        for d in drives[:15]:
            e = entries.get(d.id)
            if d.id in calculated:
                eligible, probability, reasons = calculated[d.id]
            else:
                eligible = bool(e and e.eligible)
                probability = e.ml_probability if e else None
                reasons = e.reasons if e else \
                    ("placements open in final year" if student.year != 4 else "")
            out.append({"company": d.company, "role": d.role,
                        "package_lpa": d.package_lpa, "date": str(d.drive_date),
                        "departments": d.departments,
                        "eligible": eligible, "probability": probability,
                        "reasons": reasons})
        return out

    def stats(self, db) -> dict:
        from sqlalchemy import func
        eligible = (db.query(Student.dept_code,
                             func.count(func.distinct(PlacementShortlist.usn)))
                      .join(PlacementShortlist,
                            PlacementShortlist.usn == Student.usn)
                      .filter(PlacementShortlist.eligible.is_(True))
                      .group_by(Student.dept_code).all())
        return {"upcoming_drives": len(self._upcoming_drives(db)),
                "eligible_finalists_by_dept": {d: c for d, c in eligible}}
