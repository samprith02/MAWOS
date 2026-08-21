# Placement Agent — Handoff Document (continue from here)

## Context
This is a 4-person final-year college project: "Multi-Agent Workflow
Orchestration System for Educational Institutions Using Hybrid AI" (MAWOS).
I am building the **Placement Agent**, one of 11 agents in a single-process
FastAPI monolith (NOT separate microservices — all agents are Python classes
in one backend, communicating via an in-process pub/sub EventBus, sharing
one SQLAlchemy/SQLite database). My teammates are building the other agents
in the same repo, each on their own git branch, to be merged later.

Repo: https://github.com/samprith02/MAWOS (private, I have push access)
My branch: `feature/placement-agent`
I have NO prior coding experience — I need exact terminal commands and full
file contents for every change, not diffs or manual-edit instructions.

## Environment
- Windows, PowerShell, VS Code
- Python 3.14.0 (no other version installed; works fine, all packages have
  3.14 wheels — do not suggest downgrading unless something actually breaks)
- Virtual env exists at `venv\` in project root — always activate first:
  `.\venv\Scripts\Activate.ps1`
- Project root: `C:\Users\Pranit\Documents\week2ProjectMawos\MAWOS`
- DB: SQLite, file `mawos.db` in project root, auto-seeded on first run if
  empty (5 depts, ~1200 students, 60 placement drives, etc. — see
  `backend/app/seed.py`)
- Run the app: `python run.py` (starts Uvicorn on http://127.0.0.1:8000,
  Swagger docs at /docs)
- Ollama (local LLM) is OPTIONAL — the system runs fine without it via a
  deterministic keyword-based intent classifier fallback. Do not chase
  Ollama-related issues unless explicitly relevant to Placement Agent work.

## Architecture patterns to follow (already established, do not deviate)
- Each agent = a class in `backend/app/agents/{name}.py` extending
  `BaseAgent` (see `backend/app/agents/base.py`)
- Agents subscribe to bus topics in `register_subscriptions()`, publish via
  `self.publish(topic, payload)`
- All agents registered in `backend/app/agents/__init__.py` under
  `get_agents()`, keyed by e.g. `"placement_agent"`
- DB session: `db.session()` per BaseAgent, or FastAPI `Depends(get_session)`
  in routes
- Auth: JWT via `backend/app/auth.py`; `require_role("admin")` /
  `get_current_user` as FastAPI dependencies; roles are
  student|faculty|hod|principal|admin (NO separate "placement_coordinator"
  role exists — placement management is gated to `admin`)
- Routes live in `backend/app/api/*.py`, each a separate `APIRouter`,
  included in `backend/app/main.py` via `app.include_router(...)`
- Business logic stays in the agent class, NOT in route files
- Every bus event auto-logs to `workflow_events` table (audit trail is
  already handled by the bus itself, see `backend/app/bus.py`)

## What's been completed so far (Stages 1–4, all committed + pushed)

### Stage 1 — `backend/app/models.py`
Added `PlacementOutcome` model (tracks OFFER_MADE/OFFER_ACCEPTED/
OFFER_DECLINED/REJECTED per drive+student). Added `status`,
`requires_fee_clearance`, `application_deadline`, `created_at`, `updated_at`
to `PlacementDrive`. Added `model_version` to `PlacementShortlist`.

### Stage 2 — `backend/app/agents/placement.py` (full rewrite)
`PlacementAgent` now has: fee-clearance check integrated into the hard
filter (via `finance.fees_cleared()`), full drive CRUD
(`create_drive`/`update_drive`/`close_drive`/`list_drives`/`get_drive`),
idempotent batch `generate_shortlist()` (rejects re-run with a
`PermissionError` unless `regenerate=True`, flips drive status to
`SHORTLIST_GENERATED`), `get_shortlist()`, `get_eligibility()`
(explainability endpoint payload), `record_outcome()` (blocks a 2nd
`OFFER_ACCEPTED` across drives unless `allow_multiple_offers=True`),
`get_outcomes()`. Finalized outcomes (`OFFER_ACCEPTED`/`OFFER_DECLINED`/
`REJECTED`) are protected from being overwritten by background
re-evaluation triggered by `attendance.updated`/`fees.updated` events.
Also added `PLACEMENT_ML_THRESHOLD` and `PLACEMENT_MODEL_VERSION` config
vars (env-overridable) to `backend/app/config.py`.

### Stage 3 — `backend/app/api/placement.py` (new file) + `main.py` wiring
Full REST API, prefix `/api/placement`:
- GET/POST `/drives`, GET/PUT `/drives/{id}`, POST `/drives/{id}/close`
- POST `/drives/{id}/generate-shortlist?regenerate=bool`
- GET `/drives/{id}/shortlist`
- GET `/drives/{id}/candidates/{usn}/eligibility` (student can only view own)
- POST `/drives/{id}/candidates/{usn}/outcome`
- GET `/drives/{id}/outcomes`
Registered in `main.py` via `app.include_router(placement_router)`.

### Stage 4 — `INTEGRATION.md` (repo root)
Written for teammates: full endpoint table, event contract (published +
consumed topics), auth notes, ML model status, known limitations.

## Verified working (manually, via Swagger UI at /docs), all passed:
- Admin login → Authorize → list 60 seeded drives (all new fields present)
- Created a test drive (id 61, loose criteria) → generated shortlist
  (300 evaluated, 269 shortlisted, `model_version: null` since no model
  file exists yet — expected, confirms graceful fallback works)
- Re-running generate-shortlist without `regenerate=true` → correctly got
  `409 Conflict`, `"SHORTLIST_EXISTS"`
- Fetched shortlist → confirmed a real rejection reason appeared correctly
  (e.g. `"CGPA 5.9 below cutoff of 6.0"`)
- Recorded an outcome (`OFFER_MADE`, drive 61, USN `4MT22CS051`) → 200 OK,
  correct payload returned
- Logged in as a student (`4MT22CS051` / `student123`) → tried
  `POST /drives` → correctly got `403 Forbidden`,
  `"Requires role: ('admin',)"` — role gating confirmed working

## NOT done yet — pick up here

### Stage 5 — Automated tests (`tests/test_agents.py`)
Write pytest tests replaying the manual Swagger checks above
programmatically (using FastAPI's `TestClient`), so verification doesn't
require manually clicking through `/docs` every time. Look at existing
`tests/test_agents.py`, `tests/conftest.py`, `tests/test_workflows.py` first
to match existing test patterns/fixtures before writing new ones — I have
NOT yet shown these files' contents to any Claude session, so request them
first. Should at minimum cover: drive creation validation (reject negative
CGPA), shortlist idempotency (409 on duplicate), role gating (403 for
non-admin on admin routes), student can't view another student's
eligibility (403), outcome double-offer prevention.

### Stage 6 — Train the Random Forest model
Currently `ml/models/placement_rf.joblib` does not exist, so
`PlacementAgent` runs in rules-only fallback mode (works correctly, just
has no ML score). To train it: look at how the Scholarship Agent's CART
model was trained (same pattern, see `ml/train.py`, `ml/generate_datasets.py`,
`ml/calibrate.py`, and `docs/DATASET_METHODOLOGY.md`) and replicate for
placement: features `[cgpa, backlogs, attendance]`, target = historical
placement success (synthetic), `RandomForestClassifier(n_estimators=100)`
per the original task spec, saved via `joblib.dump()` to
`ml/models/placement_rf.joblib`. Need to see `ml/train.py` and
`ml/generate_datasets.py` contents before writing this.

### Also outstanding (lower priority)
- Frontend (`frontend/static/` or `frontend-react/`) does not yet display
  placement drive/shortlist/outcome data — currently only
  `student_view()`/`stats()` feed into existing dashboard JSON, nothing
  placement-specific has been added to the UI.
- Have not yet opened a Pull Request from `feature/placement-agent` into
  `Main` — branch is ready for it, but decision to merge is pending my call.
- Timetable agent had an unrelated bug a teammate flagged (something about
  needing Ollama) — explicitly OUT OF SCOPE for Placement Agent work, do
  not get pulled into debugging it unless I ask.

## How I like to work (please follow)
- I have NO prior coding experience. Explain new tools/concepts in plain
  language before using them (e.g. what a venv is, what Ollama does, what
  git branching means) — don't assume I know jargon.
- Give me FULL file contents to copy-paste, never partial diffs or "add
  this line here" manual edit instructions.
- Always give exact PowerShell commands, one step at a time.
- Before I run the next command, tell me clearly what success looks like
  (exact expected output/behavior), so I know whether it worked without
  having to guess.
- Wait for me to paste back real terminal output/errors/screenshots before
  assuming something worked — don't assume success.
- Ask for existing file contents via `Get-Content` before writing new code
  that depends on them, rather than guessing their structure.
- Work in small, independently testable stages. After each stage: verify it
  works (via a command or via Swagger UI at /docs), then give me the exact
  `git add` / `git commit` / `git push` commands for that stage before
  moving to the next one. Don't bundle multiple stages into one big
  untested change.
- If something in the existing codebase doesn't match what a spec/task
  document assumes (e.g. architecture mismatches), tell me plainly and
  proactively — don't silently force the mismatch or silently go along
  with a flawed plan.
- If a design decision has real tradeoffs and isn't obvious, ask me ONE
  clear question (with options) rather than guessing silently or asking
  many things at once.
- Stay in scope. If I say we're deferring something (e.g. an unrelated bug
  in another teammate's agent), don't get pulled into it unless I
  explicitly bring it back up.
- When explaining what a manual verification step accomplished (e.g. after
  I test something in Swagger UI), summarize plainly what just got proven
  to work — I don't always know how to interpret raw JSON/output myself.
- I use PowerShell in VS Code on Windows — commands must be PowerShell-
  compatible, not bash/Linux syntax.