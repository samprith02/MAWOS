"""LLM layer v2.

Primary path: local Ollama chat API with native tool calling (Qwen2.5-class
models). The Orchestrator sends the conversation + the role-filtered tool
schemas; the model decides which tools to call and finally writes a grounded
natural-language answer.

Offline fallback: deterministic weighted-keyword classifier mapping a query
to the single most likely tool. Always available; its share of traffic is
the measured fallback-trigger rate.

11 intents (P2): `admission_query` was retired with `get_admissions_funnel`
(docs/RESEARCH_PLAN_V3.md §7.1) — Admission no longer meets the agent
criterion and this was its only chat-facing capability.
"""
import re
import time

import httpx

from . import config

# fallback intent -> tool name
INTENT_TOOL = {
    "attendance_query": "get_attendance",
    "fees_query": "get_fees",
    "scholarship_query": "get_scholarship",
    "exam_query": "get_hall_ticket",
    "exam_schedule_query": "get_exam_schedule",
    "marks_query": "get_marks",
    "timetable_query": "get_timetable",
    "placement_query": "get_placements",
    "analytics_query": "get_dept_analytics",
    "notification_query": "get_notifications",
    "profile_query": "get_student_overview",
}
INTENTS = list(INTENT_TOOL)

_LEXICON: dict[str, list[tuple[str, float]]] = {
    "attendance_query": [
        (r"attendance(?!.*event)", 3), (r"absent", 2), (r"shortage", 2.5),
        (r"miss\w*\b.{0,20}\b(class|lecture)", 3), (r"75\s*%", 2),
        (r"bunk|skip\w*", 2), (r"below the limit", 2.5), (r"present", 1.5),
    ],
    "fees_query": [
        (r"fees?", 3), (r"tuition", 2.5), (r"payment", 2), (r"fine", 1.5),
        (r"dues?\b|owe", 2.5), (r"pay\b", 1.5), (r"defaulter", 2.5),
        (r"penalt\w*", 2), (r"receipt", 2),
    ],
    "scholarship_query": [
        # "fee waiver" outranks the bare "fee" signal: a waiver request is a
        # financial-aid request by definition, not a payment query.
        (r"scholarship", 3.5), (r"stipend", 2.5), (r"fee waiver", 4.5),
        (r"waive", 2.5),
        (r"(financial|money) (aid|help|support)", 3.5), (r"grant", 2),
        (r"merit.{0,15}(scholar|award)", 2.5),
    ],
    "exam_query": [
        (r"hall\s*ticket", 3.5), (r"admit card", 3),
        (r"eligib\w*.{0,20}exam", 3), (r"sit for the (finals?|exams?)", 3),
        (r"writ\w* (my )?(papers?|exams?|finals?)", 2.5),
        (r"exam hall", 3), (r"blocked", 1.5),
    ],
    "exam_schedule_query": [
        (r"exam (schedule|time\s*table|dates?)", 3.5), (r"when.{0,25}exams?", 3),
        (r"(sem|semester).{0,15}exam", 2), (r"exams? (start|begin)", 3),
    ],
    "marks_query": [
        (r"marks?\b", 3), (r"internals?\b", 2.5), (r"\bcie\b", 3.5),
        (r"scores?\b", 1.5), (r"test (result|performance)", 2.5),
    ],
    "timetable_query": [
        (r"time\s*table(?!.*exam)", 3.5), (r"class schedule", 3),
        (r"(what|which).{0,15}(class(es)?|periods?|subjects?)\b", 3),
        (r"(class(es)?|periods?).{0,20}(today|tomorrow|this week)", 3),
        (r"my (classes|schedule)\b", 2.5), (r"routine", 2),
    ],
    "placement_query": [
        (r"placement", 3), (r"compan(y|ies)|firms?", 2), (r"drive", 2),
        (r"job|recruit\w*|hired?", 2.5), (r"shortlist\w*", 2.5),
        (r"package|lpa", 2), (r"interview", 2), (r"cutoff", 2),
        (r"openings?", 2.5), (r"campus", 1.5),
    ],
    "analytics_query": [
        (r"analytics|statistics|overview of (the )?(dept|department|branch)", 3),
        (r"how (is|are) (the )?(dept|department|students) (doing|performing)", 3),
        # "average X" is an aggregate signal — outranks the per-student domain word.
        (r"average (attendance|cgpa|marks)", 4.5), (r"department report", 3),
        (r"department\b", 1.5), (r"health check", 2.5),
    ],
    "notification_query": [
        (r"notifications?", 3), (r"alerts?", 2.5), (r"announce\w*", 2.5),
        (r"messages?", 2), (r"warnings?", 2), (r"should know", 2),
        (r"what did i miss", 2.5), (r"remind\w*", 2),
    ],
    "profile_query": [
        (r"profile|my details|dashboard", 3), (r"cgpa", 2.5),
        (r"backlogs?", 2), (r"who am i", 3), (r"overview|summary|rundown", 2),
        (r"where i stand|my standing", 2.5), (r"overall", 1.5),
    ],
}


class IntentResult:
    def __init__(self, intent, method, latency_ms, tool=None, margin=0.0):
        self.intent = intent
        self.method = method
        self.latency_ms = latency_ms
        self.tool = tool or INTENT_TOOL.get(intent)
        #: Top-1 minus top-2 intent score — the classifier's own confidence,
        #: and the signal the hybrid router escalates on (see router.py).
        #: Zero means nothing matched at all and `intent` is the
        #: `profile_query` default rather than a decision.
        self.margin = margin


def classify_keyword(query: str) -> IntentResult:
    start = time.perf_counter()
    q = query.lower()
    scores = {intent: 0.0 for intent in INTENTS}
    for intent, patterns in _LEXICON.items():
        for pattern, weight in patterns:
            if re.search(pattern, q):
                scores[intent] += weight
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    margin = ranked[0] - ranked[1]
    if scores[best] <= 0:
        best = "profile_query"
    return IntentResult(best, "keyword", (time.perf_counter() - start) * 1000,
                        margin=margin)


_ollama_available: bool | None = None


def check_ollama(force: bool = False) -> bool:
    global _ollama_available
    if _ollama_available is not None and not force:
        return _ollama_available
    try:
        r = httpx.get(f"{config.OLLAMA_HOST}/api/tags", timeout=1.5)
        _ollama_available = r.status_code == 200
    except Exception:
        _ollama_available = False
    return _ollama_available


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict | None:
    """One Ollama chat call. Returns the assistant message dict, or None."""
    if not check_ollama():
        return None
    try:
        body = {"model": config.OLLAMA_MODEL, "messages": messages,
                "stream": False, "options": {"temperature": 0.1}}
        if tools:
            body["tools"] = tools
        r = httpx.post(f"{config.OLLAMA_HOST}/api/chat", json=body,
                       timeout=config.OLLAMA_TIMEOUT_S * 4)
        r.raise_for_status()
        return r.json().get("message")
    except Exception:
        return None
