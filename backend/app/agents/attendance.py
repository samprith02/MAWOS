"""Attendance Agent — validated attendance intake, percentage computation,
shortage/streak detection, downstream propagation, and a proactive scan
(the agent acts on its own schedule, not only on request)."""
import datetime as dt

from sqlalchemy import case, func

from .. import config
from ..models import (AttendanceRecord, AttendanceSummary, Student, Subject,
                      TeachingAssignment)
from .base import BaseAgent


def overall_percentage(db, usn: str) -> float:
    held = db.query(func.count(AttendanceRecord.id)).filter(
        AttendanceRecord.usn == usn).scalar() or 0
    if held == 0:
        return 0.0
    attended = db.query(func.count(AttendanceRecord.id)).filter(
        AttendanceRecord.usn == usn, AttendanceRecord.present.is_(True)).scalar() or 0
    return round(100.0 * attended / held, 2)


class AttendanceAgent(BaseAgent):
    name = "attendance_agent"
    description = ("Attendance intake with duplicate prevention, % computation, "
                   "shortage detection, proactive nightly scan")

    def register_subscriptions(self):
        self.bus.subscribe("attendance.uploaded", self.name, self.on_attendance_uploaded)

    # ---------- intake (called by faculty routes, permission-checked there) ----
    async def upload_attendance(self, db, uploaded_by: str, records: list[dict]) -> dict:
        accepted, rejected = [], []
        touched = set()
        for rec in records:
            usn = str(rec.get("usn", "")).upper().strip()
            subject_code = str(rec.get("subject_code", "")).upper().strip()
            try:
                date = dt.date.fromisoformat(str(rec.get("date")))
            except (TypeError, ValueError):
                rejected.append({**rec, "reason": "invalid date"})
                continue
            if db.get(Student, usn) is None:
                rejected.append({**rec, "reason": f"unknown USN {usn}"})
                continue
            if db.get(Subject, subject_code) is None:
                rejected.append({**rec, "reason": f"unknown subject {subject_code}"})
                continue
            if db.query(AttendanceRecord).filter_by(
                    usn=usn, subject_code=subject_code, date=date).first():
                rejected.append({**rec, "reason": "duplicate entry"})
                continue
            db.add(AttendanceRecord(usn=usn, subject_code=subject_code, date=date,
                                    present=bool(rec.get("present", True)),
                                    uploaded_by=uploaded_by))
            accepted.append(rec)
            touched.add(usn)
        db.commit()
        workflow_id = None
        if touched:
            workflow_id = await self.publish("attendance.uploaded", {
                "usns": sorted(touched), "uploaded_by": uploaded_by,
                "count": len(accepted)})
        return {"accepted": len(accepted), "rejected": rejected,
                "workflow_id": workflow_id}

    # ---------- write tool (v5 chat/guard path) ---------------------------------
    def mark(self, db, section: str, subject_code: str, date: str | None,
             absentees: list[str], marked_by: str = "system") -> dict:
        """Synchronous write path for `execute()` (backend/app/agents/tools.py:
        `mark_attendance`). Unlike `upload_attendance` -- the async REST intake
        path that also publishes `attendance.uploaded` for the event cascade --
        this is a single guarded write with no downstream announcement, so it
        stays synchronous and calls `_recompute_student` directly rather than
        duplicating its logic or awaiting the event bus from a sync call site.

        Marks the whole roster present except the named `absentees`, mirroring
        `POST /faculty/attendance` (routes.py `mark_attendance`).
        """
        section = str(section or "").upper().strip()
        subject_code = str(subject_code or "").upper().strip()
        if not section or not subject_code:
            return {"applied": False, "changed": [],
                    "detail": "section and subject_code are required"}
        if db.get(Subject, subject_code) is None:
            return {"applied": False, "changed": [],
                    "detail": f"unknown subject {subject_code}"}
        try:
            day = dt.date.fromisoformat(str(date)) if date else dt.date.today()
        except (TypeError, ValueError):
            return {"applied": False, "changed": [],
                    "detail": f"invalid date {date!r}"}
        ta = (db.query(TeachingAssignment)
                .filter_by(subject_code=subject_code, section=section).first())
        if ta is None:
            return {"applied": False, "changed": [],
                    "detail": f"no teaching assignment for {subject_code}/{section}"}
        roster = db.query(Student).filter_by(dept_code=ta.dept_code, year=ta.year,
                                             section=section).all()
        if not roster:
            return {"applied": False, "changed": [],
                    "detail": f"no students in {ta.dept_code} year {ta.year} "
                              f"section {section}"}
        absent = {str(u).upper().strip() for u in (absentees or [])}
        touched = set()
        for s in roster:
            if db.query(AttendanceRecord).filter_by(
                    usn=s.usn, subject_code=subject_code, date=day).first():
                continue  # duplicate prevention, matches upload_attendance
            db.add(AttendanceRecord(usn=s.usn, subject_code=subject_code, date=day,
                                    present=s.usn not in absent,
                                    uploaded_by=marked_by))
            touched.add(s.usn)
        if not touched:
            return {"applied": False, "changed": [],
                    "detail": "attendance already recorded for every roster "
                              "student on this date"}
        changed = [self._recompute_student(db, usn) for usn in sorted(touched)]
        db.commit()
        return {"applied": True, "changed": changed,
                "detail": f"marked {len(touched)} students for "
                          f"{subject_code}/{section} on {day.isoformat()} "
                          f"({len(absent)} absent)"}

    # ---------- event handler ---------------------------------------------------
    async def on_attendance_uploaded(self, payload: dict):
        db = self.session()
        try:
            updates = [self._recompute_student(db, usn)
                       for usn in payload.get("usns", [])]
            db.commit()
        finally:
            db.close()
        await self.publish("attendance.updated", {
            "workflow_id": payload["workflow_id"],
            "_hop": payload.get("_hop", 1), "updates": updates})

    def _recompute_student(self, db, usn: str) -> dict:
        attended_expr = func.sum(case((AttendanceRecord.present.is_(True), 1), else_=0))
        rows = (db.query(AttendanceRecord.subject_code,
                         func.count(AttendanceRecord.id), attended_expr)
                  .filter(AttendanceRecord.usn == usn)
                  .group_by(AttendanceRecord.subject_code).all())
        total_held = total_attended = 0
        for subject_code, held, attended in rows:
            attended = int(attended or 0)
            total_held += held
            total_attended += attended
            pct = round(100.0 * attended / held, 2) if held else 0.0
            summary = db.query(AttendanceSummary).filter_by(
                usn=usn, subject_code=subject_code).first()
            if summary is None:
                summary = AttendanceSummary(usn=usn, subject_code=subject_code)
                db.add(summary)
            summary.classes_held = held
            summary.classes_attended = attended
            summary.percentage = pct
            summary.shortage = pct < config.ATTENDANCE_THRESHOLD
        overall = round(100.0 * total_attended / total_held, 2) if total_held else 0.0
        return {"usn": usn, "overall_percentage": overall,
                "shortage": overall < config.ATTENDANCE_THRESHOLD,
                "absence_streak": self._absence_streak(db, usn) >= config.ABSENCE_STREAK_ALERT}

    def _absence_streak(self, db, usn: str) -> int:
        present_expr = func.max(case((AttendanceRecord.present.is_(True), 1), else_=0))
        recent = (db.query(AttendanceRecord.date, present_expr)
                    .filter(AttendanceRecord.usn == usn)
                    .group_by(AttendanceRecord.date)
                    .order_by(AttendanceRecord.date.desc()).limit(10).all())
        streak = 0
        for _, any_present in recent:
            if int(any_present or 0) == 0:
                streak += 1
            else:
                break
        return streak

    # ---------- proactive behaviour ----------------------------------------------
    async def proactive_scan(self) -> dict:
        """Autonomous periodic scan: find shortage students and alert them
        without any user asking. Called by the background scheduler."""
        db = self.session()
        try:
            shortage_usns = [u for (u,) in
                             db.query(AttendanceSummary.usn)
                               .filter(AttendanceSummary.shortage.is_(True))
                               .distinct().limit(500).all()]
        finally:
            db.close()
        if shortage_usns:
            await self.publish("attendance.scan", {
                "shortage_usns": shortage_usns[:200],
                "count": len(shortage_usns)})
        return {"shortage_students": len(shortage_usns)}
