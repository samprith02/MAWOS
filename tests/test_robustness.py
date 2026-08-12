"""Fault-isolation test: a crashing agent must not break the cascade (v2)."""
import asyncio
import datetime as dt

from backend.app.models import WorkflowEvent


def test_failing_agent_does_not_kill_cascade(agents, db):
    scholarship = agents["scholarship_agent"]
    bus = scholarship.bus
    subs = bus._subscribers["attendance.updated"]
    idx = next(i for i, (name, _) in enumerate(subs)
               if name == scholarship.name)
    original = subs[idx]

    async def broken(payload):
        raise RuntimeError("injected fault: scholarship agent down")

    subs[idx] = (scholarship.name, broken)
    try:
        records = []
        d, made = dt.date(2026, 4, 6), 0
        while made < 5:
            if d.weekday() < 5:
                records.append({"usn": "4MT23AI001", "subject_code": "23AI52",
                                "date": d.isoformat(), "present": True})
                made += 1
            d += dt.timedelta(days=1)
        result = asyncio.run(agents["attendance_agent"].upload_attendance(
            db, "fault-test", records))
        events = db.query(WorkflowEvent).filter_by(
            workflow_id=result["workflow_id"]).all()
        topics = {e.topic for e in events}
        assert "exam.updated" in topics
        assert "placement.updated" in topics
        errors = [e for e in events if e.topic == "agent.error"]
        assert len(errors) == 1 and errors[0].agent == "scholarship_agent"
        assert "injected fault" in errors[0].payload
    finally:
        subs[idx] = original
