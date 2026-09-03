"""Central configuration for MAWOS.

Everything is overridable via environment variables so the same codebase
runs on SQLite (default, zero-install) or PostgreSQL, and with or without
a local Ollama LLM.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ConfigurationError(RuntimeError):
    """Raised when a security-sensitive MAWOS setting is unsafe."""


ENVIRONMENTS = frozenset({"development", "test", "production"})
MIN_JWT_SECRET_BYTES = 32

# This fallback is deliberately limited to non-production modes. It is
# convenient for local development, but is public source code and unsafe for
# any deployed service.
INSECURE_DEVELOPMENT_JWT_SECRET = "mawos-development-only-insecure-secret-do-not-use-in-production"
KNOWN_INSECURE_JWT_SECRETS = frozenset({
    "mawos-dev-secret-change-in-prod",
    INSECURE_DEVELOPMENT_JWT_SECRET,
    "replace-with-a-long-random-secret",
})


def environment_mode() -> str:
    """Return the explicit MAWOS deployment mode."""
    raw_mode = os.getenv("MAWOS_ENV")
    if raw_mode is None or not raw_mode.strip():
        raise ConfigurationError(
            "MAWOS_ENV must be explicitly configured as development, test, or production"
        )
    mode = raw_mode.strip().lower()
    if mode not in ENVIRONMENTS:
        raise ConfigurationError(
            "MAWOS_ENV must be one of: development, test, production"
        )
    return mode


def _boolean_setting(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ConfigurationError(f"{name} must be true or false")


def _has_strong_secret_shape(secret: str) -> bool:
    """Reject obvious low-entropy values; operators must use random secrets."""
    return len(set(secret)) >= 16


def jwt_secret() -> str:
    """Return the configured signing secret, enforcing production safety."""
    mode = environment_mode()
    configured_secret = os.getenv("MAWOS_JWT_SECRET")

    if mode != "production" and not configured_secret:
        return INSECURE_DEVELOPMENT_JWT_SECRET

    if mode == "production" and not configured_secret:
        raise ConfigurationError(
            "MAWOS_JWT_SECRET must be explicitly configured in production"
        )

    assert configured_secret is not None
    if mode == "production":
        if configured_secret in KNOWN_INSECURE_JWT_SECRETS:
            raise ConfigurationError(
                "MAWOS_JWT_SECRET must not use a known development secret in production"
            )
        if len(configured_secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
            raise ConfigurationError(
                "MAWOS_JWT_SECRET must contain at least 32 bytes in production"
            )
        if not _has_strong_secret_shape(configured_secret):
            raise ConfigurationError(
                "MAWOS_JWT_SECRET must be a high-entropy random value in production"
            )
    return configured_secret


def seed_demo_data_enabled() -> bool:
    """Return whether automatic demo-data seeding is allowed at startup."""
    enabled = _boolean_setting("MAWOS_SEED_DEMO_DATA", default=False)
    if environment_mode() == "production" and enabled:
        raise ConfigurationError(
            "MAWOS_SEED_DEMO_DATA is not allowed in production; "
            "production demo seeding requires a separate administrative operation"
        )
    return enabled


def validate_security_configuration() -> None:
    """Validate all security-sensitive startup settings without exposing secrets."""
    jwt_secret()
    seed_demo_data_enabled()

# Shared Institutional Context Store.
# Default: SQLite file. Set MAWOS_DATABASE_URL=postgresql://... to use Postgres.
DATABASE_URL = os.getenv("MAWOS_DATABASE_URL", f"sqlite:///{BASE_DIR / 'mawos.db'}")

# JWT auth
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

# ML model artifacts
ML_MODELS_DIR = BASE_DIR / "ml" / "models"
ML_DATA_DIR = BASE_DIR / "ml" / "data"
