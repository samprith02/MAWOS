"""FROZEN v2 keyword lexicon — the deterministic routing baseline.

Extracted verbatim from `backend/app/llm.py` at P0 (MAWOS v2, commit
46a0c6e) by slicing the source, not by retyping it.

This file exists for one reason. The v2 lexicon is the baseline every
routing result is measured against, and it lives in a module we are about
to keep editing. Without a pinned copy, any later improvement to the live
lexicon would silently raise the baseline too, and the comparison would
quietly stop meaning anything.

Do not edit. Do not "fix" a regex here, however wrong it looks — a wrong
regex is part of what v2 measured. Improvements belong in
`backend/app/llm.py`.

    sha256(body) = 313809cb23022e267d9afeb00b0c1e7f0dbfcef8cf0a53f7cf8e28a1803a9bbc

Measured performance on the 108 v2 dev queries (now DEV ONLY):
    overall 89.8%  |  standard 100.0%  |  colloquial 69.4%
"""
import re
import time

BODY_SHA256 = "313809cb23022e267d9afeb00b0c1e7f0dbfcef8cf0a53f7cf8e28a1803a9bbc"


INTENT_TOOL = {
    "attendance_query": "get_attendance",
    "fees_query": "get_fees",
    "scholarship_query": "get_scholarship",
    "exam_query": "get_hall_ticket",
    "exam_schedule_query": "get_exam_schedule",
    "marks_query": "get_marks",
    "timetable_query": "get_timetable",
    "placement_query": "get_placements",
    "admission_query": "get_admissions_funnel",
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
    "admission_query": [
        (r"admissions?", 3.5), (r"applicants?|applications?", 2.5),
        (r"merit list", 3), (r"seats?\b.{0,12}\b(allot|left|fill|vacant|remain)", 3),
        (r"intake", 2.5), (r"enroll?\w*", 2), (r"counsell?ing", 2.5),
        (r"verificat\w*", 2), (r"branch(es)?\b", 1.5),
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
    def __init__(self, intent, method, latency_ms, tool=None):
        self.intent = intent
        self.method = method
        self.latency_ms = latency_ms
        self.tool = tool or INTENT_TOOL.get(intent)


def classify_keyword(query: str) -> IntentResult:
    start = time.perf_counter()
    q = query.lower()
    scores = {intent: 0.0 for intent in INTENTS}
    for intent, patterns in _LEXICON.items():
        for pattern, weight in patterns:
            if re.search(pattern, q):
                scores[intent] += weight
    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        best = "profile_query"
    return IntentResult(best, "keyword", (time.perf_counter() - start) * 1000)
