"""Claim 1 rests on this module: guard placement, not model choice,
determines safety. Every case below is an authorisation outcome that must
be recorded in the same shape whether it allowed or denied."""
from backend.app import guard
from backend.app.models import GuardDecision, User


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
