"""REST API v2 — role-scoped gateway in front of the agent layer."""
import datetime as dt

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import llm, metrics
from ..agents import get_agents
from ..auth import create_token, get_current_user, require_role, verify_password
from ..database import get_session
from ..models import (Department, HallTicket, ScholarshipAssessment, Student,
                      TeachingAssignment, User)
from ..pdf_slip import render_slip_pdf

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
        "library": {
            "borrowed": agents["library_agent"].student_borrowed(db, user.usn),
            "fines": agents["library_agent"].student_fines(db, user.usn),
        },
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
    return {"roster": get_agents()["academic_agent"].class_roster(
        db, dept.upper(), year, section.upper())}


class AttendanceSheet(BaseModel):
    dept: str
    year: int
    section: str
    subject_code: str
    date: str
    absent_usns: list[str] = []


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


@router.post("/faculty/marks")
def enter_marks(sheet: MarksSheet,
                user: User = Depends(require_role("faculty", "hod", "admin")),
                db: Session = Depends(get_session)):
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


# ---------- library ----------------------------------------------------------------
@router.get("/library/books")
def library_books(q: str = "", skip: int = 0, limit: int = 20,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_session)):
    return get_agents()["library_agent"].search_books(db, q=q, skip=skip, limit=limit)


@router.get("/library/books/{book_id}")
def library_book_detail(book_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_session)):
    book = get_agents()["library_agent"].get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.get("/library/books/{book_id}/reviews")
def library_book_reviews(book_id: int, user: User = Depends(get_current_user),
                         db: Session = Depends(get_session)):
    """Public to any logged-in user -- read what others thought of a book
    before reserving it, not just the average star rating."""
    return {"items": get_agents()["library_agent"].book_reviews(db, book_id)}


class AddBookRequest(BaseModel):
    isbn: str
    title: str
    author: str
    publisher: str | None = None
    category: str
    dept_relevance: list[str] = []
    total_copies: int = 1
    available_copies: int | None = None
    description: str | None = None


@router.post("/library/books")
def library_add_book(body: AddBookRequest,
                     user: User = Depends(require_role("admin", "principal", "librarian")),
                     db: Session = Depends(get_session)):
    payload = body.model_dump()
    if payload.get("available_copies") is None:
        payload["available_copies"] = payload["total_copies"]
    return get_agents()["library_agent"].add_book(db, payload)


class UpdateBookRequest(BaseModel):
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    category: str | None = None
    dept_relevance: list[str] | None = None
    total_copies: int | None = None
    available_copies: int | None = None
    description: str | None = None


@router.put("/library/books/{book_id}")
def library_update_book(book_id: int, body: UpdateBookRequest,
                        user: User = Depends(require_role("admin", "principal", "librarian")),
                        db: Session = Depends(get_session)):
    return get_agents()["library_agent"].update_book(db, book_id, body.model_dump())


@router.delete("/library/books/{book_id}")
def library_remove_book(book_id: int,
                        user: User = Depends(require_role("admin", "principal", "librarian")),
                        db: Session = Depends(get_session)):
    return get_agents()["library_agent"].remove_book(db, book_id)


class LibraryRequestBody(BaseModel):
    book_id: int


@router.post("/library/requests")
async def library_request_book(body: LibraryRequestBody,
                               user: User = Depends(require_role("student")),
                               db: Session = Depends(get_session)):
    """Agent decides automatically (availability + fine standing). On
    success, the student gets an acknowledgement slip (see the /slip
    endpoint below) to show the librarian in person."""
    return await get_agents()["library_agent"].request_book(db, user.usn, body.book_id)


@router.get("/library/requests/{request_id}/slip")
def library_request_slip(request_id: int, user: User = Depends(require_role("student")),
                         db: Session = Depends(get_session)):
    return get_agents()["library_agent"].get_request_slip(db, request_id, user.usn)


@router.get("/library/requests/{request_id}/slip/pdf")
def library_request_slip_pdf(request_id: int, user: User = Depends(require_role("student")),
                             db: Session = Depends(get_session)):
    """Downloadable PDF version of the acknowledgement slip -- same data
    as the in-app slip, carrying the 6-digit verification code, meant to
    be shown (on a phone) or printed and handed to the librarian."""
    slip = get_agents()["library_agent"].get_request_slip(db, request_id, user.usn)
    if not slip.get("ok"):
        raise HTTPException(status_code=404, detail=slip.get("error", "Slip not found"))
    pdf_bytes = render_slip_pdf(slip)
    headers = {"Content-Disposition": f'inline; filename="slip_{request_id}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.post("/library/requests/{request_id}/cancel")
def library_cancel_request(request_id: int,
                           user: User = Depends(require_role("student")),
                           db: Session = Depends(get_session)):
    return get_agents()["library_agent"].cancel_request(db, request_id, user.usn)


class LibraryReturnRequestBody(BaseModel):
    issue_id: int
    rating: int | None = None   # optional 1-5 review, saved immediately
    comment: str | None = None


@router.post("/library/return-request")
def library_return_request(body: LibraryReturnRequestBody,
                           user: User = Depends(require_role("student")),
                           db: Session = Depends(get_session)):
    """Student declares intent to return -- the librarian confirms actual
    receipt separately (see /librarian/library/returns/{id}/confirm)."""
    return get_agents()["library_agent"].request_return(
        db, body.issue_id, user.usn, rating=body.rating, comment=body.comment)


@router.get("/student/library/requests")
def library_student_requests(user: User = Depends(require_role("student")),
                             db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].student_requests(db, user.usn)}


@router.get("/student/library/borrowed")
def library_student_borrowed(user: User = Depends(require_role("student")),
                             db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].student_borrowed(db, user.usn)}


@router.get("/student/library/history")
def library_student_history(user: User = Depends(require_role("student")),
                            db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].student_history(db, user.usn)}


@router.get("/student/library/fines")
def library_student_fines(user: User = Depends(require_role("student")),
                          db: Session = Depends(get_session)):
    return get_agents()["library_agent"].student_fines(db, user.usn)


@router.get("/student/library/recommendations")
def library_student_recommendations(limit: int | None = None,
                                    user: User = Depends(require_role("student")),
                                    db: Session = Depends(get_session)):
    return get_agents()["library_agent"].recommendations(db, user.usn, limit=limit)


# ---------- librarian: catalogue management + physical handover + oversight --------
# The agent decides eligibility/availability automatically (including a
# fine-standing check) -- the librarian doesn't approve individual
# reservations. Their job is: (1) confirm the physical pickup/return that
# an approved reservation still needs, (2) keep the catalogue accurate,
# and (3) have full visibility into everything happening with books.
@router.get("/librarian/library/pickups/pending")
def librarian_pending_pickups(user: User = Depends(require_role("librarian", "admin")),
                              db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].librarian_pending_pickups(db)}


@router.get("/librarian/library/verify/{slip_code}")
def librarian_verify_slip(slip_code: str,
                          user: User = Depends(require_role("librarian", "admin")),
                          db: Session = Depends(get_session)):
    """Librarian types in (or scans) the 6-digit code off a student's
    slip to confirm it's genuine and still awaiting pickup before handing
    the book over."""
    return get_agents()["library_agent"].verify_slip(db, slip_code)


@router.post("/librarian/library/requests/{request_id}/confirm-pickup")
async def librarian_confirm_pickup(request_id: int,
                                   user: User = Depends(require_role("librarian", "admin")),
                                   db: Session = Depends(get_session)):
    """Librarian has physically handed the book to the student holding
    the acknowledgement slip."""
    return await get_agents()["library_agent"].confirm_collection(db, request_id)


@router.get("/librarian/library/returns/pending")
def librarian_pending_returns(user: User = Depends(require_role("librarian", "admin")),
                              db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].librarian_pending_returns(db)}


@router.post("/librarian/library/returns/{issue_id}/confirm")
async def librarian_confirm_return(issue_id: int,
                                   user: User = Depends(require_role("librarian", "admin")),
                                   db: Session = Depends(get_session)):
    """Librarian confirms they've physically received the book back."""
    return await get_agents()["library_agent"].confirm_return(db, issue_id)


class RejectReturnBody(BaseModel):
    reason: str


@router.post("/librarian/library/returns/{issue_id}/reject")
def librarian_reject_return(issue_id: int, body: RejectReturnBody,
                            user: User = Depends(require_role("librarian", "admin")),
                            db: Session = Depends(get_session)):
    """The claimed return didn't actually happen -- reverts to issued."""
    return get_agents()["library_agent"].reject_return(db, issue_id, body.reason)


@router.get("/librarian/library/requests")
def librarian_all_requests(status: str | None = None,
                           user: User = Depends(require_role("librarian", "admin")),
                           db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].librarian_all_requests(db, status=status)}


@router.get("/librarian/library/issues")
def librarian_all_issues(status: str = "issued",
                         user: User = Depends(require_role("librarian", "admin")),
                         db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].librarian_all_issues(db, status=status)}


@router.get("/librarian/library/overdue")
def librarian_overdue_report(user: User = Depends(require_role("librarian", "admin")),
                             db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].librarian_overdue_report(db)}


@router.get("/librarian/library/fines")
def librarian_all_fines(user: User = Depends(require_role("librarian", "admin")),
                        db: Session = Depends(get_session)):
    return get_agents()["library_agent"].librarian_all_fines(db)


@router.post("/librarian/library/fines/{fine_id}/mark-paid")
def librarian_mark_fine_paid(fine_id: int,
                             user: User = Depends(require_role("librarian", "admin")),
                             db: Session = Depends(get_session)):
    """Student pays the fine in person (cash at the desk); the librarian
    records it here, which clears it from the student's outstanding
    balance immediately."""
    return get_agents()["library_agent"].pay_fine(db, fine_id, user.username)


@router.get("/librarian/library/reviews")
def librarian_all_reviews(user: User = Depends(require_role("librarian", "admin")),
                          db: Session = Depends(get_session)):
    return {"items": get_agents()["library_agent"].librarian_all_reviews(db)}


class LibrarianIssueBody(BaseModel):
    usn: str
    book_id: int


@router.post("/librarian/library/issue")
async def librarian_counter_issue(body: LibrarianIssueBody,
                                  user: User = Depends(require_role("librarian", "admin")),
                                  db: Session = Depends(get_session)):
    """Walk-in counter issue: librarian hands a book directly to a
    student, no prior reservation involved."""
    return await get_agents()["library_agent"].issue_book(db, body.usn, body.book_id)


class LibrarianReturnBody(BaseModel):
    issue_id: int
    rating: int | None = None
    comment: str | None = None


@router.post("/librarian/library/return")
async def librarian_counter_return(body: LibrarianReturnBody,
                                   user: User = Depends(require_role("librarian", "admin")),
                                   db: Session = Depends(get_session)):
    """Walk-in counter return: student is physically present, processed
    in one step, no separate request/confirm needed."""
    return await get_agents()["library_agent"].return_book(
        db, body.issue_id, rating=body.rating, comment=body.comment)
