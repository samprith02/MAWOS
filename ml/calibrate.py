"""Statistical calibration of MAWOS synthetic data against a real public dataset.

Source: UCI Student Performance Data Set (Cortez & Silva, 2008) —
ml/data/external/student/student-mat.csv + student-por.csv (1,044 records
from two Portuguese secondary schools; the standard public benchmark for
student academic data).

What we estimate from the real data (and how it maps to MAWOS):
  * G3 final grade (0-20)  -> linearly mapped to CGPA scale (4.0-10.0):
      cgpa = 4 + 6 * G3/20. We take the empirical mean/std after mapping.
  * absences (days)        -> attendance% = 100 * (1 - absences/course_days),
      course_days=93 (max observed; one academic year of course sessions).
      Empirical mean/std of the resulting percentage.
  * failures (0-3+)        -> empirical distribution reused as the
      backlog-count distribution.

Family income is NOT available in UCI; we keep a log-normal assumption
(documented in generate_datasets.py) since Indian household income is
conventionally modelled as log-normal.

Output: ml/data/calibration.json — consumed by generate_datasets.py.
Run:    python ml/calibrate.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
EXTERNAL = DATA_DIR / "external" / "student"
COURSE_DAYS = 93.0  # max absences observed in the dataset


def main():
    frames = []
    for name in ("student-mat.csv", "student-por.csv"):
        path = EXTERNAL / name
        if path.exists():
            frames.append(pd.read_csv(path, sep=";"))
    if not frames:
        raise SystemExit(
            "UCI files not found under ml/data/external/student/ — "
            "download https://archive.ics.uci.edu/static/public/320/student+performance.zip")
    df = pd.concat(frames, ignore_index=True)

    # G3 (0-20) -> CGPA (4-10). Drop G3=0 rows (dropouts coded as zero, not a grade).
    g3 = df.loc[df["G3"] > 0, "G3"].astype(float)
    cgpa = 4.0 + 6.0 * g3 / 20.0

    attendance_pct = 100.0 * (1.0 - df["absences"].clip(0, COURSE_DAYS) / COURSE_DAYS)

    failures = df["failures"].clip(0, 4).astype(int)
    backlog_counts = failures.value_counts(normalize=True).sort_index()
    backlog_probs = [round(float(backlog_counts.get(k, 0.0)), 4) for k in range(5)]
    # renormalise rounding drift
    s = sum(backlog_probs)
    backlog_probs = [p / s for p in backlog_probs]

    # Correlation structure between the three shared variables, estimated on
    # rows where all three are defined. Preserved in generation via a
    # Gaussian copula so synthetic data keeps the real relationships
    # (e.g. more past failures <-> lower grades) instead of sampling
    # each feature independently.
    mask = df["G3"] > 0
    joint = np.vstack([
        4.0 + 6.0 * df.loc[mask, "G3"].astype(float) / 20.0,
        100.0 * (1.0 - df.loc[mask, "absences"].clip(0, COURSE_DAYS) / COURSE_DAYS),
        df.loc[mask, "failures"].clip(0, 4).astype(float),
    ])
    corr = np.corrcoef(joint)

    calibration = {
        "source": "UCI Student Performance (Cortez & Silva 2008), n=%d" % len(df),
        "cgpa_mean": round(float(cgpa.mean()), 3),
        "cgpa_std": round(float(cgpa.std()), 3),
        "attendance_mean_pct": round(float(attendance_pct.mean()), 2),
        "attendance_std_pct": round(float(attendance_pct.std()), 2),
        "backlog_probs": [round(p, 4) for p in backlog_probs],
        "correlation_order": ["cgpa", "attendance_pct", "backlogs"],
        "correlation_matrix": [[round(float(v), 4) for v in row] for row in corr],
    }
    out = DATA_DIR / "calibration.json"
    out.write_text(json.dumps(calibration, indent=2))
    print(json.dumps(calibration, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
