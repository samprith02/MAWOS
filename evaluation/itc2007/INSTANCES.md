# ITC-2007 track 3 instances — what is missing, and why

E4b needs the `comp01.ctt … comp21.ctt` curriculum-based instances. They
are **not in this repository and were not obtainable automatically.** The
cost model, the solver and the official validator are all in place and
verified; this is the only thing standing between them and a number.

## What is already verified without them

| Piece | State |
|---|---|
| Official validator (`validator.cc` v1.1) | fetched over valid TLS from the competition site, sha256 recorded in `build.py`, compiles and runs |
| `ctt.py` cost model | agrees with the official validator on **1,900 random instance/solution pairs across two seeds**, on all eight components separately — not just the total |
| Published toy example | our model reproduces the officially stated `Violations = 5, Total Cost = 30` |
| `solver.py` | solves the toy instance to 0 violations / 0 cost from three seeds; the official validator confirms it with no warnings |
| Incremental cost | equals a full rescore after random move sequences (60 instances × 120 moves) |

## Why the download failed

**Queen's University Belfast** (`eeecs.qub.ac.uk/itc2007/`) — the
competition's own site — serves the problem model, the input/output
formats and `validator.cc` over a valid certificate, and all of those were
fetched successfully. The instances themselves sit behind
`Login/Login.php`: *"You can download the first 'Early' seven instances
[here]"* links to a login page. There is no anonymous download.

**University of Udine** (`tabu.diegm.uniud.it/ctt/`) — the maintained
CB-CTT repository, which also publishes the best-known results — fails TLS
verification:

```
SEC_E_WRONG_PRINCIPAL — the target principal name is incorrect
subject=CN=auth-opthub.uniud.it
issuer=C=GR, O=Hellenic Academic and Research Institutions CA, CN=GEANT TLS RSA 1
notBefore=Feb 21 2026   notAfter=Feb 21 2027
```

That is a **hostname mismatch on a currently valid certificate belonging
to the same institution**, issued by a real academic CA — a misconfigured
virtual host, not evidence of interception. It would almost certainly be
fine. But "almost certainly" is a judgement about someone else's machine
and someone else's benchmark provenance, so the download was not forced
with `--insecure`. That is a decision for the team, not for a script.

## How to supply them

Any one of these; then run `python evaluation/itc2007/run_e4b.py`.

1. **Log in at QUB** and download the instance set, or
2. **Fetch from Udine** in a browser (browsers show the same warning and
   let a human accept it), or
3. **Use a copy the department already has** from earlier coursework.

Drop the `.ctt` files into `evaluation/itc2007/instances/`. `run_e4b.py`
hashes every file it reads and records the hashes in its output, so
whichever route is used, the exact instance bytes behind a reported
penalty are recoverable afterwards.

## Published bests

`run_e4b.py` will compare against best-known results **only if**
`instances/BESTS.json` exists, mapping instance name to the published
figure and citing where it came from:

```json
{"comp01": {"best": 5, "source": "tabu.diegm.uniud.it/ctt/, retrieved YYYY-MM-DD"}}
```

Without that file the harness reports our own penalties and says the
comparison is pending. It does **not** carry a hardcoded table of
published bests: a number nobody in this project can regenerate or point
at a source for is exactly what CLAUDE.md forbids, and a wrong reference
value would make our result look better or worse than it is.
