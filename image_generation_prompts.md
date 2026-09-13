# MAWOS Review-1 — Image-Generation Prompts

Two required figures (Slides 4 and 5) and one optional figure (Slide 6, if you
want the math slide illustrated rather than left as typeset equations). Paste
each prompt as-is into your image generator. Generate at a wide aspect ratio
(16:9 or similar) so they drop cleanly into the slide's figure box.

---

## Figure 1 — System Architecture Block Diagram (Slide 4, required)

```
Clean academic system-architecture flowchart, top-to-bottom flow, white
background, minimal flat design, large legible sans-serif labels, no
decorative elements, no photorealistic imagery, no gradients — vector-style
boxes and arrows only, suitable for a college research presentation slide.

Layout, top to bottom:

1. Top row: five equal small boxes side by side, labeled "Student Portal",
   "Faculty Portal", "HOD Portal", "Principal Portal", "Admin Portal".

2. Below them, one arrow converging down into a single wide box labeled
   "FastAPI Gateway (JWT auth, role-guarded routes)".

3. Below that, one arrow down into a large box labeled "Orchestrator Agent".
   Inside this box, show two smaller sub-boxes side by side connected by a
   small diamond labeled "confidence gate (margin <= tau)":
     - left sub-box: "Keyword Lexicon (primary tier)"
     - right sub-box: "LLM Escalation Tier (Ollama + Qwen2.5, tool-calling)"

4. Below the Orchestrator box, one arrow down into a wide box labeled
   "Role-Filtered Tool Registry — 12 typed tools, permissions enforced in code".

5. Below that, arrows fan out to a row of 8 smaller boxes labeled:
   "Academic", "Admission", "Attendance*", "Finance", "Eligibility*",
   "Placement", "Scheduling*", "Notification"
   (the three boxes marked with an asterisk — Attendance*, Eligibility*,
   Scheduling* — should be visually distinguished with a slightly bolder
   border or a different fill shade than the other five, to indicate they
   are "core agents" versus "tool-backed components")

6. Below that row, all 8 boxes connect down into one horizontal band labeled
   "Instrumented Event Bus — publish/subscribe, workflow IDs, per-hop
   latency, fault isolation".

7. At the very bottom, one arrow down into a final box labeled
   "Shared Institutional Context Store (SQLite / PostgreSQL)".

Use a restricted palette: dark navy blue box borders, very light blue-gray
fills, black text. Keep all text horizontal and large enough to read at
slide size. No 3D effects, no icons, no mascots — this is a technical
architecture diagram for an academic audience.
```

---

## Figure 2 — Event-Driven Cascade Diagram (Slide 5, required)

```
Clean academic flowchart illustrating an event-driven propagation cascade,
left-to-right or top-to-bottom flow, white background, minimal flat design,
large legible sans-serif labels, vector-style boxes and arrows only, no
photorealistic imagery, suitable for a college research presentation slide.

Sequence of boxes connected by labeled arrows, in order:

1. Start box: "Attendance Upload (faculty marks a class)" — label the arrow
   leaving it "publishes: attendance.uploaded (hop 0)"

2. Second box: "Attendance Agent recomputes percentage, shortage flag,
   absence streak" — label the arrow leaving it "publishes: attendance.updated
   (hop 1)"

3. From the second box, THREE arrows branch out in parallel to three boxes
   side by side (show them as a clear fan-out, not sequential):
     - "Eligibility Agent -> re-evaluates hall-ticket + scholarship"
     - "Placement Agent -> refreshes shortlist"
     - "Notification -> shortage alert to student"
   Label all three branch arrows "hop 2" and show them happening
   simultaneously/automatically, with no human action between hop 1 and hop 2.

4. Below or beside the three parallel boxes, add one dashed horizontal bar
   spanning underneath all three, labeled "single workflow_id threads
   through every hop — logged with per-hop elapsed time for audit/replay".

Use a restricted palette: dark navy blue box borders, very light blue-gray
fills, one accent color (e.g. teal) for the "hop 2" fan-out arrows to
visually emphasize the parallel/automatic nature of the propagation. No 3D
effects, no icons, no mascots — this is a technical event-flow diagram for
an academic audience.
```

---

## Figure 3 — Mathematical Model Illustration (Slide 6, optional)

Only generate this if you want Slide 6 to carry a supporting visual next to
the typeset equations already on the slide — the slide works fine as
equations alone.

```
Clean academic diagram split into two side-by-side panels on a white
background, minimal flat design, large legible sans-serif labels, no
photorealistic imagery, suitable for a college research presentation slide.

LEFT PANEL, titled "Confidence-Gated Routing":
Show a small flowchart: a box "Query" with an arrow into a box "Lexicon
scores every intent", with an arrow into a small formula label
"margin = score(top1) - score(top2)", with an arrow into a diamond decision
shape labeled "margin <= tau?" (tau = 0), which splits into two arrows:
one labeled "no" going to a box "Lexicon answers directly", and one labeled
"yes" going to a box "Escalate to local LLM".

RIGHT PANEL, titled "Simulated Annealing Scheduler":
Show a simple 2D line chart with x-axis "iteration" and y-axis "temperature
T", plotting a smooth downward-curving exponential/geometric decay line from
a labeled point "T_start" at the top-left to a labeled point "T_end" near
the bottom-right. Next to the curve, add a small text label:
"accept if delta-cost <= 0, else with probability exp(-delta-cost / T)".
Optionally show two tiny simplified timetable-grid icons near the start and
end of the curve — the first grid sparse/gappy, the second grid compact —
to suggest the schedule becoming more compact as temperature cools.

Use a restricted palette: dark navy blue lines/borders, very light
blue-gray fills, one accent color (e.g. teal) for the decay curve. No 3D
effects, no photorealistic elements — this is a technical/mathematical
diagram for an academic audience.
```

---

## Notes

- These prompts describe the **actual, current MAWOS architecture** as
  implemented in `backend/app/` — component names, the 12-tool registry,
  the 4 core agents (Orchestrator, Attendance, Eligibility, Scheduling),
  the event bus, and the confidence-gate/annealing formulas match the real
  code (`router.py`, `scheduler.py`, `bus.py`, `agents/tools.py`,
  `agents/__init__.py`) as of 2026-08-21.
- Do not substitute the old 10-agent framing or the old "LLM primary /
  lexicon fallback" framing if you see either in older project docs —
  `docs/ARCHITECTURE.md` is intentionally still v2-era pending a later
  rewrite (P8); the routing/agent-count facts above are the current,
  v3 state and are what these prompts (and the slides) use.
