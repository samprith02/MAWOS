"""FROZEN v2 greedy timetable solver — the scheduling baseline.

Copied from `backend/app/agents/timetable.py` at P0 (MAWOS v2, commit
46a0c6e). This is the comparator for E4. P1 replaces the live solver with
greedy-seed + simulated annealing; without a pinned copy of what came
before, "we improved the scheduler" would be unfalsifiable.

Do not edit, and in particular do not fix the defect it exists to
demonstrate: this solver optimises **hard feasibility only**. It has no
objective function, so a schedule with holes at 09:00 and 12:15 scores
exactly as well as a compact one. Measured on the shipped database:

    42.0% of section-days have no first period  (84 / 200)
    225 idle gaps inside days  (1.12 per section-day)
    within-section daily-load sigma  1.0 periods

    sha256(source timetable.py at freeze) = aff9dd553c9b0b700d56f68c8cca9c14ba97ed84aaa6e8c06456dfca5a8096e0

Verbatim except for these import rewrites, forced by the move out of the
agents package:
      - 'from ..models import Department, TeachingAssignment, TimetableSlot'
        -> 'from backend.app.models import TeachingAssignment, TimetableSlot'
      - 'from .base import BaseAgent'
        -> 'BaseAgent = object'

The class no longer subclasses BaseAgent (it is bound to `object` above),
so the bus-publishing method `generate_and_announce` is inert here. The
solver itself — `generate`, and every constraint and restart in it — is
untouched.
"""
import random
import time

from backend.app.models import TeachingAssignment, TimetableSlot
BaseAgent = object

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PERIODS = ["9:00", "10:00", "11:15", "12:15", "14:00", "15:00"]
N_DAYS, N_PERIODS = 5, 6


class TimetableAgent(BaseAgent):
    name = "timetable_agent"
    description = ("Conflict-free weekly timetable generation "
                   "(global teacher constraints), CSV/print export")

    def generate(self, db, dept_code: str | None = None,
                 max_restarts: int = 40, seed: int = 7) -> dict:
        """(Re)generate timetables for one department or the whole institution."""
        q = db.query(TeachingAssignment)
        if dept_code:
            q = q.filter(TeachingAssignment.dept_code == dept_code)
        assignments = q.all()
        if not assignments:
            return {"ok": False, "error": "no teaching assignments found"}

        # Existing bookings by faculty OUTSIDE the scope being regenerated
        # must stay respected (global conflict-freedom).
        outside = db.query(TimetableSlot)
        if dept_code:
            outside = outside.filter(TimetableSlot.dept_code != dept_code)
        else:
            outside = outside.filter(False)
        busy_base: set[tuple[int, int, int]] = {
            (s.faculty_id, s.day, s.period) for s in outside.all()}

        sections: dict[tuple, list[TeachingAssignment]] = {}
        for a in assignments:
            sections.setdefault((a.dept_code, a.year, a.section), []).append(a)

        rng = random.Random(seed)
        t0 = time.perf_counter()
        best = None
        for restart in range(max_restarts):
            busy = set(busy_base)
            placed: list[dict] = []
            unplaced = 0
            for key in sorted(sections):
                sec_free = {(d, p) for d in range(N_DAYS) for p in range(N_PERIODS)}
                # hardest-first: subjects needing more periods placed first
                todo = sorted(sections[key],
                              key=lambda a: -a.subject.credits)
                for a in todo:
                    per_day = {d: 0 for d in range(N_DAYS)}
                    need = a.subject.credits
                    slots = sorted(sec_free, key=lambda s: rng.random())
                    for (d, p) in slots:
                        if need == 0:
                            break
                        if per_day[d] >= 2:
                            continue
                        if (a.faculty_id, d, p) in busy:
                            continue
                        busy.add((a.faculty_id, d, p))
                        sec_free.discard((d, p))
                        per_day[d] += 1
                        placed.append(dict(dept_code=a.dept_code, year=a.year,
                                           section=a.section, day=d, period=p,
                                           subject_code=a.subject_code,
                                           faculty_id=a.faculty_id,
                                           room=f"{a.dept_code}-{a.year}{a.section}"))
                        need -= 1
                    unplaced += need
            if best is None or unplaced < best[0]:
                best = (unplaced, placed, restart + 1)
            if best[0] == 0:
                break

        unplaced, placed, restarts = best
        # replace scope atomically
        dq = db.query(TimetableSlot)
        if dept_code:
            dq = dq.filter(TimetableSlot.dept_code == dept_code)
        dq.delete()
        db.bulk_insert_mappings(TimetableSlot, placed)
        db.commit()
        elapsed = round((time.perf_counter() - t0) * 1000, 1)

        total_needed = sum(a.subject.credits for a in assignments)
        result = {
            "ok": True, "scope": dept_code or "ALL",
            "sections": len(sections), "slots_placed": len(placed),
            "slots_required": total_needed, "unplaced": unplaced,
            "placement_rate": round(100 * len(placed) / total_needed, 2),
            "teacher_conflicts": 0,  # guaranteed by construction
            "restarts_used": restarts, "solve_ms": elapsed,
        }
        return result

    async def generate_and_announce(self, db, dept_code: str | None,
                                    triggered_by: str) -> dict:
        result = self.generate(db, dept_code)
        if result.get("ok"):
            await self.publish("timetable.generated", {
                "scope": result["scope"], "sections": result["sections"],
                "placement_rate": result["placement_rate"],
                "solve_ms": result["solve_ms"], "triggered_by": triggered_by})
        return result

    def grid(self, db, dept_code: str, year: int, section: str) -> dict:
        slots = (db.query(TimetableSlot)
                   .filter_by(dept_code=dept_code, year=year, section=section)
                   .all())
        cells = {}
        for s in slots:
            cells[f"{s.day}-{s.period}"] = {
                "subject": s.subject_code, "subject_name": s.subject.name,
                "faculty": s.faculty.name, "room": s.room}
        return {"dept": dept_code, "year": year, "section": section,
                "days": DAYS, "periods": PERIODS, "cells": cells}

    def faculty_grid(self, db, faculty_id: int) -> dict:
        slots = db.query(TimetableSlot).filter_by(faculty_id=faculty_id).all()
        cells = {}
        for s in slots:
            cells[f"{s.day}-{s.period}"] = {
                "subject": s.subject_code, "subject_name": s.subject.name,
                "room": s.room,
                "class": f"{s.dept_code} {s.year}{s.section}"}
        return {"days": DAYS, "periods": PERIODS, "cells": cells}

    def csv_export(self, db, dept_code: str, year: int, section: str) -> str:
        g = self.grid(db, dept_code, year, section)
        lines = [f"Timetable,{dept_code} Year {year} Section {section}"]
        lines.append("Day," + ",".join(PERIODS))
        for d, day in enumerate(DAYS):
            row = [day]
            for p in range(N_PERIODS):
                c = g["cells"].get(f"{d}-{p}")
                row.append(f"{c['subject']} ({c['faculty']})" if c else "-")
            lines.append(",".join('"' + v + '"' if "," in v else v for v in row))
        return "\n".join(lines)
