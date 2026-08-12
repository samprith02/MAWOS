"""System metrics — the numbers that make MAWOS evaluable.

  * intent routing accuracy (on evaluation-labelled queries)
  * fallback-trigger rate (keyword path vs LLM path)
  * cross-agent propagation latency (per workflow cascade, from the
    workflow_events audit log)
  * cascade depth / completion statistics
"""
import statistics
from collections import defaultdict

from sqlalchemy import func

from .models import IntentLog, Notification, WorkflowEvent


def intent_metrics(db) -> dict:
    total = db.query(func.count(IntentLog.id)).scalar() or 0
    if total == 0:
        return {"total_classifications": 0}
    fallback = db.query(func.count(IntentLog.id)).filter(
        IntentLog.method == "keyword").scalar() or 0
    labelled = db.query(IntentLog).filter(IntentLog.correct.isnot(None)).all()
    accuracy = (sum(1 for l in labelled if l.correct) / len(labelled)
                if labelled else None)
    avg_latency = db.query(func.avg(IntentLog.latency_ms)).scalar() or 0.0
    return {
        "total_classifications": total,
        "fallback_rate": round(fallback / total, 4),
        "llm_rate": round(1 - fallback / total, 4),
        "routing_accuracy": round(accuracy, 4) if accuracy is not None else None,
        "evaluated_queries": len(labelled),
        "avg_classify_latency_ms": round(avg_latency, 3),
    }


def propagation_metrics(db) -> dict:
    rows = db.query(WorkflowEvent).all()
    by_wf: dict[str, list[WorkflowEvent]] = defaultdict(list)
    for r in rows:
        by_wf[r.workflow_id].append(r)

    durations, depths, agents_involved = [], [], []
    for wf, events in by_wf.items():
        if len(events) < 2:
            continue  # single-event workflows have no propagation to measure
        durations.append(max(e.elapsed_ms for e in events))
        depths.append(max(e.hop for e in events))
        agents_involved.append(len({e.agent for e in events}))

    if not durations:
        return {"cascades_measured": 0}
    durations.sort()
    p95 = durations[min(len(durations) - 1, int(0.95 * len(durations)))]
    return {
        "cascades_measured": len(durations),
        "avg_cascade_ms": round(statistics.mean(durations), 2),
        "p95_cascade_ms": round(p95, 2),
        "max_cascade_ms": round(max(durations), 2),
        "avg_cascade_depth_hops": round(statistics.mean(depths), 2),
        "avg_agents_per_cascade": round(statistics.mean(agents_involved), 2),
        "meets_2s_propagation_target": p95 < 2000,
        "meets_5s_end_to_end_target": max(durations) < 5000,
    }


def summary(db) -> dict:
    return {
        "intent": intent_metrics(db),
        "propagation": propagation_metrics(db),
        "notifications_generated": db.query(func.count(Notification.id)).scalar() or 0,
        "bus_events_logged": db.query(func.count(WorkflowEvent.id)).scalar() or 0,
    }
