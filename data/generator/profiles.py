"""Correlated student academic profiles, UCI-calibrated.

Carried forward unchanged in method from v3 (`docs/DATASET_METHODOLOGY.md`,
`ml/calibrate.py`, `ml/data/calibration.json`). Only the consumer changed.

The generator does **not** sample CGPA, attendance and backlogs
independently — that would destroy the real relationships (better-attending
students earn better grades; past failures predict lower grades). It draws
z ~ N(0, C) with C the correlation matrix estimated from n=1,044 real UCI
records, then applies each variable's calibrated marginal: Gaussian for CGPA
and attendance, quantile-mapping onto the empirical count distribution for
backlogs.

Family income is **not** in UCI and is a stated assumption (log-normal), as
`docs/DATASET_METHODOLOGY.md` §3 already discloses.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION = ROOT / "ml" / "data" / "calibration.json"

#: Used only if the calibration file is absent. Values are the ones
#: `ml/calibrate.py` estimated from the real dataset, so behaviour is
#: identical; the fallback exists so the generator never silently invents a
#: distribution when the file is missing.
_FALLBACK = {
    "source": "fallback copy of ml/data/calibration.json (UCI n=1044)",
    "cgpa_mean": 7.585, "cgpa_std": 0.874,
    "attendance_mean_pct": 95.23, "attendance_std_pct": 6.68,
    "backlog_probs": [0.8248, 0.1149, 0.0316, 0.0287, 0.0],
    "correlation_order": ["cgpa", "attendance_pct", "backlogs"],
    "correlation_matrix": [[1.0, 0.218, -0.3494],
                           [0.218, 1.0, -0.1514],
                           [-0.3494, -0.1514, 1.0]],
}


@dataclass(frozen=True)
class Profile:
    cgpa: float
    attendance_pct: float
    backlogs: int
    family_income: float


def load_calibration() -> dict:
    if CALIBRATION.exists():
        return json.loads(CALIBRATION.read_text(encoding="utf-8"))
    return dict(_FALLBACK)


class ProfileSampler:
    """Gaussian copula over (cgpa, attendance, backlogs) + income."""

    def __init__(self, rng: np.random.Generator, calibration: dict | None = None):
        self.rng = rng
        self.cal = calibration or load_calibration()
        C = np.array(self.cal["correlation_matrix"], dtype=float)
        # Nearest positive-definite nudge: an estimated correlation matrix
        # need not be PD, and Cholesky must not fail on real input.
        eig = np.linalg.eigvalsh(C)
        if eig.min() <= 1e-9:
            C = C + np.eye(len(C)) * (abs(eig.min()) + 1e-6)
            C = C / np.sqrt(np.outer(np.diag(C), np.diag(C)))
        self._L = np.linalg.cholesky(C)
        probs = np.array(self.cal["backlog_probs"], dtype=float)
        self._backlog_cdf = np.cumsum(probs / probs.sum())

    @staticmethod
    def _norm_cdf(x):
        from math import erf, sqrt
        if np.isscalar(x):
            return 0.5 * (1.0 + erf(x / sqrt(2.0)))
        return 0.5 * (1.0 + np.vectorize(erf)(x / sqrt(2.0)))

    def sample(self, n: int) -> list[Profile]:
        z = self.rng.standard_normal((n, 3)) @ self._L.T
        u = self._norm_cdf(z)

        cgpa = np.clip(
            self.cal["cgpa_mean"] + self.cal["cgpa_std"] * z[:, 0], 4.5, 9.9)
        # Attendance here is the *profile* marginal. Operational attendance
        # records are generated separately with a wider spread, exactly as
        # DATASET_METHODOLOGY.md §4 discloses: UCI absenteeism is low, and an
        # Indian 75% rule needs a heavier left tail to be exercised at all.
        att = np.clip(self.cal["attendance_mean_pct"]
                      + self.cal["attendance_std_pct"] * z[:, 1], 40.0, 100.0)
        backlogs = np.searchsorted(self._backlog_cdf, u[:, 2])

        income = np.clip(self.rng.lognormal(13.0, 0.6, size=n),
                         80_000, 2_500_000)

        return [Profile(cgpa=round(float(c), 2),
                        attendance_pct=round(float(a), 2),
                        backlogs=int(min(b, len(self._backlog_cdf) - 1)),
                        family_income=float(round(i, -3)))
                for c, a, b, i in zip(cgpa, att, backlogs, income)]
