# Scalability Sweep

**Constant workload** — every row uploads the same 60 students x 5 subjects = 300 attendance records; only the size of the surrounding institution changes. Fresh database and fresh process per configuration.

| Students | Attendance rows in DB | Cascade (ms) | Wall incl. upload (ms) | Process RSS (MB) | DB size (MB) | Seed time (s) |
|---|---|---|---|---|---|---|
| 1,200 | ~180,000 | 808.0 | 1121.0 | 202.6 | 26.4 | 4.0 |
| 2,400 | ~360,000 | 807.9 | 1056.0 | 203.1 | 52.5 | 6.9 |
| 3,600 | ~540,000 | 537.1 | 865.6 | 202.9 | 78.6 | 10.0 |
| 4,800 | ~720,000 | 582.0 | 886.3 | 203.3 | 104.9 | 14.9 |

Institution grew 4.0x (1,200 -> 4,800 students); cascade latency for identical work changed 0.72x and process memory stayed flat.

Interpretation: cascade cost tracks the *number of students actually affected by an upload*, not institution size — each agent recomputes only the touched cohort. Residual latency growth is the database component (the same indexed queries over larger tables), not agent or bus overhead.
