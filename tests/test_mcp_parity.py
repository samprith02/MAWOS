"""Guard-parity suite -- the project's second experiment
(docs/superpowers/specs/2026-09-13-mawos-v5-design.md §6).

The claim under test, stated precisely:

    Guard decisions are identical regardless of which LLM drives the tools.

MAWOS has two entry points to its capabilities:
  - the internal planner  -> backend/app/agents/tools.py::execute
  - an external MCP client -> backend/app/mcp_server.py::call_as

Both MUST reach tools through the same deterministic guard
(backend/app/guard.py), so an external LLM gets no privilege the internal
planner lacks. `call_as` is, by reading, a thin delegation straight to
`execute` -- so this suite is also a regression guard: if a future change
ever gives the MCP path its own authorisation logic, this file is what
would catch the divergence.

Each item below is one adversarial (or control) case, run through BOTH
paths with the SAME parity assertion:

  - the same allow/deny outcome,
  - the same reason_code,
  - the same number of GuardDecision rows written (exactly one per call),
  - and, for denied write attempts, that the underlying table row count
    is unchanged by EITHER path.

If any item ever diverges between the two paths, that is a genuine
research finding for the guard-parity experiment. Report it -- do not
edit this file (or the fixtures) to make it pass again.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func

from backend.app import guard
from backend.app.agents import tools as toolreg
from backend.app.mcp_server import call_as
from backend.app.models import AttendanceRecord, GuardDecision, HallTicket, User
from tests.fixtures.mini_institution import (
    FACULTY_USER, HOD_USER, STUDENT_OK, STUDENT_OTHER_DEPT, STUDENT_RISK,
    STUDENT_UNKNOWN, SUBJECT_OTHER_DEPT, SUBJECT_THEORY, SECTION,
)

PATHS = {
    "internal_planner": toolreg.execute,   # backend/app/agents/tools.py::execute
    "mcp_external": call_as,               # backend/app/mcp_server.py::call_as
}


def _user(db, username):
    return db.query(User).filter_by(username=username).one()


def _table_count(db, model, **filters):
    q = db.query(model)
    if filters:
        q = q.filter_by(**filters)
    return q.count()


def _static(args):
    """Wrap a plain args dict so it can be called per-path like the
    per-path callables below (used for the one item -- Item 9 -- where the
    two paths must use different dates to avoid tripping mark_attendance's
    own duplicate-prevention, which is business logic, not the guard, and
    would otherwise make an *allowed* write look like it diverged)."""
    return lambda _path: dict(args)


# --------------------------------------------------------------------- items
# (id, actor, capability, args_for(path), expected verdict, expected
#  reason_code, optional (model, filter-kwargs) to prove a denied write
#  touched nothing, why this is adversarial)
ITEMS = [
    dict(
        id="01_student_reads_another_students_record",
        actor=STUDENT_OK,
        capability="get_attendance",
        args=_static({"usn": STUDENT_RISK}),
        verdict="denied", reason=guard.REASON_OUT_OF_SCOPE,
        table=None,
        why="Horizontal privilege escalation: a student passes a "
            "classmate's USN instead of their own to a read tool that "
            "accepts a usn argument.",
    ),
    dict(
        id="02_student_invokes_staff_only_read_tool",
        actor=STUDENT_OK,
        capability="get_dept_analytics",
        args=_static({"dept": "AIML"}),
        verdict="denied", reason=guard.REASON_NOT_PERMITTED,
        table=None,
        why="Vertical privilege escalation: a student calls a capability "
            "never exposed to the student role at all (STAFF-only), "
            "distinct from item 1's within-role scope violation.",
    ),
    dict(
        id="03_student_invokes_write_tool",
        actor=STUDENT_OK,
        capability="mark_attendance",
        args=_static({"section": SECTION, "subject_code": SUBJECT_THEORY,
                      "date": "2031-01-03", "absentees": []}),
        verdict="denied", reason=guard.REASON_NOT_PERMITTED,
        table=(AttendanceRecord, {"subject_code": SUBJECT_THEORY,
                                   "date": dt.date(2031, 1, 3)}),
        why="A student attempts a write outright (mark_attendance is "
            "STAFF-only, writes=True) -- the sharpest possible escalation.",
    ),
    dict(
        id="04_faculty_writes_subject_section_not_taught",
        actor=FACULTY_USER,
        capability="mark_attendance",
        args=_static({"section": SECTION, "subject_code": SUBJECT_OTHER_DEPT,
                      "date": "2031-01-04", "absentees": []}),
        verdict="denied", reason=guard.REASON_OUT_OF_SCOPE,
        table=(AttendanceRecord, {"subject_code": SUBJECT_OTHER_DEPT,
                                   "date": dt.date(2031, 1, 4)}),
        why="A legitimate write role (faculty) targets a subject-section "
            "they hold no TeachingAssignment for -- the guard's only "
            "data-dependent ownership rule, cheap for a confused or "
            "adversarial LLM to get wrong by citing the wrong subject code.",
    ),
    dict(
        id="05_hod_writes_against_another_departments_student",
        actor=HOD_USER,
        capability="issue_eligibility_override",
        args=_static({"usn": STUDENT_OTHER_DEPT, "exam": "mid-sem",
                      "reason": "parity probe"}),
        verdict="denied", reason=guard.REASON_OUT_OF_SCOPE,
        table=(HallTicket, {"usn": STUDENT_OTHER_DEPT}),
        why="HOD department scoping on the highest-privilege write in the "
            "system: the target student is real and the USN well-formed, "
            "so only the department-ownership check can catch this.",
    ),
    dict(
        id="06_unknown_hallucinated_capability_name",
        actor=STUDENT_OK,
        capability="generate_admin_report_v2",
        args=_static({}),
        verdict="denied", reason=guard.REASON_NOT_PERMITTED,
        table=None,
        # NOTE: tools.execute() short-circuits on `TOOLS.get(name) is None`
        # BEFORE ever calling guard.authorise() (backend/app/agents/tools.py
        # execute(), the `if t is None: return ...` branch) -- so a truly
        # unregistered capability name writes ZERO GuardDecision rows,
        # unlike a real-but-forbidden one (item 2/3/10, which all log 1).
        # Both paths take this same shortcut (call_as delegates straight to
        # execute), so it is NOT a parity divergence -- see parity-report.md
        # for why this is still worth flagging as a separate finding: a
        # hallucinated-tool-name attempt is invisible to the audit trail.
        guard_rows_expected=0,
        why="A capability name that was never registered at all -- what an "
            "LLM hallucinating a plausible-sounding tool would produce. "
            "Must be denied the same way as a real-but-forbidden tool "
            "(test_guard.py::test_role_exclusion_and_unknown_capability_"
            "are_distinguishable already proves that at the guard-unit "
            "level; this proves both entry points reach that same branch).",
    ),
    dict(
        id="07_write_attempt_nonexistent_student_usn",
        actor=HOD_USER,
        capability="issue_eligibility_override",
        args=_static({"usn": STUDENT_UNKNOWN, "exam": "mid-sem",
                      "reason": "parity probe"}),
        verdict="denied", reason=guard.REASON_PRECONDITION_FAILED,
        table=(HallTicket, {"usn": STUDENT_UNKNOWN}),
        why="An otherwise-authorised HOD names a USN that was never "
            "inserted -- an LLM inventing or mistyping a student "
            "identifier. Distinguishes PRECONDITION_FAILED from the two "
            "role/scope reason codes exercised elsewhere in this suite.",
    ),
    dict(
        id="08_control_staff_read_legitimately_allowed",
        actor=FACULTY_USER,
        capability="get_student_overview",
        args=_static({"usn": STUDENT_OK}),
        verdict="allowed", reason="",
        table=None,
        why="CONTROL: parity must hold for allows too, not just denials. "
            "Faculty reading a real student's overview is unremarkable and "
            "must succeed identically on both paths.",
    ),
    dict(
        id="09_control_faculty_writes_subject_section_taught",
        actor=FACULTY_USER,
        capability="mark_attendance",
        # Distinct dates per path: mark_attendance has its own
        # duplicate-prevention (backend/app/agents/attendance.py `mark`),
        # which is business logic, not the guard. Reusing one date across
        # both paths would make the second call's *tool-level* outcome
        # differ (no roster student left to mark) even though the guard's
        # allow/reason_code verdict is identical either way -- that would
        # be a false alarm, not a guard divergence.
        args=lambda path: {
            "section": SECTION, "subject_code": SUBJECT_THEORY,
            "date": "2031-02-01" if path == "internal_planner" else "2031-02-02",
            "absentees": [],
        },
        verdict="allowed", reason="",
        table=None,
        why="CONTROL: the write-side mirror of item 8 -- faculty writing "
            "against a subject-section they ARE assigned to must be "
            "allowed on both paths, not just the denial shapes.",
    ),
    dict(
        id="10_faculty_attempts_hod_only_write",
        actor=FACULTY_USER,
        capability="issue_eligibility_override",
        args=_static({"usn": STUDENT_OK, "exam": "mid-sem",
                      "reason": "parity probe"}),
        verdict="denied", reason=guard.REASON_NOT_PERMITTED,
        table=(HallTicket, {"usn": STUDENT_OK}),
        why="A faculty member -- a real write-capable role -- reaches for "
            "the one write narrower than plain STAFF (issue_eligibility_"
            "override is hod/principal only). Distinct from item 3: here "
            "the actor CAN write in general, just not this capability, so "
            "the role-exposure check has to fire on a per-tool roles list, "
            "not a coarse student/staff split.",
    ),
]


@pytest.mark.parametrize("item", ITEMS, ids=[i["id"] for i in ITEMS])
def test_guard_parity(db, agents, base_data, item):
    actor = _user(db, item["actor"])
    capability = item["capability"]

    table_spec = item["table"]
    baseline = None
    if table_spec:
        model, filters = table_spec
        baseline = _table_count(db, model, **filters)

    expected_guard_rows = item.get("guard_rows_expected", 1)

    logged = {}
    for path_name, executor in PATHS.items():
        args = item["args"](path_name)

        guard_max_before = db.query(func.max(GuardDecision.id)).scalar() or 0
        result = executor(db, agents, actor, capability, args)
        db.commit()
        new_rows = (db.query(GuardDecision)
                    .filter(GuardDecision.id > guard_max_before).all())
        guard_delta = len(new_rows)

        if guard_delta == 1:
            verdict, reason_code = new_rows[0].verdict, new_rows[0].reason_code
        elif guard_delta == 0:
            # No GuardDecision row was written at all (e.g. a genuinely
            # unregistered capability -- tools.execute() short-circuits
            # before ever calling guard.authorise(), see item 6's note
            # above). Fall back to the call's own result, since there is
            # no logged row to read a verdict off of.
            verdict = "denied" if "error" in result else "allowed"
            reason_code = result.get("reason_code", "")
        else:
            verdict = reason_code = None  # surfaced by the assertion below

        logged[path_name] = {
            "result": result, "guard_delta": guard_delta,
            "verdict": verdict, "reason_code": reason_code,
        }

        # The expected number of GuardDecision rows per call (1 for every
        # item except the unregistered-capability case, which is 0).
        assert logged[path_name]["guard_delta"] == expected_guard_rows, (
            f"{path_name} wrote {logged[path_name]['guard_delta']} "
            f"GuardDecision row(s) for {item['id']}, expected "
            f"{expected_guard_rows}")

        # This path matches the pre-registered expectation for the item.
        assert logged[path_name]["verdict"] == item["verdict"], (
            f"{path_name} verdict {logged[path_name]['verdict']!r} != "
            f"expected {item['verdict']!r} for {item['id']}")
        assert logged[path_name]["reason_code"] == item["reason"], (
            f"{path_name} reason_code {logged[path_name]['reason_code']!r} "
            f"!= expected {item['reason']!r} for {item['id']}")

        if table_spec and item["verdict"] == "denied":
            model, filters = table_spec
            after = _table_count(db, model, **filters)
            assert after == baseline, (
                f"{path_name} changed {model.__name__} row count for a "
                f"DENIED write in {item['id']}: {baseline} -> {after}")

    # -------------------------------------------------- the parity assertion
    # Both paths must have produced the identical guard-level outcome. This
    # is the actual claim under test -- everything above just establishes
    # each path independently matched the pre-registered expectation; this
    # is what proves they matched EACH OTHER.
    a, b = logged["internal_planner"], logged["mcp_external"]
    assert a["verdict"] == b["verdict"], (
        f"GUARD PARITY DIVERGENCE in {item['id']}: internal_planner="
        f"{a['verdict']!r} vs mcp_external={b['verdict']!r}")
    assert a["reason_code"] == b["reason_code"], (
        f"GUARD PARITY DIVERGENCE in {item['id']}: internal_planner "
        f"reason_code={a['reason_code']!r} vs mcp_external="
        f"{b['reason_code']!r}")
    assert a["guard_delta"] == b["guard_delta"], (
        f"GUARD PARITY DIVERGENCE in {item['id']}: internal_planner logged "
        f"{a['guard_delta']} GuardDecision row(s) vs mcp_external "
        f"{b['guard_delta']}")
