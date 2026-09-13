"""ORM models v2 — the Shared Institutional Context Store for a full college:
5 departments x 4 years x 2 sections, faculty with teaching assignments,
admissions pipeline, timetables, marks, and the v1 research spine
(attendance, fees, eligibility, workflow audit)."""
import datetime as dt

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Department(Base):
    __tablename__ = "departments"
    code = Column(String(8), primary_key=True)        # AIML, CSE, ...
    name = Column(String(128), nullable=False)
    intake = Column(Integer, nullable=False, default=60)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), nullable=False)  # student|faculty|hod|principal|admin|librarian
    display_name = Column(String(128), nullable=False)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    dept_code = Column(String(8), ForeignKey("departments.code"), nullable=True)


class Student(Base):
    __tablename__ = "students"
    usn = Column(String(16), primary_key=True)         # 4MT23AM001
    name = Column(String(128), nullable=False)
    dept_code = Column(String(8), ForeignKey("departments.code"), nullable=False, index=True)
    year = Column(Integer, nullable=False)              # 1-4
    semester = Column(Integer, nullable=False)           # 1/3/5/7 (odd term)
    section = Column(String(4), nullable=False, default="A")
    cgpa = Column(Float, nullable=False)
    backlogs = Column(Integer, nullable=False, default=0)
    category = Column(String(16), nullable=False, default="GM")
    family_income = Column(Float, nullable=False, default=500000.0)
    admission_year = Column(Integer, nullable=False, default=2023)
    email = Column(String(128), nullable=True)
    phone = Column(String(16), nullable=True)
    status = Column(String(16), nullable=False, default="enrolled")
    is_synthetic = Column(Boolean, nullable=False, default=True)


class Faculty(Base):
    __tablename__ = "faculty"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    dept_code = Column(String(8), ForeignKey("departments.code"), nullable=False, index=True)
    designation = Column(String(64), nullable=False, default="Assistant Professor")
    email = Column(String(128), nullable=True)


class Subject(Base):
    __tablename__ = "subjects"
    code = Column(String(16), primary_key=True)          # 23AM51 ...
    name = Column(String(128), nullable=False)
    dept_code = Column(String(8), ForeignKey("departments.code"), nullable=False, index=True)
    semester = Column(Integer, nullable=False)
    credits = Column(Integer, nullable=False, default=4)  # = periods/week


class TeachingAssignment(Base):
    """Who teaches which subject to which section."""
    __tablename__ = "teaching_assignments"
    __table_args__ = (UniqueConstraint("subject_code", "dept_code", "year",
                                       "section", name="uq_teach"),)
    id = Column(Integer, primary_key=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False, index=True)
    subject_code = Column(String(16), ForeignKey("subjects.code"), nullable=False)
    dept_code = Column(String(8), nullable=False)
    year = Column(Integer, nullable=False)
    section = Column(String(4), nullable=False)
    faculty = relationship("Faculty")
    subject = relationship("Subject")


class TimetableSlot(Base):
    __tablename__ = "timetable_slots"
    __table_args__ = (UniqueConstraint("dept_code", "year", "section",
                                       "day", "period", name="uq_tt_slot"),)
    id = Column(Integer, primary_key=True)
    dept_code = Column(String(8), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    section = Column(String(4), nullable=False)
    day = Column(Integer, nullable=False)      # 0=Mon .. 4=Fri
    period = Column(Integer, nullable=False)   # 0..5
    subject_code = Column(String(16), ForeignKey("subjects.code"), nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False)
    room = Column(String(16), nullable=False, default="")
    subject = relationship("Subject")
    faculty = relationship("Faculty")


class Application(Base):
    """Admissions pipeline record."""
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    applicant_name = Column(String(128), nullable=False)
    email = Column(String(128), nullable=False)
    phone = Column(String(16), nullable=False)
    dept_code = Column(String(8), ForeignKey("departments.code"), nullable=False, index=True)
    category = Column(String(16), nullable=False, default="GM")
    tenth_pct = Column(Float, nullable=False)
    twelfth_pct = Column(Float, nullable=False)
    entrance_score = Column(Float, nullable=False)   # 0-200 (CET-style)
    family_income = Column(Float, nullable=False)
    # submitted | verified | merit_listed | seat_allotted | enrolled | rejected
    status = Column(String(16), nullable=False, default="submitted", index=True)
    merit_score = Column(Float, nullable=True)
    merit_rank = Column(Integer, nullable=True)
    allotted_usn = Column(String(16), nullable=True)
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class MarksRecord(Base):
    __tablename__ = "marks_records"
    __table_args__ = (UniqueConstraint("usn", "subject_code", "internal",
                                       name="uq_marks"),)
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    subject_code = Column(String(16), ForeignKey("subjects.code"), nullable=False)
    internal = Column(Integer, nullable=False)         # 1..3
    marks = Column(Float, nullable=False)
    max_marks = Column(Float, nullable=False, default=50.0)
    entered_by = Column(String(64), nullable=False, default="")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("usn", "subject_code", "date",
                                       name="uq_attendance_entry"),)
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    subject_code = Column(String(16), ForeignKey("subjects.code"), nullable=False)
    date = Column(Date, nullable=False)
    present = Column(Boolean, nullable=False)
    uploaded_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utcnow)


class AttendanceSummary(Base):
    __tablename__ = "attendance_summary"
    __table_args__ = (UniqueConstraint("usn", "subject_code",
                                       name="uq_attendance_summary"),)
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    subject_code = Column(String(16), ForeignKey("subjects.code"), nullable=False)
    classes_held = Column(Integer, nullable=False, default=0)
    classes_attended = Column(Integer, nullable=False, default=0)
    percentage = Column(Float, nullable=False, default=0.0)
    shortage = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class FeeRecord(Base):
    __tablename__ = "fee_records"
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    fee_type = Column(String(32), nullable=False)
    amount_due = Column(Float, nullable=False)
    amount_paid = Column(Float, nullable=False, default=0.0)
    due_date = Column(Date, nullable=False)
    paid_date = Column(Date, nullable=True)
    fine = Column(Float, nullable=False, default=0.0)
    status = Column(String(16), nullable=False, default="pending")


class ExamSchedule(Base):
    __tablename__ = "exam_schedules"
    id = Column(Integer, primary_key=True)
    subject_code = Column(String(16), ForeignKey("subjects.code"), nullable=False)
    dept_code = Column(String(8), nullable=False, index=True)
    semester = Column(Integer, nullable=False)
    exam_date = Column(Date, nullable=False)
    session = Column(String(16), nullable=False, default="FN")


class HallTicket(Base):
    __tablename__ = "hall_tickets"
    __table_args__ = (UniqueConstraint("usn", "semester", name="uq_hall_ticket"),)
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    semester = Column(Integer, nullable=False)
    eligible = Column(Boolean, nullable=False)
    reasons = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ScholarshipAssessment(Base):
    __tablename__ = "scholarship_assessments"
    __table_args__ = (UniqueConstraint("usn", "scheme", name="uq_scholarship_scheme"),)
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    scheme = Column(String(64), nullable=False, default="Merit-cum-Means")
    status = Column(String(16), nullable=False)
    ml_score = Column(Float, nullable=True)
    reasons = Column(Text, nullable=False, default="")
    assessed_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class PlacementDrive(Base):
    __tablename__ = "placement_drives"
    id = Column(Integer, primary_key=True)
    company = Column(String(128), nullable=False)
    role = Column(String(128), nullable=False)
    package_lpa = Column(Float, nullable=False)
    min_cgpa = Column(Float, nullable=False, default=6.0)
    max_backlogs = Column(Integer, nullable=False, default=0)
    min_attendance = Column(Float, nullable=False, default=75.0)
    drive_date = Column(Date, nullable=False)
    departments = Column(String(64), nullable=False, default="ALL")  # csv of codes


class PlacementShortlist(Base):
    __tablename__ = "placement_shortlists"
    __table_args__ = (UniqueConstraint("drive_id", "usn", name="uq_shortlist_entry"),)
    id = Column(Integer, primary_key=True)
    drive_id = Column(Integer, ForeignKey("placement_drives.id"), nullable=False)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    eligible = Column(Boolean, nullable=False)
    ml_probability = Column(Float, nullable=True)
    reasons = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    drive = relationship("PlacementDrive")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), nullable=True, index=True)
    audience_role = Column(String(16), nullable=True)
    dept_code = Column(String(8), nullable=True)
    channel = Column(String(16), nullable=False, default="in-app")
    title = Column(String(256), nullable=False)
    message = Column(Text, nullable=False)
    source_agent = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    read = Column(Boolean, nullable=False, default=False)


class WorkflowEvent(Base):
    """Audit log of every bus event — powers propagation metrics + trace UI."""
    __tablename__ = "workflow_events"
    id = Column(Integer, primary_key=True)
    workflow_id = Column(String(36), nullable=False, index=True)
    topic = Column(String(64), nullable=False)
    agent = Column(String(32), nullable=False)
    hop = Column(Integer, nullable=False, default=0)
    payload = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=utcnow)
    elapsed_ms = Column(Float, nullable=False, default=0.0)


class IntentLog(Base):
    """Every orchestrator decision — routing accuracy / LLM-vs-fallback metrics."""
    __tablename__ = "intent_logs"
    id = Column(Integer, primary_key=True)
    query = Column(Text, nullable=False)
    predicted_intent = Column(String(64), nullable=False)   # tool name in LLM mode
    method = Column(String(16), nullable=False)              # llm | keyword
    latency_ms = Column(Float, nullable=False, default=0.0)
    expected_intent = Column(String(64), nullable=True)
    correct = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Library Agent (added) — catalogue, reservations, issue/return, fines.
# Kept as its own small set of tables rather than folding fines into
# FeeRecord, so Finance's grace-period/refresh_status logic (which assumes
# daily-accruing fees) never runs over a library fine's fixed one-time
# amount.
# ---------------------------------------------------------------------------
class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True)
    isbn = Column(String(32), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    author = Column(String(255), nullable=False)
    publisher = Column(String(255), nullable=True)
    category = Column(String(64), nullable=False, index=True)
    dept_relevance = Column(String(64), nullable=False, default="")  # csv of dept codes
    total_copies = Column(Integer, nullable=False, default=1)
    available_copies = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)
    popularity_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow)


class BookRequest(Base):
    """A reservation the agent handles automatically: checks availability
    and fine standing, sets a pickup deadline, and auto-expires with a
    fine if uncollected. On successful request, the student gets an
    acknowledgement slip (request id + deadline) to physically show the
    librarian, who confirms the actual pickup -- so `status` moves to
    "collected" via a librarian action, not the student's own click.

    Status flow: pending -> collected (librarian confirmed pickup, a
                            BookIssue is created)
                          -> expired (deadline passed, uncollected)
                          -> cancelled (student cancelled before pickup)
    """
    __tablename__ = "book_requests"
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    requested_at = Column(DateTime, default=utcnow)
    pickup_deadline = Column(DateTime, nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    collected_at = Column(DateTime, nullable=True)
    fine_generated = Column(Boolean, nullable=False, default=False)
    # Unique 6-digit code stamped on the acknowledgement slip (screen + PDF)
    # at creation time. The librarian checks this against the student
    # standing at the desk -- unlike the sequential request id, it isn't
    # guessable. verify_slip() only treats it as "valid" while pending.
    slip_code = Column(String(6), unique=True, nullable=True, index=True)


class BookReview(Base):
    """An optional rating+comment a student can leave when returning a
    book. Never required -- return_book() works identically with or
    without one. Average rating feeds into recommendation scoring."""
    __tablename__ = "book_reviews"
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    issue_id = Column(Integer, ForeignKey("book_issues.id"), nullable=False, unique=True)
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class BookIssue(Base):
    """status: issued -> return_pending (student submitted a return
    request, book not yet physically confirmed received) -> returned
    (librarian confirmed receipt) | issued (librarian rejected a false
    return claim, reverts back to issued).

    Fine calculation uses `return_requested_at` (when the student
    declared intent to return), not whenever the librarian gets around
    to confirming it -- a busy front desk shouldn't cost the student
    extra overdue days."""
    __tablename__ = "book_issues"
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    request_id = Column(Integer, ForeignKey("book_requests.id"), nullable=True)
    issue_date = Column(DateTime, default=utcnow)
    due_date = Column(DateTime, nullable=False)
    return_requested_at = Column(DateTime, nullable=True)
    return_date = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False, default="issued", index=True)


class LibraryFine(Base):
    """source_type: 'pickup_expiry' | 'overdue_return'. source_id: the
    book_requests.id or book_issues.id that generated it. The unique
    constraint is what makes fine generation idempotent — a proactive
    scan or return that runs twice on the same source can never create
    a duplicate fine."""
    __tablename__ = "library_fines"
    __table_args__ = (UniqueConstraint("source_type", "source_id",
                                       name="uq_library_fine_source"),)
    id = Column(Integer, primary_key=True)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=False, index=True)
    source_type = Column(String(24), nullable=False)
    source_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="unpaid")
    created_at = Column(DateTime, default=utcnow)
    # Fines are paid in person at the library desk -- there's no online
    # payment gateway here. The librarian collects the cash and marks it
    # paid; these two fields are that receipt.
    paid_at = Column(DateTime, nullable=True)
    collected_by = Column(String(64), nullable=True)  # librarian username
