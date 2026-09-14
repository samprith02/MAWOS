"""Eligibility Agent — hall-ticket (exam) eligibility and scholarship
assessment, merged under P2 (docs/RESEARCH_PLAN_V3.md §7).

R1: the scholarship CART was removed (docs/v4/04_DATA_MODEL.md §2). Both
verdicts are now deterministic policy rules with reason codes, which is
what the domain actually is.

Exam and Scholarship were split in v2 but own the same two upstream
triggers (attendance.updated, fees.updated) and the same shape of policy
(deterministic rule checks against attendance/fees, with a reason-coded
verdict). Under the pre-registered agent criterion — owns state/policy
that outlives a request, and acts on events without direct invocation —
they are one agent, not two. Merging the agent does not merge the tools:
`get_hall_ticket` and `get_scholarship` stay two distinct tools (§7.1),
so the dev benchmark's gold labels are untouched.
"""
from .. import config
from ..models import (EligibilityOverride, ExamSchedule, HallTicket,
                      ScholarshipAssessment, Student)
from .attendance import overall_percentage
from .base import BaseAgent
from .finance import fees_cleared

SCHEME = "Merit-cum-Means"


class EligibilityAgent(BaseAgent):
    name = "eligibility_agent"
    description = ("Hall-ticket eligibility and scholarship scoring "
                   "(rules + CART), with reason codes")

    def register_subscriptions(self):
        self.bus.subscribe("attendance.updated", self.name, self.on_upstream_change)
        self.bus.subscribe("fees.updated", self.name, self.on_upstream_change)

    async def on_upstream_change(self, payload: dict):
        usns = [u["usn"] if isinstance(u, dict) else u
                for u in payload.get("updates", payload.get("usns", []))]
        db = self.session()
        try:
            hall_ticket_results = [self.evaluate_hall_ticket(db, usn) for usn in usns]
            scholarship_results = [self.evaluate_scholarship(db, usn) for usn in usns]
            db.commit()
        finally:
            db.close()
        await self.publish("exam.updated", {
            "workflow_id": payload["workflow_id"],
            "_hop": payload.get("_hop", 1), "results": hall_ticket_results})
        await self.publish("scholarship.updated", {
            "workflow_id": payload["workflow_id"],
            "_hop": payload.get("_hop", 1), "results": scholarship_results})

    # ---------- hall-ticket eligibility -----------------------------------
    def evaluate_hall_ticket(self, db, usn: str) -> dict:
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
        # A recorded manual override (issue_eligibility_override) may flip an
        # otherwise-ineligible verdict to eligible. It does not rewrite the
        # rule: the blocking reasons above stay in the record, with the
        # override appended, so the audit trail shows what was waived and by
        # whom rather than silently recomputing a clean verdict.
        override = (db.query(EligibilityOverride)
                      .filter_by(usn=usn, semester=student.semester)
                      .order_by(EligibilityOverride.id.desc()).first())
        if override is not None and not eligible:
            eligible = True
            reasons.append(f"overridden by {override.decided_by}: {override.reason}")
        elif eligible:
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

    # ---------- write tool (v5 chat/guard path) ---------------------------------
    def override(self, db, usn: str, exam: str | None, reason: str | None,
                 decided_by: str = "system") -> dict:
        """Manual override of a hall-ticket verdict (backend/app/agents/tools.py:
        `issue_eligibility_override`). Records an `EligibilityOverride` row --
        `evaluate_hall_ticket` is the only place that interprets it -- then
        re-runs that same evaluation so `changed` reports the real post-write
        verdict rather than assuming the override took effect (it is a no-op
        on an already-eligible student, and that must show up as such).
        """
        usn = str(usn or "").upper().strip()
        student = db.get(Student, usn)
        if student is None:
            return {"applied": False, "changed": [],
                    "detail": f"unknown student {usn}"}
        reason = str(reason or "").strip()
        if not reason:
            return {"applied": False, "changed": [],
                    "detail": "a reason is required"}
        exam = str(exam or "").strip()
        before = self.evaluate_hall_ticket(db, usn)
        # `db` is autoflush=False (backend/app/database.py) and this is the
        # only call site that runs `evaluate_hall_ticket` twice in one
        # session: without an explicit flush here, the second call's query
        # for the HallTicket row this one may have just created returns None
        # (the pending insert isn't visible yet) and adds a SECOND row for
        # the same (usn, semester), which then fails the unique constraint
        # at commit. Flush so the row -- and its id -- is visible to the
        # re-evaluation below.
        db.flush()
        db.add(EligibilityOverride(usn=usn, semester=student.semester, exam=exam,
                                   reason=reason, decided_by=decided_by))
        db.flush()
        after = self.evaluate_hall_ticket(db, usn)
        db.commit()
        return {"applied": True,
                "changed": [{"usn": usn, "semester": student.semester,
                             "exam": exam, "eligible_before": before["eligible"],
                             "eligible_after": after["eligible"],
                             "reasons": after["reasons"]}],
                "detail": (f"override recorded by {decided_by} for {usn}"
                          + (f" ({exam})" if exam else "") + f": {reason} -- "
                          + f"eligible {before['eligible']} -> {after['eligible']}")}

    # ---------- scholarship scoring -----------------------------------------
    def evaluate_scholarship(self, db, usn: str) -> dict:
        student = db.get(Student, usn)
        if student is None:
            return {"usn": usn, "status": "not_eligible", "reasons": ["unknown student"]}
        attendance = overall_percentage(db, usn)
        cleared = fees_cleared(db, usn)
        reasons = []
        if attendance < config.ATTENDANCE_THRESHOLD:
            reasons.append(f"attendance {attendance}% below 75%")
        if not cleared:
            reasons.append("outstanding overdue fees")
        if 0 < student.cgpa < 6.0:
            reasons.append(f"CGPA {student.cgpa} below 6.0 minimum")
        # R1: the CART is deleted. It was trained on a label our own banded
        # rule generated (docs/v4/04_DATA_MODEL.md §2) -- learning our own
        # rule and calling the output AI. Scholarship eligibility is a
        # policy decision, so it is stated as one, with reason codes.
        if reasons:
            status = "not_eligible"
        elif student.cgpa >= 8.0:
            status = "eligible"
            reasons.append(f"CGPA {student.cgpa} >= 8.0 merit band")
        elif student.cgpa >= 7.0:
            status = "waitlist"
            reasons.append(f"CGPA {student.cgpa} in the 7.0-8.0 waitlist band")
        else:
            status = "not_eligible"
            reasons.append(f"CGPA {student.cgpa} below the 7.0 merit floor")
        assessment = db.query(ScholarshipAssessment).filter_by(
            usn=usn, scheme=SCHEME).first()
        if assessment is None:
            assessment = ScholarshipAssessment(usn=usn, scheme=SCHEME, status=status)
            db.add(assessment)
        assessment.status = status
        assessment.reasons = "; ".join(reasons)
        return {"usn": usn, "status": status, "reasons": reasons}
