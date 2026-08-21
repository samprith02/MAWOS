"""Copy the shipped SQLite database into the configured PostgreSQL database.

The destination database must already exist and must be empty. This utility
creates tables from the SQLAlchemy models, copies rows in foreign-key order,
and advances PostgreSQL sequences for copied integer primary keys.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
from pathlib import Path
import sys

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, insert, text

# Allow the utility to be run directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.database import Base, engine
from backend.app.models import (  # noqa: F401 - importing models registers tables
    Application,
    AttendanceRecord,
    AttendanceSummary,
    Department,
    ExamSchedule,
    Faculty,
    FeeRecord,
    HallTicket,
    IntentLog,
    MarksRecord,
    Notification,
    PlacementDrive,
    PlacementShortlist,
    ScholarshipAssessment,
    Student,
    Subject,
    TeachingAssignment,
    TimetableSlot,
    User,
    WorkflowEvent,
)


def _parse_value(value, column):
    if value is None:
        return None
    if isinstance(column.type, Boolean):
        return bool(value)
    if isinstance(column.type, DateTime):
        if isinstance(value, dt.datetime):
            return value.replace(tzinfo=None)
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    if isinstance(column.type, Date):
        if isinstance(value, dt.date):
            return value
        return dt.date.fromisoformat(str(value)[:10])
    if isinstance(column.type, Integer):
        return int(value)
    if isinstance(column.type, Float):
        return float(value)
    return value


def _sqlite_rows(sqlite, table):
    columns = list(table.columns)
    names = ", ".join(f'"{column.name}"' for column in columns)
    rows = sqlite.execute(f'SELECT {names} FROM "{table.name}"').fetchall()
    return [
        {column.name: _parse_value(value, column) for column, value in zip(columns, row)}
        for row in rows
    ]


def _advance_sequences(connection):
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if not isinstance(column.type, Integer) or not column.primary_key:
                continue
            maximum = connection.execute(
                text(f'SELECT MAX("{column.name}") FROM "{table.name}"')
            ).scalar()
            if maximum is None:
                continue
            sequence = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": f"public.{table.name}", "column_name": column.name},
            ).scalar()
            if sequence:
                connection.execute(
                    text("SELECT setval(:sequence_name, :maximum, true)"),
                    {"sequence_name": sequence, "maximum": maximum},
                )


def migrate(source: Path) -> dict[str, int]:
    if not source.exists():
        raise FileNotFoundError(source)

    sqlite = sqlite3.connect(source)
    sqlite.row_factory = sqlite3.Row
    try:
        source_tables = {
            row[0]
            for row in sqlite.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        expected_tables = {table.name for table in Base.metadata.sorted_tables}
        missing = expected_tables - source_tables
        if missing:
            raise RuntimeError(f"SQLite source is missing tables: {sorted(missing)}")

        Base.metadata.create_all(bind=engine)
        counts: dict[str, int] = {}
        with engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                source_count = sqlite.execute(
                    f'SELECT COUNT(*) FROM "{table.name}"'
                ).fetchone()[0]
                destination_count = connection.execute(
                    text(f'SELECT COUNT(*) FROM "{table.name}"')
                ).scalar_one()
                if destination_count:
                    raise RuntimeError(
                        f'Destination table "{table.name}" is not empty '
                        f"({destination_count} rows); refusing to duplicate data."
                    )
                rows = _sqlite_rows(sqlite, table)
                for start in range(0, len(rows), 1000):
                    connection.execute(insert(table), rows[start : start + 1000])
                counts[table.name] = source_count
            _advance_sequences(connection)
        return counts
    finally:
        sqlite.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parents[1] / "mawos.db"
    )
    args = parser.parse_args()
    counts = migrate(args.source)
    print("Migrated tables:")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
