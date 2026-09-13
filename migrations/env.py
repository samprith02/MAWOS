"""Alembic environment for MAWOS v4.

The database URL is taken from `backend.app.config` -- i.e. from
`MAWOS_DATABASE_URL` -- so migrations follow the same SQLite-in-dev /
Postgres-in-deployment split as the application (docs/v4/08_DEPLOYMENT.md
§3) and there is never a second source of truth for the connection string.

`alembic.ini`'s `sqlalchemy.url` is deliberately left empty for that reason.
"""
from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import config as app_config   # noqa: E402
from backend.app import models                 # noqa: E402,F401
from backend.app.database import Base          # noqa: E402

cfg = context.config
if cfg.config_file_name is not None:
    fileConfig(cfg.config_file_name)

cfg.set_main_option("sqlalchemy.url",
                    app_config.DATABASE_URL.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=cfg.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata,
                      literal_binds=True,
                      render_as_batch=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        cfg.get_section(cfg.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata,
            # SQLite cannot ALTER most things in place; batch mode rewrites
            # the table instead. Harmless on Postgres, essential in dev.
            render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
