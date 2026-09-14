"""Seeding entry points.

R1 (docs/v4/04_DATA_MODEL.md §1): the v2 340-line inline seeder is replaced
by `data/generator/`, a deterministic, scale-parameterised, feasibility-
asserting package driven entirely by `data/institution.yaml`. This module is
now the thin adapter the app boots through, so `main.py` is unchanged.

`bootstrap_evaluations` is unchanged in purpose: a one-time post-seed pass
that materialises attendance summaries and eligibility verdicts by calling
the agents directly rather than over the bus.
"""
from .database import SessionLocal
from .models import Student


def seed_all(per_section: int | None = None) -> bool:
    """Idempotent. Institution size lives in data/institution.yaml, not here
    -- `per_section` is accepted only so existing callers keep working, and
    overrides the configured value when given."""
    from data.generator import write_db
    from data.generator.config import load

    inst = load()
    if per_section is not None:
        inst.raw["generation"]["students_per_section"] = per_section
    return write_db.seed_if_empty(SessionLocal)


def bootstrap_evaluations(agents: dict) -> None:
    """One-time post-seed pass: summaries + eligibility, direct calls (no bus)."""
    db = SessionLocal()
    try:
        usns = [u for (u,) in db.query(Student.usn).all()]
        att = agents["attendance_agent"]
        for usn in usns:
            att._recompute_student(db, usn)
        db.commit()
        agents["finance_agent"].refresh_status(db)
        for usn in usns:
            agents["eligibility_agent"].evaluate_hall_ticket(db, usn)
            agents["eligibility_agent"].evaluate_scholarship(db, usn)
        db.commit()
        # Placement: final-year students only (realistic + fast).
        finals = [u for (u,) in db.query(Student.usn)
                  .filter(Student.year == 4).all()]
        for usn in finals:
            agents["placement_agent"].evaluate_student(db, usn)
        db.commit()
    finally:
        db.close()
