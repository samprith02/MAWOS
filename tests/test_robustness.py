"""Fault-isolation test: a crashing agent must not break the cascade (v2).

Exam and Scholarship merged into Eligibility under P2 (docs/RESEARCH_PLAN_V3.md
§7): they now share one subscription and one handler for attendance.updated,
so a fault in that handler withholds both exam.updated and scholarship.updated
together rather than just one. That coupling is the direct, honest consequence
of merging two reactions into one agent, not a partial isolation failure. What
must still hold is isolation ACROSS agents: placement, reacting to the same
attendance.updated event through an independent subscription, must still
complete.
"""
import asyncio
import datetime as dt

from backend.app.models import WorkflowEvent


def test_failing_agent_does_not_kill_cascade(agents, db):
    eligibility = agents["eligibility_agent"]
    bus = eligibility.bus
    subs = bus._subscribers["attendance.updated"]
    idx = next(i for i, (name, _) in enumerate(subs)
               if name == eligibility.name)
    original = subs[idx]

    async def broken(payload):
        raise RuntimeError("injected fault: eligibility agent down")

    subs[idx] = (eligibility.name, broken)
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
        assert "placement.updated" in topics
        assert "exam.updated" not in topics
        assert "scholarship.updated" not in topics
        errors = [e for e in events if e.topic == "agent.error"]
        assert len(errors) == 1 and errors[0].agent == "eligibility_agent"
        assert "injected fault" in errors[0].payload
    finally:
        subs[idx] = original
