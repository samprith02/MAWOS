"""Orchestrator Agent v2 — the LLM-driven brain of MAWOS.

LLM mode (Ollama reachable): agentic tool-calling loop —
    conversation -> LLM picks tools (role-filtered schemas) ->
    tools execute under hard permission checks -> results fed back ->
    LLM writes the final grounded answer. Up to 3 tool rounds.

Fallback mode (offline): weighted-keyword classifier -> single mapped tool
-> deterministic formatter. Same tools, same permissions — only the
language understanding degrades. The mode is reported on every response
and logged (fallback-trigger rate is a first-class metric).
"""
import json
import time

from .. import llm
from ..models import IntentLog
from . import tools as toolreg
from .base import BaseAgent

SYSTEM_PROMPT = """You are MAWOS, the AI assistant of Mangalore Institute of \
Technology & Engineering. You answer questions for {role} users by calling \
the provided tools and grounding every answer ONLY in tool results — never \
invent numbers. The current user is {name} ({detail}). Be concise, warm and \
specific; use short sentences; include the key numbers. If a tool returns an \
'error' field, explain the limitation politely.

All money is Indian rupees: write amounts as ₹1,234 — never $ or any other \
currency symbol. Report every field exactly as the tool returned it: if a \
value is a true/false flag such as 'shortage', say only whether it holds — \
do not convert it into a quantity, duration or count that the tool did not \
return."""


class OrchestratorAgent(BaseAgent):
    name = "orchestrator_agent"
    description = ("LLM tool-calling brain with role-scoped tools and a "
                   "deterministic offline fallback")

    def __init__(self, bus, agents: dict):
        super().__init__(bus)
        self.agents = agents

    # ------------------------------------------------------------------ LLM path
    async def _handle_llm(self, db, user, message: str) -> dict | None:
        start = time.perf_counter()
        detail = f"USN {user.usn}" if user.usn else f"dept {user.dept_code or 'ALL'}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(
                role=user.role, name=user.display_name, detail=detail)},
            {"role": "user", "content": message},
        ]
        schemas = toolreg.schemas_for_role(user.role)
        tools_used = []
        for _round in range(3):
            reply = llm.chat(messages, tools=schemas)
            if reply is None:
                return None  # LLM went away mid-flight -> fallback
            calls = reply.get("tool_calls") or []
            if not calls:
                latency = (time.perf_counter() - start) * 1000
                first_tool = tools_used[0]["name"] if tools_used else "direct_answer"
                db.add(IntentLog(query=message, predicted_intent=first_tool,
                                 method="llm", latency_ms=round(latency, 1)))
                db.commit()
                return {"text": reply.get("content", "").strip() or
                        "I could not compose an answer.",
                        "mode": "llm", "model": llm.config.OLLAMA_MODEL,
                        "tools_used": tools_used,
                        "latency_ms": round(latency, 1)}
            messages.append(reply)
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                t0 = time.perf_counter()
                result = toolreg.execute(db, self.agents, user, name, args)
                tools_used.append({"name": name, "args": args,
                                   "ms": round((time.perf_counter() - t0) * 1000, 1)})
                messages.append({"role": "tool", "name": name,
                                 "content": json.dumps(result, default=str)[:4000]})
        return None  # too many rounds -> fallback

    # ------------------------------------------------------------- fallback path
    def _format(self, tool_name: str, result: dict) -> str:
        if "error" in result:
            return result["error"]
        f = _FORMATTERS.get(tool_name)
        return f(result) if f else json.dumps(result, indent=1, default=str)[:1200]

    async def _handle_fallback(self, db, user, message: str) -> dict:
        r = llm.classify_keyword(message)
        t0 = time.perf_counter()
        result = toolreg.execute(db, self.agents, user, r.tool, {})
        tool_ms = (time.perf_counter() - t0) * 1000
        db.add(IntentLog(query=message, predicted_intent=r.intent,
                         method="keyword", latency_ms=round(r.latency_ms, 3)))
        db.commit()
        return {"text": self._format(r.tool, result),
                "mode": "fallback", "intent": r.intent,
                "tools_used": [{"name": r.tool, "ms": round(tool_ms, 1)}],
                "latency_ms": round(r.latency_ms + tool_ms, 1),
                "data": result}

    async def handle_chat(self, db, user, message: str) -> dict:
        if llm.check_ollama():
            response = await self._handle_llm(db, user, message)
            if response is not None:
                return response
        return await self._handle_fallback(db, user, message)


# ---------------------------------------------------------------- formatters
def _fmt_overview(r):
    p = r["profile"]
    lines = [f"{p['name']} ({p['usn']}) — {p['dept']} Year {p['year']}, "
             f"Section {p['section']}",
             f"CGPA {p['cgpa']} · backlogs {p['backlogs']} · "
             f"attendance {r['overall_attendance_pct']}%",
             "Fees: " + ("cleared ✓" if r["fees_cleared"]
                         else f"₹{r['fees_outstanding']:,.0f} outstanding")]
    if r.get("hall_ticket"):
        lines.append("Hall ticket: "
                     + ("ELIGIBLE ✓" if r["hall_ticket"]["eligible"] else "BLOCKED ✗")
                     + f" — {r['hall_ticket']['reasons']}")
    if r.get("scholarship"):
        lines.append(f"Scholarship: {r['scholarship']['status']} "
                     f"— {r['scholarship']['reasons']}")
    return "\n".join(lines)


def _fmt_attendance(r):
    lines = [f"Overall attendance: {r['overall_pct']}%"
             + (" — SHORTAGE (below 75%)" if r["overall_pct"] < 75 else " ✓")]
    lines += [f"  {s['subject']}: {s['attended']}/{s['held']} = {s['pct']}%"
              + (" ⚠" if s["shortage"] else "") for s in r["subjects"]]
    return "\n".join(lines)


def _fmt_fees(r):
    pending = [i for i in r["items"] if i["status"] != "paid"]
    if not pending:
        return "All fees are cleared ✓"
    lines = [f"Outstanding: ₹{r['total_outstanding']:,.0f} across {len(pending)} item(s):"]
    lines += [f"  {i['type']}: ₹{i['amount_due']:,.0f}"
              + (f" + fine ₹{i['fine']:,.0f} (OVERDUE)" if i["status"] == "overdue" else
                 f" due {i['due_date']}") for i in pending]
    return "\n".join(lines)


def _fmt_hall_ticket(r):
    return ("Hall ticket: " + ("ELIGIBLE ✓" if r["eligible"] else "BLOCKED ✗")
            + "\n" + "\n".join(f"  • {x}" for x in r["reasons"]))


def _fmt_scholarship(r):
    label = {"eligible": "ELIGIBLE ✓", "waitlist": "WAITLISTED",
             "not_eligible": "NOT ELIGIBLE ✗"}.get(r["status"], r["status"])
    return (f"Scholarship (Merit-cum-Means): {label}\n"
            + "\n".join(f"  • {x}" for x in r["reasons"]))


def _fmt_placements(r):
    drives = r.get("drives")
    if drives is None:
        return json.dumps(r, indent=1, default=str)[:800]
    lines = [f"{len(drives)} upcoming drives:"]
    for d in drives[:8]:
        status = "ELIGIBLE ✓" if d["eligible"] else "not eligible"
        line = (f"  {d['company']} · {d['role']} · {d['package_lpa']} LPA "
                f"· {d['date']} — {status}")
        if d.get("probability") is not None:
            line += f" ({d['probability']:.0%} success prob.)"
        lines.append(line)
    return "\n".join(lines)


def _fmt_timetable(r):
    lines = []
    header = r.get("dept") and f"Timetable — {r['dept']} Year {r.get('year')} {r.get('section')}"
    if header:
        lines.append(header)
    for d, day in enumerate(r["days"]):
        cells = [r["cells"].get(f"{d}-{p}") for p in range(len(r["periods"]))]
        row = ", ".join(c["subject"] if c else "—" for c in cells)
        lines.append(f"  {day}: {row}")
    return "\n".join(lines)


def _fmt_exams(r):
    lines = [f"Exam schedule — {r['dept']} sem {r['semester']}:"]
    lines += [f"  {e['date']} {e['session']}: {e['subject']}" for e in r["exams"]]
    return "\n".join(lines)


def _fmt_marks(r):
    lines = ["Internal (CIE) marks:"]
    for m in r["marks"]:
        internals = ", ".join(f"{k} {v:.0f}" for k, v in m["internals"].items())
        lines.append(f"  {m['subject']} ({m['name']}): {internals}"
                     + (f" — avg {m['cie_average']}" if m["cie_average"] else ""))
    return "\n".join(lines)


def _fmt_notifications(r):
    items = r["notifications"]
    if not items:
        return "No notifications."
    return "\n".join(f"[{n['at'][:16]}] {n['title']}: {n['message']}"
                     for n in items[:8])


def _fmt_dept(r):
    lines = [f"{r['dept']}: {r['students']} students · avg attendance "
             f"{r['avg_attendance']}% · avg CGPA {r['avg_cgpa']} · "
             f"{r['shortage_students']} in shortage"]
    if r.get("fee_defaulters"):
        lines.append(f"Top fee defaulters: "
                     + ", ".join(d["usn"] for d in r["fee_defaulters"][:5]))
    return "\n".join(lines)


def _fmt_admissions(r):
    s = r["stages"]
    lines = ["Admissions funnel: "
             + " → ".join(f"{k} {v}" for k, v in s.items())]
    for code, d in r["departments"].items():
        lines.append(f"  {code}: {d['applications']} applications, "
                     f"{d['allotted']}/{d['intake']} seats allotted")
    return "\n".join(lines)


_FORMATTERS = {
    "get_student_overview": _fmt_overview,
    "get_attendance": _fmt_attendance,
    "get_fees": _fmt_fees,
    "get_hall_ticket": _fmt_hall_ticket,
    "get_scholarship": _fmt_scholarship,
    "get_placements": _fmt_placements,
    "get_timetable": _fmt_timetable,
    "get_exam_schedule": _fmt_exams,
    "get_marks": _fmt_marks,
    "get_notifications": _fmt_notifications,
    "get_dept_analytics": _fmt_dept,
    "get_admissions_funnel": _fmt_admissions,
}
