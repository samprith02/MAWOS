"""SQLAlchemy engine and session lifecycle for MAWOS."""
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, declarative_base

from . import config

connect_args = {}
if config.DATABASE_URL.startswith("sqlite"):
    # Agents run in one process across async handlers/threads.
    connect_args = {"check_same_thread": False}

engine = create_engine(
    config.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def verify_existing_schema() -> None:
    """Fail safely when a non-SQLite database lacks MAWOS tables."""
    from . import models  # noqa: F401 - register every ORM table before inspection.

    expected_tables = set(Base.metadata.tables)
    with engine.connect() as connection:
        existing_tables = set(inspect(connection).get_table_names(schema="public"))
    missing_tables = expected_tables - existing_tables
    if missing_tables:
        raise RuntimeError(
            "Configured database is missing required MAWOS tables: "
            + ", ".join(sorted(missing_tables))
        )


def get_session():
    """FastAPI dependency: yield a DB session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
