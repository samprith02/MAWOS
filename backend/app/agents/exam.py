"""Exam Agent — dept/semester exam schedules + hall-ticket eligibility
(attendance >= 75% AND fees cleared) with transparent reason codes."""
from .. import config
from ..models import ExamSchedule, HallTicket, Student
from .attendance import overall_percentage
from .finance import fees_cleared
from .base import BaseAgent


class ExamAgent(BaseAgent):
    name = "exam_agent"
    description = "Exam schedules and hall-ticket eligibility with reason codes"

    def register_subscriptions(self):
        self.bus.subscribe("attendance.updated", self.name, self.on_upstream_change)
        self.bus.subscribe("fees.updated", self.name, self.on_upstream_change)

    async def on_upstream_change(self, payload: dict):
        usns = [u["usn"] if isinstance(u, dict) else u
                for u in payload.get("updates", payload.get("usns", []))]
        db = self.session()
        try:
            results = [self.evaluate(db, usn) for usn in usns]
            db.commit()
        finally:
            db.close()
        await self.publish("exam.updated", {
            "workflow_id": payload["workflow_id"],
            "_hop": payload.get("_hop", 1), "results": results})

    def evaluate(self, db, usn: str) -> dict:
        student = db.get(Student, usn)
        if student is None:
            return {"usn": usn, "eligible": False, "reasons": ["unknown student"]}
        attendance = overall_percentage(db, usn)
        cleared = fees_cleared(db, usn)
        reasons = []
        if attendance < config.ATTENDANCE_THRESHOLD:
            reasons.append(f"attendance {attendance}% below {config.ATTENDANCE_THRESHOLD}%")
        if not cleared:
            reasons.append("overdue fees pending")
        eligible = not reasons
        if eligible:
            reasons.append(f"attendance {attendance}% ok; fees cleared")
        ticket = db.query(HallTicket).filter_by(usn=usn,
                                                semester=student.semester).first()
        if ticket is None:
            ticket = HallTicket(usn=usn, semester=student.semester, eligible=eligible)
            db.add(ticket)
        ticket.eligible = eligible
        ticket.reasons = "; ".join(reasons)
        return {"usn": usn, "eligible": eligible, "reasons": reasons}

    def schedule_for(self, db, dept_code: str, semester: int) -> list[dict]:
        rows = (db.query(ExamSchedule)
                  .filter_by(dept_code=dept_code, semester=semester)
                  .order_by(ExamSchedule.exam_date).all())
        return [{"subject": e.subject_code, "date": str(e.exam_date),
                 "session": e.session} for e in rows]
