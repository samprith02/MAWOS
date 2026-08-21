# Placement Agent — Integration Guide

This document is for the other MAWOS teammates who need to call into the
Placement Agent from the frontend, the Orchestrator, or another agent.

## 1. Where it lives

The Placement Agent is **not** a separate microservice — it runs inside the
single MAWOS backend process, same as every other agent. You don't start it
separately; it comes up automatically with `python run.py`.

- Logic: `backend/app/agents/placement.py` (class `PlacementAgent`)
- Routes: `backend/app/api/placement.py`
- Models: `PlacementDrive`, `PlacementShortlist`, `PlacementOutcome` in `backend/app/models.py`
- Registered in the agent registry as `"placement_agent"` (see `backend/app/agents/__init__.py`)

## 2. Authentication

All routes require a JWT bearer token, same as the rest of MAWOS. Get one via:

POST /api/auth/login
{"username": "...", "password": "..."}


Drive management, shortlist generation, and outcome recording require the
`admin` role. Read-only routes (list drives, view eligibility) work for any
authenticated user; a student can only view their **own** eligibility (`usn`
in the URL must match their own USN, or they get a 403).

## 3. REST API

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/api/placement/drives` | any | List all drives (optional `?status=OPEN`) |
| GET | `/api/placement/drives/{drive_id}` | any | Get one drive |
| POST | `/api/placement/drives` | admin | Create a drive |
| PUT | `/api/placement/drives/{drive_id}` | admin | Update a drive |
| POST | `/api/placement/drives/{drive_id}/close` | admin | Close a drive |
| POST | `/api/placement/drives/{drive_id}/generate-shortlist?regenerate=false` | admin | Run hard filter + ML scoring for all eligible final-years, save shortlist. Returns 409 if already generated unless `regenerate=true`. |
| GET | `/api/placement/drives/{drive_id}/shortlist` | admin | List the generated shortlist with reasons |
| GET | `/api/placement/drives/{drive_id}/candidates/{usn}/eligibility` | any (own record for students) | Explainability: hard-filter/ML reasons for one student |
| POST | `/api/placement/drives/{drive_id}/candidates/{usn}/outcome` | admin | Record OFFER_MADE / OFFER_ACCEPTED / OFFER_DECLINED / REJECTED |
| GET | `/api/placement/drives/{drive_id}/outcomes` | admin | List outcomes for a drive |

Full request/response schemas are visible live at `/docs` (Swagger UI) once
the server is running — every field, type, and example is auto-generated
from the code, so treat `/docs` as the source of truth over this table.

### Drive creation example

```json
POST /api/placement/drives
{
  "company": "TCS", "role": "GET", "package_lpa": 4.5,
  "min_cgpa": 7.5, "max_backlogs": 0, "min_attendance": 75.0,
  "drive_date": "2026-09-15", "departments": "CSE,AIML,ECE",
  "status": "OPEN", "requires_fee_clearance": false
}
```
`departments` is either `"ALL"` or a comma-separated list of department
codes (`AIML`, `CSE`, `ECE`, `ME`, `CV`).

## 4. Existing dashboard integration (already wired)

- `GET /api/student/dashboard` → includes a `"placements"` key, populated by
  `PlacementAgent.student_view()`. Already live, no changes needed by the
  Student Agent/frontend team.
- `GET /api/principal/analytics` → includes a `"placements"` key from
  `PlacementAgent.stats()` (dept-wise eligible-finalist counts).

## 5. Events published (in-process bus, `backend/app/bus.py`)

The bus is semantically Redis pub/sub but runs in-process — no external
infra needed. Subscribe with `bus.subscribe(topic, agent_name, handler)`.

| Topic | Fired when | Payload highlights |
|---|---|---|
| `placement.updated` | Attendance/fee change triggers re-evaluation | `usns`, `entries_updated` |
| `placement.shortlist_generated` | `generate-shortlist` endpoint called | `drive_id`, `data.company`, `data.shortlisted_count`, `data.model_version` |
| `placement.notification_required` | Once per shortlisted student, right after shortlist generation | `student_id`, `data.notification_type`, `data.metadata.drive_id` |
| `placement.offer_made` / `placement.offer_accepted` / `placement.offer_declined` / `placement.rejected` | Outcome recorded via the outcome endpoint | `drive_id`, `student_id`, `data.outcome_status`, `data.package_offered` |

Every event is also logged to the `workflow_events` table automatically
(handled by the bus itself), viewable via `GET /api/workflows/recent` — no
extra work needed for audit logging.

## 6. Events consumed

`PlacementAgent` subscribes to:
- `attendance.updated` — re-evaluates affected final-year students against all active drives
- `fees.updated` — same, for drives with `requires_fee_clearance=true`

It does **not** rewrite shortlists for drive/student pairs that already have
a finalized outcome (`OFFER_ACCEPTED`, `OFFER_DECLINED`, `REJECTED`) — those
are protected from being silently overwritten by background recalculation.

## 7. ML model

- Expected at `ml/models/placement_rf.joblib` (a `RandomForestClassifier`
  trained on `[cgpa, backlogs, attendance]` → probability).
- **Currently not present** — the agent runs correctly without it, falling
  back to rules-only evaluation (every shortlist entry says `"Meets all
  drive criteria (model unavailable, rules-only evaluation)"` and
  `model_version: null`). Training this model is a separate task (see
  `ml/train.py` for the pattern used by the Scholarship Agent's CART model)
  and is not required for the Placement Agent's API contract to work.
- Threshold is configurable via `MAWOS_PLACEMENT_ML_THRESHOLD` env var
  (default `0.5`); version string via `MAWOS_PLACEMENT_MODEL_VERSION`
  (default `v1`).

## 8. Known limitations (be aware, not blockers)

- No Postgres advisory locks / Redis — concurrency protection on shortlist
  generation is a status check, not a true row lock. Fine for the
  single-process demo scale this project runs at.
- No dedicated `placement_coordinator` role exists in the system yet — all
  placement-management actions are gated to `admin`. Extend `require_role()`
  calls in `backend/app/api/placement.py` if/when that role is added.