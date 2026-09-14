# P3 -- provenance gate dev-only engineering validation

`qwen2.5:3b-instruct`, dev split, seed 0 -- **one seed, not the 3-seed convention** (see this file's module docstring for why). 51 genuine answers checked, 3 tasks skipped (no tool called, or the LLM path gave up).

## Headline numbers

- **Catch rate on synthetic corruption: 100.0%** (39/39) -- one real numeric claim per answer replaced with a fabricated value; ground truth is ungrounded by construction.
- **Block rate on genuine answers: 23.5%** (12/51) -- not automatically labelled false-vs-true, see manual review below.
- Gate overhead: **468.1 µs/check** -- pure regex/set arithmetic, no model call; negligible next to LLM inference latency.

## Manual review of blocks on genuine (uncorrected) answers

Each row needs a human read of `text` against `ungrounded` to decide: a real catch (the model actually stated an invented number) or a false block (a real, grounded number the extractor/matcher missed -- e.g. an unusual phrasing).

| task | ungrounded values | answer text |
|---|---|---|
| att-s01 | [9.33] | Your overall attendance percentage is 82.67%. Here are the details for each subject:  - **23AI51**: 83.33% (No shortage) - **23AI52**: 66.67% (Shortage of 9.33%) - **23AI53**: 76.67% (No shortage) - * |
| att-s02 | [90.0] | Based on the information provided by the get_student_overview function call:  - Your overall attendance percentage is 82.67%. - You are not eligible for a hall ticket due to outstanding fees (₹1,03,34 |
| att-s03 | [100.0] | You have an attendance shortage in any subject as your overall attendance percentage is below 100%. Specifically, you currently have an overall attendance of 82.67%.  Additionally, due to overdue fees |
| att-s06 | [10.0] | The student's attendance status is as follows:  - In the subject 23AI51, they have attended 25 out of 30 classes (83.33%). - In the subject 23AI52, they have attended 20 out of 30 classes (66.67%, sho |
| fee-s05 | [1.0] | The fee defaulter list includes the following students with outstanding fees:  1. **USN: 4MT23AI049**    - Total Outstanding Amount: ₹103,340.55    - Tuition Fee (Overdue): ₹97,590.55    - Library Fin |
| plc-s03 | [1.0] | This month (August), the following companies are coming for placements:  1. **IBM**    - Role: Systems Engineer / Design Engineer    - Package per LPA: ₹12.00 / ₹5.00    - Date: August 18, 19, 24, 26, |
| ana-s02 | [2.0] | The department of AIML has a student headcount of 240. There are 94 shortage students this year.  In terms of attendance and CGPA: - The average class attendance is 84.4%. - The average CGPA across al |
| ana-s04 | [2.0] | The department report for AIML is as follows:  - Total number of students: 240 - Number of shortage students (students who are below the average attendance): 94  Average Attendance and CGPA: - Average |
| ana-s05 | [2.0, 9.0, 123158.5] | The department of AIML has a total student headcount of 240. There is a shortage of 94 students in the department.  Here are some additional details: - The average attendance across all years is 84.4% |
| att-h02 | [10.0, 33.33, 80.0] | The professor marked you absent in the following subjects due to insufficient attendance: - 23AI52: shortage of 10% (you attended 66.67%, missed 33.33%)    You have been present for more than 80% in a |
| ana-h01 | [183.075] | The health check of the AIML department reveals that there are currently 240 students enrolled in the department. However, there is a shortage of 94 students.  In terms of academic performance, the av |
| ana-h02 | [2056194.85] | The section with the most students struggling is Section 1 of Department AIML with a shortage count of 94 students. The average attendance for this department is 84.4%, and the average CGPA is 7.37. T |

## How to state this

*A dev-only engineering pass of the provenance gate mechanism catches 100% of synthetically injected ungrounded numeric claims at a 24% block rate on real (uncorrupted) answers.* This is not RQ2's confirmed result -- it validates the mechanism works at all, on synthetic ground truth, at one seed. A corpus of real annotated hallucinations and the 3-seed convention are both still pending (tracks with P5, blocked on external authors).
