"""Placement Agent REST API — drive management, shortlist generation,
eligibility explanation, and outcome tracking."""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agents import get_agents
from ..auth import get_current_user, require_role
from ..database import get_session
from ..models import User

router = APIRouter(prefix="/api/placement", tags=["placement"])


# ---------- schemas ----------------------------------------------------------
class DriveCreateRequest(BaseModel):
    company: str
    role: str
    package_lpa: float
    min_cgpa: float = 6.0
    max_backlogs: int = 0
    min_attendance: float = 75.0
    drive_date: dt.date
    departments: str = "ALL"          # "ALL" or CSV of dept codes e.g. "CSE,AIML"
    status: str = "OPEN"              # DRAFT | OPEN
    requires_fee_clearance: bool = False
    application_deadline: dt.date | None = None


class DriveUpdateRequest(BaseModel):
    company: str | None = None
    role: str | None = None
    package_lpa: float | None = None
    min_cgpa: float | None = None
    max_backlogs: int | None = None
    min_attendance: float | None = None
    drive_date: dt.date | None = None
    departments: str | None = None
    requires_fee_clearance: bool | None = None
    application_deadline: dt.date | None = None


class OutcomeRequest(BaseModel):
    outcome_status: str        # OFFER_MADE | OFFER_ACCEPTED | OFFER_DECLINED | REJECTED
    package_offered: float | None = None
    allow_multiple_offers: bool = False


def _drive_dict(d) -> dict:
    return {"id": d.id, "company": d.company, "role": d.role,
            "package_lpa": d.package_lpa, "min_cgpa": d.min_cgpa,
            "max_backlogs": d.max_backlogs, "min_attendance": d.min_attendance,
            "drive_date": str(d.drive_date), "departments": d.departments,
            "status": d.status, "requires_fee_clearance": d.requires_fee_clearance,
            "application_deadline": (str(d.application_deadline)
                                     if d.application_deadline else None)}


# ---------- drive CRUD ---------------------------------------------------------
@router.get("/drives")
def list_drives(status: str | None = None,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_session)):
    drives = get_agents()["placement_agent"].list_drives(db, status=status)
    return {"drives": [_drive_dict(d) for d in drives]}


@router.get("/drives/{drive_id}")
def get_drive(drive_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_session)):
    drive = get_agents()["placement_agent"].get_drive(db, drive_id)
    if drive is None:
        raise HTTPException(status_code=404, detail={
            "success": False, "error": {"code": "DRIVE_NOT_FOUND",
                                        "message": "Drive not found."}})
    return _drive_dict(drive)


@router.post("/drives", status_code=201)
def create_drive(body: DriveCreateRequest,
                 user: User = Depends(require_role("admin")),
                 db: Session = Depends(get_session)):
    try:
        drive = get_agents()["placement_agent"].create_drive(db, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "success": False, "error": {"code": "INVALID_DRIVE",
                                        "message": str(exc)}})
    return _drive_dict(drive)


@router.put("/drives/{drive_id}")
def update_drive(drive_id: int, body: DriveUpdateRequest,
                 user: User = Depends(require_role("admin")),
                 db: Session = Depends(get_session)):
    try:
        drive = get_agents()["placement_agent"].update_drive(
            db, drive_id, body.model_dump(exclude_unset=True))
    except LookupError:
        raise HTTPException(status_code=404, detail={
            "success": False, "error": {"code": "DRIVE_NOT_FOUND",
                                        "message": "Drive not found."}})
    return _drive_dict(drive)


@router.post("/drives/{drive_id}/close")
def close_drive(drive_id: int, user: User = Depends(require_role("admin")),
                db: Session = Depends(get_session)):
    try:
        drive = get_agents()["placement_agent"].close_drive(db, drive_id)
    except LookupError:
        raise HTTPException(status_code=404, detail={
            "success": False, "error": {"code": "DRIVE_NOT_FOUND",
                                        "message": "Drive not found."}})
    return _drive_dict(drive)


# ---------- shortlist generation -----------------------------------------------
@router.post("/drives/{drive_id}/generate-shortlist")
async def generate_shortlist(drive_id: int, regenerate: bool = False,
                             user: User = Depends(require_role("admin")),
                             db: Session = Depends(get_session)):
    agent = get_agents()["placement_agent"]
    try:
        result = await agent.generate_shortlist_and_announce(
            db, drive_id, regenerate=regenerate)
    except LookupError:
        raise HTTPException(status_code=404, detail={
            "success": False, "error": {"code": "DRIVE_NOT_FOUND",
                                        "message": "Drive not found."}})
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail={
            "success": False, "error": {"code": "SHORTLIST_EXISTS",
                                        "message": str(exc)}})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={
            "success": False, "error": {"code": "DRIVE_NOT_OPEN",
                                        "message": str(exc)}})
    return result


@router.get("/drives/{drive_id}/shortlist")
def get_shortlist(drive_id: int, user: User = Depends(require_role("admin")),
                  db: Session = Depends(get_session)):
    agent = get_agents()["placement_agent"]
    if agent.get_drive(db, drive_id) is None:
        raise HTTPException(status_code=404, detail={
            "success": False, "error": {"code": "DRIVE_NOT_FOUND",
                                        "message": "Drive not found."}})
    return {"drive_id": drive_id, "shortlist": agent.get_shortlist(db, drive_id)}


# ---------- eligibility explanation ---------------------------------------------
@router.get("/drives/{drive_id}/candidates/{usn}/eligibility")
def get_eligibility(drive_id: int, usn: str,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_session)):
    usn = usn.upper().strip()
    if user.role == "student" and user.usn != usn:
        raise HTTPException(status_code=403, detail={
            "success": False, "error": {"code": "FORBIDDEN",
                                        "message": "You can only view your own eligibility."}})
    try:
        return get_agents()["placement_agent"].get_eligibility(db, drive_id, usn)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={
            "success": False, "error": {"code": "NOT_FOUND", "message": str(exc)}})


# ---------- outcomes -----------------------------------------------------------
@router.post("/drives/{drive_id}/candidates/{usn}/outcome")
async def record_outcome(drive_id: int, usn: str, body: OutcomeRequest,
                         user: User = Depends(require_role("admin")),
                         db: Session = Depends(get_session)):
    usn = usn.upper().strip()
    agent = get_agents()["placement_agent"]
    try:
        return await agent.record_outcome_and_announce(
            db, drive_id, usn, body.outcome_status.upper(),
            package_offered=body.package_offered,
            allow_multiple_offers=body.allow_multiple_offers)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={
            "success": False, "error": {"code": "NOT_FOUND", "message": str(exc)}})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "success": False, "error": {"code": "INVALID_OUTCOME",
                                        "message": str(exc)}})
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail={
            "success": False, "error": {"code": "ALREADY_PLACED",
                                        "message": str(exc)}})


@router.get("/drives/{drive_id}/outcomes")
def list_outcomes(drive_id: int, user: User = Depends(require_role("admin")),
                  db: Session = Depends(get_session)):
    agent = get_agents()["placement_agent"]
    if agent.get_drive(db, drive_id) is None:
        raise HTTPException(status_code=404, detail={
            "success": False, "error": {"code": "DRIVE_NOT_FOUND",
                                        "message": "Drive not found."}})
    return {"drive_id": drive_id, "outcomes": agent.get_outcomes(db, drive_id)}