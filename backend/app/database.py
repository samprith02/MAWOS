"""SQLAlchemy engine + session factory for the Shared Institutional Context Store."""
from sqlalchemy import create_engine
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
