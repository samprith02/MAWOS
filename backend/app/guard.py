"""Deterministic authorisation. Non-bypassable, and the single place where
"may this actor do this?" is answered.

Two properties are load-bearing for `docs/v4/07_CONTRIBUTION.md` claim 1:

1. Allowed and denied outcomes are recorded in the SAME shape. If denials
   were exceptions and successes were silent, the attempt rate would be
   uncomputable -- and the attempt rate is the claim.
2. `exposed` distinguishes "tried and was stopped" from "never could have
   tried". R0.5 measured 0 attempts, but only because the role filter never
   showed the capability. That is a different fact and must stay visible.

Nothing here consults the LLM. That is the point: the model may propose
anything; what executes is decided by this module alone.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import GuardDecision, Student, TeachingAssignment

REASON_NOT_PERMITTED = "NOT_PERMITTED"
REASON_OUT_OF_SCOPE = "OUT_OF_SCOPE"
REASON_PRECONDITION_FAILED = "PRECONDITION_FAILED"


@dataclass
class GuardVerdict:
    allowed: bool
    reason_code: str = ""
    detail: str = ""
    capability: str = ""
    target: str = ""


def _spec(capability: str) -> dict | None:
    from .agents.tools import TOOLS
    return TOOLS.get(capability)


def _is_exposed(user, capability: str) -> bool:
    spec = _spec(capability)
    return bool(spec) and user.role in spec["roles"]


def _target_of(capability: str, args: dict) -> str:
    for key in ("usn", "section", "subject_code", "student", "target"):
        if args.get(key):
            return f"{key}={args[key]}"
    return ""


def _owns_subject_section(db, user, args: dict) -> bool:
    """Faculty may only write against a subject-section they are assigned."""
    if user.faculty_id is None:
        return False
    q = db.query(TeachingAssignment).filter_by(faculty_id=user.faculty_id)
    if args.get("subject_code"):
        q = q.filter_by(subject_code=args["subject_code"])
    if args.get("section"):
        q = q.filter_by(section=args["section"])
    return db.query(q.exists()).scalar()


def _decide(db, user, capability: str, args: dict) -> GuardVerdict:
    target = _target_of(capability, args)
    spec = _spec(capability)

    if spec is None or user.role not in spec["roles"]:
        return GuardVerdict(False, REASON_NOT_PERMITTED,
                            f"role '{user.role}' may not use {capability}",
                            capability, target)

    # Students are locked to their own record, regardless of what was asked.
    if user.role == "student":
        asked = str(args.get("usn") or "").upper().strip()
        if asked and asked != (user.usn or "").upper():
            return GuardVerdict(False, REASON_OUT_OF_SCOPE,
                                "students may only read their own record",
                                capability, target)

    if spec.get("writes"):
        if user.role == "faculty" and not _owns_subject_section(db, user, args):
            return GuardVerdict(False, REASON_OUT_OF_SCOPE,
                                "faculty is not assigned to this subject-section",
                                capability, target)
        if args.get("usn") and db.get(Student, str(args["usn"]).upper()) is None:
            return GuardVerdict(False, REASON_PRECONDITION_FAILED,
                                f"unknown student {args['usn']}",
                                capability, target)

    return GuardVerdict(True, "", "", capability, target)


def authorise(db, user, capability: str, args: dict,
              turn_id: str | None = None) -> GuardVerdict:
    """The only authorisation entry point. Always logs, then returns."""
    args = args or {}
    verdict = _decide(db, user, capability, args)
    db.add(GuardDecision(
        turn_id=turn_id,
        actor=user.username,
        actor_role=user.role,
        capability=capability,
        target=verdict.target,
        verdict="allowed" if verdict.allowed else "denied",
        reason_code=verdict.reason_code,
        detail=verdict.detail,
        was_exposed=_is_exposed(user, capability),
    ))
    return verdict
