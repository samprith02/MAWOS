"""Central configuration for MAWOS.

Everything is overridable via environment variables so the same codebase
runs on SQLite (default, zero-install) or PostgreSQL, and with or without
a local Ollama LLM.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Shared Institutional Context Store.
# Default: SQLite file. Set MAWOS_DATABASE_URL=postgresql://... to use Postgres.
DATABASE_URL = os.getenv("MAWOS_DATABASE_URL", f"sqlite:///{BASE_DIR / 'mawos.db'}")

# JWT auth
JWT_SECRET = os.getenv("MAWOS_JWT_SECRET", "mawos-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 12

# Local LLM (optional). The system is fully functional without it —
# the deterministic keyword classifier handles intent routing.
OLLAMA_HOST = os.getenv("MAWOS_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("MAWOS_OLLAMA_MODEL", "qwen2.5:3b-instruct")
OLLAMA_TIMEOUT_S = float(os.getenv("MAWOS_OLLAMA_TIMEOUT", "8.0"))

# P3 — PCN-style provenance gate on the LLM tier's free-text answers
# (backend/app/provenance.py, docs/RESEARCH_PLAN_V3.md §3.2). On by
# default; the dev-only evaluation is evaluation/gate_p3.py.
PROVENANCE_GATE_ENABLED = os.getenv("MAWOS_PROVENANCE_GATE", "1") == "1"

# Institutional business rules
ATTENDANCE_THRESHOLD = 75.0          # % required for hall ticket
ABSENCE_STREAK_ALERT = 3             # consecutive absences that trigger an alert
FEE_LATE_FINE_PER_DAY = 50.0         # Rs per day after grace period
FEE_GRACE_DAYS = 7
LIBRARY_LOAN_DAYS = 14
LIBRARY_FINE_PER_DAY = 5.0           # Rs per day overdue
LIBRARY_PICKUP_DEADLINE_DAYS = 2     # days to collect a reserved book before it expires
LIBRARY_PICKUP_FINE = 10.0           # Rs, flat fine for an uncollected reservation
LIBRARY_RECOMMENDATION_LIMIT = 5     # default number of recommendations returned
LIBRARY_FINE_THRESHOLD = 25.0        # Rs; a student with unpaid fines at/above this
                                      # cannot make new reservations until they clear some
LIBRARY_SLIP_CODE_LENGTH = 6         # digits in the unique slip verification code

# ML model artifacts
ML_MODELS_DIR = BASE_DIR / "ml" / "models"
ML_DATA_DIR = BASE_DIR / "ml" / "data"

# Frontend static files
STATIC_DIR = BASE_DIR / "frontend" / "static"
