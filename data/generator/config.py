"""Institution configuration loader.

`data/institution.yaml` is the single place an institution's identity
exists. Nothing under `backend/`, `frontend/` or `data/` may hardcode a
name, USN prefix, email domain or crest — the R1 gate greps for the v3
identity and must return zero hits (`docs/v4/04_DATA_MODEL.md` §3).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "institution.yaml"


@dataclass(frozen=True)
class Institution:
    raw: dict

    # ---- identity -------------------------------------------------------
    @property
    def name(self) -> str:
        return self.raw["institution"]["name"]

    @property
    def short_name(self) -> str:
        return self.raw["institution"]["short_name"]

    @property
    def usn_prefix(self) -> str:
        return self.raw["institution"]["usn_prefix"]

    @property
    def email_domain(self) -> str:
        return self.raw["institution"]["email_domain"]

    @property
    def name_is_placeholder(self) -> bool:
        return bool(self.raw["institution"].get("name_is_placeholder"))

    # ---- calendar -------------------------------------------------------
    @property
    def days(self) -> list[str]:
        return list(self.raw["calendar"]["days"])

    @property
    def periods(self) -> list[dict]:
        return list(self.raw["calendar"]["periods"])

    @property
    def period_labels(self) -> list[str]:
        return [p["label"] for p in self.periods]

    @property
    def n_days(self) -> int:
        return len(self.days)

    @property
    def n_periods(self) -> int:
        return len(self.periods)

    # ---- structure ------------------------------------------------------
    @property
    def departments(self) -> list[dict]:
        return list(self.raw["departments"])

    @property
    def rooms(self) -> dict:
        return dict(self.raw["rooms"])

    @property
    def gen(self) -> dict:
        return dict(self.raw["generation"])

    @property
    def policies(self) -> dict:
        return dict(self.raw["policies"])

    # ---- derived --------------------------------------------------------
    @property
    def sections(self) -> list[str]:
        return list(self.gen["sections_per_year"])

    @property
    def years(self) -> list[int]:
        return list(self.gen["years"])

    @property
    def year_to_semester(self) -> dict:
        return {int(k): int(v) for k, v in self.gen["year_to_semester"].items()}

    @property
    def n_sections_total(self) -> int:
        return len(self.departments) * len(self.years) * len(self.sections)


def _validate(raw: dict) -> None:
    """Fail loudly on the two mistakes that would defeat the point of this
    file: reintroducing the v3 identity, or a grid the frozen solver cannot
    represent."""
    inst = raw["institution"]
    banned = {"4mt": "usn_prefix", "mite.ac.in": "email_domain"}
    blob = f"{inst.get('usn_prefix','')} {inst.get('email_domain','')} " \
           f"{inst.get('name','')}".lower()
    for token, where in banned.items():
        if token in blob:
            raise ValueError(
                f"institution.yaml reintroduces the v3 identity ({token!r} "
                f"in/near {where}). See docs/v4/04_DATA_MODEL.md §3.")

    n_days = len(raw["calendar"]["days"])
    n_periods = len(raw["calendar"]["periods"])
    # backend/app/scheduler.py is frozen at a 5x6 grid with 6-bit masks.
    if (n_days, n_periods) != (5, 6):
        raise ValueError(
            f"calendar is {n_days}x{n_periods}; backend/app/scheduler.py is "
            f"built on 5 days x 6 periods (6-bit occupancy masks). Changing "
            f"the grid is a solver change, not a config change.")


@lru_cache(maxsize=4)
def load(path: str | os.PathLike | None = None) -> Institution:
    p = Path(path or os.getenv("MAWOS_INSTITUTION_CONFIG") or DEFAULT_PATH)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    _validate(raw)
    return Institution(raw=raw)
