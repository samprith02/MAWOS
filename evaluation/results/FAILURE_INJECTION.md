# Failure-Injection Experiment — PASS

Fault model: the Eligibility Agent's event handler raises
("service unavailable") mid-cascade. Eligibility owns both hall-ticket and
scholarship reactions (merged under P2), so this fault withholds
exam.updated AND scholarship.updated together — a direct consequence of
one agent, one handler, not a partial isolation failure.

| Property | Result |
|---|---|
| Sibling agents (Placement, Notification) completed | True |
| Both coupled reactions (exam, scholarship) withheld together | True |
| Failure recorded as `agent.error` under the same workflow_id | True |
| Recovery by event replay after agent restored | True |

Cascade trace with the fault injected:

```
+     0.0 ms  attendance_agent     attendance.uploaded
+   106.7 ms  attendance_agent     attendance.updated
+   116.3 ms  eligibility_agent    agent.error
+   134.9 ms  placement_agent      placement.updated
+   153.9 ms  notification_agent   notification.sent
```

Design note: the bus isolates each subscriber (backend/app/bus.py); a failed
handler becomes an auditable `agent.error` event instead of an aborted
cascade, and the audit log retains everything needed to replay the missed
event once the agent recovers — which is exactly what this experiment does.
Isolation is at agent granularity: Placement and Notification, independent
subscribers to the same attendance.updated event, are unaffected by
Eligibility's fault.
