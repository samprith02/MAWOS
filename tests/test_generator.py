"""R1 gates for the institution generator (docs/v4/09_ROADMAP.md R1).

These are the executable form of the phase gate, not incidental unit tests:
gate 2 (byte-reproducible), gate 4 (no real identity) and gate 5 (feasible by
construction) each have an assertion here.
"""
import datetime as dt

import pytest

from data.generator import names as N
from data.generator.build import Infeasible, assert_feasible, build
from data.generator.config import load

#: Pinned so the digest is stable across day boundaries — the generator
#: anchors attendance and fee dates to a reference date that defaults to
#: today (see build.build's docstring).
PINNED = dt.date(2026, 9, 1)


@pytest.fixture(scope="module")
def inst():
    return load()


@pytest.fixture(scope="module")
def generated(inst):
    return build(inst, reference_date=PINNED)


# ------------------------------------------------------------- R1 gate 2
def test_generator_is_byte_reproducible(inst):
    a = build(inst, reference_date=PINNED)
    b = build(inst, reference_date=PINNED)
    assert a.digest() == b.digest()
    assert a.counts() == b.counts()


def test_seed_actually_changes_the_institution(inst):
    a = build(inst, seed=1, reference_date=PINNED)
    b = build(inst, seed=2, reference_date=PINNED)
    assert a.digest() != b.digest(), "seed has no effect — not really seeded"


# ------------------------------------------------------------- R1 gate 4
def test_no_real_institution_identity_anywhere(generated, inst):
    """The v3 identity must not survive anywhere in generated data."""
    banned = ("4mt", "mite.ac.in", "mangalore institute")
    blobs = []
    blobs += [s["usn"].lower() + " " + (s["email"] or "").lower()
              for s in generated.students]
    blobs += [f["email"].lower() + " " + f["name"].lower()
              for f in generated.faculty]
    haystack = " ".join(blobs)
    for token in banned:
        assert token not in haystack, f"v3 identity {token!r} leaked into data"
    assert generated.students[0]["usn"].startswith(inst.usn_prefix)


def test_config_rejects_reintroducing_the_v3_identity():
    """The loader is the enforcement point, not a convention."""
    from data.generator.config import _validate
    raw = {"institution": {"usn_prefix": "4MT", "email_domain": "x.edu",
                           "name": "Test"},
           "calendar": {"days": [1] * 5, "periods": [1] * 6}}
    with pytest.raises(ValueError, match="v3 identity"):
        _validate(raw)


def test_config_rejects_a_grid_the_frozen_solver_cannot_represent():
    from data.generator.config import _validate
    raw = {"institution": {"usn_prefix": "1VT", "email_domain": "x.edu",
                           "name": "Test"},
           "calendar": {"days": [1] * 6, "periods": [1] * 8}}
    with pytest.raises(ValueError, match="5 days x 6 periods"):
        _validate(raw)


# ------------------------------------------------------------- R1 gate 5
def test_generated_instance_is_feasible_by_construction(generated, inst):
    report = assert_feasible(inst, generated)
    assert report["max_section_load"] <= report["cells_per_week"]
    assert report["max_teacher_utilisation"] <= 1.0
    assert report["classrooms"] >= report["concurrent_sections"]


def test_feasibility_check_actually_rejects_an_impossible_instance(inst, generated):
    """A guard that never fires is not a guard."""
    import copy
    bad = copy.copy(generated)
    bad.availability = list(generated.availability)
    fid = generated.teaching[0]["faculty_id"]
    # Block every cell in the week for a teacher who has classes to teach.
    bad.availability += [{"faculty_id": fid, "day": d, "period": p,
                          "reason": "test", "source": "test",
                          "valid_from": None, "valid_until": None}
                         for d in range(inst.n_days)
                         for p in range(inst.n_periods)]
    with pytest.raises(Infeasible):
        assert_feasible(inst, bad)


# --------------------------------------------------------------- structure
def test_every_new_entity_is_populated(generated):
    c = generated.counts()
    for key in ("rooms", "availability", "requests"):
        assert c[key] > 0, f"{key} generated nothing"


def test_lab_subjects_carry_a_block_size(generated):
    labs = [s for s in generated.subjects if s["kind"] == "lab"]
    assert labs, "no lab subjects generated"
    assert all(s["block_size"] >= 2 for s in labs)
    theory = [s for s in generated.subjects if s["kind"] == "theory"]
    assert all(s["block_size"] == 1 for s in theory)


def test_faculty_qualifications_cover_what_they_teach(generated):
    qual = {f["id"]: set(filter(None, f["qualified_subjects"].split(",")))
            for f in generated.faculty}
    for t in generated.teaching:
        assert t["subject_code"] in qual[t["faculty_id"]]


def test_unavailability_never_over_blocks_a_teacher(generated, inst):
    """A member is never blocked below the cells their own load needs."""
    credits = {s["code"]: s["credits"] for s in generated.subjects}
    load, blocked = {}, {}
    for t in generated.teaching:
        load[t["faculty_id"]] = load.get(t["faculty_id"], 0) \
            + credits[t["subject_code"]]
    for a in generated.availability:
        blocked[a["faculty_id"]] = blocked.get(a["faculty_id"], 0) + 1
    cells = inst.n_days * inst.n_periods
    for fid, l in load.items():
        assert l <= cells - blocked.get(fid, 0)


def test_name_pools_contain_no_v3_team_members(generated):
    """v3 seeded four real teammates at their real USNs. They are gone."""
    real = {"nikil s suvarna", "pranit r raj", "samprith c amin"}
    names = {s["name"].lower() for s in generated.students}
    names |= {f["name"].lower() for f in generated.faculty}
    assert not (names & real)
    assert not (set(N.FIRST) & {"Samprith", "Nikil", "Pranit", "Prathik"})
