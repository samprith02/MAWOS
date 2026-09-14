# VidyaERP — Multi-Agent College ERP (Admin Console)

A working prototype of a **SMART, agentic ERP for an Indian engineering college** (autonomous /
VTU-affiliated model). The differentiator is not the CRUD — it is the **agent mesh** sitting on top
of the institutional database that an administrator can *talk to* and *delegate work to*.

Live app: `python3 -m uvicorn app:app --host 0.0.0.0 --port 8000` → open the preview.

---

## 1. The idea in one line

> The admin doesn't navigate the ERP. The admin states a problem, and a supervisor agent
> decomposes it, queries the right specialists, and comes back with **ranked, executable plans**
> that commit only on human approval.

---

## 2. Two engines, one interface

| | Rule engine (default) | **LLM agent** (add a key) |
|---|---|---|
| Routing | keyword scoring + regex priority rules | the model plans and chooses tools |
| Answers | templated narrative | genuine prose, interprets the numbers |
| Multi-step | hard-coded flows | chains tools freely, up to 6 reasoning hops |
| Cost / latency | 0 ms, free | one API round-trip per hop |
| Guardrails | PolicyGuard + HITL | **identical** — enforced in code, outside the model |

The UI badge in the top bar shows which engine is live; click it to ping the endpoint.
Everything degrades gracefully: if the LLM is unreachable mid-turn, the rule engine answers
and says so.

### Enabling the LLM agent

```bash
cp .env.example .env      # already done
# edit .env:
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.groq.com/openai/v1     # any OpenAI-compatible endpoint
LLM_MODEL=llama-3.3-70b-versatile
```

Presets for OpenAI, Groq, OpenRouter, Together, DeepSeek, Gemini-compat and local Ollama are
listed in `.env.example`. No SDK is installed — `llm.py` talks raw HTTP over `urllib`, so there
is nothing to `pip install`. Restart the server and the badge flips to green.

**The 20 tools the model can call:** `institution_overview · get_timetable · faculty_timetable ·
find_free_faculty · find_free_rooms · faculty_profile · faculty_workload · student_lookup ·
attendance_defaulters · fee_summary · exam_schedule · exam_eligibility · list_requests ·
list_leaves · plan_absence_coverage · apply_coverage_plan · undo_last_change · decide_request ·
create_request · broadcast_notice`

**Write-guard, proven by test:** `tests/mock_llm.py` includes a *rogue agent* endpoint that tries
to call `apply_coverage_plan` with no admin approval. PolicyGuard returns `{"BLOCKED": ...}`,
the database is untouched, and the model is told why. The same call succeeds the moment the
admin's message contains an approval. The model cannot talk its way past this — the check is in
`tools.py`, not in the prompt.

---

### Running against a metered API (why it stays up)

Free tiers are stingy — Groq allows **8,000 tokens/minute per model**, and an early
multi-hop turn was spending 7,196 of them. Four things fixed that:

| Technique | Effect |
|---|---|
| **Tool router** — the rule-engine NLU pre-selects ~4–8 of the 20 tools per utterance | tool payload **−64%**, and the model picks better from a short menu |
| **Prompt diet** — live-context preamble trimmed, history 8→4 turns, tool results capped at 2.8 KB | system prompt ~1,500 → ~600 tokens |
| **Model failover chain** — `LLM_FALLBACK_MODELS`, tried in order on 429/5xx/`tool_use_failed` | quotas are *per model*, so the chain multiplies usable throughput |
| **Nullable optional params** — every non-required arg accepts `null` | models emit `{"dept": null}` constantly; strict validators 400 on it. 41 params were latent landmines |

Result: a typical turn now costs **~2,000 tokens and answers in ~1.2 s**, and the
console survives a rate limit twice over — first by hopping to another model, and only
if the whole chain is exhausted by falling back to the rule engine with an honest notice.
The trace shows exactly which of these happened:

```
· ToolRouter    narrow_toolset    7 of 20 tools offered: plan_absence_coverage, …
· LLM Planner   reason (hop 1)    openai/gpt-oss-120b · 1032→107 tok · 513ms
· LLM Planner   model_failover    primary rate-limited → answered on qwen/qwen3.8-27b
```

### Tests

```bash
python3 tests/smoke.py      # deterministic rule-engine regression (no API cost)
python3 tests/live_llm.py   # 6 real-model queries: engine, latency, tokens, table leaks
```

## 3. Agent architecture

```
                          ┌──────────────────────────────┐
   admin utterance  ─────▶│   SUPERVISOR / ROUTER        │
                          │  intent scoring + priority   │
                          │  regex rules, 99% ceiling    │
                          └──────────┬───────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
      ┌──────────────┐      ┌─────────────────┐     ┌──────────────┐
      │ POLICY GUARD │      │ ENTITY RESOLVER │     │  RETRIEVER   │
      │ RBAC · scope │      │ fuzzy faculty,  │     │  SQL over    │
      │ HITL gating  │      │ dept/sem/sec,   │     │  live ERP    │
      │ ₹ ceilings   │      │ Indian dates    │     │  tables      │
      └──────────────┘      └─────────────────┘     └──────────────┘
                                     │
   ┌─────────────────────────────────┼──────────────────────────────────┐
   ▼            ▼           ▼        ▼         ▼          ▼            ▼
Substitution Timetable  Faculty   Student   Finance     Exam       Request
  Agent        Agent     Agent     Agent     Agent      Agent       Agent
   │            │          │         │         │          │            │
   └────────────┴──────────┴────┬────┴─────────┴──────────┴────────────┘
                                ▼
                    ┌───────────────────────┐      ┌──────────────┐
                    │  SYNTHESIZER          │─────▶│ NOTIFY AGENT │
                    │  narrative + tables + │      │ students/    │
                    │  plans + next actions │      │ faculty/HOD  │
                    └───────────┬───────────┘      └──────────────┘
                                ▼
                    ┌───────────────────────┐
                    │  AUDITOR (immutable)  │  who asked · which agent
                    └───────────────────────┘  acted · what changed
```

Support agents that fire situationally: **WorkloadBalancer** (fairness), **RiskAgent** (severity
bucketing), **SLAMonitor** (approval ageing), **HRAgent** (leave ledger).

---

## 4. Flagship flow — teacher absence → timetable rescheduling

Say: *“Prof. Sneha Mallya is absent next Monday, arrange coverage.”*

1. **Impact scan** — every period that faculty holds on that weekday, with student-hours at stake.
2. **Constraint solve** — for each vacant slot the SubstitutionAgent searches all faculty against:
   - **Hard constraints:** no clash in that period, not on approved leave, within load cap +2,
     lab sessions need lab competency.
   - **Soft scoring:** already teaches the same subject to another section (+46), subject in
     expertise profile (+24), same department (+14), free head-room (up to +16), fairness penalty
     for a second adjustment the same day (−9), professors de-prioritised for adjustments (−4).
3. **Three strategies generated, then re-ranked** by `0.6·confidence + 0.25·coverage + 0.15·continuity`:

   | Plan | Strategy | Best when |
   |------|----------|-----------|
   | **A** | Competency-matched substitution | students' timetable must not change |
   | **B** | Swap-forward re-sequencing (trade the hour with a later class of the same batch) | exam-critical subject, zero syllabus loss |
   | **C** | Release + guaranteed make-up in the earliest mutually-free slot | no qualified substitute free |

4. **Human-in-the-loop** — nothing is written. The admin says *“apply plan B”* (bound by **plan code**,
   not list position).
5. **Commit** — timetable overrides written, leave ledger updated, notifications drafted and
   dispatched to each affected section, each substitute, and the HOD/Principal digest, audit row
   recorded. The published timetable grid shows overridden cells in amber.
6. **Rollback** — *“undo”* reverts the whole plan by its reference id.

---

## 5. What else the copilot handles

| Domain | Example utterance |
|---|---|
| Availability | “Which ECE faculty are free on Monday period 4?” · “Free rooms at period 6” |
| Timetable | “Show CSE 5th sem A timetable” · “Who is teaching at period 3?” |
| Faculty | “Faculty workload above 90%” · “Who teaches Machine Learning?” |
| Students | “Attendance defaulters below 65% in CSE sem 5” · “Student 4VP24CS017 details” · risk radar |
| Finance | “Fee dues by department” |
| Exams | “SEE eligibility check for MECH” · “Draft invigilation roster” |
| Approvals | “Pending approvals” · “Approve 3” · “Bulk approve under ₹50,000” · “Raise a purchase request to the Principal for ₹3 lakh, urgent” |
| Broadcast | “Notify all CSE students that lab exams are postponed to 15 Sep” |
| Analytics | “Brief me on today's institution status” |
| Leave | “Who is on leave this week?” |

**Conversation quality built in:** multi-turn pending state, context switching (a fresh command mid-proposal
does *not* get swallowed as a “yes”), disambiguation when a faculty name is a weak match
(“did you mean…” with match %), and contextual follow-ups (“show me the updated timetable” opens the
class that was actually changed, on the date that was changed).

---

## 6. Guardrails (the part that makes it deployable)

- **RBAC scopes** — admin = institution-wide; HOD = department; faculty = self.
- **HITL gate** — every write intent (`absence.cover`, `request.manage`, `notify.broadcast`) returns
  a proposal, never a commit.
- **Delegation ceilings** — bulk approval respects a rupee cap; high-value requests route to Principal.
- **Immutable audit ledger** — actor, agent, action, payload, outcome, timestamp. Exportable for
  NAAC / NBA / ISO audits.
- **No silent guessing** — weak entity matches ask instead of acting.

---

## 7. Data model (seeded, realistic)

`departments · faculty · subjects · rooms · students · timetable · leaves · overrides · requests ·
notifications · audit · exams · attendance · placements`

Seed: **5 departments, 53 faculty, 1,095 students, 707 timetable slots** across semesters 3/5/7,
plus leave records, an approvals inbox, SEE calendar and placement stats.

### The timetable generator (`db.py`) — how a real college day is modelled

```
P1 09:00–09:55   P2 09:55–10:50   ┃ 20-min break ┃   P3 11:10–12:05   P4 12:05–13:00
┃ 45-min lunch ┃   P5 13:45–14:40   P6 14:40–15:35   P7 15:35–16:30
```

Hard rules the generator enforces, and `db.verify()` asserts:

1. **No holes.** A class's day is periods 1…N back-to-back. You will never see
   `class / free / free / class`. Breaks are gaps in the *clock*, not empty slots.
2. **Day length by seniority** — sem 3 runs to P7 (39 hrs/wk), sem 5 to P6 (34), sem 7 to P5 (28),
   because final-year batches leave early for project work. Saturdays are short.
3. **Labs are 3 consecutive periods**, inside one session (P1–P3 or P5–P7) so they never straddle
   lunch. Project Phase-I gets two such blocks.
4. **One teacher owns a subject for a class** all semester — allocated up front by expertise and
   load balance, exactly like a department meeting would.
5. **No faculty or room is ever double-booked**, and nobody exceeds their sanctioned load
   (3 hrs of every cap is reserved for activity supervision).
6. **Curriculum gaps become real academic activities** — placement training, mini-project, library,
   mentoring, sports, remedial — never a blank cell. That's ~24% of slots, which matches a real
   VTU timetable.

Because labs are contiguous blocks, the SubstitutionAgent groups consecutive periods of the same
subject into **one teaching block**: an absent lab instructor produces a single `P1–P3` coverage
decision, not three unrelated ones.

---

## 8. Files

```
erp/
├── app.py              FastAPI routes, engine switch, static hosting
├── db.py               schema + seeder + CONTIGUOUS timetable generator + verify()
├── nlu.py              intent scoring, priority rules, entity + Indian date parsing
├── agents.py           the nine specialists + PolicyGuard + Auditor
├── orchestrator.py     rule-engine supervisor: routing, HITL state machine
├── llm.py              provider-agnostic OpenAI-compatible client (urllib, no SDK)
├── tools.py            the 20 tool schemas + PolicyGuard-wrapped dispatch
├── llm_agent.py        the LLM reasoning loop (plan → call tools → answer), with failover
├── .env / .env.example LLM configuration
├── static/index.html   admin console SPA (dark, zero external assets)
└── tests/
    ├── smoke.py        end-to-end conversation regression
    └── mock_llm.py     fake OpenAI endpoint + rogue-agent guard test
```

UI sections: **AI Copilot** (with a live agent-trace panel showing every hop and its latency),
Dashboard, Timetable (override-aware grid), Faculty, Students, Approvals, Overrides, Agent Audit.

---

## 9. Design notes

The NLU + planning layer is deliberately isolated. To go LLM-native:

- Replace `nlu.classify()` with a function-calling LLM; keep `PRIORITY` rules as a cheap
  fallback/validator.
- Expose each specialist method as a **tool schema** (they already return structured dicts).
- Keep `PolicyGuard`, the HITL gate and `Auditor` **outside** the model — the model proposes,
  deterministic code enforces and commits.
- The constraint solver in `SubstitutionAgent` should stay deterministic; LLMs are bad at
  clash-freeness, good at explaining trade-offs.

## 10. Roadmap beyond admin

Student portal agent (attendance/marks/fee self-service), faculty agent (lesson plans, CIE entry,
leave with auto-coverage attached), parent WhatsApp agent, NAAC/NBA evidence-pack generator,
predictive dropout model feeding the RiskAgent, and Kannada/Hindi voice input for support staff.
