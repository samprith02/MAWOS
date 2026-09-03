# MAWOS v2 Evaluation Results

Generated: 2026-08-03T23:01:28
LLM available at benchmark time: True
Both routing tiers were scored on the same 108 queries against the
same target tools — see §1.3 for the head-to-head.

## 1. Intent routing — deterministic fallback baseline

Benchmark: 108 labelled queries across 12 intents
(72 standard + 36 hard/colloquial).

| Metric | Value |
|---|---|
| **Overall routing accuracy** | **89.8%** |
| Standard tier (72) | 100.0% |
| Hard tier (36) | 69.4% |

Per-intent accuracy: adm 100%, ana 78%, att 89%, exm 100%, esc 78%, fee 89%, mrk 89%, ntf 89%, plc 100%, prf 100%, sch 89%, tt 78%

### Confusion matrix

| true \ pred | att | fee | sch | exm | esc | mrk | tt | plc | adm | ana | ntf | prf |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **att** | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| **fee** | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| **sch** | 0 | 1 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **exm** | 0 | 0 | 0 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **esc** | 0 | 0 | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| **mrk** | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 1 |
| **tt** | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 2 |
| **plc** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 9 | 0 | 0 | 0 | 0 |
| **adm** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 9 | 0 | 0 | 0 |
| **ana** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 7 | 0 | 1 |
| **ntf** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 1 |
| **prf** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 9 |

Misrouted queries (11):
- [hard] 'How many more classes can I afford to miss?' -> profile_query (expected attendance_query)
- [hard] 'The accounts office is asking for money again, what's pending?' -> profile_query (expected fees_query)
- [hard] 'Will the college waive my fees given my family situation?' -> fees_query (expected scholarship_query)
- [hard] 'How far away are the semester finals?' -> profile_query (expected exam_schedule_query)
- [hard] 'When do we write our papers?' -> profile_query (expected exam_schedule_query)
- [hard] 'How did the ML test go for me?' -> profile_query (expected marks_query)
- [hard] 'What's my day looking like tomorrow?' -> profile_query (expected timetable_query)
- [hard] 'Where should I be for the first class on Monday?' -> profile_query (expected timetable_query)
- [hard] 'Which section is struggling the most?' -> profile_query (expected analytics_query)
- [hard] 'How does our branch compare this semester?' -> admission_query (expected analytics_query)
- [hard] 'Did the college send me anything?' -> profile_query (expected notification_query)

The hard tier is where this classifier is weakest, and every miss is listed
above rather than hidden. Whether the LLM path recovers those misses is a
measured question, not an assumption — see §1.2/§1.3.

## 1.2 Intent routing — LLM tool-selection tier

Model: `qwen2.5:3b-instruct` (local Ollama, temperature 0.1). Identical 108
queries, identical target tools, scored strictly on the **first tool the
model selects**.

Each query is asked by the role that would really ask it — students ask the
first-person questions ("my attendance", "my hall ticket"), staff ask the
departmental and admissions ones — which is how queries actually reach the
orchestrator, since every request arrives inside one portal's session.
§1.2b shows why that choice is load-bearing rather than cosmetic.

| Metric | Value |
|---|---|
| **Overall routing accuracy** | **70.4%** |
| Standard tier (72) | 83.3% |
| Hard tier (36) | 44.4% |
| Lenient variant | 70.4% (counts get_institution_analytics as correct for analytics_query; headline number is strict) |
| Answered without calling a tool | 23 |
| Selected an off-benchmark tool | 24 |
| LLM call failures | 0 |
| Latency per query | avg 4474 ms · p95 4903 ms |

Per-intent accuracy: adm 44%, ana 89%, att 67%, exm 67%, esc 67%, fee 100%, mrk 67%, ntf 89%, plc 78%, prf 78%, sch 44%, tt 56%

### Confusion matrix — LLM tier

| true \ pred | att | fee | sch | exm | esc | mrk | tt | plc | adm | ana | ntf | prf |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **att** | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **fee** | 0 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **sch** | 0 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **exm** | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **esc** | 0 | 0 | 0 | 0 | 6 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| **mrk** | 0 | 0 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| **tt** | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 |
| **plc** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 0 | 0 | 0 | 0 |
| **adm** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 2 | 1 | 0 |
| **ana** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 |
| **ntf** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 |
| **prf** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 7 |

Misrouted queries (32):
- [standard] 'Am I short of attendance?' -> no_tool (expected get_attendance)
- [standard] 'Any update on my financial aid application?' -> get_fees (expected get_scholarship)
- [standard] 'Will I receive the stipend this year?' -> get_fees (expected get_scholarship)
- [standard] 'Do I qualify for a fee waiver?' -> get_fees (expected get_scholarship)
- [standard] 'Am I eligible to write the exam?' -> no_tool (expected get_hall_ticket)
- [standard] 'Exam timetable please' -> get_timetable (expected get_exam_schedule)
- [standard] 'What did I score in CIE 2?' -> no_tool (expected get_marks)
- [standard] 'Which subject is in the first period tomorrow?' -> no_tool (expected get_timetable)
- [standard] 'weekly routine' -> no_tool (expected get_timetable)
- [standard] 'Has the merit list been prepared?' -> no_tool (expected get_admissions_funnel)
- [standard] 'How many seats are left in CSE?' -> get_dept_analytics (expected get_admissions_funnel)
- [standard] 'How many students enrolled this year?' -> get_institution_analytics (expected get_admissions_funnel)
- [hard] 'The professor marked me absent even though I came' -> no_tool (expected get_attendance)
- [hard] 'How many more classes can I afford to miss?' -> no_tool (expected get_attendance)
- [hard] 'Will the college waive my fees given my family situation?' -> get_fees (expected get_scholarship)
- [hard] 'Is there money help for students like me?' -> no_tool (expected get_scholarship)
- [hard] 'Is anything blocking me from writing my papers?' -> no_tool (expected get_hall_ticket)
- [hard] 'Can I sit for the finals?' -> no_tool (expected get_hall_ticket)
- [hard] 'How far away are the semester finals?' -> no_tool (expected get_exam_schedule)
- [hard] 'When do we write our papers?' -> no_tool (expected get_exam_schedule)
- [hard] 'How did I do in the second internals?' -> no_tool (expected get_marks)
- [hard] 'How did the ML test go for me?' -> no_tool (expected get_marks)
- [hard] 'What's my first period tomorrow?' -> no_tool (expected get_timetable)
- [hard] 'Where should I be for the first class on Monday?' -> no_tool (expected get_timetable)
- [hard] 'Do I meet the cutoff for the next drive?' -> no_tool (expected get_placements)
- [hard] 'What are my chances of getting hired?' -> no_tool (expected get_placements)
- [hard] 'How many candidates cleared verification?' -> get_notifications (expected get_admissions_funnel)
- [hard] 'How full are the branches this year?' -> get_dept_analytics (expected get_admissions_funnel)
- [hard] 'How does our branch compare this semester?' -> no_tool (expected get_dept_analytics)
- [hard] 'Anything I should know about?' -> no_tool (expected get_notifications)
- [hard] 'Give me a rundown of where I stand' -> no_tool (expected get_student_overview)
- [hard] 'Summarise my academics' -> no_tool (expected get_student_overview)


## 1.2b Permission sensitivity — the same queries under one staff persona

The identical 108 queries, re-run with **every** query asked by the admin
persona instead of the role that would naturally ask it. All 12 target tools
are in scope for admin, so tool *availability* cannot explain any drop.

| | Role-matched | Single-role (admin) |
|---|---|---|
| Overall accuracy | 70.4% | 55.6% |
| Standard tier | 83.3% | 59.7% |
| Hard tier | 44.4% | 47.2% |
| Answered with **no tool call** | 23 | 35 |

Accuracy falls **14.8%** — and the mechanism is visible in the last row:
under the staff persona the model declines to call a tool on
35 queries. This is the model behaving *correctly*, not
failing. A first-person question like "Am I short of attendance?" is genuinely
unanswerable for an admin: `get_attendance` resolves a student's own USN for
students but demands an explicit USN from staff, and the persona never
supplied one. The model asks for clarification instead of inventing a USN.

Two consequences worth stating plainly. First, any single-persona tool-calling
benchmark understates a role-scoped system — the number measures the harness,
not the model. Second, the permission layer is doing real work at inference
time: role scoping does not merely reject unauthorised calls after the fact,
it changes which calls the model is willing to make at all.

## 1.3 Head-to-head — deterministic vs LLM routing

| Tier | Overall | Standard | Hard | Latency/query |
|---|---|---|---|---|
| Deterministic keyword classifier | 89.8% | 100.0% | 69.4% | <1 ms |
| LLM tool selection (`qwen2.5:3b-instruct`) | 70.4% | 83.3% | 44.4% | 4474 ms |
| **Delta** | **-19.4%** | **-16.7%** | **-25.0%** | — |

The hard tier is the honest test: colloquial, indirect phrasings that carry
no keyword the lexicon can score. On this run the LLM tier did **not** beat the lexicon on hard phrasings (**-25.0%**), and is **-19.4%** overall. Reported as measured: at this model size tool selection is not reliably better than the tuned keyword classifier, and the honest conclusion is that the LLM's contribution here is answer *composition* rather than routing. Each LLM-routed query costs 4474 ms (p95 4903 ms) against <1 ms for the keyword tier, which sharpens the trade-off further.

The deterministic tier remains the offline degradation path, and the system
reports which tier served every answer — so this table describes a real
runtime choice, not a hypothetical one.

## 2. Attendance computation — deterministic verification

Attendance percentage calculation is a deterministic algorithm, not a learned
model; this is a correctness check, **not** an "AI accuracy" figure.

- Summaries verified against independent brute-force recomputation: 1000
- Mismatches: 0 (correctness target >= 99%: MET)

## 3. Cross-agent propagation (live cascades)

Measurement boundary: bus cascade latency runs from the first
`attendance.uploaded` publish to the last downstream event, including all
agent logic, ORM/database commits and audit-log writes. Wall time adds
request validation and the bulk insert of the uploaded records.

Measurement conditions: the local LLM was resident in memory during this run.
This matters — the cascade path never calls the LLM, but a resident
~2 GB model competes for RAM and CPU, and the same benchmark measures
roughly 3-4x lower on this laptop with Ollama stopped. Compare cascade
figures only across runs taken under the same conditions.

| Metric | Value |
|---|---|
| Cascades executed | 10 (x50 records each) |
| Avg bus cascade latency | 466.1 ms |
| p95 bus cascade latency | 478.7 ms |
| Max bus cascade latency | 541.4 ms |
| Avg wall time incl. upload | 663.4 ms |
| Avg agents involved | 5 |
| <2 s propagation target | MET |
| <5 s end-to-end target | MET |

Cascade topics observed: attendance.updated, attendance.uploaded, exam.updated, notification.sent, placement.updated, scholarship.updated

## 4. Modeled comparison vs manual workflow

> Modeled estimate from stated per-step assumptions, not a field measurement. Validate these step times with a structured
> interview of the exam cell / accounts office before final submission.

| Manual step (assumed) | Minutes |
|---|---|
| Faculty compiles and submits attendance register | 15 |
| Office clerk enters records into the register/spreadsheet | 20 |
| Exam cell cross-checks hall-ticket eligibility | 240 |
| Scholarship cell re-verifies eligibility | 240 |
| Placement cell updates candidate lists | 240 |
| Notices prepared and circulated to affected students | 120 |
| **Total** | **875 min (14.6 working hours)** |

| | Manual | MAWOS |
|---|---|---|
| End-to-end time | 875 min (modeled) | 466 ms (measured) |
| Human touchpoints | 6 | 1 (the upload itself) |

Sensitivity: even with every manual step overestimated 10x
(total 87 min), MAWOS remains
~11,201x faster,
and the touchpoint reduction (6 -> 1) is independent of timing assumptions.

## 5. ML models (UCI-calibrated, correlation-preserving, noise-injected)

| Model | Test acc. | Precision | Recall | F1 | 5-fold CV |
|---|---|---|---|---|---|
| Scholarship CART (entropy) | 0.9 | 0.8958 | 0.8958 | 0.8958 | 0.8525 ± 0.033 |
| Placement Random Forest (100 trees) | 0.82 | 0.7959 | 0.8298 | 0.8125 | 0.8083 ± 0.0118 |

Methodology: docs/DATASET_METHODOLOGY.md (Gaussian copula over UCI-estimated
correlations; 3% label noise; stochastic outcomes — accuracy is deliberately
below 100% by construction).
