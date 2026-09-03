"""Frozen benchmark task definitions — MAWOS v3.

FROZEN AT P0. Do not edit without a dated entry in evaluation/PROTOCOL.md.

The point of this module is that a task's gold answer is defined
**independently of any tool registry**. `gold_tool` is a name, not a
reference: it does not require that tool to exist in the system under
test. Every experimental condition is then obliged to construct a tool
space that *contains* `gold_tool`, so the 5-tool and 30-tool conditions
are provably answering the same task.

This is the fix for the defect found in rev. 2 planning, where removing
the Admission agent would have made 9 tasks unanswerable and turned a
tool-space experiment into an answerability experiment.

Provenance
----------
`source="v2-dev"` tasks are the 108 queries shipped in MAWOS v2, of which
99 remain after P2 (docs/RESEARCH_PLAN_V3.md §7.1): the 9 admission_query
tasks were dropped when `get_admissions_funnel` was retired as a tool,
documented in PROTOCOL.md §12. They are **development data only**.
CLAUDE.md already records that the keyword lexicon was tuned to their
phrasings, so they cannot support a headline
number. They are exactly right for tuning tau, prompts and weights.

`stratum_provenance` records how a task landed in its stratum:
  * "team-assembled-v2" — we sorted it, after the fact, into standard vs
    hard. This is NOT a clean stratum and must never be reported as one.
  * "annotator-preregistered" — an external annotator assigned the stratum
    at authoring time, before any system saw the query.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    """One benchmark item. Immutable by construction."""

    id: str
    query: str
    gold_intent: str
    gold_tool: str
    stratum: str                # "standard" | "colloquial"
    asker_role: str             # the role that would naturally ask this
    source: str                 # "v2-dev" | "heldout-<date>"
    stratum_provenance: str


def _v2(tid, query, intent, tool, stratum, role):
    return Task(id=tid, query=query, gold_intent=intent, gold_tool=tool,
                stratum=stratum, asker_role=role, source="v2-dev",
                stratum_provenance="team-assembled-v2")


# --------------------------------------------------------------- dev split
# The 108 v2 queries, minus 9 admission_query tasks dropped at P2 (99
# remain). DEV ONLY — never a headline number.
DEV_TASKS: list[Task] = [
    _v2("att-s01", "What is my attendance percentage?",
        "attendance_query", "get_attendance", "standard", "student"),
    _v2("att-s02", "Am I short of attendance?",
        "attendance_query", "get_attendance", "standard", "student"),
    _v2("att-s03", "Do I have attendance shortage in any subject?",
        "attendance_query", "get_attendance", "standard", "student"),
    _v2("att-s04", "Was I marked absent yesterday?",
        "attendance_query", "get_attendance", "standard", "student"),
    _v2("att-s05", "Is my attendance above 75%?",
        "attendance_query", "get_attendance", "standard", "student"),
    _v2("att-s06", "attendance status",
        "attendance_query", "get_attendance", "standard", "student"),
    _v2("fee-s01", "Do I have any pending fees?",
        "fees_query", "get_fees", "standard", "student"),
    _v2("fee-s02", "How much tuition fee is due?",
        "fees_query", "get_fees", "standard", "student"),
    _v2("fee-s03", "What is my fine amount?",
        "fees_query", "get_fees", "standard", "student"),
    _v2("fee-s04", "Have I paid my exam fees?",
        "fees_query", "get_fees", "standard", "student"),
    _v2("fee-s05", "Show the fee defaulter list",
        "fees_query", "get_fees", "standard", "student"),
    _v2("fee-s06", "fee status",
        "fees_query", "get_fees", "standard", "student"),
    _v2("sch-s01", "Am I eligible for the scholarship?",
        "scholarship_query", "get_scholarship", "standard", "student"),
    _v2("sch-s02", "What is my scholarship status?",
        "scholarship_query", "get_scholarship", "standard", "student"),
    _v2("sch-s03", "Any update on my financial aid application?",
        "scholarship_query", "get_scholarship", "standard", "student"),
    _v2("sch-s04", "Will I receive the stipend this year?",
        "scholarship_query", "get_scholarship", "standard", "student"),
    _v2("sch-s05", "Do I qualify for a fee waiver?",
        "scholarship_query", "get_scholarship", "standard", "student"),
    _v2("sch-s06", "scholarship eligibility check",
        "scholarship_query", "get_scholarship", "standard", "student"),
    _v2("exm-s01", "Will I get my hall ticket?",
        "exam_query", "get_hall_ticket", "standard", "student"),
    _v2("exm-s02", "Am I eligible to write the exam?",
        "exam_query", "get_hall_ticket", "standard", "student"),
    _v2("exm-s03", "Is my admit card released?",
        "exam_query", "get_hall_ticket", "standard", "student"),
    _v2("exm-s04", "Why is my hall ticket blocked?",
        "exam_query", "get_hall_ticket", "standard", "student"),
    _v2("exm-s05", "hall ticket status",
        "exam_query", "get_hall_ticket", "standard", "student"),
    _v2("exm-s06", "Can I sit for the exams?",
        "exam_query", "get_hall_ticket", "standard", "student"),
    _v2("esc-s01", "When do semester exams start?",
        "exam_schedule_query", "get_exam_schedule", "standard", "student"),
    _v2("esc-s02", "Show me the exam schedule",
        "exam_schedule_query", "get_exam_schedule", "standard", "student"),
    _v2("esc-s03", "What are the exam dates?",
        "exam_schedule_query", "get_exam_schedule", "standard", "student"),
    _v2("esc-s04", "Exam timetable please",
        "exam_schedule_query", "get_exam_schedule", "standard", "student"),
    _v2("esc-s05", "When are the sem exams?",
        "exam_schedule_query", "get_exam_schedule", "standard", "student"),
    _v2("esc-s06", "semester exam dates",
        "exam_schedule_query", "get_exam_schedule", "standard", "student"),
    _v2("mrk-s01", "Show my internal marks",
        "marks_query", "get_marks", "standard", "student"),
    _v2("mrk-s02", "What did I score in CIE 2?",
        "marks_query", "get_marks", "standard", "student"),
    _v2("mrk-s03", "My DBMS internal marks",
        "marks_query", "get_marks", "standard", "student"),
    _v2("mrk-s04", "Show my CIE scores",
        "marks_query", "get_marks", "standard", "student"),
    _v2("mrk-s05", "How much did I get in the internals?",
        "marks_query", "get_marks", "standard", "student"),
    _v2("mrk-s06", "internal marks please",
        "marks_query", "get_marks", "standard", "student"),
    _v2("tt-s01", "What classes do I have this week?",
        "timetable_query", "get_timetable", "standard", "student"),
    _v2("tt-s02", "Show my timetable",
        "timetable_query", "get_timetable", "standard", "student"),
    _v2("tt-s03", "Which subject is in the first period tomorrow?",
        "timetable_query", "get_timetable", "standard", "student"),
    _v2("tt-s04", "My class schedule please",
        "timetable_query", "get_timetable", "standard", "student"),
    _v2("tt-s05", "What periods do I have today?",
        "timetable_query", "get_timetable", "standard", "student"),
    _v2("tt-s06", "weekly routine",
        "timetable_query", "get_timetable", "standard", "student"),
    _v2("plc-s01", "Which placement drives am I eligible for?",
        "placement_query", "get_placements", "standard", "student"),
    _v2("plc-s02", "When is the next campus drive?",
        "placement_query", "get_placements", "standard", "student"),
    _v2("plc-s03", "What companies are coming this month?",
        "placement_query", "get_placements", "standard", "student"),
    _v2("plc-s04", "Show my placement eligibility",
        "placement_query", "get_placements", "standard", "student"),
    _v2("plc-s05", "Any job opportunities for me?",
        "placement_query", "get_placements", "standard", "student"),
    _v2("plc-s06", "placement drive list",
        "placement_query", "get_placements", "standard", "student"),
    _v2("ana-s01", "Show department analytics",
        "analytics_query", "get_dept_analytics", "standard", "hod"),
    _v2("ana-s02", "How is my department performing?",
        "analytics_query", "get_dept_analytics", "standard", "hod"),
    _v2("ana-s03", "What is the average attendance in AIML?",
        "analytics_query", "get_dept_analytics", "standard", "hod"),
    _v2("ana-s04", "Department report please",
        "analytics_query", "get_dept_analytics", "standard", "hod"),
    _v2("ana-s05", "Give me an overview of the department",
        "analytics_query", "get_dept_analytics", "standard", "hod"),
    _v2("ana-s06", "How are the students performing this semester?",
        "analytics_query", "get_dept_analytics", "standard", "hod"),
    _v2("ntf-s01", "Show my notifications",
        "notification_query", "get_notifications", "standard", "student"),
    _v2("ntf-s02", "Any new alerts for me?",
        "notification_query", "get_notifications", "standard", "student"),
    _v2("ntf-s03", "What are the latest announcements?",
        "notification_query", "get_notifications", "standard", "student"),
    _v2("ntf-s04", "Any reminders pending?",
        "notification_query", "get_notifications", "standard", "student"),
    _v2("ntf-s05", "Did I get any messages?",
        "notification_query", "get_notifications", "standard", "student"),
    _v2("ntf-s06", "notifications please",
        "notification_query", "get_notifications", "standard", "student"),
    _v2("prf-s01", "Show my profile",
        "profile_query", "get_student_overview", "standard", "student"),
    _v2("prf-s02", "What is my CGPA?",
        "profile_query", "get_student_overview", "standard", "student"),
    _v2("prf-s03", "How many backlogs do I have?",
        "profile_query", "get_student_overview", "standard", "student"),
    _v2("prf-s04", "Show my details",
        "profile_query", "get_student_overview", "standard", "student"),
    _v2("prf-s05", "Give me my overall summary",
        "profile_query", "get_student_overview", "standard", "student"),
    _v2("prf-s06", "Who am I logged in as?",
        "profile_query", "get_student_overview", "standard", "student"),
    _v2("att-h01", "If I skip tomorrow will I fall below the limit?",
        "attendance_query", "get_attendance", "colloquial", "student"),
    _v2("att-h02", "The professor marked me absent even though I came",
        "attendance_query", "get_attendance", "colloquial", "student"),
    _v2("att-h03", "How many more classes can I afford to miss?",
        "attendance_query", "get_attendance", "colloquial", "student"),
    _v2("fee-h01", "How much do I still owe the college?",
        "fees_query", "get_fees", "colloquial", "student"),
    _v2("fee-h02", "Is there a penalty added to my dues?",
        "fees_query", "get_fees", "colloquial", "student"),
    _v2("fee-h03", "The accounts office is asking for money again, what's pending?",
        "fees_query", "get_fees", "colloquial", "student"),
    _v2("sch-h01", "Any chance of getting financial support this semester?",
        "scholarship_query", "get_scholarship", "colloquial", "student"),
    _v2("sch-h02", "Will the college waive my fees given my family situation?",
        "scholarship_query", "get_scholarship", "colloquial", "student"),
    _v2("sch-h03", "Is there money help for students like me?",
        "scholarship_query", "get_scholarship", "colloquial", "student"),
    _v2("exm-h01", "Am I allowed into the exam hall?",
        "exam_query", "get_hall_ticket", "colloquial", "student"),
    _v2("exm-h02", "Is anything blocking me from writing my papers?",
        "exam_query", "get_hall_ticket", "colloquial", "student"),
    _v2("exm-h03", "Can I sit for the finals?",
        "exam_query", "get_hall_ticket", "colloquial", "student"),
    _v2("esc-h01", "How far away are the semester finals?",
        "exam_schedule_query", "get_exam_schedule", "colloquial", "student"),
    _v2("esc-h02", "When do we write our papers?",
        "exam_schedule_query", "get_exam_schedule", "colloquial", "student"),
    _v2("esc-h03", "Are the exam dates out yet?",
        "exam_schedule_query", "get_exam_schedule", "colloquial", "student"),
    _v2("mrk-h01", "How did I do in the second internals?",
        "marks_query", "get_marks", "colloquial", "student"),
    _v2("mrk-h02", "How did the ML test go for me?",
        "marks_query", "get_marks", "colloquial", "student"),
    _v2("mrk-h03", "Are my CIE scores decent?",
        "marks_query", "get_marks", "colloquial", "student"),
    _v2("tt-h01", "What's my first period tomorrow?",
        "timetable_query", "get_timetable", "colloquial", "student"),
    _v2("tt-h02", "What's my day looking like tomorrow?",
        "timetable_query", "get_timetable", "colloquial", "student"),
    _v2("tt-h03", "Where should I be for the first class on Monday?",
        "timetable_query", "get_timetable", "colloquial", "student"),
    _v2("plc-h01", "Which firms can I sit for?",
        "placement_query", "get_placements", "colloquial", "student"),
    _v2("plc-h02", "Do I meet the cutoff for the next drive?",
        "placement_query", "get_placements", "colloquial", "student"),
    _v2("plc-h03", "What are my chances of getting hired?",
        "placement_query", "get_placements", "colloquial", "student"),
    _v2("ana-h01", "Give me a health check of the department",
        "analytics_query", "get_dept_analytics", "colloquial", "hod"),
    _v2("ana-h02", "Which section is struggling the most?",
        "analytics_query", "get_dept_analytics", "colloquial", "hod"),
    _v2("ana-h03", "How does our branch compare this semester?",
        "analytics_query", "get_dept_analytics", "colloquial", "hod"),
    _v2("ntf-h01", "Did the college send me anything?",
        "notification_query", "get_notifications", "colloquial", "student"),
    _v2("ntf-h02", "Anything I should know about?",
        "notification_query", "get_notifications", "colloquial", "student"),
    _v2("ntf-h03", "What did I miss while I was away?",
        "notification_query", "get_notifications", "colloquial", "student"),
    _v2("prf-h01", "Give me a rundown of where I stand",
        "profile_query", "get_student_overview", "colloquial", "student"),
    _v2("prf-h02", "How am I doing overall this semester?",
        "profile_query", "get_student_overview", "colloquial", "student"),
    _v2("prf-h03", "Summarise my academics",
        "profile_query", "get_student_overview", "colloquial", "student"),
]

# -------------------------------------------------------------- test split
# Authored OUTSIDE the team, blind to the lexicon. Populated at P5.
# Until then this is deliberately empty: any headline number computed
# before it is filled is invalid by construction.
TEST_TASKS: list[Task] = []


ALL_GOLD_TOOLS = sorted({t.gold_tool for t in DEV_TASKS} |
                        {t.gold_tool for t in TEST_TASKS})


def tasks(split: str) -> list[Task]:
    """Fetch a split. Raises rather than silently returning the wrong one."""
    if split == "dev":
        return list(DEV_TASKS)
    if split == "test":
        if not TEST_TASKS:
            raise RuntimeError(
                "The test split is empty. Held-out queries are authored "
                "outside the team at P5; computing a headline number before "
                "then is invalid. See evaluation/PROTOCOL.md.")
        return list(TEST_TASKS)
    raise ValueError(f"unknown split {split!r} (expected 'dev' or 'test')")
