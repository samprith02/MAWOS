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

# Institutional business rules.
#
# R1: these are facts about an institution, so they live in
# `data/institution.yaml` and are read from there -- one source of truth.
# The module-level names are kept so every existing caller (agents,
# provenance.STATIC_GROUNDED, the evaluation harness) is unchanged.
INSTITUTION_CONFIG = Path(
    os.getenv("MAWOS_INSTITUTION_CONFIG", BASE_DIR / "data" / "institution.yaml"))


def _policies() -> dict:
    try:
        import yaml
        raw = yaml.safe_load(INSTITUTION_CONFIG.read_text(encoding="utf-8"))
        return raw.get("policies", {}) or {}
    except Exception:
        # A missing or unreadable config must not stop the app booting; the
        # defaults below are the same values institution.yaml ships with.
        return {}


def _identity() -> dict:
    try:
        import yaml
        raw = yaml.safe_load(INSTITUTION_CONFIG.read_text(encoding="utf-8"))
        return raw.get("institution", {}) or {}
    except Exception:
        return {}


_P = _policies()
_I = _identity()

#: Institution identity, read from data/institution.yaml — never hardcoded.
#: `docs/v4/04_DATA_MODEL.md` §3: this file is the only place it may live.
INSTITUTION_NAME = str(_I.get("name", "the institute"))
INSTITUTION_SHORT = str(_I.get("short_name", "INST"))
USN_PREFIX = str(_I.get("usn_prefix", ""))
EMAIL_DOMAIN = str(_I.get("email_domain", "example.edu"))

ATTENDANCE_THRESHOLD = float(_P.get("attendance_threshold_pct", 75.0))
ABSENCE_STREAK_ALERT = int(_P.get("absence_streak_alert", 3))
FEE_LATE_FINE_PER_DAY = float(_P.get("fee_late_fine_per_day", 50.0))
FEE_GRACE_DAYS = int(_P.get("fee_grace_days", 7))
SCHOLARSHIP_MIN_CGPA = float(_P.get("scholarship_min_cgpa", 6.0))
SCHOLARSHIP_SCHEME = str(_P.get("scholarship_scheme", "Merit-cum-Means"))

# Library rules are not modelled by any v4 module; kept only because
# provenance.STATIC_GROUNDED references them as institutional constants.
LIBRARY_LOAN_DAYS = 14
LIBRARY_FINE_PER_DAY = 5.0

# ML data. R1 deleted both trained models (docs/v4/04_DATA_MODEL.md §2);
# ML_DATA_DIR remains because ml/calibrate.py and the UCI calibration that
# feeds data/generator/profiles.py are carried forward unchanged.
ML_DATA_DIR = BASE_DIR / "ml" / "data"

# Frontend static files
STATIC_DIR = BASE_DIR / "frontend" / "static"
