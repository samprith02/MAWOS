"""Synthetic seed v2 — a full institution.

5 departments x 4 years x 2 sections x ~30 students ≈ 1,200 students,
75 faculty with teaching assignments, per-semester subject catalogue,
admissions applications, fees, exam schedules, placement drives.
Deterministic (seeded RNG); statistically calibrated where the ML touches it
(see ml/calibrate.py and docs/DATASET_METHODOLOGY.md).
"""
import datetime as dt
import random

import numpy as np

from . import config
from .auth import hash_password
from .database import SessionLocal
from .models import (
    Application, AttendanceRecord, Department, ExamSchedule, Faculty,
    FeeRecord, MarksRecord, PlacementDrive, Student, Subject,
    TeachingAssignment, User,
)

RNG_SEED = 42

DEPARTMENTS = [
    ("AIML", "Artificial Intelligence & Machine Learning", "AI"),
    ("CSE", "Computer Science & Engineering", "CS"),
    ("ECE", "Electronics & Communication Engineering", "EC"),
    ("ME", "Mechanical Engineering", "ME"),
    ("CV", "Civil Engineering", "CV"),
]
DEPT_LETTERS = {code: letters for code, _, letters in DEPARTMENTS}

SUBJECT_POOLS = {
    "AIML": ["Machine Learning", "Deep Learning", "Data Mining", "NLP",
             "Computer Vision", "Big Data Analytics", "Reinforcement Learning",
             "MLOps", "AI Ethics", "Pattern Recognition", "Neural Networks",
             "Data Visualization", "Statistics for ML", "Python Programming",
             "Discrete Mathematics", "DBMS", "Operating Systems",
             "Computer Networks", "Software Engineering", "Linear Algebra"],
    "CSE": ["Data Structures", "Algorithms", "Operating Systems", "DBMS",
            "Computer Networks", "Compiler Design", "Web Technologies",
            "Cloud Computing", "Cyber Security", "Distributed Systems",
            "Software Engineering", "Theory of Computation", "Java Programming",
            "Microprocessors", "Discrete Mathematics", "Computer Graphics",
            "IoT Systems", "Mobile Computing", "DevOps", "System Design"],
    "ECE": ["Digital Electronics", "Analog Circuits", "Signals & Systems",
            "Communication Systems", "VLSI Design", "Embedded Systems",
            "Microwave Engineering", "Antenna Theory", "Control Systems",
            "DSP", "Network Analysis", "Electromagnetics", "Optical Comm.",
            "Wireless Networks", "Circuit Theory", "Power Electronics",
            "Satellite Comm.", "Radar Systems", "FPGA Design", "5G Systems"],
    "ME": ["Thermodynamics", "Fluid Mechanics", "Machine Design",
           "Manufacturing Processes", "Heat Transfer", "Dynamics of Machinery",
           "CAD/CAM", "Robotics", "Automobile Engineering", "Turbomachines",
           "Material Science", "Engineering Mechanics", "Metrology",
           "Operations Research", "IC Engines", "Mechatronics",
           "Finite Element Analysis", "Refrigeration & AC", "Kinematics",
           "Industrial Engineering"],
    "CV": ["Structural Analysis", "Concrete Technology", "Geotechnical Engg.",
           "Surveying", "Transportation Engg.", "Environmental Engg.",
           "Hydraulics", "Steel Structures", "Construction Management",
           "Estimation & Costing", "Building Materials", "Earthquake Engg.",
           "Foundation Engg.", "Water Resources", "Highway Engg.",
           "Remote Sensing & GIS", "Prestressed Concrete", "Bridge Engg.",
           "Irrigation Engg.", "Green Buildings"],
}

# Report team members — kept at their real USNs (AIML, 2023 batch -> year 3).
TEAM = {37: "Nikil S Suvarna", 38: "Pranit R Raj", 40: "Prathik",
        49: "Samprith C Amin"}

FIRST = ["Aditi", "Rahul", "Sneha", "Kiran", "Divya", "Manoj", "Pooja",
         "Vikas", "Anusha", "Rohan", "Shreya", "Karthik", "Meghana", "Nithin",
         "Bhavana", "Suhas", "Ramya", "Akash", "Deeksha", "Varun", "Ishita",
         "Tejas", "Nandini", "Yashas", "Prerana", "Chetan", "Sanjana", "Om"]
LAST = ["Shetty", "Rao", "Kamath", "Hegde", "Nayak", "Pai", "Kulkarni",
        "Bhat", "Acharya", "Salian", "Poojary", "Kini", "Prabhu", "Suvarna",
        "Ballal", "Amin", "Shenoy", "Mallya", "Karkera", "Devadiga"]

COMPANIES = ["Infosys", "TCS", "Wipro", "Accenture", "Cognizant", "IBM",
             "LTIMindtree", "Mphasis", "Capgemini", "Tech Mahindra", "Bosch",
             "Continental", "Sasken", "Happiest Minds", "UST", "EY GDS",
             "Deloitte", "KPMG", "Oracle", "SAP Labs", "Cisco", "Toyota",
             "L&T", "Tata Elxsi", "Nokia"]
ROLES = ["Software Engineer", "Systems Engineer", "Data Analyst", "GET",
         "Associate Consultant", "QA Engineer", "ML Engineer", "Design Engineer"]
DESIGNATIONS = ["Professor", "Associate Professor", "Assistant Professor",
                "Assistant Professor", "Assistant Professor"]

YEAR_TO_SEM = {1: 1, 2: 3, 3: 5, 4: 7}
SECTIONS = ["A", "B"]
PER_SECTION = 30


def _class_days(n_days: int, end: dt.date) -> list[dt.date]:
    days, d = [], end - dt.timedelta(days=1)
    while len(days) < n_days:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    return sorted(days)


def seed_all(per_section: int = PER_SECTION) -> bool:
    """Seed only an empty database. per_section scales the institution.

    Existing data is left untouched, including when a development operator
    explicitly enables demo seeding at startup.
    """
    db = SessionLocal()
    try:
        existing_models = (User, Student, Faculty, Department, Subject,
                           TeachingAssignment, Application, FeeRecord,
                           AttendanceRecord, MarksRecord, ExamSchedule,
                           PlacementDrive)
        if any(db.query(model).first() is not None for model in existing_models):
            return False
        rng = np.random.default_rng(RNG_SEED)
        pyrng = random.Random(RNG_SEED)
        today = dt.date.today()
        this_year = today.year

        # --- departments ----------------------------------------------------
        for code, name, _ in DEPARTMENTS:
            db.add(Department(code=code, name=name, intake=60))

        # --- subjects: 5 per odd semester per dept ---------------------------
        subjects_by = {}   # (dept, sem) -> [codes]
        for code, _, letters in DEPARTMENTS:
            pool = SUBJECT_POOLS[code]
            for si, sem in enumerate([1, 3, 5, 7]):
                codes = []
                for k in range(5):
                    sc = f"23{letters}{sem}{k + 1}"
                    db.add(Subject(code=sc, name=pool[si * 5 + k],
                                   dept_code=code, semester=sem,
                                   credits=4 if k < 3 else 3))
                    codes.append(sc)
                subjects_by[(code, sem)] = codes

        # --- faculty: 15 per department --------------------------------------
        faculty_by_dept = {}
        for code, _, _ in DEPARTMENTS:
            members = []
            for i in range(15):
                name = f"{'Dr. ' if i < 5 else ''}{pyrng.choice(FIRST)} {pyrng.choice(LAST)}"
                f = Faculty(name=name, dept_code=code,
                            designation="Professor & HOD" if i == 0
                            else DESIGNATIONS[min(i // 3, 4)],
                            email=f"{code.lower()}.f{i + 1:02d}@mite.ac.in")
                db.add(f)
                members.append(f)
            faculty_by_dept[code] = members
        db.flush()

        # --- students: dept x year x section ---------------------------------
        students = []
        for code, _, letters in DEPARTMENTS:
            for year in (1, 2, 3, 4):
                batch = this_year - year   # admission year
                sem = YEAR_TO_SEM[year]
                idx = 0
                for section in SECTIONS:
                    for _ in range(per_section):
                        idx += 1
                        usn = f"4MT{batch % 100:02d}{letters}{idx:03d}"
                        name = None
                        if code == "AIML" and year == 3:
                            name = TEAM.get(idx)
                        name = name or f"{pyrng.choice(FIRST)} {pyrng.choice(LAST)}"
                        cgpa = float(np.clip(rng.normal(7.4, 1.0), 4.5, 9.9).round(2))
                        students.append(Student(
                            usn=usn, name=name, dept_code=code, year=year,
                            semester=sem, section=section, cgpa=cgpa,
                            backlogs=int(rng.choice([0, 0, 0, 1, 1, 2, 3],
                                                    p=[.55, .12, .1, .1, .06, .04, .03])),
                            category=pyrng.choice(["GM", "GM", "OBC", "SC", "ST", "CAT-1"]),
                            family_income=float(np.clip(
                                rng.lognormal(13.0, 0.6), 80_000, 2_500_000).round(-3)),
                            admission_year=batch,
                            email=f"{usn.lower()}@mite.ac.in",
                            phone=f"9{rng.integers(100000000, 999999999)}"))
        db.add_all(students)
        db.flush()

        # --- teaching assignments: round-robin within department --------------
        for code, _, _ in DEPARTMENTS:
            fac = faculty_by_dept[code]
            rr = 1  # skip HOD (index 0) for a lighter load; HOD gets last picks
            for year in (1, 2, 3, 4):
                sem = YEAR_TO_SEM[year]
                for section in SECTIONS:
                    for sc in subjects_by[(code, sem)]:
                        db.add(TeachingAssignment(
                            faculty_id=fac[rr % len(fac)].id, subject_code=sc,
                            dept_code=code, year=year, section=section))
                        rr += 1

        # --- users -------------------------------------------------------------
        student_pw = hash_password("student123")
        faculty_pw = hash_password("faculty123")
        db.add(User(username="admin", password_hash=hash_password("admin123"),
                    role="admin", display_name="Registrar (Admin)"))
        db.add(User(username="principal",
                    password_hash=hash_password("principal123"),
                    role="principal", display_name="Dr. Prashanth C M, Principal"))
        for code, _, _ in DEPARTMENTS:
            hod = faculty_by_dept[code][0]
            db.add(User(username=f"hod.{code.lower()}", password_hash=faculty_pw,
                        role="hod", display_name=f"{hod.name} (HOD, {code})",
                        faculty_id=hod.id, dept_code=code))
            for i, f in enumerate(faculty_by_dept[code][1:], start=2):
                db.add(User(username=f"{code.lower()}.f{i:02d}",
                            password_hash=faculty_pw, role="faculty",
                            display_name=f.name, faculty_id=f.id, dept_code=code))
        for s in students:
            db.add(User(username=s.usn, password_hash=student_pw, role="student",
                        display_name=s.name, usn=s.usn, dept_code=s.dept_code))

        # --- attendance: 30 class days for every student's 5 subjects ----------
        days = _class_days(30, today)
        # Per-student attendance propensity. Beta(10, 1.8) has mean ~0.85 and
        # leaves roughly 15-20% of the cohort below the 75% rule — the
        # realistic shortage rate for a VTU-affiliated college, and enough to
        # exercise the shortage/hall-ticket workflows without making the
        # institution look pathological.
        propensity = np.clip(rng.beta(10, 1.8, size=len(students)), 0.45, 0.995)
        rows, chunk = [], 25_000
        for si, s in enumerate(students):
            for sc in subjects_by[(s.dept_code, s.semester)]:
                present = rng.random(len(days)) < propensity[si]
                for day, p in zip(days, present):
                    rows.append(dict(usn=s.usn, subject_code=sc, date=day,
                                     present=bool(p), uploaded_by="seed"))
            if len(rows) >= chunk:
                db.bulk_insert_mappings(AttendanceRecord, rows)
                rows = []
        if rows:
            db.bulk_insert_mappings(AttendanceRecord, rows)

        # --- internal marks (2 CIEs entered so far) -----------------------------
        marks = []
        for si, s in enumerate(students):
            base = np.clip((s.cgpa - 4) / 6, 0.2, 1.0)
            for sc in subjects_by[(s.dept_code, s.semester)]:
                for internal in (1, 2):
                    m = float(np.clip(rng.normal(base * 42, 6), 8, 50).round(0))
                    marks.append(dict(usn=s.usn, subject_code=sc,
                                      internal=internal, marks=m,
                                      max_marks=50.0, entered_by="seed"))
        db.bulk_insert_mappings(MarksRecord, marks)

        # --- fees: 4 items per student; ~15% of students default ----------------
        defaulters = set(pyrng.sample([s.usn for s in students],
                                      k=int(0.15 * len(students))))
        fee_rows = []
        fee_types = [("tuition", 98_000), ("exam", 1_800),
                     ("development", 12_000), ("library", 600)]
        for s in students:
            unpaid_left = pyrng.randint(1, 2) if s.usn in defaulters else 0
            for ftype, base in fee_types:
                due = today - dt.timedelta(days=100)
                amount = round(base * float(rng.uniform(0.97, 1.03)), 2)
                if unpaid_left > 0 and rng.random() < 0.5:
                    unpaid_left -= 1
                    fee_rows.append(dict(usn=s.usn, fee_type=ftype,
                                         amount_due=amount, amount_paid=0.0,
                                         due_date=due, paid_date=None,
                                         fine=0.0, status="pending"))
                else:
                    fee_rows.append(dict(
                        usn=s.usn, fee_type=ftype, amount_due=amount,
                        amount_paid=amount, due_date=due,
                        paid_date=due - dt.timedelta(days=int(rng.integers(0, 12))),
                        fine=0.0, status="paid"))
        db.bulk_insert_mappings(FeeRecord, fee_rows)

        # --- exam schedules: per dept per odd semester ---------------------------
        start = today + dt.timedelta(days=25)
        for (code, sem), codes in subjects_by.items():
            for i, sc in enumerate(codes):
                db.add(ExamSchedule(subject_code=sc, dept_code=code,
                                    semester=sem,
                                    exam_date=start + dt.timedelta(days=2 * i),
                                    session="FN"))

        # --- placement drives (final-years) ---------------------------------------
        for i in range(60):
            depts = "ALL" if rng.random() < 0.6 else ",".join(
                pyrng.sample([d[0] for d in DEPARTMENTS], k=pyrng.randint(1, 3)))
            db.add(PlacementDrive(
                company=pyrng.choice(COMPANIES), role=pyrng.choice(ROLES),
                package_lpa=round(float(rng.choice(
                    [3.5, 4.0, 4.5, 5.0, 6.0, 7.5, 10.0, 12.0],
                    p=[.2, .2, .15, .15, .12, .1, .05, .03])), 1),
                min_cgpa=float(rng.choice([6.0, 6.5, 7.0, 7.5], p=[.35, .3, .25, .1])),
                max_backlogs=int(rng.choice([0, 0, 1, 2], p=[.5, .2, .2, .1])),
                min_attendance=75.0, departments=depts,
                drive_date=today + dt.timedelta(days=int(rng.integers(3, 90)))))

        # --- admissions: applications for next batch -------------------------------
        for i in range(400):
            dept = pyrng.choice([d[0] for d in DEPARTMENTS])
            db.add(Application(
                applicant_name=f"{pyrng.choice(FIRST)} {pyrng.choice(LAST)}",
                email=f"applicant{i + 1:03d}@gmail.com",
                phone=f"9{rng.integers(100000000, 999999999)}",
                dept_code=dept,
                category=pyrng.choice(["GM", "GM", "OBC", "SC", "ST", "CAT-1"]),
                tenth_pct=float(np.clip(rng.normal(82, 8), 50, 99).round(1)),
                twelfth_pct=float(np.clip(rng.normal(78, 9), 50, 99).round(1)),
                entrance_score=float(np.clip(rng.normal(95, 30), 10, 195).round(0)),
                family_income=float(np.clip(rng.lognormal(13.0, 0.6),
                                            80_000, 2_500_000).round(-3)),
                status="submitted"))

        db.commit()
        return True
    finally:
        db.close()


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
