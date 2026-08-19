"""Failure-injection experiment — is the cascade fault tolerant?

Protocol: run one baseline cascade, then re-run with the Eligibility Agent's
event handler replaced by one that raises. Exam and Scholarship merged into
one Eligibility agent under P2 (docs/RESEARCH_PLAN_V3.md §7): they now share
one subscription and one handler for attendance.updated, so this fault
withholds exam.updated AND scholarship.updated together — that coupling is
the direct, honest consequence of the merge, not a partial isolation
failure. What the experiment verifies is isolation ACROSS agents: (a) sibling
agents (Placement, Notification), reacting to the same attendance.updated
event through independent subscriptions, still complete, (b) the failure is
recorded as an `agent.error` event under the same workflow_id, and
(c) recovery is possible by replaying the event after the agent is restored.

Writes evaluation/results/FAILURE_INJECTION.md.
Run:  python evaluation/failure_injection.py
"""
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import func  # noqa: E402

from backend.app.agents import get_agents  # noqa: E402
from backend.app.bus import bus  # noqa: E402
from backend.app.database import Base, SessionLocal, engine  # noqa: E402
from backend.app.models import (  # noqa: E402
    AttendanceRecord, ScholarshipAssessment, Student, Subject, WorkflowEvent,
)
from backend.app.seed import bootstrap_evaluations, seed_all  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
UPLOADER = "failure-injection"


def _fresh_day(db, offset: int) -> dt.date:
    min_date = db.query(func.min(AttendanceRecord.date)).scalar() or dt.date.today()
    d = min_date - dt.timedelta(days=3 + offset)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


async def run(db):
    agents = get_agents()
    students = (db.query(Student).filter_by(dept_code="AIML", semester=5)
                  .order_by(Student.usn).limit(10).all())
    subjects = [s.code for s in db.query(Subject)
                .filter_by(dept_code="AIML", semester=5).all()]

    def records(day):
        return [{"usn": s.usn, "subject_code": c, "date": day.isoformat(),
                 "present": True} for s in students for c in subjects]

    def trace(workflow_id):
        events = (db.query(WorkflowEvent).filter_by(workflow_id=workflow_id)
                    .order_by(WorkflowEvent.elapsed_ms).all())
        return [{"topic": e.topic, "agent": e.agent,
                 "elapsed_ms": e.elapsed_ms} for e in events]

    # --- baseline ---------------------------------------------------------
    r1 = await agents["attendance_agent"].upload_attendance(
        db, UPLOADER, records(_fresh_day(db, 14)))
    baseline = trace(r1["workflow_id"])

    # --- inject: eligibility agent raises ------------------------------------
    eligibility = agents["eligibility_agent"]
    subs = bus._subscribers["attendance.updated"]
    idx = next(i for i, (name, _) in enumerate(subs) if name == eligibility.name)
    original = subs[idx]

    async def broken(payload):
        raise RuntimeError("injected fault: eligibility service unavailable")

    subs[idx] = (eligibility.name, broken)
    try:
        r2 = await agents["attendance_agent"].upload_attendance(
            db, UPLOADER, records(_fresh_day(db, 21)))
        injected = trace(r2["workflow_id"])
    finally:
        subs[idx] = original

    # --- recovery: replay the event after the agent is restored -------------
    usns = [s.usn for s in students]
    before = db.query(func.max(ScholarshipAssessment.assessed_at)).filter(
        ScholarshipAssessment.usn.in_(usns)).scalar()
    r3 = await bus.publish("attendance.updated", {
        "updates": [{"usn": u} for u in usns]}, source_agent="recovery_replay")
    db.expire_all()
    after = db.query(func.max(ScholarshipAssessment.assessed_at)).filter(
        ScholarshipAssessment.usn.in_(usns)).scalar()

    inj_topics = {e["topic"] for e in injected}
    results = {
        "baseline_topics": sorted({e["topic"] for e in baseline}),
        "injected_topics": sorted(inj_topics),
        "siblings_survived": {"placement.updated",
                              "notification.sent"} <= inj_topics,
        "coupled_reactions_withheld": not ({"exam.updated", "scholarship.updated"}
                                           & inj_topics),
        "error_audited": "agent.error" in inj_topics,
        "recovery_replay_workflow": r3,
        "recovery_reassessed": bool(before and after and after > before),
        "injected_trace": injected,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "failure_injection.json").write_text(json.dumps(results, indent=2))
    ok = "PASS" if (results["siblings_survived"]
                    and results["coupled_reactions_withheld"]
                    and results["error_audited"]
                    and results["recovery_reassessed"]) else "FAIL"
    md = f"""# Failure-Injection Experiment — {ok}

Fault model: the Eligibility Agent's event handler raises
("service unavailable") mid-cascade. Eligibility owns both hall-ticket and
scholarship reactions (merged under P2), so this fault withholds
exam.updated AND scholarship.updated together — a direct consequence of
one agent, one handler, not a partial isolation failure.

| Property | Result |
|---|---|
| Sibling agents (Placement, Notification) completed | {results['siblings_survived']} |
| Both coupled reactions (exam, scholarship) withheld together | {results['coupled_reactions_withheld']} |
| Failure recorded as `agent.error` under the same workflow_id | {results['error_audited']} |
| Recovery by event replay after agent restored | {results['recovery_reassessed']} |

Cascade trace with the fault injected:

```
{chr(10).join(f"+{e['elapsed_ms']:>8.1f} ms  {e['agent']:<20} {e['topic']}" for e in injected)}
```

Design note: the bus isolates each subscriber (backend/app/bus.py); a failed
handler becomes an auditable `agent.error` event instead of an aborted
cascade, and the audit log retains everything needed to replay the missed
event once the agent recovers — which is exactly what this experiment does.
Isolation is at agent granularity: Placement and Notification, independent
subscribers to the same attendance.updated event, are unaffected by
Eligibility's fault.
"""
    (RESULTS_DIR / "FAILURE_INJECTION.md").write_text(md, encoding="utf-8")
    print(f"{ok} — wrote {RESULTS_DIR / 'FAILURE_INJECTION.md'}")


def main():
    Base.metadata.create_all(bind=engine)
    if seed_all():
        bootstrap_evaluations(get_agents())
    db = SessionLocal()
    try:
        db.query(AttendanceRecord).filter_by(uploaded_by=UPLOADER).delete()
        db.commit()
        asyncio.run(run(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
