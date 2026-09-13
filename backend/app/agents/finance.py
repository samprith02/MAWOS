"""Finance Agent — fee tracking, Rs 50/day fines after grace, payments,
defaulter lists, clearance checks, and a proactive overdue scan."""
import datetime as dt

from sqlalchemy import func

from .. import config
from ..models import FeeRecord, Student
from .base import BaseAgent


def fees_cleared(db, usn: str) -> bool:
    return db.query(FeeRecord).filter(
        FeeRecord.usn == usn, FeeRecord.status == "overdue").count() == 0


class FinanceAgent(BaseAgent):
    name = "finance_agent"
    description = "Fees, fines, payments, defaulter tracking, clearance checks"

    def refresh_status(self, db, usn: str | None = None,
                       today: dt.date | None = None) -> int:
        today = today or dt.date.today()
        q = db.query(FeeRecord).filter(FeeRecord.paid_date.is_(None))
        if usn:
            q = q.filter(FeeRecord.usn == usn)
        changed = 0
        for fee in q.all():
            grace_end = fee.due_date + dt.timedelta(days=config.FEE_GRACE_DAYS)
            if today > grace_end:
                fine = round((today - grace_end).days * config.FEE_LATE_FINE_PER_DAY, 2)
                status = "overdue"
            else:
                fine, status = 0.0, "pending"
            if fee.fine != fine or fee.status != status:
                fee.fine, fee.status = fine, status
                changed += 1
        db.commit()
        return changed

    async def pay_fee(self, db, usn: str, fee_id: int) -> dict:
        fee = db.get(FeeRecord, fee_id)
        if fee is None or fee.usn != usn:
            return {"ok": False, "error": "Fee record not found"}
        if fee.paid_date is not None:
            return {"ok": False, "error": "Already paid"}
        fee.amount_paid = fee.amount_due + fee.fine
        fee.paid_date = dt.date.today()
        fee.status = "paid"
        db.commit()
        workflow_id = await self.publish("fees.updated", {"usns": [usn]})
        return {"ok": True, "workflow_id": workflow_id,
                "paid": fee.amount_paid, "fee_type": fee.fee_type}

    def student_fees(self, db, usn: str) -> dict:
        self.refresh_status(db, usn)
        fees = db.query(FeeRecord).filter_by(usn=usn).all()
        pending = [f for f in fees if f.status != "paid"]
        return {
            "cleared": len(pending) == 0,
            "total_outstanding": round(sum(f.amount_due + f.fine - f.amount_paid
                                           for f in pending), 2),
            "items": [{"id": f.id, "type": f.fee_type, "amount_due": f.amount_due,
                       "fine": f.fine, "status": f.status,
                       "due_date": str(f.due_date)} for f in fees],
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
