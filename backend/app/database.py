"""SQLAlchemy engine + session factory for the Shared Institutional Context Store."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from . import config

connect_args = {}
if config.DATABASE_URL.startswith("sqlite"):
    # Agents run in one process across async handlers/threads.
    connect_args = {"check_same_thread": False}

engine = create_engine(config.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_session():
    """FastAPI dependency: yield a DB session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Light auto-migration for SQLite dev databases.
#
# Base.metadata.create_all() only creates tables that don't exist yet -- it
# never adds a column to a table that's already there. That's fine for a
# brand-new mawos.db, but anyone with an existing dev database from before
# columns like BookRequest.slip_code / LibraryFine.paid_at existed would hit
# a hard "no such column" error. This adds any missing columns in place
# (SQLite only -- Postgres deployments should use a real migration tool
# like Alembic instead).
# ---------------------------------------------------------------------------
def run_light_migrations() -> None:
    if not config.DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if table.name not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(engine.dialect)
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
                print(f"[MAWOS] migrated: added {table.name}.{column.name}")
