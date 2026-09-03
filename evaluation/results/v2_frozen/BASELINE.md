# MAWOS v2 — frozen baseline

Generated 2026-08-15T10:34:49 · commit `46a0c6e`
Shipped database `2056e866a843d948…` (verified unchanged).

This is the comparator for every v3 result. It is frozen: rerunning it is
a mistake, not a refresh. See `evaluation/PROTOCOL.md`.

## 1. Routing — v2 keyword lexicon, 108 dev queries

| Tier | Accuracy | Seed σ |
|---|---|---|
| Overall | 89.8% | 0.0% |
| Standard (72) | 100.0% | 0.0% |
| Colloquial (36) | 69.4% | 0.0% |

Lexicon body `sha256 313809cb23022e26…`.

The lexicon is deterministic, so the seed bands are zero by construction. They are reported anyway: a zero variance band is evidence, and it is the contrast against the LLM tier's non-zero band that makes the comparison honest.

**These 108 queries are development data.** The lexicon was tuned against
their phrasing, so this number cannot be a headline. It is the tuning
comparator and nothing else.

Misrouted (11):

- `att-h03` [colloquial] "How many more classes can I afford to miss?" → profile_query (expected attendance_query)
- `fee-h03` [colloquial] "The accounts office is asking for money again, what's pending?" → profile_query (expected fees_query)
- `sch-h02` [colloquial] "Will the college waive my fees given my family situation?" → fees_query (expected scholarship_query)
- `esc-h01` [colloquial] "How far away are the semester finals?" → profile_query (expected exam_schedule_query)
- `esc-h02` [colloquial] "When do we write our papers?" → profile_query (expected exam_schedule_query)
- `mrk-h02` [colloquial] "How did the ML test go for me?" → profile_query (expected marks_query)
- `tt-h02` [colloquial] "What's my day looking like tomorrow?" → profile_query (expected timetable_query)
- `tt-h03` [colloquial] "Where should I be for the first class on Monday?" → profile_query (expected timetable_query)
- `ana-h02` [colloquial] "Which section is struggling the most?" → profile_query (expected analytics_query)
- `ana-h03` [colloquial] "How does our branch compare this semester?" → admission_query (expected analytics_query)
- `ntf-h01` [colloquial] "Did the college send me anything?" → profile_query (expected notification_query)

## 2. Scheduler — v2 greedy solver, 10 seeds

The defects the P1 rewrite targets, measured:

| Metric | Mean | σ | Min | Max |
|---|---|---|---|---|
| Late-start days (of 200) | 80.80 | 5.56 | 74.00 | 90.00 |
| Late-start rate | 40.4% | 2.8% | 37.0% | 45.0% |
| Idle gaps (total) | 223.00 | 11.44 | 207.00 | 250.00 |
| Idle gaps per section-day | 1.11 | 0.06 | 1.03 | 1.25 |
| Daily-load σ (mean) | 1.01 | 0.04 | 0.96 | 1.09 |
| Longest contiguous block | 2.63 | 0.04 | 2.56 | 2.69 |
| Subject repeats within a day | 138.50 | 7.06 | 123.00 | 149.00 |
| Faculty idle gaps | 322.00 | 11.30 | 304.00 | 338.00 |
| Placement rate | 1.000 | 0.000 | 1.000 | 1.000 |
| Unplaced | 0.00 | 0.00 | 0.00 | 0.00 |
| Objective (lower better) | 2441 | 42 | 2394 | 2531 |
| Solve time (ms) | 163 | 18 | 141 | 192 |

Hard constraints hold in every seed: faculty conflicts
0 max, section conflicts
0 max. The v2 solver is *feasible*; it
simply has no notion of a good schedule, because it optimises hard
constraints only and no objective function exists in it.
