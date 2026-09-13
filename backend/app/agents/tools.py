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


def tool(name, description, params=None, roles=ALL_ROLES, writes=False):
    def wrap(fn):
        TOOLS[name] = {
            "name": name, "description": description,
            "parameters": {"type": "object",
                           "properties": params or {},
                           "required": []},
            "roles": roles, "fn": fn, "writes": writes,
        }
        return fn
    return wrap


def write_tool_names() -> tuple[str, ...]:
    """Capabilities that mutate institutional state. These are the ones the
    graph must route through a human confirmation turn."""
    return tuple(n for n, t in TOOLS.items() if t.get("writes"))


#: No realistic example value here, deliberately. R0.5 measured two local
#: models copying the example USN straight out of this description and then
#: answering about a student nobody had asked about
#: (evaluation/results/v4_gates/r05_findings.md 3.1).
USN_PARAM = {"usn": {"type": "string",
                     "description": "Student USN in the institution's format "
                                    "(staff only; students always get their "
                                    "own record and must not pass this)"}}


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
      "eligibility against each drive's cutoffs (final years).", USN_PARAM)
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


def execute(db, agents, user, name: str, args: dict,
            turn_id: str | None = None) -> dict:
    """Every capability call passes the guard first. Role checks used to
    live inline here; they now live in `guard.authorise`, which also logs
    the outcome. Nothing may reach a tool function without a verdict.
    """
    from ..guard import authorise
    t = TOOLS.get(name)
    if t is None:
        return {"error": f"unknown tool {name}", "reason_code": "NOT_PERMITTED"}
    verdict = authorise(db, user, name, args or {}, turn_id=turn_id)
    if not verdict.allowed:
        return {"error": verdict.detail or f"{name} refused",
                "reason_code": verdict.reason_code}
    try:
        return t["fn"](db, agents, user, args or {})
    except Exception as exc:  # tool errors go back to the LLM, not the user
        return {"error": f"{type(exc).__name__}: {exc}",
                "reason_code": "PRECONDITION_FAILED"}


# --------------------------------------------------------------- write tools
# The three MVRS writes (spec §7.1). Each mutates institutional state and is
# therefore gated by a human confirmation turn in the graph -- the guard
# decides whether a write may be PROPOSED; the human decides whether it happens.

@tool("mark_attendance",
      "Mark attendance for a section on a date, naming the absentees.",
      {"section": {"type": "string"}, "subject_code": {"type": "string"},
       "date": {"type": "string"}, "absentees": {"type": "array",
                                                 "items": {"type": "string"}}},
      roles=STAFF, writes=True)
def mark_attendance(db, agents, user, args):
    return agents["attendance_agent"].mark(
        db, section=args.get("section"), subject_code=args.get("subject_code"),
        date=args.get("date"), absentees=args.get("absentees") or [],
        marked_by=user.username)


@tool("apply_timetable_change",
      "Move a class to a different slot after counterfactual scoring.",
      {"section": {"type": "string"}, "slot_id": {"type": "integer"},
       "new_day": {"type": "integer"}, "new_period": {"type": "integer"}},
      roles=("hod", "principal", "admin"), writes=True)
def apply_timetable_change(db, agents, user, args):
    return agents["timetable_agent"].apply_change(
        db, slot_id=args.get("slot_id"), new_day=args.get("new_day"),
        new_period=args.get("new_period"))


@tool("issue_eligibility_override",
      "Override a hall-ticket eligibility decision for one student, with a "
      "recorded reason. The highest-privilege write in the system.",
      {"usn": {"type": "string"}, "exam": {"type": "string"},
       "reason": {"type": "string"}},
      roles=("hod", "principal"), writes=True)
def issue_eligibility_override(db, agents, user, args):
    return agents["eligibility_agent"].override(
        db, usn=args.get("usn"), exam=args.get("exam"),
        reason=args.get("reason"), decided_by=user.username)
