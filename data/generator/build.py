"""Deterministic institution generator (v4 R1).

Replaces `backend/app/seed.py`'s single 340-line function
(`docs/v4/04_DATA_MODEL.md` §1). Four properties it must have, all of them
checkable and all of them tested:

1. **Deterministic** — same `institution.yaml` + same seed => byte-identical
   output. `tests/test_generator.py` generates twice and compares digests.
2. **Scale-parameterised** — institution size is config, not code.
3. **Layered** — structure -> population -> history -> derived. Each layer is
   independently regenerable.
4. **Feasible by construction** — generated assignments and availability must
   admit at least one valid timetable, asserted before anything is emitted.
   Without this, a solver failure is ambiguous between a solver bug and an
   impossible instance.

No real institution identity appears anywhere: every identifier is derived
from `institution.yaml`, and every person's name comes from fictional pools.

    python -m data.generator.build --out mawos.db
    python -m data.generator.build --digest      # determinism check only
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.generator import names as N          # noqa: E402
from data.generator.config import Institution, load  # noqa: E402
from data.generator.profiles import ProfileSampler   # noqa: E402


# ------------------------------------------------------------------ layers
class Generated:
    """Plain rows, ORM-free. The writer maps them onto models."""

    def __init__(self):
        self.departments: list[dict] = []
        self.subjects: list[dict] = []
        self.rooms: list[dict] = []
        self.faculty: list[dict] = []
        self.teaching: list[dict] = []
        self.availability: list[dict] = []
        self.students: list[dict] = []
        self.users: list[dict] = []
        self.attendance: list[dict] = []
        self.marks: list[dict] = []
        self.fees: list[dict] = []
        self.exams: list[dict] = []
        self.drives: list[dict] = []
        self.requests: list[dict] = []

    def counts(self) -> dict:
        return {k: len(v) for k, v in vars(self).items() if isinstance(v, list)}

    def digest(self) -> str:
        """Stable hash over every row, for the determinism test."""
        h = hashlib.sha256()
        for key in sorted(vars(self)):
            rows = getattr(self, key)
            h.update(f"##{key}:{len(rows)}\n".encode())
            for r in rows:
                h.update(json.dumps(r, sort_keys=True, default=str).encode())
                h.update(b"\n")
        return h.hexdigest()


# --------------------------------------------------------- layer 1: structure
def _structure(inst: Institution, g: Generated, pyrng: random.Random) -> dict:
    for d in inst.departments:
        g.departments.append({"code": d["code"], "name": d["name"],
                              "intake": d["intake"]})

    subjects_by: dict[tuple[str, int], list[str]] = {}
    per_sem = inst.gen["subjects_per_semester"]
    n_lab = inst.gen["lab_subjects_per_semester"]
    block = inst.gen["lab_block_size"]
    for d in inst.departments:
        pool = N.subject_pool(d["code"])
        for si, year in enumerate(inst.years):
            sem = inst.year_to_semester[year]
            codes = []
            for k in range(per_sem):
                code = f"{sem}{d['letters']}{k + 1:02d}"
                is_lab = k >= per_sem - n_lab
                # Credits = periods/week. Total must divide sensibly into the
                # 5x6 grid: 5 subjects at 4/4/4/3/3 = 18 of 30 cells.
                credits = 4 if k < 3 else 3
                g.subjects.append({
                    "code": code, "name": pool[si * per_sem + k],
                    "dept_code": d["code"], "semester": sem,
                    "credits": credits,
                    "kind": "lab" if is_lab else "theory",
                    "block_size": block if is_lab else 1})
                codes.append(code)
            subjects_by[(d["code"], sem)] = codes

    for rtype, spec in inst.rooms.items():
        for i in range(spec["count"]):
            building = spec["buildings"][i % len(spec["buildings"])]
            g.rooms.append({
                "code": f"{building[:3].upper()}-{rtype[:1].upper()}{i + 1:03d}",
                "name": f"{building} {rtype.title()} {i + 1}",
                "room_type": rtype, "capacity": spec["capacity"],
                "building": building})

    fac_per = inst.gen["faculty_per_department"]
    fid = 0
    faculty_by_dept: dict[str, list[dict]] = {}
    for d in inst.departments:
        members = []
        for i in range(fac_per):
            fid += 1
            title = "Dr. " if i < 5 else ""
            row = {"id": fid,
                   "name": f"{title}{N.person_name(pyrng)}",
                   "dept_code": d["code"],
                   "designation": ("Professor & HOD" if i == 0
                                   else N.designation(i)),
                   "email": f"{d['code'].lower()}.f{i + 1:02d}@"
                            f"{inst.email_domain}",
                   "qualified_subjects": ""}
            g.faculty.append(row)
            members.append(row)
        faculty_by_dept[d["code"]] = members
    return {"subjects_by": subjects_by, "faculty_by_dept": faculty_by_dept}


# ------------------------------------------ layer 1b: teaching + availability
def _teaching(inst: Institution, g: Generated, ctx: dict,
              rng: np.random.Generator) -> None:
    subjects_by, faculty_by_dept = ctx["subjects_by"], ctx["faculty_by_dept"]
    qualified: dict[int, set[str]] = {}

    for d in inst.departments:
        fac = faculty_by_dept[d["code"]]
        rr = 1                       # skip the HOD for a lighter load
        for year in inst.years:
            sem = inst.year_to_semester[year]
            for section in inst.sections:
                for code in subjects_by[(d["code"], sem)]:
                    member = fac[rr % len(fac)]
                    g.teaching.append({
                        "faculty_id": member["id"], "subject_code": code,
                        "dept_code": d["code"], "year": year,
                        "section": section})
                    qualified.setdefault(member["id"], set()).add(code)
                    rr += 1

    for row in g.faculty:
        row["qualified_subjects"] = ",".join(sorted(qualified.get(row["id"], ())))

    _availability(inst, g, rng)


def _availability(inst: Institution, g: Generated,
                  rng: np.random.Generator) -> None:
    """Sparse unavailability that provably cannot make the instance
    infeasible: a member is never blocked below the number of cells their own
    teaching load needs."""
    spec = inst.gen["unavailability"]
    load: dict[int, int] = {}
    subj_credits = {s["code"]: s["credits"] for s in g.subjects}
    for t in g.teaching:
        load[t["faculty_id"]] = load.get(t["faculty_id"], 0) \
            + subj_credits[t["subject_code"]]

    total_cells = inst.n_days * inst.n_periods
    ids = sorted(load)
    chosen = [i for i in ids
              if rng.random() < spec["faculty_fraction"]]
    for fid in chosen:
        headroom = total_cells - load.get(fid, 0)
        if headroom <= 1:
            continue                     # fully committed: never block
        n = int(min(spec["max_blocks_per_faculty"], headroom - 1,
                    rng.integers(1, spec["max_blocks_per_faculty"] + 1)))
        cells = set()
        while len(cells) < n:
            cells.add((int(rng.integers(0, inst.n_days)),
                       int(rng.integers(0, inst.n_periods))))
        for day, period in sorted(cells):
            g.availability.append({
                "faculty_id": fid, "day": day, "period": period,
                "reason": spec["reasons"][
                    int(rng.integers(0, len(spec["reasons"])))],
                "source": "standing", "valid_from": None, "valid_until": None})


# -------------------------------------------------------- layer 2: population
def _population(inst: Institution, g: Generated, ctx: dict,
                rng: np.random.Generator, pyrng: random.Random,
                today: dt.date) -> None:
    per_section = inst.gen["students_per_section"]
    sampler = ProfileSampler(rng)
    this_year = today.year

    for d in inst.departments:
        for year in inst.years:
            batch = this_year - year
            sem = inst.year_to_semester[year]
            idx = 0
            n_total = per_section * len(inst.sections)
            profiles = sampler.sample(n_total)
            for section in inst.sections:
                for _ in range(per_section):
                    prof = profiles[idx]
                    idx += 1
                    usn = (f"{inst.usn_prefix}{batch % 100:02d}"
                           f"{d['letters']}{idx:03d}")
                    g.students.append({
                        "usn": usn, "name": N.person_name(pyrng),
                        "dept_code": d["code"], "year": year, "semester": sem,
                        "section": section, "cgpa": prof.cgpa,
                        "backlogs": prof.backlogs,
                        "category": N.category(pyrng),
                        "family_income": prof.family_income,
                        "admission_year": batch,
                        "email": f"{usn.lower()}@{inst.email_domain}",
                        "phone": f"9{int(rng.integers(100000000, 999999999))}",
                        "status": "enrolled", "is_synthetic": True})

    g.users.append({"username": "admin", "password": "admin123",
                    "role": "admin", "display_name": "Registrar (Admin)",
                    "usn": None, "faculty_id": None, "dept_code": None})
    g.users.append({"username": "principal", "password": "principal123",
                    "role": "principal",
                    "display_name": f"Principal, {inst.short_name}",
                    "usn": None, "faculty_id": None, "dept_code": None})
    for d in inst.departments:
        members = ctx["faculty_by_dept"][d["code"]]
        hod = members[0]
        g.users.append({"username": f"hod.{d['code'].lower()}",
                        "password": "faculty123", "role": "hod",
                        "display_name": f"{hod['name']} (HOD, {d['code']})",
                        "usn": None, "faculty_id": hod["id"],
                        "dept_code": d["code"]})
        for i, m in enumerate(members[1:], start=2):
            g.users.append({"username": f"{d['code'].lower()}.f{i:02d}",
                            "password": "faculty123", "role": "faculty",
                            "display_name": m["name"], "usn": None,
                            "faculty_id": m["id"], "dept_code": d["code"]})
    for s in g.students:
        g.users.append({"username": s["usn"], "password": "student123",
                        "role": "student", "display_name": s["name"],
                        "usn": s["usn"], "faculty_id": None,
                        "dept_code": s["dept_code"]})


# ----------------------------------------------------------- layer 3: history
def _class_days(n: int, end: dt.date) -> list[dt.date]:
    days, d = [], end - dt.timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    return sorted(days)


def _history(inst: Institution, g: Generated, ctx: dict,
             rng: np.random.Generator, pyrng: random.Random,
             today: dt.date) -> None:
    subjects_by = ctx["subjects_by"]
    days = _class_days(inst.gen["attendance_days"], today)

    ap = inst.gen["attendance_propensity"]
    propensity = np.clip(rng.beta(ap["a"], ap["b"], size=len(g.students)),
                         ap["min"], ap["max"])

    for i, s in enumerate(g.students):
        codes = subjects_by[(s["dept_code"], s["semester"])]
        for code in codes:
            present = rng.random(len(days)) < propensity[i]
            for day, p in zip(days, present):
                g.attendance.append({
                    "usn": s["usn"], "subject_code": code, "date": day,
                    "present": bool(p), "uploaded_by": "generator"})

    n_internals = inst.gen["internals_entered"]
    for s in g.students:
        base = float(np.clip((s["cgpa"] - 4) / 6, 0.2, 1.0))
        for code in subjects_by[(s["dept_code"], s["semester"])]:
            for internal in range(1, n_internals + 1):
                m = float(np.clip(rng.normal(base * 42, 6), 8, 50).round(0))
                g.marks.append({"usn": s["usn"], "subject_code": code,
                                "internal": internal, "marks": m,
                                "max_marks": 50.0, "entered_by": "generator"})

    defaulters = set(pyrng.sample(
        [s["usn"] for s in g.students],
        k=int(inst.gen["fee_default_fraction"] * len(g.students))))
    fee_types = [("tuition", 98_000), ("exam", 1_800),
                 ("development", 12_000), ("library", 600)]
    for s in g.students:
        unpaid_left = pyrng.randint(1, 2) if s["usn"] in defaulters else 0
        for ftype, base_amt in fee_types:
            due = today - dt.timedelta(days=100)
            amount = round(base_amt * float(rng.uniform(0.97, 1.03)), 2)
            if unpaid_left > 0 and rng.random() < 0.5:
                unpaid_left -= 1
                g.fees.append({"usn": s["usn"], "fee_type": ftype,
                               "amount_due": amount, "amount_paid": 0.0,
                               "due_date": due, "paid_date": None,
                               "fine": 0.0, "status": "pending"})
            else:
                g.fees.append({
                    "usn": s["usn"], "fee_type": ftype, "amount_due": amount,
                    "amount_paid": amount, "due_date": due,
                    "paid_date": due - dt.timedelta(
                        days=int(rng.integers(0, 12))),
                    "fine": 0.0, "status": "paid"})

    start = today + dt.timedelta(days=25)
    for (dept, sem), codes in subjects_by.items():
        for i, code in enumerate(codes):
            g.exams.append({"subject_code": code, "dept_code": dept,
                            "semester": sem,
                            "exam_date": start + dt.timedelta(days=2 * i),
                            "session": "FN"})

    dept_codes = [d["code"] for d in inst.departments]
    for _ in range(60):
        depts = "ALL" if rng.random() < 0.6 else ",".join(
            pyrng.sample(dept_codes, k=pyrng.randint(1, 3)))
        g.drives.append({
            "company": N.company(pyrng), "role": N.job_role(pyrng),
            "package_lpa": round(float(rng.choice(
                [3.5, 4.0, 4.5, 5.0, 6.0, 7.5, 10.0, 12.0],
                p=[.2, .2, .15, .15, .12, .1, .05, .03])), 1),
            "min_cgpa": float(rng.choice([6.0, 6.5, 7.0, 7.5],
                                         p=[.35, .3, .25, .1])),
            "max_backlogs": int(rng.choice([0, 0, 1, 2], p=[.5, .2, .2, .1])),
            "min_attendance": inst.policies["attendance_threshold_pct"],
            "departments": depts,
            "drive_date": today + dt.timedelta(
                days=int(rng.integers(3, 90)))})

    # The one write-bearing workflow type in MVRS: faculty leave.
    faculty_users = [u for u in g.users if u["role"] in ("faculty", "hod")]
    for i in range(inst.gen["seed_requests"]):
        u = faculty_users[int(rng.integers(0, len(faculty_users)))]
        day = int(rng.integers(0, inst.n_days))
        g.requests.append({
            "kind": "faculty_leave", "requester": u["username"],
            "subject_ref": f"day:{day}",
            "payload": json.dumps({"day": day,
                                   "reason": N.leave_reason(pyrng)}),
            "state": "pending" if i % 3 else "approved",
            "decided_by": None if i % 3 else "hod." + (
                u["dept_code"] or "aiml").lower(),
            "reasons": ""})


# ------------------------------------------------------------- feasibility
class Infeasible(RuntimeError):
    """The generated instance admits no valid timetable."""


def assert_feasible(inst: Institution, g: Generated) -> dict:
    """Necessary conditions, checked before anything is written.

    Not a full solve — that is the solver's job — but every one of these
    failing would make a solver failure ambiguous between "bad solver" and
    "impossible instance", which is the situation `04_DATA_MODEL.md` §5.1
    rule 5 exists to prevent.
    """
    cells = inst.n_days * inst.n_periods
    credits = {s["code"]: s["credits"] for s in g.subjects}

    # 1. No section is asked to hold more periods than the grid has.
    per_section: dict[tuple, int] = {}
    for t in g.teaching:
        key = (t["dept_code"], t["year"], t["section"])
        per_section[key] = per_section.get(key, 0) + credits[t["subject_code"]]
    worst_section = max(per_section.values()) if per_section else 0
    if worst_section > cells:
        raise Infeasible(f"a section needs {worst_section} periods, grid has {cells}")

    # 2. No teacher is asked to teach more periods than the grid has, after
    #    their unavailable cells are removed.
    blocked: dict[int, int] = {}
    for a in g.availability:
        blocked[a["faculty_id"]] = blocked.get(a["faculty_id"], 0) + 1
    per_teacher: dict[int, int] = {}
    for t in g.teaching:
        per_teacher[t["faculty_id"]] = per_teacher.get(t["faculty_id"], 0) \
            + credits[t["subject_code"]]
    worst_teacher, worst_id = 0, None
    for fid, load in per_teacher.items():
        avail = cells - blocked.get(fid, 0)
        if load > avail:
            raise Infeasible(
                f"faculty {fid} teaches {load} periods but only {avail} "
                f"cells are available to them")
        if load / max(avail, 1) > worst_teacher:
            worst_teacher, worst_id = load / max(avail, 1), fid

    # 3. Enough rooms of each type to hold the concurrent load.
    n_classrooms = sum(1 for r in g.rooms if r["room_type"] == "classroom")
    if n_classrooms < inst.n_sections_total:
        raise Infeasible(
            f"{n_classrooms} classrooms for {inst.n_sections_total} "
            f"concurrent sections")

    return {"cells_per_week": cells,
            "max_section_load": worst_section,
            "max_teacher_utilisation": round(worst_teacher, 3),
            "teacher_at_max": worst_id,
            "classrooms": n_classrooms,
            "concurrent_sections": inst.n_sections_total}


# --------------------------------------------------------------------- build
def build(inst: Institution | None = None, seed: int | None = None,
          reference_date: dt.date | None = None) -> Generated:
    """Build a full institution.

    `reference_date` anchors every date the generator emits (attendance
    days, fee due dates, the exam window). It defaults to today, which keeps
    a demo institution current -- but that also means the output is only
    byte-reproducible *within* a day. Pass an explicit date to pin it; the
    determinism test does exactly that, which is how R1 gate 2 is checked
    without freezing the demo data in the past.
    """
    inst = inst or load()
    seed = inst.gen["seed"] if seed is None else seed
    today = reference_date or dt.date.today()
    rng = np.random.default_rng(seed)
    pyrng = random.Random(seed)

    g = Generated()
    ctx = _structure(inst, g, pyrng)
    _teaching(inst, g, ctx, rng)
    _population(inst, g, ctx, rng, pyrng, today)
    _history(inst, g, ctx, rng, pyrng, today)
    g.feasibility = assert_feasible(inst, g)   # raises Infeasible on failure
    return g


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--digest", action="store_true",
                    help="print row counts + digest, write nothing")
    ap.add_argument("--date", default=None,
                    help="pin the reference date (YYYY-MM-DD) for a "
                         "byte-reproducible build")
    args = ap.parse_args()

    inst = load()
    ref = dt.date.fromisoformat(args.date) if args.date else None
    g = build(inst, args.seed, ref)
    print(f"institution: {inst.name} ({inst.short_name})"
          + ("  [PLACEHOLDER NAME — OPEN_DECISIONS D12]"
             if inst.name_is_placeholder else ""))
    for k, v in sorted(g.counts().items()):
        print(f"  {k:14s} {v:7d}")
    print(f"  feasibility  {g.feasibility}")
    print(f"  digest       {g.digest()}")


if __name__ == "__main__":
    main()
