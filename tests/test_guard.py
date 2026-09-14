"""Claim 1 rests on this module: guard placement, not model choice,
determines safety. Every case below is an authorisation outcome that must
be recorded in the same shape whether it allowed or denied."""
from backend.app import guard
from backend.app.models import GuardDecision, User
from tests.fixtures.mini_institution import FACULTY_USER, SECTION, SUBJECT_THEORY


def _user(db, username):
    return db.query(User).filter_by(username=username).one()


def test_student_may_read_own_attendance(db, agents, base_data):
    u = db.query(User).filter_by(role="student").first()
    v = guard.authorise(db, u, "get_attendance", {"usn": u.usn})
    assert v.allowed is True
    assert v.reason_code == ""


def test_student_may_not_read_another_students_attendance(db, agents, base_data):
    u = db.query(User).filter_by(role="student").first()
    v = guard.authorise(db, u, "get_attendance", {"usn": "1VT23AI999"})
    assert v.allowed is False
    assert v.reason_code == guard.REASON_OUT_OF_SCOPE


def test_student_may_not_mark_attendance(db, agents, base_data):
    u = db.query(User).filter_by(role="student").first()
    v = guard.authorise(db, u, "mark_attendance", {})
    assert v.allowed is False
    assert v.reason_code == guard.REASON_NOT_PERMITTED


def test_every_decision_is_logged_allowed_and_denied(db, agents, base_data):
    before = db.query(GuardDecision).count()
    u = db.query(User).filter_by(role="student").first()
    guard.authorise(db, u, "get_attendance", {"usn": u.usn})        # allowed
    guard.authorise(db, u, "mark_attendance", {})                   # denied
    db.commit()
    rows = db.query(GuardDecision).order_by(GuardDecision.id).all()
    assert len(rows) == before + 2
    assert {r.verdict for r in rows[-2:]} == {"allowed", "denied"}


def test_denial_of_unexposed_capability_is_marked_unexposed(db, agents, base_data):
    """A student never sees mark_attendance in their schema, so a denial
    there is NOT a real attempt. R0.5 measured 0 attempts only because the
    role filter hid the capability -- a different fact, and it must stay
    distinguishable."""
    u = db.query(User).filter_by(role="student").first()
    guard.authorise(db, u, "mark_attendance", {})
    db.commit()
    row = db.query(GuardDecision).order_by(GuardDecision.id.desc()).first()
    assert row.was_exposed is False


def test_unknown_capability_is_denied_not_crashed(db, agents, base_data):
    u = db.query(User).filter_by(role="student").first()
    v = guard.authorise(db, u, "definitely_not_a_tool", {})
    assert v.allowed is False
    assert v.reason_code == guard.REASON_NOT_PERMITTED


def test_role_exclusion_and_unknown_capability_are_distinguishable(db, agents, base_data):
    """After Task 6, mark_attendance EXISTS but is staff-only. A student hitting
    it must be denied by the ROLE filter, not by the unknown-capability branch --
    and a genuinely unknown capability must still be denied separately."""
    from backend.app.agents.tools import TOOLS
    u = db.query(User).filter_by(role="student").first()

    assert "mark_attendance" in TOOLS, "Task 6 must register this tool"
    real = guard.authorise(db, u, "mark_attendance", {})
    fake = guard.authorise(db, u, "definitely_not_a_tool", {})
    db.commit()

    assert real.allowed is False and fake.allowed is False
    assert real.reason_code == guard.REASON_NOT_PERMITTED
    assert fake.reason_code == guard.REASON_NOT_PERMITTED
    # The discriminator: a registered-but-forbidden capability is a real
    # capability; an unknown one is not. was_exposed is False for both
    # (a student never sees either), so the distinguishing fact is
    # registry membership, asserted above.


def test_faculty_without_the_assignment_is_denied_a_write(db, agents, base_data):
    """The ownership branch: a faculty member may only write against a
    subject-section they are actually assigned. This is the guard's only
    data-dependent rule, and it went live in Task 6 untested."""
    fac = db.query(User).filter_by(username=FACULTY_USER).one()

    # assigned subject+section -> allowed
    ok = guard.authorise(db, fac, "mark_attendance",
                         {"subject_code": SUBJECT_THEORY, "section": SECTION})
    # a subject they do NOT teach -> denied as out of scope
    no = guard.authorise(db, fac, "mark_attendance",
                         {"subject_code": "9ZZ99", "section": SECTION})
    db.commit()

    assert ok.allowed is True
    assert no.allowed is False
    assert no.reason_code == guard.REASON_OUT_OF_SCOPE
