# v6 — product aim: VidyaERP is the base

**Date:** 2026-09-14 · **revised the same day, before execution**
**Status:** proposed scope, nothing built on it yet

---

## 0. What this revision changes, and why

The first draft of this document proposed keeping **MAWOS** as the base and adopting Chronos as
the shell. Then `VidyaERP/erp/` appeared — 4,282 lines of Python, built in about an hour — and
it is better than MAWOS at almost everything MAWOS was trying to be.

**That draft is withdrawn. VidyaERP is the base.** Keeping MAWOS as the foundation because more
time went into it is the sunk-cost mistake, and this document existing at all is a reason to
catch it now rather than after another month.

### Why MAWOS took two months and lost

Worth stating once, plainly, because the mechanism is what matters — not the comparison.

MAWOS spent two months producing **governance, not product**: a research protocol, pre-registered
thresholds, frozen instruments, a 14-item decision register in which features could not be built
until a measurement justified them, and an explicit "do not build" list. Each of those was real
work. None of it was a feature. Two things the owner asked for repeatedly — rooms, and a
backtracking solver — were *forbidden by name* (R2 deferred; **D2: "do not build"**).

VidyaERP had one clear product brief and no constraints, so an hour of work went entirely into
features. Same tooling, opposite instructions.

This is not a defence of the two months, and the first draft of this spec made the same error at
a smaller scale — it still treated MAWOS as the foundation and still preserved the research
corpus as a live concern. The correction is to rank the three codebases on **what they do**, not
on what they cost.

---

## 1. VidyaERP, verified

Checked in the source, not taken from its README.

| Claim | Verified at | Verdict |
|---|---|---|
| Three coverage strategies generated per absence | `agents.py:227` (A), `:300` (B), `:318` (C) | **Real** |
| Re-ranked by a weighted score | `agents.py:326` — `confidence*0.6 + coverage*0.25 + continuity*0.15` | **Real** |
| PolicyGuard is outside the model | `agents.py:84`, `WRITE_INTENTS` → HITL | **Real** |
| A write with no in-turn approval is blocked | `tools.py:347` returns `{"BLOCKED": …}` before touching the DB | **Real** |
| Coverage percentages are computed | `cov_a/cov_b/cov_c` from actual covered-leg ratios | **Real** |
| Plan A confidence is computed | `min(96, mean(candidate scores × 1.05))` | **Real** |

**One honest caveat, and it is the obvious next improvement, not a takedown.** Not every number
in the ranking is computed:

- `continuity` is a **constant per strategy** (74 / 92 / 88). Defensible — continuity genuinely
  is a property of the strategy rather than of the instance — but it should be said out loud.
- Plan B and C confidence are **formulaic**: `71 + min(20, swaps*6)` and a flat `66`.

So the ranking is driven by one genuinely measured axis (A's confidence, everyone's coverage)
and two partly-assumed ones. That is fine for a demo and will be the first question an examiner
asks. §5 fixes it.

### What VidyaERP has that MAWOS never built

Substitution/Timetable/Faculty/Student/Finance/Exam/Request agents with a supervisor · entity
resolver with fuzzy faculty matching and Indian date parsing · 20 tools · a **tool router** that
narrows 20 → 4–8 per utterance (−64% payload) · **model failover chain** across providers on 429
· rule engine and LLM engine behind *identical* guardrails · multi-turn pending state with
context switching · disambiguation with match % · undo by reference id · immutable audit ledger ·
delegation ceilings in rupees · notifications to sections, substitutes and HOD.

### The one thing MAWOS has that VidyaERP does not

**An MCP server.** `grep -rn "mcp" VidyaERP/erp/*.py` returns nothing. MAWOS's
`mcp_server.py` puts the same guarded tools in front of Claude Desktop and ChatGPT, and it is
parity-tested. Both apps are Python + FastAPI + an OpenAI-compatible provider, so this ports
close to directly.

---

## 2. The decision

> **One application: VidyaERP.** Two things get ported into it. Everything else becomes
> reference material.

| Codebase | Role from here |
|---|---|
| **VidyaERP** | **The product.** All new work lands here |
| **MAWOS** | Donates `mcp_server.py`. `evaluation/` stays as report material. Otherwise archived |
| **Chronos** | Donates the **timetable generation** algorithm, which VidyaERP lacks. Otherwise reference |

Rejected: keeping three codebases; running Chronos as a Next.js sidecar (a second stack and a
second deployment for one feature); keeping MAWOS as the base (sunk cost).

---

## 3. Port one — timetable generation from scratch

The owner's own assessment: *"just timetable generation from scratch is not there in it, rest all
it feels like best smart erp."* That is the single functional gap.

Chronos's `src/lib/solver/engine.ts` is 755 lines of MRV backtracking + bounded min-conflicts
repair + hill-climb polish, documented in `SOLVER_GUIDE.md`, and it models **rooms** as a real
decision dimension along with `teachers.unavailable` and `assignments.locked`. Port it to Python
inside VidyaERP — roughly 400–600 lines against a documented algorithm — rather than running a
second stack for it.

Keep from the port:
- Rooms as a decision variable, with type and capacity
- Configurable days / periods / break slots (MAWOS hardcoded `5 × 6` with 6-bit masks)
- Assignment pinning, so a generation run can be constrained by what must not move
- The **generator structure** (`yield` per decision) so the same solver streams its search to
  the console for a live animated trace, or drains synchronously for a seeder

MAWOS's simulated-annealing scheduler places 720/720 slots with 0 conflicts in 1.3 s, so it is a
legitimate second option — but it has no rooms and a hardcoded grid, which is exactly what needs
fixing. Take Chronos's structure; borrow the annealing polish only if the hill-climb underperforms.

---

## 4. Port two — MCP

Expose VidyaERP's existing tools over MCP so an admin can drive the ERP from Claude Desktop or
ChatGPT. The rule that makes it worth doing: **the MCP surface must be a thin delegation to the
same tool functions behind the same PolicyGuard** — no second authorisation path, no tool that
exists only over MCP. MAWOS's parity suite replays the same adversarial items through both
entry points and asserts identical verdicts; port that test alongside the server.

This is the demo line that nothing else in the project can claim: *the same guard holds even
when an external LLM we do not control is driving.*

---

## 5. Make the coverage ranking defensible

Per §1's caveat. Small, high-value, and it is what turns a good demo into a good viva answer.

- **Compute continuity** instead of asserting it: syllabus hours preserved, whether the batch's
  own teacher still delivers the session, how far a make-up slips from the original date.
- **Compute B and C confidence** from the same candidate scores A uses — swap quality for B,
  make-up proximity and room availability for C.
- **Show the weights in the UI.** `0.6 / 0.25 / 0.15` is a policy choice; surfacing it invites
  the right question instead of hiding it.
- **Report a plan as uncovered when it is.** `cov_*` already measures this; make an incomplete
  plan visibly incomplete rather than letting rank order imply it is fine.

---

## 6. Phases

**A — Consolidate.** VidyaERP into the repository properly (it is currently untracked, as
Chronos was — that is what made Chronos invisible for two months). One README stating which
codebase is live. MAWOS and Chronos marked reference. Deploy VidyaERP: Render or equivalent,
`/health`, Groq key from the environment, never git.

**B — Timetable generation.** §3. Generation endpoint, rooms in the schema, streaming trace, the
animated grid in the existing console.

**C — MCP.** §4, including the parity test.

**D — Depth.** §5's ranking work, then richer data: real room inventory, non-uniform teacher
availability, an academic calendar, correlated attendance instead of `rng.random() < 0.82`,
multi-period lab blocks.

**Not building:** a second ERP shell; a rewrite of anything that already works in VidyaERP; any
new research instrument.

---

## 7. What happens to the research

`evaluation/` stays exactly where it is, in the MAWOS tree, as **report material**. The probe,
the gates, PROTOCOL, the decision register and the archived runs are all still valid evidence of
what was measured. They stop having any authority over product work.

If a paper is wanted later, the honest subject is no longer "bounded LLM autonomy over an
institutional system" in the abstract — it is the thing now actually built and testable:
**a deterministic authorisation layer that holds identically whether the caller is the app's own
planner or an external LLM over MCP.** That is a real claim with a real experiment, and §4
produces it as a side effect of shipping.

---

## 8. Success criterion

> An admin opens VidyaERP, says *"Prof. Sneha Mallya is absent next Monday, arrange coverage"*,
> gets three ranked plans with **computed** confidence, coverage and continuity, says
> *"apply plan B"*, sees the timetable update with overridden cells marked and notifications
> dispatched — and can then reach the same guarded tools from Claude Desktop over MCP and get
> the identical PolicyGuard verdict.

Steps one through four already work today. §3, §4 and §5 are what remain.
