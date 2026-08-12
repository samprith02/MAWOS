"""Academic Agent — student records, internal marks (CIE), analytics
aggregations that power the role dashboards."""
from sqlalchemy import case, func

from ..models import (
    AttendanceSummary, Department, MarksRecord, Student, Subject,
    TeachingAssignment,
)
from .attendance import overall_percentage
from .base import BaseAgent


class AcademicAgent(BaseAgent):
    name = "academic_agent"
    description = "Student records, internal marks (CIE), department analytics"

    def student_profile(self, db, usn: str) -> dict | None:
        s = db.get(Student, usn)
        if s is None:
            return None
        dept = db.get(Department, s.dept_code)
        return {"usn": s.usn, "name": s.name, "dept": s.dept_code,
                "dept_name": dept.name if dept else s.dept_code,
                "year": s.year, "semester": s.semester, "section": s.section,
                "cgpa": s.cgpa, "backlogs": s.backlogs, "category": s.category,
                "admission_year": s.admission_year}

    def student_marks(self, db, usn: str) -> list[dict]:
        rows = (db.query(MarksRecord, Subject)
                  .join(Subject, Subject.code == MarksRecord.subject_code)
                  .filter(MarksRecord.usn == usn)
                  .order_by(MarksRecord.subject_code, MarksRecord.internal).all())
        by_subject: dict[str, dict] = {}
        for m, sub in rows:
            e = by_subject.setdefault(m.subject_code, {
                "subject": m.subject_code, "name": sub.name, "internals": {}})
            e["internals"][f"CIE-{m.internal}"] = m.marks
        for e in by_subject.values():
            vals = list(e["internals"].values())
            e["cie_average"] = round(sum(vals) / len(vals), 1) if vals else None
        return list(by_subject.values())

    def enter_marks(self, db, entered_by: str, records: list[dict]) -> dict:
        accepted, rejected = 0, []
        for r in records:
            usn = str(r.get("usn", "")).upper().strip()
            if db.get(Student, usn) is None:
                rejected.append({**r, "reason": "unknown USN"})
                continue
            try:
                internal = int(r["internal"])
                marks = float(r["marks"])
                assert 1 <= internal <= 3 and 0 <= marks <= 50
            except (KeyError, ValueError, AssertionError):
                rejected.append({**r, "reason": "invalid internal/marks"})
                continue
            existing = db.query(MarksRecord).filter_by(
                usn=usn, subject_code=r["subject_code"], internal=internal).first()
            if existing:
                existing.marks = marks
                existing.entered_by = entered_by
            else:
                db.add(MarksRecord(usn=usn, subject_code=r["subject_code"],
                                   internal=internal, marks=marks,
                                   entered_by=entered_by))
            accepted += 1
        db.commit()
        return {"accepted": accepted, "rejected": rejected}

    def class_roster(self, db, dept: str, year: int, section: str) -> list[dict]:
        rows = (db.query(Student).filter_by(dept_code=dept, year=year,
                                            section=section)
                  .order_by(Student.usn).all())
        return [{"usn": s.usn, "name": s.name, "cgpa": s.cgpa,
                 "attendance": overall_percentage(db, s.usn)} for s in rows]

    def dept_analytics(self, db, dept: str) -> dict:
        students = db.query(Student).filter_by(dept_code=dept).count()
        shortage = (db.query(func.count(func.distinct(AttendanceSummary.usn)))
                      .join(Student, Student.usn == AttendanceSummary.usn)
                      .filter(Student.dept_code == dept,
                              AttendanceSummary.shortage.is_(True)).scalar() or 0)
        avg_att = (db.query(func.avg(AttendanceSummary.percentage))
                     .join(Student, Student.usn == AttendanceSummary.usn)
                     .filter(Student.dept_code == dept).scalar() or 0)
        avg_cgpa = (db.query(func.avg(Student.cgpa))
                      .filter(Student.dept_code == dept,
                              Student.cgpa > 0).scalar() or 0)
        by_year = dict(db.query(Student.year, func.count())
                         .filter(Student.dept_code == dept)
                         .group_by(Student.year).all())
        return {"dept": dept, "students": students,
                "shortage_students": int(shortage),
                "avg_attendance": round(float(avg_att), 1),
                "avg_cgpa": round(float(avg_cgpa), 2),
                "by_year": {int(k): v for k, v in by_year.items()}}

    def institution_analytics(self, db) -> dict:
        return {d.code: self.dept_analytics(db, d.code)
                for d in db.query(Department).all()}

    def faculty_assignments(self, db, faculty_id: int) -> list[dict]:
        rows = (db.query(TeachingAssignment)
                  .filter_by(faculty_id=faculty_id).all())
        return [{"subject": a.subject_code, "subject_name": a.subject.name,
                 "dept": a.dept_code, "year": a.year, "section": a.section,
                 "credits": a.subject.credits} for a in rows]
