"""Placement Agent — company drive management, rule-based hard filter +
calibrated Random Forest ranking, idempotent shortlist generation, and
placement outcome tracking (offers/selections)."""
import datetime as dt

import joblib

from .. import config
from ..models import PlacementDrive, PlacementOutcome, PlacementShortlist, Student
from .attendance import overall_percentage
from .finance import fees_cleared
from .base import BaseAgent

_MODEL_PATH = config.ML_MODELS_DIR / "placement_rf.joblib"

# Outcome statuses that mean "this drive/student pair is finalized" —
# once set, automatic recalculation must not silently overwrite it.
_FINALIZED_OUTCOMES = {"OFFER_ACCEPTED", "OFFER_DECLINED", "REJECTED"}

DRIVE_STATUSES = {"DRAFT", "OPEN", "SHORTLIST_GENERATED", "CLOSED", "CANCELLED"}
OUTCOME_STATUSES = {"OFFER_MADE", "OFFER_ACCEPTED", "OFFER_DECLINED", "REJECTED"}


class PlacementAgent(BaseAgent):
    name = "placement_agent"
    description = ("Company drive management, rule-based hard filter + Random "
                    "Forest ranking, shortlist generation, outcome tracking")

    def __init__(self, bus):
        super().__init__(bus)
        self.model = None
        if _MODEL_PATH.exists():
            # Safe: artifact produced locally by ml/train.py in this repo.
            self.model = joblib.load(_MODEL_PATH)

    def register_subscriptions(self):
        self.bus.subscribe("attendance.updated", self.name, self.on_upstream_change)
        self.bus.subscribe("fees.updated", self.name, self.on_upstream_change)

    # ---------- upstream event handling -------------------------------------
    async def on_upstream_change(self, payload: dict):
        updates = payload.get("updates", payload.get("usns", []))
        db = self.session()
        try:
            drives = self._active_drives(db)
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

    def _active_drives(self, db):
        """Drives still worth evaluating candidates against: OPEN or
        SHORTLIST_GENERATED (re-eval keeps snapshots fresh), not CLOSED/CANCELLED."""
        cutoff = dt.date.today() - dt.timedelta(days=7)
        return (db.query(PlacementDrive)
                  .filter(PlacementDrive.drive_date >= cutoff,
                         PlacementDrive.status.in_(["OPEN", "SHORTLIST_GENERATED"]))
                  .order_by(PlacementDrive.drive_date).all())

    # ---------- eligibility (hard filter + ML) -------------------------------
    def _hard_filter(self, db, student: Student, drive: PlacementDrive,
                     attendance: float) -> list[str]:
        reasons = []
        allowed = (drive.departments == "ALL"
                   or student.dept_code in drive.departments.split(","))
        if not allowed:
            reasons.append(f"Branch {student.dept_code} not in eligible list "
                          f"({drive.departments})")
        if student.cgpa < drive.min_cgpa:
            reasons.append(f"CGPA {student.cgpa} below cutoff of {drive.min_cgpa}")
        if student.backlogs > drive.max_backlogs:
            reasons.append(f"{student.backlogs} active backlog(s) exceeds "
                          f"limit of {drive.max_backlogs}")
        if attendance < drive.min_attendance:
            reasons.append(f"Attendance {attendance}% below requirement of "
                          f"{drive.min_attendance}%")
        if drive.requires_fee_clearance and not fees_cleared(db, student.usn):
            reasons.append("Outstanding fee dues; this drive requires fee clearance")
        return reasons

    def evaluate_student(self, db, usn: str, drives=None,
                         attendance: float | None = None) -> int:
        """Re-evaluate one student against all active drives. Skips any
        drive/student pair that already has a finalized outcome."""
        student = db.get(Student, usn)
        if student is None or student.year != 4:   # placements = final years
            return 0
        if attendance is None:
            attendance = overall_percentage(db, usn)
        if drives is None:
            drives = self._active_drives(db)

        finalized_drive_ids = {
            o.drive_id for o in db.query(PlacementOutcome)
            .filter_by(usn=usn)
            .filter(PlacementOutcome.outcome_status.in_(_FINALIZED_OUTCOMES)).all()
        }
        existing = {e.drive_id: e for e in
                    db.query(PlacementShortlist).filter_by(usn=usn).all()}
        changed = 0
        for drive in drives:
            if drive.id in finalized_drive_ids:
                continue  # never rewrite a finalized decision
            reasons = self._hard_filter(db, student, drive, attendance)
            hard_passed = not reasons
            prob = None
            if hard_passed:
                if self.model is not None:
                    prob = float(self.model.predict_proba(
                        [[student.cgpa, student.backlogs, attendance]])[0][1])
                    if prob >= config.PLACEMENT_ML_THRESHOLD:
                        reasons.append(
                            f"Model confidence {prob:.2f} meets threshold "
                            f"{config.PLACEMENT_ML_THRESHOLD}")
                        eligible = True
                    else:
                        reasons.append(
                            f"Model confidence {prob:.2f} below threshold "
                            f"{config.PLACEMENT_ML_THRESHOLD}")
                        eligible = False
                else:
                    reasons.append("Meets all drive criteria (model unavailable, "
                                  "rules-only evaluation)")
                    eligible = True
            else:
                eligible = False

            entry = existing.get(drive.id)
            if entry is None:
                entry = PlacementShortlist(drive_id=drive.id, usn=usn,
                                           eligible=eligible)
                db.add(entry)
            entry.eligible = eligible
            entry.ml_probability = prob
            entry.reasons = "; ".join(reasons)
            entry.model_version = (config.PLACEMENT_MODEL_VERSION
                                   if self.model is not None else None)
            changed += 1
        return changed

    # ---------- drive CRUD ----------------------------------------------------
    def create_drive(self, db, data: dict) -> PlacementDrive:
        required = ["company", "role", "package_lpa", "drive_date"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        if data.get("min_cgpa", 0) < 0 or data.get("min_cgpa", 0) > 10:
            raise ValueError("min_cgpa must be between 0 and 10")
        if data.get("max_backlogs", 0) < 0:
            raise ValueError("max_backlogs cannot be negative")
        drive = PlacementDrive(
            company=data["company"], role=data["role"],
            package_lpa=data["package_lpa"],
            min_cgpa=data.get("min_cgpa", 6.0),
            max_backlogs=data.get("max_backlogs", 0),
            min_attendance=data.get("min_attendance", 75.0),
            drive_date=data["drive_date"],
            departments=data.get("departments", "ALL"),
            status=data.get("status", "OPEN"),
            requires_fee_clearance=data.get("requires_fee_clearance", False),
            application_deadline=data.get("application_deadline"),
        )
        db.add(drive)
        db.commit()
        db.refresh(drive)
        return drive

    def update_drive(self, db, drive_id: int, data: dict) -> PlacementDrive:
        drive = db.get(PlacementDrive, drive_id)
        if drive is None:
            raise LookupError("Drive not found")
        for field in ("company", "role", "package_lpa", "min_cgpa",
                      "max_backlogs", "min_attendance", "drive_date",
                      "departments", "requires_fee_clearance",
                      "application_deadline"):
            if field in data and data[field] is not None:
                setattr(drive, field, data[field])
        db.commit()
        db.refresh(drive)
        return drive

    def close_drive(self, db, drive_id: int) -> PlacementDrive:
        drive = db.get(PlacementDrive, drive_id)
        if drive is None:
            raise LookupError("Drive not found")
        drive.status = "CLOSED"
        db.commit()
        db.refresh(drive)
        return drive

    def list_drives(self, db, status: str | None = None) -> list[PlacementDrive]:
        q = db.query(PlacementDrive)
        if status:
            q = q.filter(PlacementDrive.status == status.upper())
        return q.order_by(PlacementDrive.drive_date).all()

    def get_drive(self, db, drive_id: int) -> PlacementDrive | None:
        return db.get(PlacementDrive, drive_id)

    # ---------- shortlist generation (batch, idempotent) ----------------------
    def generate_shortlist(self, db, drive_id: int,
                           regenerate: bool = False) -> dict:
        """Runs hard filter + ML scoring for every final-year candidate in the
        drive's eligible branches, persists the shortlist, and marks the drive
        SHORTLIST_GENERATED. Rejects re-running unless regenerate=True."""
        drive = db.get(PlacementDrive, drive_id)
        if drive is None:
            raise LookupError("Drive not found")
        if drive.status not in ("OPEN", "SHORTLIST_GENERATED"):
            raise ValueError(f"Drive is not open for shortlisting "
                            f"(status: {drive.status})")
        if drive.status == "SHORTLIST_GENERATED" and not regenerate:
            raise PermissionError(
                "Shortlist already generated for this drive. "
                "Pass regenerate=True to supersede it.")

        q = db.query(Student).filter(Student.year == 4)
        if drive.departments != "ALL":
            q = q.filter(Student.dept_code.in_(drive.departments.split(",")))
        candidates = q.all()

        shortlisted_count = 0
        for student in candidates:
            attendance = overall_percentage(db, student.usn)
            reasons = self._hard_filter(db, student, drive, attendance)
            hard_passed = not reasons
            prob = None
            eligible = False
            if hard_passed:
                if self.model is not None:
                    prob = float(self.model.predict_proba(
                        [[student.cgpa, student.backlogs, attendance]])[0][1])
                    eligible = prob >= config.PLACEMENT_ML_THRESHOLD
                    reasons.append(
                        f"Model confidence {prob:.2f} "
                        f"{'meets' if eligible else 'below'} threshold "
                        f"{config.PLACEMENT_ML_THRESHOLD}")
                else:
                    eligible = True
                    reasons.append("Meets all drive criteria (model unavailable, "
                                  "rules-only evaluation)")
            entry = (db.query(PlacementShortlist)
                       .filter_by(drive_id=drive.id, usn=student.usn).first())
            if entry is None:
                entry = PlacementShortlist(drive_id=drive.id, usn=student.usn,
                                           eligible=eligible)
                db.add(entry)
            entry.eligible = eligible
            entry.ml_probability = prob
            entry.reasons = "; ".join(reasons)
            entry.model_version = (config.PLACEMENT_MODEL_VERSION
                                   if self.model is not None else None)
            if eligible:
                shortlisted_count += 1

        drive.status = "SHORTLIST_GENERATED"
        db.commit()

        return {"drive_id": drive.id, "company": drive.company,
                "candidates_evaluated": len(candidates),
                "shortlisted_count": shortlisted_count,
                "model_version": (config.PLACEMENT_MODEL_VERSION
                                  if self.model is not None else None)}

    async def generate_shortlist_and_announce(self, db, drive_id: int,
                                              regenerate: bool = False) -> dict:
        """Like generate_shortlist, but also publishes the shortlist_generated
        event and a notification_required event per shortlisted student."""
        result = self.generate_shortlist(db, drive_id, regenerate=regenerate)
        workflow_id = await self.publish("placement.shortlist_generated", {
            "drive_id": result["drive_id"],
            "data": {"company": result["company"],
                     "shortlisted_count": result["shortlisted_count"],
                     "model_version": result["model_version"]}})
        shortlisted = (db.query(PlacementShortlist)
                         .filter_by(drive_id=drive_id, eligible=True).all())
        for entry in shortlisted:
            await self.publish("placement.notification_required", {
                "workflow_id": workflow_id,
                "student_id": entry.usn,
                "data": {"notification_type": "PLACEMENT_SHORTLISTED",
                         "message_template": "PLACEMENT_SHORTLIST_RESULT",
                         "metadata": {"drive_id": drive_id}}})
        return result

    def get_shortlist(self, db, drive_id: int) -> list[dict]:
        entries = (db.query(PlacementShortlist)
                     .filter_by(drive_id=drive_id).all())
        return [{"usn": e.usn, "eligible": e.eligible,
                "ml_probability": e.ml_probability,
                "model_version": e.model_version,
                "reasons": e.reasons.split("; ") if e.reasons else []}
               for e in entries]

    def get_eligibility(self, db, drive_id: int, usn: str) -> dict:
        """Explainability endpoint payload for one student/drive pair."""
        drive = db.get(PlacementDrive, drive_id)
        if drive is None:
            raise LookupError("Drive not found")
        student = db.get(Student, usn)
        if student is None:
            raise LookupError("Student not found")
        entry = (db.query(PlacementShortlist)
                   .filter_by(drive_id=drive_id, usn=usn).first())
        if entry is None:
            # Evaluate on the fly if it hasn't been computed yet.
            attendance = overall_percentage(db, usn)
            reasons = self._hard_filter(db, student, drive, attendance)
            return {"usn": usn, "drive_id": drive_id,
                    "hard_filter_passed": not reasons, "ml_eligible": False,
                    "ml_score": None, "final_status": "NOT_EVALUATED",
                    "reasons": reasons or ["Not yet evaluated"]}
        outcome = (db.query(PlacementOutcome)
                     .filter_by(drive_id=drive_id, usn=usn).first())
        final_status = (outcome.outcome_status if outcome else
                        ("SHORTLISTED" if entry.eligible else "NOT_ELIGIBLE"))
        return {"usn": usn, "drive_id": drive_id,
                "hard_filter_passed": entry.eligible or bool(entry.ml_probability),
                "ml_eligible": entry.eligible, "ml_score": entry.ml_probability,
                "model_version": entry.model_version,
                "final_status": final_status,
                "reasons": entry.reasons.split("; ") if entry.reasons else []}

    # ---------- outcome tracking -----------------------------------------------
    def record_outcome(self, db, drive_id: int, usn: str, outcome_status: str,
                       package_offered: float | None = None,
                       allow_multiple_offers: bool = False) -> PlacementOutcome:
        if outcome_status not in OUTCOME_STATUSES:
            raise ValueError(f"Invalid outcome_status. Must be one of "
                            f"{sorted(OUTCOME_STATUSES)}")
        drive = db.get(PlacementDrive, drive_id)
        if drive is None:
            raise LookupError("Drive not found")
        student = db.get(Student, usn)
        if student is None:
            raise LookupError("Student not found")

        if outcome_status == "OFFER_ACCEPTED" and not allow_multiple_offers:
            already_placed = (db.query(PlacementOutcome)
                                 .filter(PlacementOutcome.usn == usn,
                                        PlacementOutcome.outcome_status == "OFFER_ACCEPTED",
                                        PlacementOutcome.drive_id != drive_id)
                                 .first())
            if already_placed is not None:
                raise PermissionError(
                    f"Student {usn} has already accepted an offer for drive "
                    f"{already_placed.drive_id}; multiple offers are not enabled")

        outcome = (db.query(PlacementOutcome)
                     .filter_by(drive_id=drive_id, usn=usn).first())
        if outcome is None:
            outcome = PlacementOutcome(drive_id=drive_id, usn=usn,
                                       outcome_status=outcome_status)
            db.add(outcome)
        outcome.outcome_status = outcome_status
        if package_offered is not None:
            outcome.package_offered = package_offered
        db.commit()
        db.refresh(outcome)
        return outcome

    async def record_outcome_and_announce(self, db, drive_id: int, usn: str,
                                          outcome_status: str,
                                          package_offered: float | None = None,
                                          allow_multiple_offers: bool = False) -> dict:
        outcome = self.record_outcome(db, drive_id, usn, outcome_status,
                                      package_offered, allow_multiple_offers)
        topic = {"OFFER_MADE": "placement.offer_made",
                 "OFFER_ACCEPTED": "placement.offer_accepted",
                 "OFFER_DECLINED": "placement.offer_declined",
                 "REJECTED": "placement.rejected"}[outcome_status]
        await self.publish(topic, {
            "drive_id": drive_id, "student_id": usn,
            "data": {"outcome_status": outcome_status,
                     "package_offered": package_offered}})
        return {"drive_id": outcome.drive_id, "usn": outcome.usn,
                "outcome_status": outcome.outcome_status,
                "package_offered": outcome.package_offered}

    def get_outcomes(self, db, drive_id: int) -> list[dict]:
        outcomes = db.query(PlacementOutcome).filter_by(drive_id=drive_id).all()
        return [{"usn": o.usn, "outcome_status": o.outcome_status,
                "package_offered": o.package_offered,
                "decided_at": str(o.decided_at)} for o in outcomes]

    # ---------- student-facing / dashboard views --------------------------------
    def student_view(self, db, usn: str) -> list[dict]:
        student = db.get(Student, usn)
        if student is None:
            return []
        if student.year == 4:
            self.evaluate_student(db, usn)
            db.commit()
        entries = {e.drive_id: e for e in
                   db.query(PlacementShortlist).filter_by(usn=usn).all()}
        out = []
        for d in self._active_drives(db)[:15]:
            e = entries.get(d.id)
            out.append({"company": d.company, "role": d.role,
                        "package_lpa": d.package_lpa, "date": str(d.drive_date),
                        "departments": d.departments, "status": d.status,
                        "eligible": bool(e and e.eligible),
                        "probability": e.ml_probability if e else None,
                        "reasons": e.reasons if e else
                        ("placements open in final year" if student.year != 4 else "")})
        return out

    def stats(self, db) -> dict:
        from sqlalchemy import func
        eligible = (db.query(Student.dept_code,
                             func.count(func.distinct(PlacementShortlist.usn)))
                      .join(PlacementShortlist,
                            PlacementShortlist.usn == Student.usn)
                      .filter(PlacementShortlist.eligible.is_(True))
                      .group_by(Student.dept_code).all())
        return {"upcoming_drives": len(self._active_drives(db)),
                "eligible_finalists_by_dept": {d: c for d, c in eligible}}