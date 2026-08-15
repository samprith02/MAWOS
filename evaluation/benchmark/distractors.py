"""Frozen distractor tools — MAWOS v3.

FROZEN AT P0. Do not edit without a dated entry in evaluation/PROTOCOL.md.

Distractors pad the tool space for the RQ4 dose-response conditions
(5/9/13/20/30 exposed tools). They exist so that "30 tools" is a real
30-tool condition rather than 13 real tools plus 17 obvious absurdities —
if the padding is transparently irrelevant the task gets *easier* with
size and the hypothesis becomes untestable.

Two properties are required of every distractor, and they pull against
each other:

  **Plausible** — it must read like a function a real university portal
  would expose, phrased in the same register as the genuine tools.

  **Never correct** — it must not be a defensible answer to any benchmark
  task. If an annotator could argue a distractor answers a query, the gold
  label for that query is ambiguous and the measurement is corrupted.

`check_disjoint()` enforces the second property mechanically: every
distractor declares its domain keywords, and none of those keywords may
appear in any benchmark query. This is a necessary condition, not a
sufficient one — it catches lexical overlap, not semantic overlap — so
the human argument for each entry is recorded in `WHY_DISJOINT`.

Two candidates were rejected during authoring and are recorded here so the
reasoning is auditable rather than invisible:

  * `get_counselling_appointment` — "counselling" is an *admissions*
    keyword in the v2 lexicon (`counsell?ing` -> admission_query) and
    appears in the task "Where does the counselling process stand?".
    Replaced by `get_wellness_appointment`.
  * `get_campus_events` — "campus" appears in the placement lexicon and in
    "When is the next campus drive?", where a reader could genuinely
    argue an events tool answers the query. Dropped entirely.
"""
import re

# name -> (description shown to the model, domain keywords that must not
#          appear in any benchmark query)
DISTRACTORS: dict[str, tuple[str, tuple[str, ...]]] = {
    "get_library_loans": (
        "Books currently borrowed by the caller, due dates and overdue "
        "library charges.", ("library", "borrow", "book")),
    "get_book_reservation": (
        "Status of a hold placed on a library title.",
        ("reservation", "hold")),
    "get_hostel_room": (
        "Hostel block and room allocation for a resident student.",
        ("hostel", "room allocation")),
    "get_hostel_leave_request": (
        "Status of a hostel leave or late-entry request.",
        ("leave request", "late entry")),
    "get_mess_menu": (
        "This week's mess menu and meal timings.",
        ("mess", "menu", "meal")),
    "get_bus_route": (
        "College bus route, stop and departure time for the caller.",
        ("bus", "route", "stop")),
    "get_parking_permit": (
        "Two-wheeler and car parking permit status on campus.",
        ("parking", "permit")),
    "get_id_card_status": (
        "Student identity card issue or reprint status.",
        ("id card", "identity card")),
    "get_wifi_credentials": (
        "Campus network account status and device registration limit.",
        ("wifi", "network account")),
    "get_locker_assignment": (
        "Assigned locker number and block for the caller.",
        ("locker",)),
    "get_sports_booking": (
        "Sports facility and ground booking slots.",
        ("sports", "ground", "booking")),
    "get_gym_membership": (
        "Campus gym membership validity for the caller.",
        ("gym",)),
    "get_medical_visit_log": (
        "Visits recorded at the campus infirmary.",
        ("infirmary", "medical visit")),
    "get_wellness_appointment": (
        "Appointment slots with the student wellness officer.",
        ("wellness",)),
    "get_alumni_contact": (
        "Alumni directory lookup by graduating batch.",
        ("alumni",)),
    "get_convocation_details": (
        "Convocation ceremony date, venue and gown collection.",
        ("convocation", "gown")),
    "get_lab_equipment": (
        "Laboratory equipment inventory and issue register.",
        ("equipment", "inventory")),
    "get_grievance_status": (
        "Status of a grievance or complaint filed by the caller.",
        ("grievance", "complaint")),
    "get_club_membership": (
        "Student club and technical chapter memberships.",
        ("club", "chapter")),
    "get_feedback_form": (
        "Pending course-feedback forms for the current term.",
        ("feedback",)),
}

# Why each entry cannot be a defensible answer to any benchmark task.
# Recorded because the mechanical check below catches lexical overlap
# only; semantic overlap is a human judgement and must be auditable.
WHY_DISJOINT = """
Every benchmark task targets one of twelve academic-record intents:
attendance, fees, scholarship, hall-ticket eligibility, exam schedule,
marks, class timetable, placements, admissions, department analytics,
notifications, student profile.

The distractors above are drawn exclusively from *campus-services*
functions — accommodation, transport, catering, facilities, library,
health, alumni, clubs, grievances. None of them reads, derives or reports
an academic record, so none can answer an academic-record question. The
two candidates that blurred that line were rejected (see module docstring).
"""

DISTRACTOR_NAMES = tuple(DISTRACTORS)


def schemas() -> list[dict]:
    """Distractors in Ollama tool-schema form, parameterless."""
    return [{"type": "function",
             "function": {"name": name, "description": desc,
                          "parameters": {"type": "object", "properties": {},
                                         "required": []}}}
            for name, (desc, _kw) in DISTRACTORS.items()]


def check_disjoint(queries, real_tool_names=()) -> list[str]:
    """Necessary-condition check. Returns a list of violations (empty = pass).

    Fails if a distractor's domain keyword appears in any benchmark query,
    or if a distractor collides with a real tool name.

    Matching is on **word boundaries**, not substrings. Substring matching
    was tried first and reported `get_mess_menu` against the task "Did I
    get any messages?" — "mess" inside "messages". A dining tool has no
    semantic overlap with a notifications query, so the substring rule was
    producing false positives, not finding real collisions. Word
    boundaries are the correct rule; multi-word keywords are matched with
    boundaries at each end of the phrase.
    """
    violations = []
    lowered = [(getattr(q, "id", "?"), getattr(q, "query", str(q)).lower())
               for q in queries]
    for name, (_desc, keywords) in DISTRACTORS.items():
        if name in real_tool_names:
            violations.append(f"{name}: collides with a real tool name")
        for kw in keywords:
            pattern = re.compile(rf"\b{re.escape(kw)}\b")
            for qid, text in lowered:
                if pattern.search(text):
                    violations.append(
                        f"{name}: keyword {kw!r} appears in task {qid}")
    return violations
