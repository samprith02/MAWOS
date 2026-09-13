"""ORM models v4 — the Shared Institutional Context Store.

Changed at R1 per `docs/v4/04_DATA_MODEL.md` §4:

  added     Room, FacultyAvailability, Request, Conversation,
            ConversationTurn, TraceRecord, GuardDecision
  modified  TimetableSlot.room -> FK to Room; Subject gains kind/block_size;
            Faculty gains qualified_subjects; ScholarshipAssessment drops
            ml_score
  removed   Application (the admissions pipeline)

`GuardDecision` exists specifically so that *attempted but blocked* actions
are countable. `07_CONTRIBUTION.md` claim 1 -- that guard placement rather
than model choice determines safety -- is unmeasurable without it, which is
why it lands in R1 rather than being retrofitted at R5.
"""
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
    role = Column(String(16), nullable=False)  # student|faculty|hod|principal|admin
    display_name = Column(String(128), nullable=False)
    usn = Column(String(16), ForeignKey("students.usn"), nullable=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    dept_code = Column(String(8), ForeignKey("departments.code"), nullable=True)


class Student(Base):
    __tablename__ = "students"
    usn = Column(String(16), primary_key=True)   # format from institution.yaml
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
    #: CSV of subject codes this member can teach. Substitution search needs
    #: it explicitly; in v3 it was implicit in TeachingAssignment.
    qualified_subjects = Column(Text, nullable=False, default="")


class Subject(Base):
    __tablename__ = "subjects"
    code = Column(String(16), primary_key=True)
    name = Column(String(128), nullable=False)
    dept_code = Column(String(8), ForeignKey("departments.code"), nullable=False, index=True)
    semester = Column(Integer, nullable=False)
    credits = Column(Integer, nullable=False, default=4)  # = periods/week
    #: "theory" | "lab". Lab subjects want contiguous periods. The solver
    #: does not honour block_size until R2/SHOULD-tier; the columns land now
    #: so the schema does not change twice (04_DATA_MODEL.md 4.3).
    kind = Column(String(8), nullable=False, default="theory")
    block_size = Column(Integer, nullable=False, default=1)


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


class Room(Base):
    """A schedulable space. New at R1 -- in v3 `room` was a cosmetic
    f-string, which is exactly why the v3 plan had to descope ITC-2007
    track 3 (RESEARCH_PLAN_V3.md 0.2b)."""
    __tablename__ = "rooms"
    code = Column(String(16), primary_key=True)       # e.g. MAIN-101
    name = Column(String(64), nullable=False)
    room_type = Column(String(16), nullable=False, default="classroom")
    capacity = Column(Integer, nullable=False, default=70)
    building = Column(String(32), nullable=False, default="Main")


class FacultyAvailability(Base):
    """When a faculty member cannot be scheduled, from any source.

    Generalises what v3 already had as `Schedule.blocked` -- a
    (faculty, day) -> period bitmask used only for out-of-scope
    commitments. Making the source explicit is what allows leave-driven
    re-solving (docs/v4/05_TIMETABLE_SCOPE.md 2.3).
    """
    __tablename__ = "faculty_availability"
    __table_args__ = (UniqueConstraint("faculty_id", "day", "period",
                                       name="uq_faculty_unavailable"),)
    id = Column(Integer, primary_key=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False,
                        index=True)
    day = Column(Integer, nullable=False)        # 0=Mon .. 4=Fri
    period = Column(Integer, nullable=False)     # 0..5
    reason = Column(String(64), nullable=False, default="")
    source = Column(String(16), nullable=False, default="standing")
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    faculty = relationship("Faculty")


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
    #: R1: a real reference, not a cosmetic string.
    room_code = Column(String(16), ForeignKey("rooms.code"), nullable=True,
                       index=True)
    subject = relationship("Subject")
    faculty = relationship("Faculty")
    room = relationship("Room")


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
    #: ml_score removed at R1: the v3 CART was trained on a label our own
    #: banded rule generated (docs/v4/04_DATA_MODEL.md 2). Scholarship
    #: eligibility is a policy decision and is now stated as one.
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
    #: ml_probability removed at R1 with the placement RF (04_DATA_MODEL.md 2).
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


# ===================================================================== v4
# Workflow, conversation and audit entities. New at R1
# (docs/v4/04_DATA_MODEL.md 4.2).

class Request(Base):
    """The one write-bearing workflow type in MVRS.

    A single table and a single state machine carry every request kind, so
    adding re-evaluation or room-booking later is a new `kind`, not a new
    table (docs/v4/02_SCOPE.md: the general Requests module is SHOULD-tier).
    """
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True)
    kind = Column(String(32), nullable=False, index=True)   # faculty_leave | ...
    requester = Column(String(64), nullable=False, index=True)  # username
    subject_ref = Column(String(64), nullable=True)   # what it is about
    payload = Column(Text, nullable=False, default="{}")
    #: pending | approved | rejected | withdrawn | applied
    state = Column(String(16), nullable=False, default="pending", index=True)
    decided_by = Column(String(64), nullable=True)
    reasons = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Conversation(Base):
    """Per-user dialogue container. Persisted, not in process memory: it
    must survive restart and be inspectable in the trace UI
    (docs/v4/01_ARCHITECTURE.md 8)."""
    __tablename__ = "conversations"
    id = Column(String(36), primary_key=True)          # uuid
    owner = Column(String(64), nullable=False, index=True)   # username
    started_at = Column(DateTime, default=utcnow)
    last_active_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    #: which LLM tier served each turn, newest last -- degradation is
    #: measurable rather than anecdotal.
    tier_history = Column(Text, nullable=False, default="[]")
    title = Column(String(128), nullable=False, default="")


class ConversationTurn(Base):
    """One exchange, plus the orchestrator state that outlives it."""
    __tablename__ = "conversation_turns"
    id = Column(String(36), primary_key=True)          # uuid; == turn_id
    conversation_id = Column(String(36), ForeignKey("conversations.id"),
                             nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    role = Column(String(16), nullable=False)          # user | assistant
    content = Column(Text, nullable=False, default="")
    #: What "she" / "that section" refers to. Never dropped when history is
    #: truncated -- losing it is what makes an assistant feel amnesiac.
    resolved_entities = Column(Text, nullable=False, default="{}")
    pending_clarification = Column(Text, nullable=True)
    pending_confirmation = Column(Text, nullable=True)
    plan_state = Column(Text, nullable=False, default="{}")
    tier = Column(String(16), nullable=False, default="")
    created_at = Column(DateTime, default=utcnow)
    conversation = relationship("Conversation")


class TraceRecord(Base):
    """One step of one turn: plan, delegation, tool call, guard verdict or
    provenance check. This is simultaneously the debugging story, the
    explainability feature and the evaluation instrument."""
    __tablename__ = "trace_records"
    id = Column(Integer, primary_key=True)
    turn_id = Column(String(36), ForeignKey("conversation_turns.id"),
                     nullable=False, index=True)
    step = Column(Integer, nullable=False)
    #: plan | delegate | tool | guard | gate | clarify | confirm | synthesise
    kind = Column(String(16), nullable=False, index=True)
    actor = Column(String(48), nullable=False, default="")   # agent or tool
    verdict = Column(String(24), nullable=False, default="")
    payload = Column(Text, nullable=False, default="{}")
    latency_ms = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=utcnow)


class GuardDecision(Base):
    """Every authorisation outcome -- allowed AND blocked, in the same shape.

    The shape matters: if denials were exceptions and successes were silent,
    the *attempt* rate would be uncomputable, and the attempt rate is the
    headline of `07_CONTRIBUTION.md` claim 1. R0.5 already showed why this
    must be explicit -- it measured 0 attempts, but only because the role
    filter never exposed the capability, which is a different fact.
    """
    __tablename__ = "guard_decisions"
    id = Column(Integer, primary_key=True)
    turn_id = Column(String(36), nullable=True, index=True)
    actor = Column(String(64), nullable=False, index=True)   # username
    actor_role = Column(String(16), nullable=False, default="")
    capability = Column(String(64), nullable=False, index=True)
    target = Column(String(128), nullable=False, default="")
    #: allowed | denied
    verdict = Column(String(16), nullable=False, index=True)
    #: NOT_PERMITTED | OUT_OF_SCOPE | PRECONDITION_FAILED | ""
    reason_code = Column(String(32), nullable=False, default="")
    detail = Column(Text, nullable=False, default="")
    #: True when the capability WAS exposed to this actor's schema, so a
    #: denial here is a real attempt rather than an impossible one.
    was_exposed = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow)
