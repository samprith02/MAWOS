"""Finance Agent — fee tracking, Rs 50/day fines after grace, payments,
defaulter lists, clearance checks, and a proactive overdue scan."""
import datetime as dt

from sqlalchemy import func

from .. import config
from ..models import FeeRecord, Student
from .base import BaseAgent


def _remaining_balance(fee: FeeRecord) -> float:
    return round((fee.amount_due or 0.0) + (fee.fine or 0.0)
                 - (fee.amount_paid or 0.0), 2)


def _current_unpaid_state(fee: FeeRecord, today: dt.date) -> tuple[float, str]:
    """Return the status a currently unpaid fee should display.

    This is deliberately a pure calculation.  Read endpoints can use it to
    show today's fine and status without turning a dashboard refresh into a
    database write.
    """
    grace_end = fee.due_date + dt.timedelta(days=config.FEE_GRACE_DAYS)
    if today > grace_end:
        return (round((today - grace_end).days * config.FEE_LATE_FINE_PER_DAY,
                      2), "overdue")
    return (0.0, "pending")


def fees_cleared(db, usn: str) -> bool:
    fees = db.query(FeeRecord).filter(FeeRecord.usn == usn).all()
    return all(_remaining_balance(f) <= 0
               and str(f.status or "").lower() == "paid"
               for f in fees)


class FinanceAgent(BaseAgent):
    name = "finance_agent"
    description = "Fees, fines, payments, defaulter tracking, clearance checks"

    def refresh_status(self, db, usn: str | None = None,
                       today: dt.date | None = None, *, commit: bool = True) -> int:
        """Persist fee-state maintenance from an explicit write workflow."""
        today = today or dt.date.today()
        q = db.query(FeeRecord).filter(FeeRecord.paid_date.is_(None))
        if usn:
            q = q.filter(FeeRecord.usn == usn)
        changed = 0
        for fee in q.all():
            fine, status = _current_unpaid_state(fee, today)
            if fee.fine != fine or fee.status != status:
                fee.fine, fee.status = fine, status
                changed += 1
        if commit:
            db.commit()
        return changed

    async def pay_fee(self, db, usn: str, fee_id: int) -> dict:
        fee = db.get(FeeRecord, fee_id)
        if fee is None or fee.usn != usn:
            return {"ok": False, "error": "Fee record not found"}
        if fee.paid_date is not None:
            return {"ok": False, "error": "Already paid"}
        # A payment is a write workflow, so synchronise the current fine here
        # and commit the resulting paid state atomically below.
        self.refresh_status(db, usn, commit=False)
        fee.amount_paid = fee.amount_due + fee.fine
        fee.paid_date = dt.date.today()
        fee.status = "paid"
        db.commit()
        workflow_id = await self.publish("fees.updated", {"usns": [usn]})
        return {"ok": True, "workflow_id": workflow_id,
                "paid": fee.amount_paid, "fee_type": fee.fee_type}

    def student_fees(self, db, usn: str) -> dict:
        fees = db.query(FeeRecord).filter_by(usn=usn).all()
        today = dt.date.today()
        items = []
        cleared = True
        total_outstanding = 0.0
        for fee in fees:
            fine, status = ((fee.fine or 0.0), fee.status) if fee.paid_date else \
                _current_unpaid_state(fee, today)
            outstanding = max(round((fee.amount_due or 0.0) + fine
                                    - (fee.amount_paid or 0.0), 2), 0.0)
            total_outstanding += outstanding
            cleared = cleared and outstanding <= 0 \
                and str(status or "").lower() == "paid"
            items.append({"id": fee.id, "type": fee.fee_type,
                          "amount_due": fee.amount_due, "fine": fine,
                          "status": status, "due_date": str(fee.due_date)})
        return {
            "cleared": cleared,
            "total_outstanding": round(total_outstanding, 2),
            "items": items,
        }

    def defaulter_list(self, db, dept_code: str | None = None,
                       limit: int = 50) -> list[dict]:
        q = (db.query(FeeRecord, Student)
               .join(Student, Student.usn == FeeRecord.usn)
               .filter(FeeRecord.status == "overdue"))
        if dept_code:
            q = q.filter(Student.dept_code == dept_code)
        return [{"usn": f.usn, "name": s.name, "dept": s.dept_code,
                 "year": s.year, "fee_type": f.fee_type,
                 "amount_due": f.amount_due, "fine": f.fine}
                for f, s in q.limit(limit).all()]

    def collection_stats(self, db) -> dict:
        rows = (db.query(Student.dept_code,
                         func.sum(FeeRecord.amount_due),
                         func.sum(FeeRecord.amount_paid))
                  .join(Student, Student.usn == FeeRecord.usn)
                  .group_by(Student.dept_code).all())
        return {dept: {"due": round(due or 0, 2), "collected": round(paid or 0, 2),
                       "pct": round(100 * (paid or 0) / due, 1) if due else 0}
                for dept, due, paid in rows}

    async def proactive_scan(self) -> dict:
        db = self.session()
        try:
            changed = self.refresh_status(db)
            overdue = db.query(FeeRecord).filter(FeeRecord.status == "overdue").count()
        finally:
            db.close()
        await self.publish("fees.scan", {"newly_flagged": changed,
                                         "total_overdue": overdue})
        return {"newly_flagged": changed, "total_overdue": overdue}
