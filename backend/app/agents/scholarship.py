"""Scholarship Agent — deterministic rule pre-filter, then the calibrated
CART decision tree for scoring. Re-evaluates on upstream changes."""
import joblib

from .. import config
from ..models import ScholarshipAssessment, Student
from .attendance import overall_percentage
from .finance import fees_cleared
from .base import BaseAgent

SCHEME = "Merit-cum-Means"
_MODEL_PATH = config.ML_MODELS_DIR / "scholarship_cart.joblib"


class ScholarshipAgent(BaseAgent):
    name = "scholarship_agent"
    description = "Rule pre-filter + CART scoring for scholarship eligibility"

    def __init__(self, bus):
        super().__init__(bus)
        self.model = None
        if _MODEL_PATH.exists():
            # Safe: artifact produced locally by ml/train.py in this repo.
            self.model = joblib.load(_MODEL_PATH)

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
        await self.publish("scholarship.updated", {
            "workflow_id": payload["workflow_id"],
            "_hop": payload.get("_hop", 1), "results": results})

    def evaluate(self, db, usn: str) -> dict:
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
        ml_score = None
        if reasons:
            status = "not_eligible"
        elif self.model is not None:
            features = [[student.cgpa, attendance, student.family_income,
                         student.backlogs, 1 if cleared else 0]]
            ml_score = float(self.model.predict_proba(features)[0][1])
            if ml_score >= 0.60:
                status = "eligible"
                reasons.append(f"CART score {ml_score:.2f} >= 0.60")
            elif ml_score >= 0.40:
                status = "waitlist"
                reasons.append(f"CART score {ml_score:.2f} in waitlist band")
            else:
                status = "not_eligible"
                reasons.append(f"CART score {ml_score:.2f} < 0.40")
        else:
            status = "eligible" if student.cgpa >= 7.5 else "waitlist"
            reasons.append("rules-only evaluation (model unavailable)")
        assessment = db.query(ScholarshipAssessment).filter_by(
            usn=usn, scheme=SCHEME).first()
        if assessment is None:
            assessment = ScholarshipAssessment(usn=usn, scheme=SCHEME, status=status)
            db.add(assessment)
        assessment.status = status
        assessment.ml_score = ml_score
        assessment.reasons = "; ".join(reasons)
        return {"usn": usn, "status": status, "ml_score": ml_score,
                "reasons": reasons}
