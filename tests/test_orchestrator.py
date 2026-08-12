"""Intent classification (fallback path) + orchestrator response shape (v2)."""
import asyncio

from backend.app import llm
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


def test_orchestrator_fallback_response_shape(agents, db):
    user = db.query(User).filter_by(username="4MT23AI001").first()
    r = asyncio.run(agents["orchestrator_agent"].handle_chat(
        db, user, "What is my attendance percentage?"))
    assert r["mode"] in ("fallback", "llm")
    assert r["tools_used"][0]["name"] == "get_attendance"
    assert "attendance" in r["text"].lower() or "%" in r["text"]
