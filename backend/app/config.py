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

# Institutional business rules
ATTENDANCE_THRESHOLD = 75.0          # % required for hall ticket
ABSENCE_STREAK_ALERT = 3             # consecutive absences that trigger an alert
FEE_LATE_FINE_PER_DAY = 50.0         # Rs per day after grace period
FEE_GRACE_DAYS = 7
LIBRARY_LOAN_DAYS = 14
LIBRARY_FINE_PER_DAY = 5.0           # Rs per day overdue

# Placement Agent
PLACEMENT_ML_THRESHOLD = float(os.getenv("MAWOS_PLACEMENT_ML_THRESHOLD", "0.5"))
PLACEMENT_MODEL_VERSION = os.getenv("MAWOS_PLACEMENT_MODEL_VERSION", "v1")

# ML model artifacts
ML_MODELS_DIR = BASE_DIR / "ml" / "models"
ML_DATA_DIR = BASE_DIR / "ml" / "data"

# Frontend static files
STATIC_DIR = BASE_DIR / "frontend" / "static"