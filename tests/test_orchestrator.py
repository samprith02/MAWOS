"""Intent classification, the v3 hybrid router, and response shape."""
import asyncio

import pytest

from backend.app import llm, router
from backend.app.models import User


def test_keyword_classifier_v2_intents():
    cases = {
        "What is my attendance percentage?": "attendance_query",
        "Do I have pending fees?": "fees_query",
        "Am I eligible for the scholarship?": "scholarship_query",
        "Will I get my hall ticket?": "exam_query",
        "When do semester exams start?": "exam_schedule_query",
        "Show my internal marks": "marks_query",
        "What classes do I have this week?": "timetable_query",
        "Which placement drives am I eligible for?": "placement_query",
        "Show the admissions funnel": "admission_query",
        "Show my notifications": "notification_query",
    }
    for query, expected in cases.items():
        assert llm.classify_keyword(query).intent == expected, query


def test_orchestrator_response_shape(agents, db):
    user = db.query(User).filter_by(username="4MT23AI001").first()
    r = asyncio.run(agents["orchestrator_agent"].handle_chat(
        db, user, "What is my attendance percentage?"))
    assert r["mode"] in ("lexicon", "llm")
    assert r["tools_used"][0]["name"] == "get_attendance"
    assert "attendance" in r["text"].lower() or "%" in r["text"]
    assert r["routing"]["tier"] in ("lexicon", "llm")
    assert r["routing"]["tau"] == router.TAU


# --------------------------------------------------------------- P4 router
def test_live_lexicon_matches_the_frozen_baseline():
    """The deployed classifier must not drift from the frozen instrument.

    `evaluation/baselines/lexicon_v2.py` is a hashed copy taken at P0, and
    every v3 number — the 89.8% baseline, the margins, the tuned tau — is
    computed against it. If the live classifier ever disagrees, those
    numbers stop describing the running system, silently. This is the
    tripwire.
    """
    lexicon_v2 = pytest.importorskip("evaluation.baselines.lexicon_v2")
    from evaluation.benchmark.tasks import DEV_TASKS
    for task in DEV_TASKS:
        assert (llm.classify_keyword(task.query).intent
                == lexicon_v2.classify_keyword(task.query).intent), task.id


def test_margin_is_the_tuned_definition():
    """Top-1 minus top-2, and zero when nothing matches at all."""
    assert llm.classify_keyword("qwertyuiop zxcvbnm").margin == 0.0
    assert llm.classify_keyword("What is my attendance percentage?").margin > 0


def test_escalation_policy_is_the_frozen_threshold():
    assert router.should_escalate(router.TAU)
    assert not router.should_escalate(router.TAU + 0.5)
    cfg = router._load()
    assert cfg["model"] == "qwen2.5:3b-instruct"     # PROTOCOL 9.2
    assert cfg["tau"] == router.TAU                  # PROTOCOL 9.3


def test_unmatched_queries_escalate_and_confident_ones_do_not():
    _, unknown = router.decide("qwertyuiop zxcvbnm")
    assert unknown.margin == 0.0
    # `escalated` also depends on Ollama being up; the policy call does not.
    assert router.should_escalate(unknown.margin)
    _, clear = router.decide("What is my attendance percentage?")
    assert not clear.escalated and clear.tier == "lexicon"
