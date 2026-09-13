"""Write a generated institution into the database.

Kept separate from `build.py` so the generator stays ORM-free and testable
without a database: `build()` produces plain rows, this maps them onto
models. That separation is what lets `tests/test_generator.py` check
determinism without touching SQLite at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.auth import hash_password            # noqa: E402
from backend.app.models import (                      # noqa: E402
    AttendanceRecord, Department, ExamSchedule, Faculty, FacultyAvailability,
    FeeRecord, MarksRecord, PlacementDrive, Request, Room, Student, Subject,
    TeachingAssignment, User,
)
from data.generator.build import Generated, build     # noqa: E402
from data.generator.config import load                # noqa: E402

CHUNK = 25_000


def write(db, g: Generated) -> dict:
    """Insert a generated institution. Assumes an empty schema."""
    db.bulk_insert_mappings(Department, g.departments)
    db.bulk_insert_mappings(Subject, g.subjects)
    db.bulk_insert_mappings(Room, g.rooms)
    db.bulk_insert_mappings(Faculty, g.faculty)
    db.flush()

    db.bulk_insert_mappings(TeachingAssignment, g.teaching)
    db.bulk_insert_mappings(FacultyAvailability, g.availability)
    db.bulk_insert_mappings(Student, g.students)
    db.flush()

    # Passwords are hashed once per distinct plaintext, not once per user:
    # 1,277 users share three demo passwords and scrypt is deliberately slow.
    cache: dict[str, str] = {}
    users = []
    for u in g.users:
        pw = u["password"]
        if pw not in cache:
            cache[pw] = hash_password(pw)
        users.append({"username": u["username"], "password_hash": cache[pw],
                      "role": u["role"], "display_name": u["display_name"],
                      "usn": u["usn"], "faculty_id": u["faculty_id"],
                      "dept_code": u["dept_code"]})
    db.bulk_insert_mappings(User, users)

    for i in range(0, len(g.attendance), CHUNK):
        db.bulk_insert_mappings(AttendanceRecord, g.attendance[i:i + CHUNK])
    db.bulk_insert_mappings(MarksRecord, g.marks)
    db.bulk_insert_mappings(FeeRecord, g.fees)
    db.bulk_insert_mappings(ExamSchedule, g.exams)
    db.bulk_insert_mappings(PlacementDrive, g.drives)
    db.bulk_insert_mappings(Request, g.requests)
    db.commit()
    return g.counts()


def seed_if_empty(session_factory, reference_date=None) -> bool:
    """Idempotent bootstrap. Returns True only if it actually seeded."""
    db = session_factory()
    try:
        if db.query(Student).count() > 0:
            return False
        inst = load()
        g = build(inst, reference_date=reference_date)
        write(db, g)
        return True
    finally:
        db.close()
