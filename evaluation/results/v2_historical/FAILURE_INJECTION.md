# Failure-Injection Experiment — PASS

Fault model: the Scholarship Agent's event handler raises
("service unavailable") mid-cascade.

| Property | Result |
|---|---|
| Sibling agents (Exam, Placement, Notification) completed | True |
| Failure recorded as `agent.error` under the same workflow_id | True |
| Recovery by event replay after agent restored | True |

Cascade trace with the fault injected:

```
+     0.0 ms  attendance_agent     attendance.uploaded
+    41.7 ms  attendance_agent     attendance.updated
+    75.7 ms  exam_agent           exam.updated
+    80.6 ms  scholarship_agent    agent.error
+    91.1 ms  placement_agent      placement.updated
+   105.6 ms  notification_agent   notification.sent
```

Design note: the bus isolates each subscriber (backend/app/bus.py); a failed
handler becomes an auditable `agent.error` event instead of an aborted
cascade, and the audit log retains everything needed to replay the missed
event once the agent recovers — which is exactly what this experiment does.
