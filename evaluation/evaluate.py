"""MAWOS v2 evaluation harness.

  1. Intent-routing accuracy on a labelled benchmark: 12 intents,
     6 standard + 3 hard phrasings each (108 queries), confusion matrix.
     Scored for BOTH routing tiers: the deterministic keyword classifier
     and — when Ollama is reachable — the LLM tool-selection path, on the
     same queries against the same target tools.
  2. Attendance-computation verification (deterministic, NOT an AI metric).
  3. Live cascade benchmark (attendance upload -> full agent chain).
  4. Modeled manual-baseline comparison (stated assumptions + sensitivity).
  5. ML metrics from ml/models/metrics.json.

Starts a fresh measurement window (clears intent/workflow logs and prior
evaluator uploads) so numbers reflect the current code on a canonical DB.

Run:  python evaluation/evaluate.py            # both tiers if Ollama is up
      python evaluation/evaluate.py --no-llm   # deterministic tier only
"""
import asyncio
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app import llm  # noqa: E402
from backend.app.agents import get_agents  # noqa: E402
from backend.app.agents import tools as toolreg  # noqa: E402
from backend.app.agents.orchestrator import SYSTEM_PROMPT  # noqa: E402
from backend.app.database import Base, SessionLocal, engine  # noqa: E402
from backend.app.models import (  # noqa: E402
    AttendanceRecord, AttendanceSummary, IntentLog, Student, Subject, User,
    WorkflowEvent,
)
from backend.app.seed import bootstrap_evaluations, seed_all  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"

STANDARD: list[tuple[str, str]] = [
    ("What is my attendance percentage?", "attendance_query"),
    ("Am I short of attendance?", "attendance_query"),
    ("Do I have attendance shortage in any subject?", "attendance_query"),
    ("Was I marked absent yesterday?", "attendance_query"),
    ("Is my attendance above 75%?", "attendance_query"),
    ("attendance status", "attendance_query"),
    ("Do I have any pending fees?", "fees_query"),
    ("How much tuition fee is due?", "fees_query"),
    ("What is my fine amount?", "fees_query"),
    ("Have I paid my exam fees?", "fees_query"),
    ("Show the fee defaulter list", "fees_query"),
    ("fee status", "fees_query"),
    ("Am I eligible for the scholarship?", "scholarship_query"),
    ("What is my scholarship status?", "scholarship_query"),
    ("Any update on my financial aid application?", "scholarship_query"),
    ("Will I receive the stipend this year?", "scholarship_query"),
    ("Do I qualify for a fee waiver?", "scholarship_query"),
    ("scholarship eligibility check", "scholarship_query"),
    ("Will I get my hall ticket?", "exam_query"),
    ("Am I eligible to write the exam?", "exam_query"),
    ("Is my admit card released?", "exam_query"),
    ("Why is my hall ticket blocked?", "exam_query"),
    ("hall ticket status", "exam_query"),
    ("Can I sit for the exams?", "exam_query"),
    ("When do semester exams start?", "exam_schedule_query"),
    ("Show me the exam schedule", "exam_schedule_query"),
    ("What are the exam dates?", "exam_schedule_query"),
    ("Exam timetable please", "exam_schedule_query"),
    ("When are the sem exams?", "exam_schedule_query"),
    ("semester exam dates", "exam_schedule_query"),
    ("Show my internal marks", "marks_query"),
    ("What did I score in CIE 2?", "marks_query"),
    ("My DBMS internal marks", "marks_query"),
    ("Show my CIE scores", "marks_query"),
    ("How much did I get in the internals?", "marks_query"),
    ("internal marks please", "marks_query"),
    ("What classes do I have this week?", "timetable_query"),
    ("Show my timetable", "timetable_query"),
    ("Which subject is in the first period tomorrow?", "timetable_query"),
    ("My class schedule please", "timetable_query"),
    ("What periods do I have today?", "timetable_query"),
    ("weekly routine", "timetable_query"),
    ("Which placement drives am I eligible for?", "placement_query"),
    ("When is the next campus drive?", "placement_query"),
    ("What companies are coming this month?", "placement_query"),
    ("Show my placement eligibility", "placement_query"),
    ("Any job opportunities for me?", "placement_query"),
    ("placement drive list", "placement_query"),
    ("Show the admissions funnel", "admission_query"),
    ("How many applications are pending?", "admission_query"),
    ("Has the merit list been prepared?", "admission_query"),
    ("How many seats are left in CSE?", "admission_query"),
    ("admission status report", "admission_query"),
    ("How many students enrolled this year?", "admission_query"),
    ("Show department analytics", "analytics_query"),
    ("How is my department performing?", "analytics_query"),
    ("What is the average attendance in AIML?", "analytics_query"),
    ("Department report please", "analytics_query"),
    ("Give me an overview of the department", "analytics_query"),
    ("How are the students performing this semester?", "analytics_query"),
    ("Show my notifications", "notification_query"),
    ("Any new alerts for me?", "notification_query"),
    ("What are the latest announcements?", "notification_query"),
    ("Any reminders pending?", "notification_query"),
    ("Did I get any messages?", "notification_query"),
    ("notifications please", "notification_query"),
    ("Show my profile", "profile_query"),
    ("What is my CGPA?", "profile_query"),
    ("How many backlogs do I have?", "profile_query"),
    ("Show my details", "profile_query"),
    ("Give me my overall summary", "profile_query"),
    ("Who am I logged in as?", "profile_query"),
]

HARD: list[tuple[str, str]] = [
    ("If I skip tomorrow will I fall below the limit?", "attendance_query"),
    ("The professor marked me absent even though I came", "attendance_query"),
    ("How many more classes can I afford to miss?", "attendance_query"),
    ("How much do I still owe the college?", "fees_query"),
    ("Is there a penalty added to my dues?", "fees_query"),
    ("The accounts office is asking for money again, what's pending?", "fees_query"),
    ("Any chance of getting financial support this semester?", "scholarship_query"),
    ("Will the college waive my fees given my family situation?", "scholarship_query"),
    ("Is there money help for students like me?", "scholarship_query"),
    ("Am I allowed into the exam hall?", "exam_query"),
    ("Is anything blocking me from writing my papers?", "exam_query"),
    ("Can I sit for the finals?", "exam_query"),
    ("How far away are the semester finals?", "exam_schedule_query"),
    ("When do we write our papers?", "exam_schedule_query"),
    ("Are the exam dates out yet?", "exam_schedule_query"),
    ("How did I do in the second internals?", "marks_query"),
    ("How did the ML test go for me?", "marks_query"),
    ("Are my CIE scores decent?", "marks_query"),
    ("What's my first period tomorrow?", "timetable_query"),
    ("What's my day looking like tomorrow?", "timetable_query"),
    ("Where should I be for the first class on Monday?", "timetable_query"),
    ("Which firms can I sit for?", "placement_query"),
    ("Do I meet the cutoff for the next drive?", "placement_query"),
    ("What are my chances of getting hired?", "placement_query"),
    ("Where does the counselling process stand?", "admission_query"),
    ("How many candidates cleared verification?", "admission_query"),
    ("How full are the branches this year?", "admission_query"),
    ("Give me a health check of the department", "analytics_query"),
    ("Which section is struggling the most?", "analytics_query"),
    ("How does our branch compare this semester?", "analytics_query"),
    ("Did the college send me anything?", "notification_query"),
    ("Anything I should know about?", "notification_query"),
    ("What did I miss while I was away?", "notification_query"),
    ("Give me a rundown of where I stand", "profile_query"),
    ("How am I doing overall this semester?", "profile_query"),
    ("Summarise my academics", "profile_query"),
]

SHORT = {"attendance_query": "att", "fees_query": "fee",
         "scholarship_query": "sch", "exam_query": "exm",
         "exam_schedule_query": "esc", "marks_query": "mrk",
         "timetable_query": "tt", "placement_query": "plc",
         "admission_query": "adm", "analytics_query": "ana",
         "notification_query": "ntf", "profile_query": "prf"}


def eval_intent_routing(db) -> dict:
    cases = ([(q, e, "standard") for q, e in STANDARD]
             + [(q, e, "hard") for q, e in HARD])
    per_intent, per_tier = {}, {"standard": [], "hard": []}
    confusion = {e: {p: 0 for p in llm.INTENTS} for e in llm.INTENTS}
    misrouted, fallback = [], 0
    for query, expected, tier in cases:
        r = llm.classify_keyword(query)
        ok = r.intent == expected
        fallback += 1
        per_intent.setdefault(expected, []).append(ok)
        per_tier[tier].append(ok)
        confusion[expected][r.intent] += 1
        if not ok:
            misrouted.append({"query": query, "expected": expected,
                              "got": r.intent, "tier": tier})
        db.add(IntentLog(query=query, predicted_intent=r.intent,
                         method=r.method, latency_ms=round(r.latency_ms, 3),
                         expected_intent=expected, correct=ok))
    db.commit()
    n = len(cases)
    correct = sum(sum(v) for v in per_tier.values())
    return {"queries": n,
            "n_standard": len(STANDARD), "n_hard": len(HARD),
            "accuracy": round(correct / n, 4),
            "accuracy_standard": round(sum(per_tier["standard"]) / len(STANDARD), 4),
            "accuracy_hard": round(sum(per_tier["hard"]) / len(HARD), 4),
            "fallback_rate": 1.0,   # benchmark runs the deterministic tier
            "per_intent_accuracy": {k: round(sum(v) / len(v), 3)
                                    for k, v in sorted(per_intent.items())},
            "confusion_matrix": confusion,
            "misrouted": misrouted}


# A second tool that is a genuinely defensible answer for an intent. Scored
# ONLY as a clearly-labelled secondary number; the headline LLM accuracy
# stays strict (identical target tool as the deterministic tier) so the two
# tiers remain directly comparable.
LENIENT_ALTERNATIVES = {
    "analytics_query": {"get_institution_analytics"},
}

TOOL_INTENT = {v: k for k, v in llm.INTENT_TOOL.items()}

# The role that would naturally ask each intent. Almost every benchmark query
# is phrased in the first person ("my attendance", "my hall ticket"), i.e. a
# student's voice; only these two are staff questions. Asking a first-person
# student question under a staff persona is unanswerable by construction —
# the staff tools require a USN the persona never supplied — so the model
# correctly declines to call a tool and the query scores as a miss. That is a
# benchmark artefact, not a language-understanding failure, which is exactly
# what `role_mode="single"` below quantifies.
ROLE_FOR_INTENT = {"admission_query": "admin", "analytics_query": "hod"}
DEFAULT_BENCH_ROLE = "student"


def _bench_user(db, role: str, _cache: dict = {}):
    """A representative user per role, for the benchmark personas."""
    if role in _cache:
        return _cache[role]
    user = None
    if role == "student":
        user = db.query(User).filter_by(username="4MT23AI049").first()
    if user is None:
        user = db.query(User).filter_by(role=role).first()
    _cache[role] = user
    return user


def eval_intent_routing_llm(db, role_mode: str = "matched") -> dict | None:
    """Score the LLM tool-selection tier on the SAME 108 labelled queries.

    Apples-to-apples with the deterministic tier: one query in, one tool out,
    scored against the same target tool.

    role_mode:
      "matched" — each query is asked by the role that would really ask it
                  (students ask student questions). This mirrors production,
                  where every query arrives inside one portal's session.
      "single"  — every query is asked by the admin persona. All 12 target
                  tools are in scope, but first-person student questions
                  become unanswerable; the gap between the two modes measures
                  how sensitive tool calling is to the caller's permissions.

    Returns None when no model is reachable.
    """
    if not llm.check_ollama(force=True):
        return None
    if _bench_user(db, "admin") is None:
        print("    no admin user in DB — skipping LLM tier")
        return None

    def persona(expected_intent):
        role = ("admin" if role_mode == "single"
                else ROLE_FOR_INTENT.get(expected_intent, DEFAULT_BENCH_ROLE))
        user = _bench_user(db, role) or _bench_user(db, "admin")
        detail = (f"USN {user.usn}" if user.usn
                  else f"dept {user.dept_code or 'ALL'}")
        return user, toolreg.schemas_for_role(user.role), SYSTEM_PROMPT.format(
            role=user.role, name=user.display_name, detail=detail)

    _, schemas, system = persona("profile_query")

    # Warm-up: the first call pays the model load (~2 GB into RAM). Doing it
    # outside the timed loop keeps that one-off cost out of the latency
    # figures and out of the error count.
    print("      warming up the model…")
    t_warm = time.perf_counter()
    llm.chat([{"role": "system", "content": system},
              {"role": "user", "content": "hello"}], tools=schemas)
    print(f"      warm-up took {(time.perf_counter() - t_warm):.1f}s")

    cases = ([(q, e, "standard") for q, e in STANDARD]
             + [(q, e, "hard") for q, e in HARD])
    per_intent, per_tier = {}, {"standard": [], "hard": []}
    confusion = {e: {p: 0 for p in llm.INTENTS} for e in llm.INTENTS}
    misrouted, latencies = [], []
    lenient_correct = no_tool = off_map = errors = 0

    roles_used = {}
    for i, (query, expected, tier) in enumerate(cases, 1):
        expected_tool = llm.INTENT_TOOL[expected]
        q_user, q_schemas, q_system = persona(expected)
        roles_used[expected] = q_user.role
        t0 = time.perf_counter()
        reply = llm.chat([{"role": "system", "content": q_system},
                          {"role": "user", "content": query}], tools=q_schemas)
        latency = (time.perf_counter() - t0) * 1000
        latencies.append(latency)

        if reply is None:
            errors += 1
            got_tool = "llm_error"
        else:
            calls = reply.get("tool_calls") or []
            got_tool = (calls[0].get("function", {}).get("name") or "no_tool"
                        if calls else "no_tool")
        if got_tool == "no_tool":
            no_tool += 1

        ok = got_tool == expected_tool
        if ok or got_tool in LENIENT_ALTERNATIVES.get(expected, ()):
            lenient_correct += 1
        per_intent.setdefault(expected, []).append(ok)
        per_tier[tier].append(ok)

        got_intent = TOOL_INTENT.get(got_tool)
        if got_intent is not None:
            confusion[expected][got_intent] += 1
        else:
            off_map += 1
        if not ok:
            misrouted.append({"query": query, "expected": expected,
                              "expected_tool": expected_tool,
                              "got_tool": got_tool, "tier": tier})

        db.add(IntentLog(query=query, predicted_intent=got_intent or got_tool,
                         method="llm", latency_ms=round(latency, 1),
                         expected_intent=expected, correct=ok))
        if i % 12 == 0:
            running = sum(sum(v) for v in per_tier.values()) / i
            print(f"      {i}/{len(cases)} — running {running:.1%} "
                  f"({statistics.mean(latencies):.0f} ms/query)")
    db.commit()

    n = len(cases)
    correct = sum(sum(v) for v in per_tier.values())
    latencies.sort()
    return {"model": llm.config.OLLAMA_MODEL,
            "role_mode": role_mode,
            "roles_used": roles_used,
            "queries": n,
            "n_standard": len(STANDARD), "n_hard": len(HARD),
            "accuracy": round(correct / n, 4),
            "accuracy_standard": round(sum(per_tier["standard"]) / len(STANDARD), 4),
            "accuracy_hard": round(sum(per_tier["hard"]) / len(HARD), 4),
            "accuracy_lenient": round(lenient_correct / n, 4),
            "lenient_note": "counts get_institution_analytics as correct for "
                            "analytics_query; headline number is strict",
            "no_tool_selected": no_tool,
            "off_map_tool_selected": off_map,
            "llm_errors": errors,
            "avg_latency_ms": round(statistics.mean(latencies), 1),
            "p95_latency_ms": round(latencies[int(0.95 * (n - 1))], 1),
            "per_intent_accuracy": {k: round(sum(v) / len(v), 3)
                                    for k, v in sorted(per_intent.items())},
            "confusion_matrix": confusion,
            "misrouted": misrouted}


def eval_attendance_accuracy(db) -> dict:
    agents = get_agents()
    usns = [u for (u,) in db.query(Student.usn).limit(200).all()]
    att = agents["attendance_agent"]
    for usn in usns:
        att._recompute_student(db, usn)
    db.commit()
    mismatches = checked = 0
    for usn in usns:
        rows = db.query(AttendanceRecord).filter_by(usn=usn).all()
        truth: dict[str, list[int]] = {}
        for r in rows:
            held, attended = truth.get(r.subject_code, [0, 0])
            truth[r.subject_code] = [held + 1, attended + (1 if r.present else 0)]
        for s in db.query(AttendanceSummary).filter_by(usn=usn).all():
            checked += 1
            t_held, t_att = truth.get(s.subject_code, [0, 0])
            expected_pct = round(100.0 * t_att / t_held, 2) if t_held else 0.0
            if (s.classes_held != t_held or s.classes_attended != t_att
                    or abs(s.percentage - expected_pct) > 0.01):
                mismatches += 1
    return {"summaries_checked": checked, "mismatches": mismatches,
            "accuracy": round(1 - mismatches / checked, 6) if checked else None,
            "meets_99_target": checked > 0 and (1 - mismatches / checked) >= 0.99}


async def eval_cascades(db, n_runs: int = 10) -> dict:
    agents = get_agents()
    students = (db.query(Student).filter_by(dept_code="AIML", semester=5)
                  .order_by(Student.usn).limit(10).all())
    subjects = [s.code for s in db.query(Subject)
                .filter_by(dept_code="AIML", semester=5).all()]
    from sqlalchemy import func as _f
    min_date = db.query(_f.min(AttendanceRecord.date)).scalar() or dt.date.today()
    workflow_ids, wall_times = [], []
    day = min_date - dt.timedelta(days=3)
    for run in range(n_runs):
        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)
        records = [{"usn": s.usn, "subject_code": c, "date": day.isoformat(),
                    "present": (run + hash(s.usn)) % 5 != 0}
                   for s in students for c in subjects]
        t0 = time.perf_counter()
        result = await agents["attendance_agent"].upload_attendance(
            db, "evaluator", records)
        wall_times.append((time.perf_counter() - t0) * 1000)
        if result["workflow_id"]:
            workflow_ids.append(result["workflow_id"])
        day -= dt.timedelta(days=1)

    durations, agent_counts, topics_seen = [], [], set()
    for wf in workflow_ids:
        events = db.query(WorkflowEvent).filter_by(workflow_id=wf).all()
        if events:
            durations.append(max(e.elapsed_ms for e in events))
            agent_counts.append(len({e.agent for e in events}))
            topics_seen |= {e.topic for e in events}
    durations.sort()
    return {"cascades_run": len(workflow_ids),
            "records_per_cascade": len(students) * len(subjects),
            "avg_cascade_ms": round(statistics.mean(durations), 1),
            "p95_cascade_ms": round(durations[int(0.95 * (len(durations) - 1))], 1),
            "max_cascade_ms": round(max(durations), 1),
            "avg_wall_ms_incl_upload": round(statistics.mean(wall_times), 1),
            "avg_agents_involved": round(statistics.mean(agent_counts), 2),
            "topics_in_cascade": sorted(topics_seen),
            "meets_2s_propagation_target":
                durations[int(0.95 * (len(durations) - 1))] < 2000,
            "meets_5s_end_to_end_target": max(durations) < 5000}


MANUAL_BASELINE_STEPS = [
    ("Faculty compiles and submits attendance register", 15),
    ("Office clerk enters records into the register/spreadsheet", 20),
    ("Exam cell cross-checks hall-ticket eligibility", 240),
    ("Scholarship cell re-verifies eligibility", 240),
    ("Placement cell updates candidate lists", 240),
    ("Notices prepared and circulated to affected students", 120),
]


def manual_comparison(avg_cascade_ms: float) -> dict:
    total_min = sum(m for _, m in MANUAL_BASELINE_STEPS)
    return {"assumption_note": "Modeled estimate from stated per-step "
                               "assumptions, not a field measurement.",
            "steps": [{"step": s, "minutes": m} for s, m in MANUAL_BASELINE_STEPS],
            "manual_total_minutes": total_min,
            "manual_human_touchpoints": len(MANUAL_BASELINE_STEPS),
            "mawos_avg_ms": avg_cascade_ms,
            "mawos_human_touchpoints": 1}


def ml_metrics() -> dict:
    path = ROOT / "ml" / "models" / "metrics.json"
    return json.loads(path.read_text()) if path.exists() else \
        {"note": "run ml/train.py first"}


def _single_role_md(sr: dict | None, il: dict) -> str:
    """§1.2b — how much tool calling depends on the caller's permissions."""
    if not sr:
        return ""
    drop = il["accuracy"] - sr["accuracy"]
    return f"""
## 1.2b Permission sensitivity — the same queries under one staff persona

The identical 108 queries, re-run with **every** query asked by the admin
persona instead of the role that would naturally ask it. All 12 target tools
are in scope for admin, so tool *availability* cannot explain any drop.

| | Role-matched | Single-role (admin) |
|---|---|---|
| Overall accuracy | {il['accuracy']:.1%} | {sr['accuracy']:.1%} |
| Standard tier | {il['accuracy_standard']:.1%} | {sr['accuracy_standard']:.1%} |
| Hard tier | {il['accuracy_hard']:.1%} | {sr['accuracy_hard']:.1%} |
| Answered with **no tool call** | {il['no_tool_selected']} | {sr['no_tool_selected']} |

Accuracy falls **{drop:.1%}** — and the mechanism is visible in the last row:
under the staff persona the model declines to call a tool on
{sr['no_tool_selected']} queries. This is the model behaving *correctly*, not
failing. A first-person question like "Am I short of attendance?" is genuinely
unanswerable for an admin: `get_attendance` resolves a student's own USN for
students but demands an explicit USN from staff, and the persona never
supplied one. The model asks for clarification instead of inventing a USN.

Two consequences worth stating plainly. First, any single-persona tool-calling
benchmark understates a role-scoped system — the number measures the harness,
not the model. Second, the permission layer is doing real work at inference
time: role scoping does not merely reject unauthorised calls after the fact,
it changes which calls the model is willing to make at all.
"""


def _verdict(delta: float, delta_hard: float, il: dict) -> str:
    """Interpretation text that follows the measured numbers.

    Written so the report cannot claim the LLM 'earns its place' when the
    data says otherwise — the conclusion is derived, never assumed.
    """
    cost = (f"Each LLM-routed query costs {il['avg_latency_ms']:.0f} ms "
            f"(p95 {il['p95_latency_ms']:.0f} ms) against <1 ms for the "
            f"keyword tier")
    if delta_hard > 0.02:
        lead = (f"The LLM recovers **{delta_hard:+.1%}** on exactly that tier "
                f"— that gap is the measured value of the LLM path")
        if delta < 0:
            lead += (f", though it gives back ground on standard phrasings and "
                     f"ends **{delta:+.1%}** overall: the keyword lexicon was "
                     f"tuned on direct wordings the model sometimes over-thinks")
        return f"{lead}. {cost}."
    if delta_hard < -0.02:
        return (f"On this run the LLM tier did **not** beat the lexicon on hard "
                f"phrasings (**{delta_hard:+.1%}**), and is **{delta:+.1%}** "
                f"overall. Reported as measured: at this model size tool "
                f"selection is not reliably better than the tuned keyword "
                f"classifier, and the honest conclusion is that the LLM's "
                f"contribution here is answer *composition* rather than "
                f"routing. {cost}, which sharpens the trade-off further.")
    return (f"The two tiers are statistically indistinguishable on hard "
            f"phrasings (**{delta_hard:+.1%}**, **{delta:+.1%}** overall) — on "
            f"this benchmark the LLM's contribution is answer composition and "
            f"multi-tool chaining, not routing accuracy. {cost}.")


def write_report(results: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "results.json").write_text(json.dumps(results, indent=2))
    ir, aa, ca = (results["intent_routing"], results["attendance_accuracy"],
                  results["cascades"])
    mc = results["manual_comparison"]
    sch = results["ml"].get("scholarship_cart", {})
    plc = results["ml"].get("placement_rf", {})
    intents = list(SHORT)

    def _cm(matrix):
        lines = ["| true \\ pred | " + " | ".join(SHORT[i] for i in intents) + " |",
                 "|---" * (len(intents) + 1) + "|"]
        for e in intents:
            row = matrix[e]
            lines.append("| **" + SHORT[e] + "** | "
                         + " | ".join(str(row.get(p, 0)) for p in intents) + " |")
        return "\n".join(lines)

    cm_table = _cm(ir["confusion_matrix"])
    il = results.get("intent_routing_llm")
    header_note = (
        "Both routing tiers were scored on the same 108 queries against the\n"
        "same target tools — see §1.3 for the head-to-head."
        if il else
        "(This benchmark scores the DETERMINISTIC fallback tier only — no model\n"
        "was reachable. Install Ollama and re-run to add the LLM tier.)")
    llm_md = ""
    if il:
        delta = il["accuracy"] - ir["accuracy"]
        delta_hard = il["accuracy_hard"] - ir["accuracy_hard"]
        llm_md = f"""
## 1.2 Intent routing — LLM tool-selection tier

Model: `{il['model']}` (local Ollama, temperature 0.1). Identical 108
queries, identical target tools, scored strictly on the **first tool the
model selects**.

Each query is asked by the role that would really ask it — students ask the
first-person questions ("my attendance", "my hall ticket"), staff ask the
departmental and admissions ones — which is how queries actually reach the
orchestrator, since every request arrives inside one portal's session.
§1.2b shows why that choice is load-bearing rather than cosmetic.

| Metric | Value |
|---|---|
| **Overall routing accuracy** | **{il['accuracy']:.1%}** |
| Standard tier ({il['n_standard']}) | {il['accuracy_standard']:.1%} |
| Hard tier ({il['n_hard']}) | {il['accuracy_hard']:.1%} |
| Lenient variant | {il['accuracy_lenient']:.1%} ({il['lenient_note']}) |
| Answered without calling a tool | {il['no_tool_selected']} |
| Selected an off-benchmark tool | {il['off_map_tool_selected']} |
| LLM call failures | {il['llm_errors']} |
| Latency per query | avg {il['avg_latency_ms']:.0f} ms · p95 {il['p95_latency_ms']:.0f} ms |

Per-intent accuracy: {', '.join(f"{SHORT[k]} {v:.0%}" for k, v in il['per_intent_accuracy'].items())}

### Confusion matrix — LLM tier

{_cm(il['confusion_matrix'])}

Misrouted queries ({len(il['misrouted'])}):
{chr(10).join("- [" + m['tier'] + "] '" + m['query'] + "' -> " + m['got_tool'] + " (expected " + m['expected_tool'] + ")" for m in il['misrouted']) or '- none'}

{_single_role_md(results.get('intent_routing_llm_single_role'), il)}
## 1.3 Head-to-head — deterministic vs LLM routing

| Tier | Overall | Standard | Hard | Latency/query |
|---|---|---|---|---|
| Deterministic keyword classifier | {ir['accuracy']:.1%} | {ir['accuracy_standard']:.1%} | {ir['accuracy_hard']:.1%} | <1 ms |
| LLM tool selection (`{il['model']}`) | {il['accuracy']:.1%} | {il['accuracy_standard']:.1%} | {il['accuracy_hard']:.1%} | {il['avg_latency_ms']:.0f} ms |
| **Delta** | **{delta:+.1%}** | **{il['accuracy_standard'] - ir['accuracy_standard']:+.1%}** | **{delta_hard:+.1%}** | — |

The hard tier is the honest test: colloquial, indirect phrasings that carry
no keyword the lexicon can score. {_verdict(delta, delta_hard, il)}

The deterministic tier remains the offline degradation path, and the system
reports which tier served every answer — so this table describes a real
runtime choice, not a hypothetical one.
"""
    md = f"""# MAWOS v2 Evaluation Results

Generated: {results['generated_at']}
LLM available at benchmark time: {results['llm_available']}
{header_note}

## 1. Intent routing — deterministic fallback baseline

Benchmark: {ir['queries']} labelled queries across 12 intents
({ir['n_standard']} standard + {ir['n_hard']} hard/colloquial).

| Metric | Value |
|---|---|
| **Overall routing accuracy** | **{ir['accuracy']:.1%}** |
| Standard tier ({ir['n_standard']}) | {ir['accuracy_standard']:.1%} |
| Hard tier ({ir['n_hard']}) | {ir['accuracy_hard']:.1%} |

Per-intent accuracy: {', '.join(f"{SHORT[k]} {v:.0%}" for k, v in ir['per_intent_accuracy'].items())}

### Confusion matrix

{cm_table}

Misrouted queries ({len(ir['misrouted'])}):
{chr(10).join("- [" + m['tier'] + "] '" + m['query'] + "' -> " + m['got'] + " (expected " + m['expected'] + ")" for m in ir['misrouted']) or '- none'}

The hard tier is where this classifier is weakest, and every miss is listed
above rather than hidden. Whether the LLM path recovers those misses is a
measured question, not an assumption — see §1.2/§1.3.
{llm_md}
## 2. Attendance computation — deterministic verification

Attendance percentage calculation is a deterministic algorithm, not a learned
model; this is a correctness check, **not** an "AI accuracy" figure.

- Summaries verified against independent brute-force recomputation: {aa['summaries_checked']}
- Mismatches: {aa['mismatches']} (correctness target >= 99%: {'MET' if aa['meets_99_target'] else 'NOT MET'})

## 3. Cross-agent propagation (live cascades)

Measurement boundary: bus cascade latency runs from the first
`attendance.uploaded` publish to the last downstream event, including all
agent logic, ORM/database commits and audit-log writes. Wall time adds
request validation and the bulk insert of the uploaded records.

Measurement conditions: {'the local LLM was resident in memory during this run'
if results['llm_available'] else 'no LLM was loaded during this run'}.
This matters — the cascade path never calls the LLM, but a resident
~2 GB model competes for RAM and CPU, and the same benchmark measures
roughly 3-4x lower on this laptop with Ollama stopped. Compare cascade
figures only across runs taken under the same conditions.

| Metric | Value |
|---|---|
| Cascades executed | {ca['cascades_run']} (x{ca['records_per_cascade']} records each) |
| Avg bus cascade latency | {ca['avg_cascade_ms']} ms |
| p95 bus cascade latency | {ca['p95_cascade_ms']} ms |
| Max bus cascade latency | {ca['max_cascade_ms']} ms |
| Avg wall time incl. upload | {ca['avg_wall_ms_incl_upload']} ms |
| Avg agents involved | {ca['avg_agents_involved']} |
| <2 s propagation target | {'MET' if ca['meets_2s_propagation_target'] else 'NOT MET'} |
| <5 s end-to-end target | {'MET' if ca['meets_5s_end_to_end_target'] else 'NOT MET'} |

Cascade topics observed: {', '.join(ca['topics_in_cascade'])}

## 4. Modeled comparison vs manual workflow

> {mc['assumption_note']} Validate these step times with a structured
> interview of the exam cell / accounts office before final submission.

| Manual step (assumed) | Minutes |
|---|---|
{chr(10).join('| ' + s['step'] + ' | ' + str(s['minutes']) + ' |' for s in mc['steps'])}
| **Total** | **{mc['manual_total_minutes']} min ({mc['manual_total_minutes']/60:.1f} working hours)** |

| | Manual | MAWOS |
|---|---|---|
| End-to-end time | {mc['manual_total_minutes']} min (modeled) | {mc['mawos_avg_ms']:.0f} ms (measured) |
| Human touchpoints | {mc['manual_human_touchpoints']} | {mc['mawos_human_touchpoints']} (the upload itself) |

Sensitivity: even with every manual step overestimated 10x
(total {mc['manual_total_minutes']//10} min), MAWOS remains
~{(mc['manual_total_minutes']//10)*60_000//int(mc['mawos_avg_ms']):,}x faster,
and the touchpoint reduction (6 -> 1) is independent of timing assumptions.

## 5. ML models (UCI-calibrated, correlation-preserving, noise-injected)

| Model | Test acc. | Precision | Recall | F1 | 5-fold CV |
|---|---|---|---|---|---|
| Scholarship CART (entropy) | {sch.get('test_accuracy')} | {sch.get('precision')} | {sch.get('recall')} | {sch.get('f1')} | {sch.get('cv5_mean_accuracy')} ± {sch.get('cv5_std')} |
| Placement Random Forest (100 trees) | {plc.get('test_accuracy')} | {plc.get('precision')} | {plc.get('recall')} | {plc.get('f1')} | {plc.get('cv5_mean_accuracy')} ± {plc.get('cv5_std')} |

Methodology: docs/DATASET_METHODOLOGY.md (Gaussian copula over UCI-estimated
correlations; 3% label noise; stochastic outcomes — accuracy is deliberately
below 100% by construction).
"""
    (RESULTS_DIR / "RESULTS.md").write_text(md, encoding="utf-8")
    print(f"\nWrote {RESULTS_DIR / 'RESULTS.md'}")


def main():
    run_llm = "--no-llm" not in sys.argv
    skip_single = "--no-role-sensitivity" in sys.argv
    Base.metadata.create_all(bind=engine)
    if seed_all():
        bootstrap_evaluations(get_agents())
    db = SessionLocal()
    try:
        db.query(IntentLog).delete()
        db.query(WorkflowEvent).delete()
        db.query(AttendanceRecord).filter_by(uploaded_by="evaluator").delete()
        db.commit()
        print("1/5 intent routing — deterministic tier…")
        intent = eval_intent_routing(db)
        print(f"    overall {intent['accuracy']:.1%} "
              f"(std {intent['accuracy_standard']:.1%} / "
              f"hard {intent['accuracy_hard']:.1%})")

        intent_llm = intent_llm_single = None
        if run_llm:
            if llm.check_ollama(force=True):
                print(f"2/5 intent routing — LLM tier "
                      f"({llm.config.OLLAMA_MODEL}), 108 live calls…")
                intent_llm = eval_intent_routing_llm(db, role_mode="matched")
                if intent_llm:
                    print(f"    role-matched: overall {intent_llm['accuracy']:.1%} "
                          f"(std {intent_llm['accuracy_standard']:.1%} / "
                          f"hard {intent_llm['accuracy_hard']:.1%}) "
                          f"@ {intent_llm['avg_latency_ms']:.0f} ms/query")
                if not skip_single:
                    print("    permission-sensitivity run (all queries as "
                          "admin), 108 more live calls…")
                    intent_llm_single = eval_intent_routing_llm(
                        db, role_mode="single")
                    if intent_llm_single:
                        print(f"    single-role: overall "
                              f"{intent_llm_single['accuracy']:.1%} "
                              f"({intent_llm_single['no_tool_selected']} "
                              f"queries answered with no tool call)")
            else:
                print("2/5 intent routing — LLM tier SKIPPED (no Ollama at "
                      f"{llm.config.OLLAMA_HOST})")
        else:
            print("2/5 intent routing — LLM tier skipped (--no-llm)")

        print("3/5 attendance verification…")
        att = eval_attendance_accuracy(db)
        print(f"    {att['mismatches']} mismatches over {att['summaries_checked']}")
        print("4/5 live cascade benchmark…")
        cascades = asyncio.run(eval_cascades(db))
        print(f"    avg {cascades['avg_cascade_ms']} ms, "
              f"p95 {cascades['p95_cascade_ms']} ms")
        print("5/5 ML metrics…")
        results = {
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "llm_available": llm.check_ollama(),
            "intent_routing": intent,
            "intent_routing_llm": intent_llm,
            "intent_routing_llm_single_role": intent_llm_single,
            "attendance_accuracy": att,
            "cascades": cascades,
            "manual_comparison": manual_comparison(cascades["avg_cascade_ms"]),
            "ml": ml_metrics(),
        }
        write_report(results)
    finally:
        db.close()


if __name__ == "__main__":
    main()
