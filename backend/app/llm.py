"""LLM layer.

**The escalation tier is HOSTED as of v5** (spec 2026-09-13 3.3, step 5:
"only then wire the winner into the runtime"). `chat()` dispatches to the
OpenAI-compatible provider configured by `MAWOS_LLM_BASE_URL` /
`MAWOS_LLM_MODEL` / `MAWOS_LLM_KEY_ENV`. Ollama is retained behind
`chat_ollama()` for one reason only: re-running archived v3 captures
locally. It is never selected while a hosted credential is present.

What did NOT change, and must not
---------------------------------
The deterministic weighted-keyword lexicon below is the **primary** tier,
not a fallback (CLAUDE.md), and it is a frozen instrument. `classify_keyword`,
`_LEXICON` and the margin definition are untouched by the v5 provider swap --
P4's tau was selected against these exact weights, and editing them would
make the deployed router a different experiment (PROTOCOL 9.3).

Which queries escalate is `router.should_escalate(margin)` and nothing else.
The functions here answer only *whether an escalation can be served*, which
is an availability question. Conflating the two is precisely the v2 defect
P4 was built to remove -- see `router.py`.

11 intents (P2): `admission_query` was retired with `get_admissions_funnel`
(docs/RESEARCH_PLAN_V3.md §7.1) — Admission no longer meets the agent
criterion and this was its only chat-facing capability.
"""
import json
import os
import re
import time

import httpx

from . import config, llm_provider

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


# ===================================================================
# Availability of the escalation tier
# ===================================================================
# Read this before editing: these functions say whether an escalation CAN
# be served. They never say whether one SHOULD happen -- that is
# `router.should_escalate(margin)`, the P4 policy, and it is deliberately
# not reachable from here.

_ollama_available: bool | None = None
_hosted_available: bool | None = None


def check_ollama(force: bool = False) -> bool:
    """Legacy local tier. Only consulted when NO hosted credential exists.

    Kept so archived v3 captures can still be reproduced on a laptop.
    """
    global _ollama_available
    if _ollama_available is not None and not force:
        return _ollama_available
    try:
        r = httpx.get(f"{config.OLLAMA_HOST}/api/tags", timeout=1.5)
        _ollama_available = r.status_code == 200
    except Exception:
        _ollama_available = False
    return _ollama_available


def check_hosted(force: bool = False) -> bool:
    """Is the configured hosted provider reachable AND the credential good?

    A real `/models` call, not just an `os.getenv` check. The distinction
    matters for honesty: a key that is set but rejected (typo, revoked,
    wrong provider) would otherwise light the badge for a tier the system
    cannot actually serve -- the same class of defect as reporting a number
    from a broken instrument.

    Cached for the process like `check_ollama`, with the same `force`
    escape hatch. `main.py` warms this at startup so `/health` -- Render's
    health-check target -- never pays the network round trip.
    """
    global _hosted_available
    if _hosted_available is not None and not force:
        return _hosted_available
    key = os.getenv(config.LLM_API_KEY_ENV)
    if not key:
        _hosted_available = False
        return False
    try:
        r = httpx.get(f"{config.LLM_BASE_URL.rstrip('/')}/models", timeout=10.0,
                      headers={"Authorization": f"Bearer {key}"})
        _hosted_available = r.status_code == 200
    except Exception:
        _hosted_available = False
    return _hosted_available


def escalation_available(force: bool = False) -> bool:
    """Can an escalation-warranted query be served by any LLM tier?"""
    return check_hosted(force) or check_ollama(force)


def active_tier(force: bool = False) -> dict:
    """What the badge, `/health` and the trace report as the live tier.

    `label` is the honest provider string, never a hardcoded "Ollama".
    """
    if check_hosted(force):
        info = llm_provider.active_provider()
        return {"available": True, "kind": "hosted", "label": info["label"],
                "model": info["model"], "base_url": info["base_url"]}
    if check_ollama(force):
        return {"available": True, "kind": "local",
                "label": f"ollama:{config.OLLAMA_MODEL}",
                "model": config.OLLAMA_MODEL, "base_url": config.OLLAMA_HOST}
    return {"available": False, "kind": "none", "label": "lexicon-only",
            "model": None, "base_url": None}


def ai_mode() -> dict:
    """The two fields every authed API response carries about the AI tier.

    `ai_mode` keeps its v3 values ("llm" / "lexicon") so the existing SPA
    needs no migration; `ai_provider` is the new field naming what actually
    serves, so the UI can stop asserting "Ollama".
    """
    t = active_tier()
    return {"ai_mode": "llm" if t["available"] else "lexicon",
            "ai_provider": t["label"]}


# ===================================================================
# The escalation call itself
# ===================================================================

def _to_openai_messages(messages: list[dict]) -> list[dict]:
    """Translate the Ollama-shaped conversation into a strictly OpenAI one.

    The orchestrator builds its message list in Ollama's shape and appends
    each assistant reply verbatim. The real Chat Completions schema that
    Groq/OpenRouter/GitHub Models validate against is stricter in three
    ways, EACH discovered live against Groq as an HTTP 400 during the D1
    probe (see `evaluation/probe/providers.py`):

    1. `tool_calls[].function.arguments` must be a JSON **string**, never
       an object;
    2. every `tool_calls[]` entry needs `id` and `type`;
    3. the following `role: "tool"` message must echo that id back as
       `tool_call_id`.

    Doing this here -- rather than in the orchestrator -- is what keeps the
    Ollama path byte-identical to what v3 measured. Exactly one of those
    two sites may know about OpenAI's schema, and it is this one.
    """
    out: list[dict] = []
    pending_ids: list[str] = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            new_calls, ids = [], []
            for i, c in enumerate(m["tool_calls"]):
                fn = c.get("function", {})
                args = fn.get("arguments")
                if not isinstance(args, str):
                    args = json.dumps(args if args is not None else {})
                cid = (c.get("_meta") or {}).get("id") or f"call_{len(out)}_{i}"
                ids.append(cid)
                new_calls.append({"id": cid, "type": "function",
                                  "function": {"name": fn.get("name", ""),
                                               "arguments": args}})
            out.append({"role": "assistant", "content": m.get("content") or "",
                        "tool_calls": new_calls})
            pending_ids = list(ids)
        elif m.get("role") == "tool":
            nm = {k: v for k, v in m.items() if k != "_meta"}
            if pending_ids:
                nm["tool_call_id"] = pending_ids.pop(0)
            out.append(nm)
        else:
            out.append(m)
    return out


def _from_openai_message(msg: dict) -> dict:
    """Normalise an OpenAI reply into the shape the orchestrator reads.

    The provider's `tool_calls[].id` is carried in `_meta` so the NEXT
    round can echo it as `tool_call_id` (rule 3 above). Dropping it would
    make every multi-round tool conversation fail on its second request.
    """
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function", {})
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except ValueError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append({"function": {"name": fn.get("name", ""),
                                   "arguments": args},
                      "_meta": {"id": c.get("id")}})
    out: dict = {"role": "assistant", "content": msg.get("content") or ""}
    if calls:
        out["tool_calls"] = calls
    return out


def chat_ollama(messages: list[dict], tools: list[dict] | None = None) -> dict | None:
    """One local Ollama chat call. Returns the assistant message, or None.

    Named explicitly (it was the unqualified `chat()` in v3) so the archived
    v3 harness in `evaluation/evaluate.py` can never silently start
    measuring a hosted model just because a key happens to be in the
    environment. An instrument that changes what it measures without saying
    so is the failure mode CLAUDE.md's "check M9 first" rule exists to catch.
    """
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


def chat_hosted(messages: list[dict], tools: list[dict] | None = None) -> dict | None:
    """One hosted chat call over the OpenAI-compatible API.

    Any failure returns None rather than raising -- including HTTP 429,
    which a free tier will produce under demo load. The caller then degrades
    to the lexicon answer it already computed and *says so* in the routing
    record (`fallback_from="llm"`), so a rate-limited turn stays visible in
    the trace instead of passing for a confident lexicon hit.
    """
    key = os.getenv(config.LLM_API_KEY_ENV)
    if not key:
        return None
    body = {"model": config.LLM_MODEL,
            "messages": _to_openai_messages(messages),
            "temperature": 0.1}
    if tools:
        body["tools"] = tools
    try:
        r = httpx.post(f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
                       json=body, timeout=config.LLM_TIMEOUT_S,
                       headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        choices = r.json().get("choices") or []
        if not choices:
            return None
        return _from_openai_message(choices[0].get("message") or {})
    except Exception:
        return None


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict | None:
    """One escalation round on whichever tier is live.

    Hosted first, unconditionally: the hosted provider is v5's runtime tier,
    and a developer who still has Ollama running locally must not be served
    by a different system than the deployed instance uses.
    """
    if check_hosted():
        return chat_hosted(messages, tools)
    if check_ollama():
        return chat_ollama(messages, tools)
    return None
