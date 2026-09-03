"""Tool registry — the capabilities the Orchestrator's LLM can invoke.

Each tool: JSON-schema parameters (sent to the LLM), allowed roles,
an executor, and a text formatter used by the offline fallback path.
Role enforcement happens HERE, not in the prompt: a student physically
cannot read another student's record regardless of what the LLM asks for.

12 tools (P2, docs/RESEARCH_PLAN_V3.md §7.1): `get_admissions_funnel` was
retired here because Admission no longer meets the agent criterion and
this was its only chat-facing capability — the admissions funnel itself
is unaffected and still served directly by the admin/principal REST
routes (`AdmissionAgent.funnel`, `backend/app/api/routes.py`).
"""
from ..models import Department, Student, User

STAFF = ("faculty", "hod", "principal", "admin")
ALL_ROLES = ("student",) + STAFF


def _resolve_usn(db, user: User, args: dict):
    """Students are locked to themselves; staff may pass any USN."""
    if user.role == "student":
        return user.usn, None
    usn = str(args.get("usn") or "").upper().strip()
    if not usn:
        return None, "Please specify the student USN."
    if db.get(Student, usn) is None:
        return None, f"Unknown USN {usn}."
    return usn, None


def _student_ctx(db, user: User):
    return db.get(Student, user.usn) if user.usn else None


TOOLS: dict[str, dict] = {}


def tool(name, description, params=None, roles=ALL_ROLES):
    def wrap(fn):
        TOOLS[name] = {
            "name": name, "description": description,
            "parameters": {"type": "object",
                           "properties": params or {},
                           "required": []},
            "roles": roles, "fn": fn,
        }
        return fn
    return wrap


USN_PARAM = {"usn": {"type": "string",
                     "description": "Student USN, e.g. 4MT23AI049 "
                                    "(staff only; students get their own)"}}


@tool("get_student_overview",
      "Full academic overview of a student: profile, attendance, fees, "
      "hall ticket, scholarship status.", USN_PARAM)
def get_student_overview(db, agents, user, args):
    usn, err = _resolve_usn(db, user, args)
    if err:
        return {"error": err}
    profile = agents["academic_agent"].student_profile(db, usn)
    from .attendance import overall_percentage
    fees = agents["finance_agent"].student_fees(db, usn)
    from ..models import HallTicket, ScholarshipAssessment
    ht = db.query(HallTicket).filter_by(usn=usn).first()
    sch = db.query(ScholarshipAssessment).filter_by(usn=usn).first()
    return {"profile": profile,
            "overall_attendance_pct": overall_percentage(db, usn),
            "fees_cleared": fees["cleared"],
            "fees_outstanding": fees["total_outstanding"],
            "hall_ticket": {"eligible": ht.eligible, "reasons": ht.reasons} if ht else None,
            "scholarship": {"status": sch.status, "reasons": sch.reasons} if sch else None}


@tool("get_attendance", "Per-subject attendance percentages for a student.",
      USN_PARAM)
def get_attendance(db, agents, user, args):
    usn, err = _resolve_usn(db, user, args)
    if err:
        return {"error": err}
    from ..models import AttendanceSummary
    from .attendance import overall_percentage
    subs = db.query(AttendanceSummary).filter_by(usn=usn).all()
    return {"usn": usn, "overall_pct": overall_percentage(db, usn),
            "subjects": [{"subject": s.subject_code, "attended": s.classes_attended,
                          "held": s.classes_held, "pct": s.percentage,
                          "shortage": s.shortage} for s in subs]}


@tool("get_marks", "Internal (CIE) marks per subject for a student.", USN_PARAM)
def get_marks(db, agents, user, args):
    usn, err = _resolve_usn(db, user, args)
    if err:
        return {"error": err}
    return {"usn": usn, "marks": agents["academic_agent"].student_marks(db, usn)}


@tool("get_fees", "Fee items, dues, fines and payment status for a student.",
      USN_PARAM)
def get_fees(db, agents, user, args):
    usn, err = _resolve_usn(db, user, args)
    if err:
        return {"error": err}
    return {"usn": usn, **agents["finance_agent"].student_fees(db, usn)}


@tool("get_hall_ticket", "Hall-ticket (exam) eligibility with reasons.", USN_PARAM)
def get_hall_ticket(db, agents, user, args):
    usn, err = _resolve_usn(db, user, args)
    if err:
        return {"error": err}
    result = agents["eligibility_agent"].evaluate_hall_ticket(db, usn)
    db.commit()
    return result


@tool("get_scholarship", "Scholarship eligibility (rules + CART score).", USN_PARAM)
def get_scholarship(db, agents, user, args):
    usn, err = _resolve_usn(db, user, args)
    if err:
        return {"error": err}
    result = agents["eligibility_agent"].evaluate_scholarship(db, usn)
    db.commit()
    return result


@tool("get_placements", "Upcoming placement drives and the student's "
      "eligibility/success probability (final years).", USN_PARAM)
def get_placements(db, agents, user, args):
    if user.role == "student":
        return {"drives": agents["placement_agent"].student_view(db, user.usn)}
    usn = str(args.get("usn") or "").upper().strip()
    if usn:
        return {"drives": agents["placement_agent"].student_view(db, usn)}
    return agents["placement_agent"].stats(db)


@tool("get_timetable", "Weekly class timetable. Students/faculty get their own "
      "automatically; staff may pass dept/year/section.",
      {"dept": {"type": "string"}, "year": {"type": "integer"},
       "section": {"type": "string"}})
def get_timetable(db, agents, user, args):
    tt = agents["timetable_agent"]
    if user.role == "student":
        s = _student_ctx(db, user)
        return tt.grid(db, s.dept_code, s.year, s.section)
    if user.role in ("faculty", "hod") and not args.get("dept"):
        if user.faculty_id:
            return tt.faculty_grid(db, user.faculty_id)
    dept = str(args.get("dept") or "AIML").upper()
    return tt.grid(db, dept, int(args.get("year") or 3),
                   str(args.get("section") or "A").upper())


@tool("get_exam_schedule", "Semester-end exam schedule for a dept/semester.",
      {"dept": {"type": "string"}, "semester": {"type": "integer"}})
def get_exam_schedule(db, agents, user, args):
    if user.role == "student":
        s = _student_ctx(db, user)
        dept, sem = s.dept_code, s.semester
    else:
        dept = str(args.get("dept") or "AIML").upper()
        sem = int(args.get("semester") or 5)
    return {"dept": dept, "semester": sem,
            "exams": agents["eligibility_agent"].schedule_for(db, dept, sem)}


@tool("get_notifications", "The caller's recent notifications.")
def get_notifications(db, agents, user, args):
    return {"notifications": agents["notification_agent"].for_user(
        db, usn=user.usn, role=user.role, dept=user.dept_code)}


@tool("get_dept_analytics", "Department analytics: headcount, average "
      "attendance/CGPA, shortage counts, fee defaulters.",
      {"dept": {"type": "string"}}, roles=STAFF)
def get_dept_analytics(db, agents, user, args):
    dept = str(args.get("dept") or user.dept_code or "AIML").upper()
    if user.role in ("faculty", "hod") and user.dept_code:
        dept = user.dept_code   # staff scoped to their department
    data = agents["academic_agent"].dept_analytics(db, dept)
    data["fee_defaulters"] = agents["finance_agent"].defaulter_list(db, dept, limit=10)
    return data


@tool("get_institution_analytics", "Institution-wide analytics across all "
      "departments (principal/admin view).", roles=("principal", "admin"))
def get_institution_analytics(db, agents, user, args):
    return {"departments": agents["academic_agent"].institution_analytics(db),
            "fee_collection": agents["finance_agent"].collection_stats(db),
            "placements": agents["placement_agent"].stats(db)}


def schemas_for_role(role: str) -> list[dict]:
    """Ollama tools array, filtered by the caller's role."""
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["parameters"]}}
            for t in TOOLS.values() if role in t["roles"]]


def execute(db, agents, user, name: str, args: dict) -> dict:
    t = TOOLS.get(name)
    if t is None:
        return {"error": f"unknown tool {name}"}
    if user.role not in t["roles"]:
        return {"error": f"role '{user.role}' is not permitted to use {name}"}
    try:
        return t["fn"](db, agents, user, args or {})
    except Exception as exc:  # tool errors go back to the LLM, not the user
        return {"error": f"{type(exc).__name__}: {exc}"}
