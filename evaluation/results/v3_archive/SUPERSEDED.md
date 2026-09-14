# v3 results — SUPERSEDED, not corrected

Archived at v4 R1 on **2026-09-01**. Everything under this directory was
produced by the v3 research programme and is **accurate for the instrument
that produced it**. None of it is retracted, and none of it is wrong.

## The rule

> **No v4 number may be differenced against a v3 number.**

This is `evaluation/PROTOCOL.md` §10.1 applied to the v3→v4 boundary, and it
is the same rule v3 itself applied to the v2→v3 boundary. Superseded means
*measured under conditions that no longer obtain*, not *mistaken*.

## Why these are superseded

| Change at v4 | What it invalidates |
|---|---|
| The benchmark is being replaced (`docs/v4/06_BENCHMARK.md`) — gold **outcomes**, multi-turn, six categories, write-bearing tasks — instead of 99 single-turn `query → 1 gold tool` items | Every routing / tool-selection number here. The two instruments do not measure the same quantity |
| The primary model is not chosen (`OPEN_DECISIONS.md` D1 is OPEN after R0.5 found no eligible provider) | τ = 0 was selected *for* `qwen2.5:3b-instruct`. Any change of model invalidates the threshold that was tuned to it |
| The architecture adds planning, conversation memory, delegation, a guard layer and confirmation-gated writes | The v3 orchestrator measured here is a single-turn tool-calling loop over 12 read-only getters. Different system |
| The timetable gains rooms and generalised unavailability (`05_TIMETABLE_SCOPE.md`) | Scheduler numbers here were measured on a 2-hard-constraint model with no room dimension |

## What is here, and what it remains valid for

| Directory | Contents | Still citable as |
|---|---|---|
| `v3_gates/` | P0.5 router viability, P3 provenance gate, P4 τ selection, P6 model sweep | Findings about **the 99-task/12-tool instrument** with `qwen2.5:3b-instruct`. Always name the instrument when citing |
| `v3_llm/` | Frozen-protocol captures, 1.5B / 3B / 7B × 3 seeds, 297 records each | The model sweep behind the §9.2 selection. `CONDITIONS.md` inside states the equivalence caveats |
| `v3_scheduler/` | E4 — P1 solver vs the frozen v2 greedy baseline, 10 seeds | The scheduler before/after. **This one carries forward**: v4 R2's regression gate compares against exactly these numbers, because the frozen objective is unchanged |

## Results that specifically must not be re-used as headlines

- **The routing comparison.** Three runs exist (v2 single-run −19.4 pts; pre-P2 108-task
  −12.9; post-P2 99-task −5.4). They were already mutually non-differenceable before v4
  existed. The direction was consistent every time — **the LLM tier lost the tool-selection
  comparison to a keyword lexicon** — and that finding stands and is worth stating.
- **τ = 0 and the +5.7-point hybrid gain** (95% CI [+0.3, +11.8], McNemar p = 0.070). Selected
  on dev, which was contaminated by construction, and never confirmed on a held-out set. v3's
  own documents say so; v4 does not inherit the claim.
- **P3's 100% catch rate.** Synthetic corruption of single-tool answers. v4 R0.5 additionally
  found a reproducible false positive in the gate itself (`OPEN_DECISIONS.md` D10), so the
  companion 23.5% false-block figure does not transfer either.

## Where v4's own results live

`evaluation/results/v4_gates/` — beginning with R0.5, dated 2026-08-31.

## Provenance

The v3 programme's own plan, protocol and rationale remain in place and unedited:
`docs/RESEARCH_PLAN_V3.md`, `evaluation/PROTOCOL.md` (still binding for v4),
and the phase table in `CLAUDE.md` marked historical.
