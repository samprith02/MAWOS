"""Test fixtures — isolated SQLite DB, a known mini institution, agents live.

R1: the inline seed moved to `tests/fixtures/mini_institution.py` so the
ground truth is stated in one place and no institution identity is
hardcoded in a test (docs/v4/04_DATA_MODEL.md 5.3).
"""
import os
import sys
import tempfile
from pathlib import Path

_tmpdir = tempfile.mkdtemp(prefix="mawos_test_")
os.environ["MAWOS_DATABASE_URL"] = f"sqlite:///{Path(_tmpdir) / 'test.db'}"

# The suite must never reach a real LLM provider. v5 made that possible in
# two new ways: `config._load_dotenv()` reads a developer's `.env`, and
# `llm.check_hosted()` makes a real HTTP call when a credential is present.
# Together those would turn `router.decide()` — exercised by
# tests/test_orchestrator.py — into a network call whose result depends on
# whose laptop is running the suite. Both are disabled here, before any
# backend import, so escalation availability is deterministically False.
os.environ["MAWOS_SKIP_DOTENV"] = "1"
for _k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "GITHUB_MODELS_TOKEN"):
    os.environ.pop(_k, None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import datetime as dt  # noqa: E402

import pytest  # noqa: E402

from backend.app import models  # noqa: E402,F401  (registers every table
                               #  on Base.metadata before create_all)
from backend.app.database import Base, SessionLocal, engine  # noqa: E402
from tests.fixtures import mini_institution  # noqa: E402
from tests.fixtures.mini_institution import (  # noqa: E402,F401
    DEPT, FACULTY_USER, HOD_USER, SECTION, SEMESTER, STUDENT_EMPTY,
    STUDENT_OK, STUDENT_RISK, STUDENT_UNKNOWN, SUBJECT_LAB, SUBJECT_THEORY,
    YEAR,
)


@pytest.fixture(scope="session")
def agents():
    Base.metadata.create_all(bind=engine)
    from backend.app.agents import get_agents
    return get_agents()


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="session", autouse=True)
def base_data():
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        mini_institution.build(s)
    finally:
        s.close()
