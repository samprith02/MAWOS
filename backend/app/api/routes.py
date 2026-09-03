"""REST API v2 — role-scoped gateway in front of the agent layer."""
import datetime as dt

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import llm, metrics
from ..agents import get_agents
from ..auth import create_token, get_current_user, require_role, verify_password
from ..database import get_session
from ..models import (Department, HallTicket, ScholarshipAssessment, Student,
                      TeachingAssignment, User)

router = APIRouter(prefix="/api")


# ---------- auth ------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_session)):
    user = db.query(User).filter(User.username == body.username.strip()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_token(user),
            "user": {"username": user.username, "role": user.role,
                     "name": user.display_name, "usn": user.usn,
                     "dept": user.dept_code},
            "ai_mode": "llm" if llm.check_ollama() else "lexicon"}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role,
            "name": user.display_name, "usn": user.usn, "dept": user.dept_code,
            "ai_mode": "llm" if llm.check_ollama() else "lexicon"}


# ---------- assistant ---------------------------------------------------------
class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(get_current_user),
               db: Session = Depends(get_session)):
    return await get_agents()["orchestrator_agent"].handle_chat(
        db, user, body.message)


# ---------- student portal ------------------------------------------------------
@router.get("/student/dashboard")
def student_dashboard(user: User = Depends(require_role("student")),
                      db: Session = Depends(get_session)):
    agents = get_agents()
    profile = agents["academic_agent"].student_profile(db, user.usn)
    from ..models import AttendanceSummary
    from ..agents.attendance import overall_percentage
    subs = db.query(AttendanceSummary).filter_by(usn=user.usn).all()
    ht = db.query(HallTicket).filter_by(usn=user.usn).first()
    sch = db.query(ScholarshipAssessment).filter_by(usn=user.usn).first()
    s = db.get(Student, user.usn)
    return {
        "profile": profile,
        "attendance": {
            "overall": overall_percentage(db, user.usn),
            "subjects": [{"subject": x.subject_code, "held": x.classes_held,
                          "attended": x.classes_attended, "pct": x.percentage,
                          "shortage": x.shortage} for x in subs]},
        "marks": agents["academic_agent"].student_marks(db, user.usn),
        "fees": agents["finance_agent"].student_fees(db, user.usn),
        "hall_ticket": ({"eligible": ht.eligible, "reasons": ht.reasons}
                        if ht else None),
        "scholarship": ({"status": sch.status, "ml_score": sch.ml_score,
                         "reasons": sch.reasons} if sch else None),
        "placements": agents["placement_agent"].student_view(db, user.usn),
        "timetable": agents["timetable_agent"].grid(db, s.dept_code, s.year,
                                                    s.section),
        "exams": agents["eligibility_agent"].schedule_for(db, s.dept_code, s.semester),
        "notifications": agents["notification_agent"].for_user(
            db, usn=user.usn),
    }


class PayFeeRequest(BaseModel):
    fee_id: int


@router.post("/student/pay-fee")
async def pay_fee(body: PayFeeRequest,
                  user: User = Depends(require_role("student")),
                  db: Session = Depends(get_session)):
    return await get_agents()["finance_agent"].pay_fee(db, user.usn, body.fee_id)


# ---------- timetable (any authenticated role) -----------------------------------
@router.get("/timetable/{dept}/{year}/{section}")
def timetable(dept: str, year: int, section: str,
              user: User = Depends(get_current_user),
              db: Session = Depends(get_session)):
    return get_agents()["timetable_agent"].grid(db, dept.upper(), year,
                                                section.upper())


@router.get("/timetable/{dept}/{year}/{section}/csv")
def timetable_csv(dept: str, year: int, section: str,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_session)):
    csv = get_agents()["timetable_agent"].csv_export(db, dept.upper(), year,
                                                     section.upper())
    return PlainTextResponse(csv, media_type="text/csv", headers={
        "Content-Disposition":
            f"attachment; filename=timetable_{dept}_{year}{section}.csv"})


# ---------- faculty console --------------------------------------------------------
@router.get("/faculty/overview")
def faculty_overview(user: User = Depends(require_role("faculty", "hod")),
                     db: Session = Depends(get_session)):
    agents = get_agents()
    assignments = agents["academic_agent"].faculty_assignments(db, user.faculty_id)
    return {"assignments": assignments,
            "timetable": agents["timetable_agent"].faculty_grid(db, user.faculty_id),
            "notifications": agents["notification_agent"].for_user(
                db, role=user.role, dept=user.dept_code)}


@router.get("/faculty/roster/{dept}/{year}/{section}")
def class_roster(dept: str, year: int, section: str,
                 user: User = Depends(require_role("faculty", "hod", "admin")),
                 db: Session = Depends(get_session)):
    dept = dept.upper()
    section = section.upper()
    if not _can_access_class(db, user, dept, year, section):
        raise HTTPException(status_code=403,
                            detail="You are not assigned to this class")
    return {"roster": get_agents()["academic_agent"].class_roster(
        db, dept, year, section)}


class AttendanceSheet(BaseModel):
    dept: str
    year: int
    section: str
    subject_code: str
    date: str
    absent_usns: list[str] = []


def _can_access_class(db, user, dept: str, year: int, section: str) -> bool:
    if user.role == "admin":
        return True
    if user.role == "hod":
        return user.dept_code == dept
    if user.role == "faculty":
        return db.query(TeachingAssignment).filter_by(
            faculty_id=user.faculty_id, dept_code=dept, year=year,
            section=section).first() is not None
    return False


def _owns_assignment(db, user, sheet: AttendanceSheet) -> bool:
    if user.role in ("admin",):
        return True
    return db.query(TeachingAssignment).filter_by(
        faculty_id=user.faculty_id, subject_code=sheet.subject_code.upper(),
        dept_code=sheet.dept.upper(), year=sheet.year,
        section=sheet.section.upper()).first() is not None


@router.post("/faculty/attendance")
async def mark_attendance(sheet: AttendanceSheet,
                          user: User = Depends(require_role("faculty", "hod", "admin")),
                          db: Session = Depends(get_session)):
    """Mark a whole class in one call: everyone present except absent_usns."""
    if not _owns_assignment(db, user, sheet):
        raise HTTPException(status_code=403,
                            detail="You are not assigned to this subject-section")
    roster = db.query(Student).filter_by(dept_code=sheet.dept.upper(),
                                         year=sheet.year,
                                         section=sheet.section.upper()).all()
    absent = {u.upper().strip() for u in sheet.absent_usns}
    records = [{"usn": s.usn, "subject_code": sheet.subject_code.upper(),
                "date": sheet.date, "present": s.usn not in absent}
               for s in roster]
    return await get_agents()["attendance_agent"].upload_attendance(
        db, user.username, records)


class MarksSheet(BaseModel):
    subject_code: str
    internal: int
    entries: list[dict]  # [{usn, marks}]


def _authorize_marks_sheet(db, user, sheet: MarksSheet) -> None:
    if user.role == "admin":
        return
    subject_code = sheet.subject_code.upper()
    usns = {str(e.get("usn", "")).upper().strip() for e in sheet.entries}
    students = {s.usn: s for s in db.query(Student).filter(Student.usn.in_(usns)).all()}
    if len(students) != len(usns) or "" in usns:
        raise HTTPException(status_code=403,
                            detail="Marks request contains unauthorized students")
    if user.role == "hod":
        if any(s.dept_code != user.dept_code for s in students.values()):
            raise HTTPException(status_code=403,
                                detail="You are not authorized for this department")
        assigned_depts = {s.dept_code for s in students.values()}
        if db.query(TeachingAssignment).filter(
                TeachingAssignment.subject_code == subject_code,
                TeachingAssignment.dept_code.in_(assigned_depts)).first() is None:
            raise HTTPException(status_code=403,
                                detail="Subject is not assigned in this department")
        return
    for student in students.values():
        ok = db.query(TeachingAssignment).filter_by(
            faculty_id=user.faculty_id, subject_code=subject_code,
            dept_code=student.dept_code, year=student.year,
            section=student.section).first() is not None
        if not ok:
            raise HTTPException(status_code=403,
                                detail="You are not assigned to this subject-section")


@router.post("/faculty/marks")
def enter_marks(sheet: MarksSheet,
                user: User = Depends(require_role("faculty", "hod", "admin")),
                db: Session = Depends(get_session)):
    _authorize_marks_sheet(db, user, sheet)
    records = [{"usn": e.get("usn"), "subject_code": sheet.subject_code.upper(),
                "internal": sheet.internal, "marks": e.get("marks")}
               for e in sheet.entries]
    return get_agents()["academic_agent"].enter_marks(db, user.username, records)


# ---------- HOD ------------------------------------------------------------------------
@router.get("/hod/analytics")
def hod_analytics(user: User = Depends(require_role("hod", "principal", "admin")),
                  db: Session = Depends(get_session)):
    agents = get_agents()
    dept = user.dept_code or "AIML"
    data = agents["academic_agent"].dept_analytics(db, dept)
    data["fee_defaulters"] = agents["finance_agent"].defaulter_list(db, dept, 20)
    data["sections"] = [
        {"year": y, "section": s}
        for y in (1, 2, 3, 4) for s in ("A", "B")]
    return data


@router.post("/hod/generate-timetable")
async def hod_generate_timetable(
        user: User = Depends(require_role("hod", "admin")),
        db: Session = Depends(get_session)):
    scope = user.dept_code if user.role == "hod" else None
    return await get_agents()["timetable_agent"].generate_and_announce(
        db, scope, user.username)


@router.post("/hod/generate-timetable-live")
async def hod_generate_timetable_live(
        user: User = Depends(require_role("hod", "admin")),
        db: Session = Depends(get_session)):
    """Same regeneration as above, plus a replayable solver event trace
    (seed placements in order, real cost/temperature curve from
    annealing) for the front-end's live simulation view."""
    scope = user.dept_code if user.role == "hod" else None
    agent = get_agents()["timetable_agent"]
    result = agent.generate_live(db, scope)
    if result.get("ok"):
        await agent.publish("timetable.generated", {
            "scope": result["scope"], "sections": result["sections"],
            "placement_rate": result["placement_rate"],
            "solve_ms": result["solve_ms"], "triggered_by": user.username})
    return result


# ---------- principal --------------------------------------------------------------------
@router.get("/principal/analytics")
def principal_analytics(user: User = Depends(require_role("principal", "admin")),
                        db: Session = Depends(get_session)):
    agents = get_agents()
    return {"departments": agents["academic_agent"].institution_analytics(db),
            "fee_collection": agents["finance_agent"].collection_stats(db),
            "placements": agents["placement_agent"].stats(db),
            "admissions": agents["admission_agent"].funnel(db)}


# ---------- admissions (admin) ---------------------------------------------------------------
@router.get("/admin/admissions")
def admissions_list(status: str | None = None, dept: str | None = None,
                    user: User = Depends(require_role("admin", "principal")),
                    db: Session = Depends(get_session)):
    agents = get_agents()
    return {"funnel": agents["admission_agent"].funnel(db),
            "applications": agents["admission_agent"].list_applications(
                db, status=status, dept=dept)}


@router.post("/admin/admissions/verify-all")
def admissions_verify(user: User = Depends(require_role("admin")),
                      db: Session = Depends(get_session)):
    return get_agents()["admission_agent"].verify_all(db)


@router.post("/admin/admissions/run-merit")
def admissions_merit(user: User = Depends(require_role("admin")),
                     db: Session = Depends(get_session)):
    return get_agents()["admission_agent"].run_merit(db)


@router.post("/admin/admissions/allot")
async def admissions_allot(user: User = Depends(require_role("admin")),
                           db: Session = Depends(get_session)):
    return await get_agents()["admission_agent"].allot_seats(db)


class EnrolRequest(BaseModel):
    application_id: int


@router.post("/admin/admissions/enrol")
async def admissions_enrol(body: EnrolRequest,
                           user: User = Depends(require_role("admin")),
                           db: Session = Depends(get_session)):
    return await get_agents()["admission_agent"].enrol(db, body.application_id)


@router.post("/admin/simulate-day")
async def simulate_day(user: User = Depends(require_role("admin")),
                       db: Session = Depends(get_session)):
    """Demo: today's attendance for AIML year-3 section A across 5 subjects."""
    rng = np.random.default_rng()
    students = db.query(Student).filter_by(dept_code="AIML", year=3,
                                           section="A").all()
    from ..models import Subject
    subjects = [s.code for s in db.query(Subject)
                .filter_by(dept_code="AIML", semester=5).all()]
    today = dt.date.today().isoformat()
    records = [{"usn": s.usn, "subject_code": c, "date": today,
                "present": bool(rng.random() < 0.82)}
               for s in students for c in subjects]
    return await get_agents()["attendance_agent"].upload_attendance(
        db, user.username, records)


# ---------- system / research views ---------------------------------------------------------
@router.get("/departments")
def departments(user: User = Depends(get_current_user),
                db: Session = Depends(get_session)):
    return {"departments": [{"code": d.code, "name": d.name, "intake": d.intake}
                            for d in db.query(Department).all()]}


@router.get("/agents")
def list_agents(user: User = Depends(get_current_user)):
    return {"agents": [{"name": a.name, "description": a.description}
                       for a in get_agents().values()],
            "ai_mode": "llm" if llm.check_ollama() else "lexicon"}


@router.get("/metrics/summary")
def metrics_summary(user: User = Depends(get_current_user),
                    db: Session = Depends(get_session)):
    return metrics.summary(db)


@router.get("/workflows/recent")
def recent_workflows(limit: int = 8, user: User = Depends(get_current_user),
                     db: Session = Depends(get_session)):
    from sqlalchemy import func
    from ..models import WorkflowEvent
    rows = (db.query(WorkflowEvent.workflow_id,
                     func.min(WorkflowEvent.created_at),
                     func.max(WorkflowEvent.elapsed_ms),
                     func.count(WorkflowEvent.id),
                     func.max(WorkflowEvent.hop))
              .group_by(WorkflowEvent.workflow_id)
              .order_by(func.min(WorkflowEvent.created_at).desc())
              .limit(limit).all())
    return {"workflows": [
        {"workflow_id": wid, "started_at": str(start),
         "duration_ms": round(dur, 1), "events": n, "depth_hops": hops}
        for wid, start, dur, n, hops in rows]}


@router.get("/workflows/{workflow_id}")
def workflow_trace(workflow_id: str, user: User = Depends(get_current_user),
                   db: Session = Depends(get_session)):
    from ..models import WorkflowEvent
    events = (db.query(WorkflowEvent).filter_by(workflow_id=workflow_id)
                .order_by(WorkflowEvent.elapsed_ms).all())
    return {"workflow_id": workflow_id, "events": [
        {"topic": e.topic, "agent": e.agent, "hop": e.hop,
         "elapsed_ms": e.elapsed_ms, "at": str(e.created_at)}
        for e in events]}
