# MAWOS v2 — Rebuild Plan: a real university, real agents, a real LLM brain

## Why v1 felt fake (honest diagnosis)

1. **The LLM did nothing.** Ollama is not installed on this laptop, so every
   chat silently used the keyword fallback. v2 makes the LLM the primary
   brain (tool-calling agent) and shows its mode on screen; the fallback
   stays only as the offline degradation path it was meant to be.
2. **Canned answers.** Agents returned fixed template strings. v2: the LLM
   composes answers from live tool results; agents expose *capabilities*
   (tools), not paragraphs.
3. **Toy institution.** One department, one semester. v2: 5 departments ×
   4 years × 2 sections ≈ 1,200 students, 75 faculty, HODs, Principal,
   real subject catalogue, teaching assignments.
4. **Roles were cosmetic.** v2: five role experiences with different
   capabilities (student / faculty / HOD / principal / admin).
5. **Missing core university functions.** v2 adds Admissions (full pipeline)
   and Timetable generation + download — both genuinely agentic tasks.

## Agent roster v2 (10 — chosen by function, not by report)

| Agent | Type | What it actually does |
|---|---|---|
| **Orchestrator** | LLM + planner | Tool-calling loop: LLM reads the request, picks tools (role-permission-checked), composes grounded answers. Offline fallback: intent → tool → template. |
| **Admission** | workflow + rules (+LLM notes) | Application pipeline: submitted → verified → merit ranked (weighted score) → seat allotted vs dept intake/quota → fee → enrolled (creates the Student record, fires cascade). |
| **Timetable** | constraint solver | Generates conflict-free weekly timetables for all 40 sections (teacher can't be in two rooms at once, subject spread rules), reports solver metrics, exports CSV/print. |
| **Academic** | records | Students, marks (CIE), SGPA; serves role dashboards. |
| **Attendance** | rules + proactive | %, shortage, streaks; nightly proactive scan publishes alerts (visible agent autonomy). |
| **Finance** | rules + proactive | Fee structures per dept/year, payments, ₹50/day fines, defaulter scans. |
| **Exam** | rules | Exam schedules per dept/sem, hall-ticket eligibility with reason codes. |
| **Scholarship** | rules + CART | Pre-filter + calibrated CART scoring (research component kept). |
| **Placement** | rules + RF | Drive eligibility + calibrated RF ranking (research component kept). |
| **Notification** | event-driven | Turns every cascade event into targeted messages. |

Removed: Library, Smart-Event, and the fake "Student/Faculty agents" —
students and faculty are *roles with permissions*, not agents.

## Role capabilities (v2 scope — Chairman/AICTE/NIRF views deferred)

- **Student**: dashboard (attendance, fees + pay, hall ticket, scholarship,
  placements, timetable view/download, notifications), AI assistant.
- **Faculty**: my teaching assignments, mark attendance for my
  subject-sections, enter internal marks, my timetable, class analytics.
- **HOD**: department analytics (attendance/fees/shortage by section),
  regenerate department timetable, defaulter lists.
- **Principal**: institution analytics — dept comparison, admissions funnel,
  fee collection, placement statistics.
- **Admin**: admissions pipeline board (verify → merit → allot seats),
  fee administration, day-simulation for demos.

## The LLM's real job (and how to switch it on)

Ollama chat API with **tool calling** (Qwen2.5 supports it):
user message → LLM selects from ~12 typed tools (get_attendance,
get_timetable, dept_analytics, admissions_summary, …) → tools execute under
the caller's role permissions → LLM writes the final grounded answer.
Every step logged (tools chosen, latency, mode). UI shows a live badge:
**AI mode: LLM (qwen2.5)** vs **deterministic fallback**.

To activate on this laptop: install Ollama → `ollama pull qwen2.5:3b-instruct`
→ restart MAWOS. Nothing else changes; the research metrics then compare
both modes honestly (that comparison is itself an experiment).

> **Outcome (2026-08-03) — this plan's central assumption did not hold.**
> Ollama is installed and the LLM path runs, but measured head-to-head the
> LLM routes *worse* than the deterministic tier it was meant to replace:
> 70.4% vs 89.8% overall, 44.4% vs 69.4% on the indirect phrasings it was
> specifically supposed to rescue, at ~4.5 s/query vs <1 ms. The plan's
> framing above ("the LLM did nothing" in v1 → make it primary) is preserved
> as the historical record; the current, measured position is in README §
> *Measured results* and ARCHITECTURE §"What is the LLM actually doing?".
> Short version: route with rules, compose with the model.

## Database v2 (real college shape)

Departments AIML/CSE/ECE/ME/CV (intake 60 each) · years 1–4 (odd semesters
1/3/5/7) · sections A/B · ~30 students each ≈ 1,200 students · 75 faculty
with designations + teaching assignments · subject catalogue per dept/sem ·
timetable slots · marks (3 CIEs) · applications table for admissions ·
plus everything kept from v1 (attendance, fees, hall tickets, scholarship,
placements, notifications, workflow audit).

## What stays from v1 (the research spine — untouched concepts)

Instrumented event bus + workflow IDs + trace inspector · calibrated
noise-injected ML (CART/RF) · evaluation harness (routing tiers, cascades,
ablation, failure injection, scalability) · FL PoC as future work.

## UI: premium university identity

Ivory/paper surfaces, deep navy, gold accents, serif display type — a
registrar's-office feel, not an admin template. Role-specific portals, a
timetable grid with one-click CSV/print download, admissions kanban,
analytics with clean charts, live agent-activity feed, workflow inspector.

## Build order

1. Schema + seed (departments, faculty, assignments, subjects, applications)
2. Timetable Agent (solver + export + metrics)
3. Admission Agent (pipeline + merit + enrollment cascade)
4. Orchestrator v2 (LLM tool loop + permission layer + fallback)
5. Port Attendance/Finance/Exam/Scholarship/Placement/Notification + proactive scans
6. API v2 (role-guarded)
7. Frontend v2 (five portals + assistant + system view)
8. Tests + evaluation scripts updated to v2
9. Full verification, docs refresh
