# MAWOS v5 — Agentic Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace MAWOS's regex-routed single-tool chat path with a LangGraph runtime in which a hosted LLM plans and delegates across agents, a deterministic guard authorises every action, writes require human confirmation, the whole chain is traced, and the same guarded tools are reachable from an external MCP client.

**Architecture:** LangGraph supplies the state machine, Postgres checkpointing and `interrupt()`-based human-in-the-loop. Above it we build what LangGraph does not provide: a deterministic guard that decides whether a write may even be proposed, a typed `Task → Result | NeedInfo | Refusal` delegation contract, a provenance gate over synthesis, and a persisted per-turn trace. Existing agents, tools, scheduler and data generator are reused unchanged; only the planning tier is replaced.

**Tech Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2.0 · Alembic · LangGraph 1.0.x · `langchain-openai` (OpenAI-compatible, pointed at Groq/OpenRouter/GitHub Models) · `langgraph-checkpoint-postgres` · MCP Python SDK · PostgreSQL · Docker · Render

**Spec:** `docs/superpowers/specs/2026-09-13-mawos-v5-design.md`

## Global Constraints

- **Licences must be permissive.** MIT / BSD / Apache-2.0 / PostgreSQL only. No GPL-family dependency may enter `requirements.txt`. Cause: §1 of the spec — the project is intended for commercial use and Indian colleges procure on-premise, which is distribution.
- **Never headline a 100% figure** (`CLAUDE.md`). Anywhere — code comments, UI, docs, commit messages.
- **Report results in the direction the data points.** Do not re-frame a loss as a win; do not delete a losing configuration.
- **Never present a number that cannot be regenerated** from `evaluation/`.
- **Cite which instrument produced every number.** v3 numbers and v5 numbers may never be differenced against each other.
- **The lexicon tier is *primary*, not a "fallback."** Do not rename it in code, UI or docs.
- **Pre-registered thresholds are not relaxed after seeing results** (`PROTOCOL.md` §1 rule 8). A threshold may only change via a dated re-registration entry written *before* the run that uses it.
- **No real institutional or personal identity** anywhere in code, data, tests or docs. `data/generator/config.py` enforces this; do not weaken it.
- **Stop the server before deleting `mawos.db`**; never run `evaluation/` scripts while the server is up (both write the same SQLite file).
- Secrets come from the environment only. `.env` and `.env.*` are gitignored (`.env.example` is the sole exception). No API key may ever enter git.
- Target: **Python 3.11+**, LangGraph **>=1.0,<2.0**.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `backend/app/guard.py` | Deterministic authorisation. One entry point, logs allowed *and* denied. |
| `backend/app/contracts.py` | Typed delegation contract: `AgentTask`, `AgentResult`, `NeedInfo`, `Refusal`. |
| `backend/app/llm_provider.py` | Runtime LLM adapter. OpenAI-compatible; provider chosen by env. |
| `backend/app/graph/state.py` | LangGraph state `TypedDict` + reducers. |
| `backend/app/graph/nodes.py` | Node functions: plan, clarify, guard, confirm, execute, observe, synthesize. |
| `backend/app/graph/build.py` | Graph assembly + checkpointer wiring. |
| `backend/app/trace.py` | Trace persistence to `trace_records`. |
| `backend/app/mcp_server.py` | MCP surface over the same guarded tools. |
| `Dockerfile` | Backend container for Render. |
| `render.yaml` | Render service + Postgres declaration. |
| `tests/test_guard.py`, `tests/test_contracts.py`, `tests/test_write_tools.py`, `tests/test_graph.py`, `tests/test_trace.py`, `tests/test_mcp.py`, `tests/test_probe_scoring.py` | One test module per unit. |

**Modified:**

| Path | Change |
|---|---|
| `evaluation/provider_probe.py` | M7 redefined over summed provider latency (D14). |
| `evaluation/probe/providers.py` | Add OpenRouter + GitHub Models to `shortlist()`. |
| `backend/app/agents/tools.py` | `@tool` gains `writes=`; 3 write tools added; `execute()` calls the guard. |
| `backend/app/config.py` | Provider env vars. |
| `backend/app/api/routes.py` | `/chat/v5` turn endpoint + `/chat/v5/resume`. |
| `requirements.txt` | LangGraph, langchain-openai, checkpoint-postgres, mcp, psycopg. |
| `docs/v4/03_LLM_LAYER.md`, `docs/v4/OPEN_DECISIONS.md` | D14 re-registration + D1 closure entries. |

**Rationale for the split:** `guard.py`, `contracts.py` and `trace.py` are deliberately separate single-purpose modules because they are the project's actual contribution — they must be readable and testable without reading the graph. `graph/` is a package rather than one file because `nodes.py` will otherwise grow past the point where it can be held in context.

---

## Task 1: Close D14 — re-register M7 over summed provider latency

`docs/v4/OPEN_DECISIONS.md` D14 records that M7 is computed from wall-clock time, which includes the client's own rate-pacing `sleep`. Local providers need no pacing, hosted ones do, so the two classes are not comparable on M7. D14's closure condition is exact: *"An explicit re-registration, made before the next probe run, defining M7 over summed provider latency (`sum(round.latency_ms)`) rather than wall time."*

Its four pre-registered constraints: it must change no completed verdict, completed runs are not re-scored, it applies only to future runs, and the motivation must be structural. **Constraint 1 is what Step 1 tests.**

**Files:**
- Modify: `evaluation/provider_probe.py` (`score()`, `THRESHOLDS` comment block)
- Modify: `docs/v4/03_LLM_LAYER.md` (new §2.3.2), `docs/v4/OPEN_DECISIONS.md` (D14 status)
- Test: `tests/test_probe_scoring.py` (create)

**Interfaces:**
- Consumes: existing `score(records) -> dict`, `eligibility(sc, thresholds) -> dict` in `evaluation/provider_probe.py`
- Produces: `score()` now emits `m7_latency_p50_s` computed as the p50 over items of `sum(r["latency_ms"] for r in rounds)`; the old wall-clock value is retained as `m7_wall_p50_s` (diagnostic, not gated)

- [ ] **Step 1: Write the failing test — the re-definition must flip no completed verdict**

Create `tests/test_probe_scoring.py`:

```python
"""D14 constraint 1: re-registering M7 must change no completed verdict.

docs/v4/OPEN_DECISIONS.md D14 allows the re-registration only if it is
verified to leave every already-published eligibility outcome intact.
This test is the executable form of that constraint.
"""
import json
from pathlib import Path

import pytest

from evaluation.provider_probe import eligibility, score

RESULTS = Path(__file__).resolve().parent.parent / "evaluation" / "results" / "v4_gates"
COMPLETED = ["r05_provider.json", "r05_provider_20260901.json"]


def _runs():
    for fname in COMPLETED:
        path = RESULTS / fname
        if not path.exists():
            continue
        blob = json.loads(path.read_text(encoding="utf-8"))
        for entry in blob.get("providers", []):
            if entry.get("records"):
                yield fname, entry["provider"], entry["records"], entry["scores"]


def test_completed_runs_exist():
    assert list(_runs()), "no completed probe runs found to verify against"


@pytest.mark.parametrize("fname,provider,records,published", list(_runs()))
def test_m7_redefinition_changes_no_verdict(fname, provider, records, published):
    fresh = score(records)
    was = eligibility(published)["eligible"]
    now = eligibility(fresh)["eligible"]
    assert now == was, (
        f"{provider} in {fname}: eligibility flipped {was} -> {now} "
        f"under the re-registered M7. D14 constraint 1 forbids this."
    )
```

- [ ] **Step 2: Run it and watch it fail**

```bash
python -m pytest tests/test_probe_scoring.py -v
```

Expected: `test_m7_redefinition_changes_no_verdict` FAILS or errors, because `score()` still returns wall-clock M7 while `published` holds wall-clock values — the test only becomes meaningful after Step 3. If it passes trivially here, confirm `_runs()` actually yielded records before continuing.

- [ ] **Step 3: Redefine M7 in `score()`**

In `evaluation/provider_probe.py`, inside `score()`, replace the wall-clock M7 computation with:

```python
    # M7 — RE-REGISTERED 2026-09-14 (D14). Defined over summed PROVIDER
    # latency per item, not wall-clock. Wall time includes this harness's
    # own rate-pacing sleep, which hosted providers require and local ones
    # do not, so wall-clock M7 was not provider-agnostic and the two
    # classes were never comparable on it. Completed runs are NOT re-scored.
    item_provider_s = sorted(
        sum(x["latency_ms"] for x in r["rounds"] if "latency_ms" in x) / 1000.0
        for r in records
    )
    m7 = statistics.median(item_provider_s) if item_provider_s else 0.0
    # Retained as a diagnostic so the pacing overhead stays visible.
    item_wall_s = sorted(r["wall_ms"] / 1000.0 for r in records if "wall_ms" in r)
    m7_wall = statistics.median(item_wall_s) if item_wall_s else 0.0
```

and add `"m7_wall_p50_s": m7_wall,` to the returned dict alongside the existing `"m7_latency_p50_s": m7,`.

> If `records` entries do not carry `wall_ms`, set `m7_wall = 0.0` and note it in the commit message rather than inventing the field.

- [ ] **Step 4: Update the threshold provenance comment**

In the `THRESHOLDS` block, extend the M7 comment:

```python
    "m7_latency_p50_s":      6.0,     # upper bound; RE-REGISTERED twice.
                                      # 2026-09-01 (D13): 3.0 -> 6.0.
                                      # 2026-09-14 (D14): the MEASURE
                                      # changed from wall-clock to summed
                                      # provider latency. Neither the
                                      # 2026-08-31 nor the 2026-09-01 run
                                      # is re-scored; both stand.
```

- [ ] **Step 5: Run the test and verify it passes**

```bash
python -m pytest tests/test_probe_scoring.py -v
```

Expected: PASS for every completed run. **If any verdict flips, stop.** D14 constraint 1 is violated and the re-registration may not proceed — report it instead.

- [ ] **Step 6: Write the dated re-registration entries**

Append to `docs/v4/03_LLM_LAYER.md` a new `§2.3.2 — M7 re-registered (D14), 2026-09-14` stating: what changed (measure, not threshold), why it is structural (pacing is a property of the harness, not the provider), that no completed run is re-scored, and that verification of constraint 1 is `tests/test_probe_scoring.py`.

In `docs/v4/OPEN_DECISIONS.md`, set D14 **Status** to `CLOSED 2026-09-14 — re-registered before any hosted re-run`, and add a row to the §4 decision log.

- [ ] **Step 7: Commit**

```bash
git add tests/test_probe_scoring.py evaluation/provider_probe.py docs/v4/03_LLM_LAYER.md docs/v4/OPEN_DECISIONS.md
git commit -m "D14: re-register M7 over summed provider latency, before any hosted re-run

Wall-clock M7 included this harness's own rate-pacing sleep. Hosted
providers require pacing; local ones do not. The measure was therefore
not provider-agnostic and the two classes were never comparable on it.

M7 is now the p50 over items of sum(round.latency_ms). Wall-clock is
retained as m7_wall_p50_s, a diagnostic, so the pacing overhead stays
visible rather than disappearing.

Neither completed run is re-scored; both verdicts stand. D14 constraint
1 -- that the change flips no completed verdict -- is verified
executably by tests/test_probe_scoring.py.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Run the hosted probe and close D1

`OpenAICompatibleProvider` already exists and Groq is already in `shortlist()`; it went untested on 2026-08-31 only because `GROQ_API_KEY` was unset. This task adds two more OpenAI-compatible candidates and runs the gate.

**Files:**
- Modify: `evaluation/probe/providers.py` (`shortlist()`)
- Modify: `.env.example`
- Output: `evaluation/results/v5_gates/r05_provider_hosted.{json,md}`

**Interfaces:**
- Consumes: `OpenAICompatibleProvider(model, base_url, key_env, label)` from `evaluation/probe/providers.py`
- Produces: a scored result file; the selected provider's label becomes the value of `MAWOS_LLM_MODEL` in Task 3

- [ ] **Step 1: Add the two remaining candidates to `shortlist()`**

In `evaluation/probe/providers.py`, inside the returned list, after the Groq entry:

```python
        OpenAICompatibleProvider("meta-llama/llama-3.3-70b-instruct",
                                 "https://openrouter.ai/api/v1",
                                 "OPENROUTER_API_KEY",
                                 label="openrouter:llama-3.3-70b"),
        OpenAICompatibleProvider("gpt-4o-mini",
                                 "https://models.inference.ai.azure.com",
                                 "GITHUB_MODELS_TOKEN",
                                 label="github-models:gpt-4o-mini"),
```

- [ ] **Step 2: Document the credentials in `.env.example`**

```bash
cat >> .env.example <<'EOF'

# --- v5 hosted provider candidates (R0.5 re-run, D1) ---
# Groq: free tier, 14,400 req/day, no card. https://console.groq.com/keys
GROQ_API_KEY=
# OpenRouter: 50 req/day free. https://openrouter.ai/keys
OPENROUTER_API_KEY=
# GitHub Models: 50 req/day high-tier. A fine-grained PAT with models:read.
GITHUB_MODELS_TOKEN=
EOF
```

- [ ] **Step 3: Obtain a Groq key and verify availability without spending quota**

Put the key in a local `.env` (gitignored), then:

```bash
python -c "
import os, sys
sys.path.insert(0, '.')
from evaluation.probe.providers import shortlist
for p in shortlist():
    ok, why = p.availability()
    print(f'{p.name:38s} {\"OK\" if ok else \"--\"}  {why}')
"
```

Expected: `groq:llama-3.3-70b  OK  ok`. Any candidate without a credential must report `no credential: <ENV> is unset` — that is the correct, honest state and it still appears in the result file as untested.

- [ ] **Step 4: Confirm the server is down, then run the gate**

```bash
python -m pytest tests -q
python evaluation/provider_probe.py --models groq,openrouter,github
```

> `CLAUDE.md`: never run `evaluation/` scripts while the server is up — both write the same SQLite file. The probe is checkpointed per `(provider, seed, item)`, so a kill costs one item, not the run; re-invoking the identical command resumes.

- [ ] **Step 5: Apply the pre-registered rule and record the outcome — whatever it is**

Read the generated `.md`. Apply `03_LLM_LAYER.md` §4.3 **as written**: eligible only if all eight mandatory thresholds pass; among eligible, select by highest `mean(clarification, refusal)`, ties broken by multi-step then latency.

Then write the D1 entry in `docs/v4/OPEN_DECISIONS.md` recording one of:
- **(a)** a candidate passed → D1 closes, name it and cite the evidence file; or
- **(b)** nothing passed → **D1 stays open, thresholds are not relaxed**, and the finding is reported. If the project then adopts a failing provider anyway, that is *"a project decision made explicitly and recorded, not something the gate supports"* — write it in exactly those terms.

Do not proceed to Task 3 until this entry exists.

- [ ] **Step 6: Commit**

```bash
git add evaluation/probe/providers.py .env.example evaluation/results/v5_gates docs/v4/OPEN_DECISIONS.md
git commit -m "R0.5 hosted re-run: probe Groq, OpenRouter and GitHub Models

Adds the two remaining OpenAI-compatible candidates. Groq was already in
the shortlist and went untested on 2026-08-31 only because no credential
was present -- this is the run that was always intended, not a new
instrument.

Scored under the M7 re-registered in the previous commit. May not be
differenced against the 2026-08-31 or 2026-09-01 results.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Runtime LLM provider adapter

One adapter covers all three candidates, because Groq, OpenRouter and GitHub Models are all OpenAI-compatible — mirroring `OpenAICompatibleProvider` in the probe. This keeps the degradation run (Claim 2) a config change.

**Files:**
- Create: `backend/app/llm_provider.py`
- Modify: `backend/app/config.py`, `requirements.txt`
- Test: `tests/test_llm_provider.py`

**Interfaces:**
- Produces: `get_chat_model(temperature: float = 0.0) -> BaseChatModel` and `active_provider() -> dict` (keys: `label`, `model`, `base_url`, `available`)

- [ ] **Step 1: Add dependencies**

```bash
cat >> requirements.txt <<'EOF'
langgraph>=1.0,<2.0          # MIT — agent runtime (v5)
langchain-core>=0.3          # MIT
langchain-openai>=0.2        # MIT — OpenAI-compatible client (Groq/OpenRouter/GH)
langgraph-checkpoint-postgres>=2.0  # MIT — PostgresSaver
psycopg[binary]>=3.1         # LGPL-free; psycopg3 is LGPL -> see note below
mcp>=1.2                     # MIT — Model Context Protocol server
EOF
pip install -r requirements.txt
```

> **Licence check required before committing.** psycopg3 is LGPL-licensed. LGPL dynamic linking is generally compatible with closed-source distribution, but the Global Constraints say permissive-only. Verify and, if it is unacceptable, substitute `pg8000` (BSD) and record the substitution in the commit message. Do not silently accept an LGPL dependency.

- [ ] **Step 2: Add config**

Append to `backend/app/config.py`:

```python
# --- v5 hosted LLM provider (D1). One adapter, three candidates: Groq,
# OpenRouter and GitHub Models are all OpenAI-compatible, so switching
# provider for the degradation run is config, never code.
LLM_BASE_URL = os.getenv("MAWOS_LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("MAWOS_LLM_MODEL", "llama-3.3-70b-versatile")
LLM_API_KEY_ENV = os.getenv("MAWOS_LLM_KEY_ENV", "GROQ_API_KEY")
LLM_TIMEOUT_S = float(os.getenv("MAWOS_LLM_TIMEOUT", "30"))
LLM_LABEL = os.getenv("MAWOS_LLM_LABEL", "groq:llama-3.3-70b")
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_llm_provider.py`:

```python
"""The runtime adapter must be provider-agnostic and must never crash the
app when no credential is present -- degradation is visible, not fatal
(docs/v4/03_LLM_LAYER.md fallback ladder)."""
import importlib

from backend.app import llm_provider


def test_active_provider_reports_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    importlib.reload(llm_provider)
    info = llm_provider.active_provider()
    assert info["available"] is False
    assert info["label"]
    assert info["model"]


def test_active_provider_reports_available_with_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    importlib.reload(llm_provider)
    info = llm_provider.active_provider()
    assert info["available"] is True


def test_get_chat_model_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    importlib.reload(llm_provider)
    assert llm_provider.get_chat_model() is None
```

- [ ] **Step 4: Run it and verify it fails**

```bash
python -m pytest tests/test_llm_provider.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.llm_provider'`

- [ ] **Step 5: Implement the adapter**

Create `backend/app/llm_provider.py`:

```python
"""Runtime LLM adapter for v5.

One OpenAI-compatible client serves every candidate D1 considered (Groq,
OpenRouter, GitHub Models), mirroring `evaluation/probe/providers.py`'s
OpenAICompatibleProvider. Swapping provider for the degradation run is a
config change, never a code change.

A missing credential is NOT fatal. It degrades the system to the
deterministic tier, which stays the primary tier by design -- the lexicon
answers ~90% of queries and is never called a fallback (CLAUDE.md).
"""
from __future__ import annotations

import os

from . import config


def _api_key() -> str | None:
    return os.getenv(config.LLM_API_KEY_ENV) or None


def active_provider() -> dict:
    """What the header badge and the trace record as the active tier."""
    return {
        "label": config.LLM_LABEL,
        "model": config.LLM_MODEL,
        "base_url": config.LLM_BASE_URL,
        "available": _api_key() is not None,
    }


def get_chat_model(temperature: float = 0.0):
    """A LangChain chat model, or None when no credential is configured."""
    key = _api_key()
    if key is None:
        return None
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=config.LLM_MODEL,
        base_url=config.LLM_BASE_URL,
        api_key=key,
        temperature=temperature,
        timeout=config.LLM_TIMEOUT_S,
        max_retries=2,
    )
```

- [ ] **Step 6: Run the tests**

```bash
python -m pytest tests/test_llm_provider.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/llm_provider.py backend/app/config.py requirements.txt tests/test_llm_provider.py
git commit -m "v5: provider-agnostic runtime LLM adapter

One OpenAI-compatible client covers Groq, OpenRouter and GitHub Models,
so the Claim 2 degradation run is a config change. A missing credential
degrades to the deterministic tier rather than failing the app.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: The deterministic guard

This is the project's primary contribution. It must be non-bypassable, must log **allowed and denied in the same shape**, and must record whether the capability was actually *exposed* to the actor — because `GuardDecision.was_exposed` is what makes the attempt rate computable, and the attempt rate is the headline of Claim 1.

**Files:**
- Create: `backend/app/guard.py`
- Test: `tests/test_guard.py`

**Interfaces:**
- Consumes: `User`, `TeachingAssignment`, `Student`, `GuardDecision` from `backend/app/models.py`; `TOOLS` from `backend/app/agents/tools.py`
- Produces:
  - `@dataclass GuardVerdict: allowed: bool, reason_code: str, detail: str, capability: str, target: str`
  - `authorise(db, user, capability: str, args: dict, turn_id: str | None = None) -> GuardVerdict`
  - `REASON_NOT_PERMITTED = "NOT_PERMITTED"`, `REASON_OUT_OF_SCOPE = "OUT_OF_SCOPE"`, `REASON_PRECONDITION_FAILED = "PRECONDITION_FAILED"`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_guard.py`:

```python
"""Claim 1 rests on this module: guard placement, not model choice,
determines safety. Every case below is an authorisation outcome that must
be recorded in the same shape whether it allowed or denied."""
from backend.app import guard
from backend.app.models import GuardDecision, User


def _user(db, username):
    return db.query(User).filter_by(username=username).one()


def test_student_may_read_own_attendance(db, agents, base_data):
    u = db.query(User).filter_by(role="student").first()
    v = guard.authorise(db, u, "get_attendance", {"usn": u.usn})
    assert v.allowed is True
    assert v.reason_code == ""


def test_student_may_not_read_another_students_attendance(db, agents, base_data):
    u = db.query(User).filter_by(role="student").first()
    v = guard.authorise(db, u, "get_attendance", {"usn": "1VT23AI999"})
    assert v.allowed is False
    assert v.reason_code == guard.REASON_OUT_OF_SCOPE


def test_student_may_not_mark_attendance(db, agents, base_data):
    u = db.query(User).filter_by(role="student").first()
    v = guard.authorise(db, u, "mark_attendance", {})
    assert v.allowed is False
    assert v.reason_code == guard.REASON_NOT_PERMITTED


def test_every_decision_is_logged_allowed_and_denied(db, agents, base_data):
    before = db.query(GuardDecision).count()
    u = db.query(User).filter_by(role="student").first()
    guard.authorise(db, u, "get_attendance", {"usn": u.usn})        # allowed
    guard.authorise(db, u, "mark_attendance", {})                   # denied
    db.commit()
    rows = db.query(GuardDecision).order_by(GuardDecision.id).all()
    assert len(rows) == before + 2
    assert {r.verdict for r in rows[-2:]} == {"allowed", "denied"}


def test_denial_of_unexposed_capability_is_marked_unexposed(db, agents, base_data):
    """A student never sees mark_attendance in their schema, so a denial
    there is NOT a real attempt. R0.5 measured 0 attempts only because the
    role filter hid the capability -- a different fact, and it must stay
    distinguishable."""
    u = db.query(User).filter_by(role="student").first()
    guard.authorise(db, u, "mark_attendance", {})
    db.commit()
    row = db.query(GuardDecision).order_by(GuardDecision.id.desc()).first()
    assert row.was_exposed is False


def test_unknown_capability_is_denied_not_crashed(db, agents, base_data):
    u = db.query(User).filter_by(role="student").first()
    v = guard.authorise(db, u, "definitely_not_a_tool", {})
    assert v.allowed is False
    assert v.reason_code == guard.REASON_NOT_PERMITTED
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_guard.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.guard'`

- [ ] **Step 3: Implement the guard**

Create `backend/app/guard.py`:

```python
"""Deterministic authorisation. Non-bypassable, and the single place where
"may this actor do this?" is answered.

Two properties are load-bearing for `docs/v4/07_CONTRIBUTION.md` claim 1:

1. Allowed and denied outcomes are recorded in the SAME shape. If denials
   were exceptions and successes were silent, the attempt rate would be
   uncomputable -- and the attempt rate is the claim.
2. `exposed` distinguishes "tried and was stopped" from "never could have
   tried". R0.5 measured 0 attempts, but only because the role filter never
   showed the capability. That is a different fact and must stay visible.

Nothing here consults the LLM. That is the point: the model may propose
anything; what executes is decided by this module alone.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import GuardDecision, Student, TeachingAssignment

REASON_NOT_PERMITTED = "NOT_PERMITTED"
REASON_OUT_OF_SCOPE = "OUT_OF_SCOPE"
REASON_PRECONDITION_FAILED = "PRECONDITION_FAILED"


@dataclass
class GuardVerdict:
    allowed: bool
    reason_code: str = ""
    detail: str = ""
    capability: str = ""
    target: str = ""


def _spec(capability: str) -> dict | None:
    from .agents.tools import TOOLS
    return TOOLS.get(capability)


def _is_exposed(user, capability: str) -> bool:
    spec = _spec(capability)
    return bool(spec) and user.role in spec["roles"]


def _target_of(capability: str, args: dict) -> str:
    for key in ("usn", "section", "subject_code", "student", "target"):
        if args.get(key):
            return f"{key}={args[key]}"
    return ""


def _owns_subject_section(db, user, args: dict) -> bool:
    """Faculty may only write against a subject-section they are assigned."""
    if user.faculty_id is None:
        return False
    q = db.query(TeachingAssignment).filter_by(faculty_id=user.faculty_id)
    if args.get("subject_code"):
        q = q.filter_by(subject_code=args["subject_code"])
    if args.get("section"):
        q = q.filter_by(section=args["section"])
    return db.query(q.exists()).scalar()


def _decide(db, user, capability: str, args: dict) -> GuardVerdict:
    target = _target_of(capability, args)
    spec = _spec(capability)

    if spec is None or user.role not in spec["roles"]:
        return GuardVerdict(False, REASON_NOT_PERMITTED,
                            f"role '{user.role}' may not use {capability}",
                            capability, target)

    # Students are locked to their own record, regardless of what was asked.
    if user.role == "student":
        asked = str(args.get("usn") or "").upper().strip()
        if asked and asked != (user.usn or "").upper():
            return GuardVerdict(False, REASON_OUT_OF_SCOPE,
                                "students may only read their own record",
                                capability, target)

    if spec.get("writes"):
        if user.role == "faculty" and not _owns_subject_section(db, user, args):
            return GuardVerdict(False, REASON_OUT_OF_SCOPE,
                                "faculty is not assigned to this subject-section",
                                capability, target)
        if args.get("usn") and db.get(Student, str(args["usn"]).upper()) is None:
            return GuardVerdict(False, REASON_PRECONDITION_FAILED,
                                f"unknown student {args['usn']}",
                                capability, target)

    return GuardVerdict(True, "", "", capability, target)


def authorise(db, user, capability: str, args: dict,
              turn_id: str | None = None) -> GuardVerdict:
    """The only authorisation entry point. Always logs, then returns."""
    args = args or {}
    verdict = _decide(db, user, capability, args)
    db.add(GuardDecision(
        turn_id=turn_id,
        actor=user.username,
        actor_role=user.role,
        capability=capability,
        target=verdict.target,
        verdict="allowed" if verdict.allowed else "denied",
        reason_code=verdict.reason_code,
        detail=verdict.detail,
        was_exposed=_is_exposed(user, capability),
    ))
    return verdict
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_guard.py -v
```

Expected: 6 passed. If `GuardDecision.was_exposed` does not exist on the model, read `backend/app/models.py:398-420` and use the column name that is actually there — do not add a column in this task.

- [ ] **Step 5: Commit**

```bash
git add backend/app/guard.py tests/test_guard.py
git commit -m "v5: deterministic guard layer

The single authorisation entry point. Logs allowed and denied in the same
shape so the attempt rate stays computable, and marks whether the
capability was exposed to the actor at all -- R0.5's 0 attempts were an
artefact of the role filter hiding the capability, which is a different
fact and must stay distinguishable.

Consults no model. What executes is decided here, not by the planner.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Typed delegation contract

**Files:**
- Create: `backend/app/contracts.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Produces: Pydantic v2 models `AgentTask`, `AgentResult`, `NeedInfo`, `Refusal`, and the union alias `Outcome = AgentResult | NeedInfo | Refusal`

- [ ] **Step 1: Write the failing test**

Create `tests/test_contracts.py`:

```python
"""Clarification is a first-class outcome, not an error string. A turn that
returns NeedInfo STOPS -- that is the behaviour whose absence made Gemini
fail M4 (it called a tool against a silent default, then asked)."""
import pytest
from pydantic import ValidationError

from backend.app.contracts import AgentResult, AgentTask, NeedInfo, Refusal


def test_task_requires_capability_and_actor():
    t = AgentTask(capability="get_attendance", args={"usn": "X"},
                  actor="stud1", agent="attendance_agent")
    assert t.capability == "get_attendance"
    assert t.args == {"usn": "X"}


def test_task_rejects_missing_capability():
    with pytest.raises(ValidationError):
        AgentTask(args={}, actor="stud1", agent="attendance_agent")


def test_result_carries_provenance_payload():
    r = AgentResult(agent="attendance_agent", data={"pct": 71.0},
                    source_tool="get_attendance")
    assert r.ok is True
    assert r.source_tool == "get_attendance"


def test_need_info_carries_the_question_and_field():
    n = NeedInfo(agent="attendance_agent", question="Which subject?",
                 field="subject_code")
    assert n.ok is False
    assert n.field == "subject_code"


def test_refusal_carries_a_reason_code():
    f = Refusal(agent="attendance_agent", reason_code="NOT_PERMITTED",
                detail="role 'student' may not use mark_attendance")
    assert f.ok is False
    assert f.reason_code == "NOT_PERMITTED"
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_contracts.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.contracts'`

- [ ] **Step 3: Implement the contract**

Create `backend/app/contracts.py`:

```python
"""The typed delegation contract: Task -> Result | NeedInfo | Refusal.

Three distinct outcomes, not two. A NeedInfo is not a failure and not an
error string -- it STOPS the turn and asks. That distinction is the whole
point: the R0.5 hosted run failed M4 because the model called a tool
against a silent default and asked afterwards.
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    """One unit of delegated work. Produced by the planner, never trusted."""
    capability: str
    args: dict[str, Any] = Field(default_factory=dict)
    actor: str
    agent: str
    rationale: str = ""


class AgentResult(BaseModel):
    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    agent: str
    data: dict[str, Any] = Field(default_factory=dict)
    #: Which tool produced `data`. The provenance gate checks answers
    #: against this, so it is required rather than decorative.
    source_tool: str


class NeedInfo(BaseModel):
    kind: Literal["need_info"] = "need_info"
    ok: Literal[False] = False
    agent: str
    question: str
    #: The argument that is missing, so the resumed turn can fill exactly it.
    field: str


class Refusal(BaseModel):
    kind: Literal["refusal"] = "refusal"
    ok: Literal[False] = False
    agent: str
    reason_code: str
    detail: str = ""


Outcome = Union[AgentResult, NeedInfo, Refusal]
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_contracts.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/contracts.py tests/test_contracts.py
git commit -m "v5: typed delegation contract

Task -> Result | NeedInfo | Refusal. Three outcomes, not two: NeedInfo
stops the turn and asks rather than guessing, which is precisely the
behaviour whose absence failed M4 on 2026-09-01.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Three write tools behind the guard

**Files:**
- Modify: `backend/app/agents/tools.py`
- Test: `tests/test_write_tools.py`

**Interfaces:**
- Consumes: `guard.authorise` (Task 4)
- Produces: `TOOLS[name]["writes"] is True` for the three write tools; `execute()` now returns `{"error": ..., "reason_code": ...}` on a guard denial; `write_tool_names() -> tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_write_tools.py`:

```python
"""Write tools must be (a) marked, (b) guarded, and (c) unable to execute
when the guard denies -- the guard is non-bypassable, so a denial must
stop the write, not merely annotate it."""
from backend.app.agents import tools as toolreg
from backend.app.models import AttendanceRecord, User


def test_three_write_tools_are_registered():
    assert set(toolreg.write_tool_names()) == {
        "mark_attendance", "apply_timetable_change", "issue_eligibility_override"}


def test_write_tools_are_staff_only():
    for name in toolreg.write_tool_names():
        assert "student" not in toolreg.TOOLS[name]["roles"]


def test_student_write_attempt_is_blocked_and_writes_nothing(db, agents, base_data):
    student = db.query(User).filter_by(role="student").first()
    before = db.query(AttendanceRecord).count()
    out = toolreg.execute(db, agents, student, "mark_attendance",
                          {"section": "A", "subject_code": "X", "absentees": []})
    assert "error" in out
    assert out["reason_code"] == "NOT_PERMITTED"
    assert db.query(AttendanceRecord).count() == before


def test_read_tools_are_not_marked_as_writes():
    assert toolreg.TOOLS["get_attendance"].get("writes") is not True
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_write_tools.py -v
```

Expected: FAIL — `AttributeError: module ... has no attribute 'write_tool_names'`

- [ ] **Step 3: Extend the `tool` decorator with a `writes` flag**

In `backend/app/agents/tools.py`, replace the `tool` function:

```python
def tool(name, description, params=None, roles=ALL_ROLES, writes=False):
    def wrap(fn):
        TOOLS[name] = {
            "name": name, "description": description,
            "parameters": {"type": "object",
                           "properties": params or {},
                           "required": []},
            "roles": roles, "fn": fn, "writes": writes,
        }
        return fn
    return wrap


def write_tool_names() -> tuple[str, ...]:
    """Capabilities that mutate institutional state. These are the ones the
    graph must route through a human confirmation turn."""
    return tuple(n for n, t in TOOLS.items() if t.get("writes"))
```

- [ ] **Step 4: Route `execute()` through the guard**

Replace `execute()` in the same file:

```python
def execute(db, agents, user, name: str, args: dict,
            turn_id: str | None = None) -> dict:
    """Every capability call passes the guard first. Role checks used to
    live inline here; they now live in `guard.authorise`, which also logs
    the outcome. Nothing may reach a tool function without a verdict.
    """
    from ..guard import authorise
    t = TOOLS.get(name)
    if t is None:
        return {"error": f"unknown tool {name}", "reason_code": "NOT_PERMITTED"}
    verdict = authorise(db, user, name, args or {}, turn_id=turn_id)
    if not verdict.allowed:
        return {"error": verdict.detail or f"{name} refused",
                "reason_code": verdict.reason_code}
    try:
        return t["fn"](db, agents, user, args or {})
    except Exception as exc:  # tool errors go back to the LLM, not the user
        return {"error": f"{type(exc).__name__}: {exc}",
                "reason_code": "PRECONDITION_FAILED"}
```

- [ ] **Step 5: Add the three write tools**

Append to `backend/app/agents/tools.py`:

```python
# --------------------------------------------------------------- write tools
# The three MVRS writes (spec §7.1). Each mutates institutional state and is
# therefore gated by a human confirmation turn in the graph -- the guard
# decides whether a write may be PROPOSED; the human decides whether it happens.

@tool("mark_attendance",
      "Mark attendance for a section on a date, naming the absentees.",
      {"section": {"type": "string"}, "subject_code": {"type": "string"},
       "date": {"type": "string"}, "absentees": {"type": "array",
                                                 "items": {"type": "string"}}},
      roles=STAFF, writes=True)
def mark_attendance(db, agents, user, args):
    return agents["attendance_agent"].mark(
        db, section=args.get("section"), subject_code=args.get("subject_code"),
        date=args.get("date"), absentees=args.get("absentees") or [])


@tool("apply_timetable_change",
      "Move a class to a different slot after counterfactual scoring.",
      {"section": {"type": "string"}, "slot_id": {"type": "integer"},
       "new_day": {"type": "integer"}, "new_period": {"type": "integer"}},
      roles=("hod", "principal", "admin"), writes=True)
def apply_timetable_change(db, agents, user, args):
    return agents["timetable_agent"].apply_change(
        db, slot_id=args.get("slot_id"), new_day=args.get("new_day"),
        new_period=args.get("new_period"))


@tool("issue_eligibility_override",
      "Override a hall-ticket eligibility decision for one student, with a "
      "recorded reason. The highest-privilege write in the system.",
      {"usn": {"type": "string"}, "exam": {"type": "string"},
       "reason": {"type": "string"}},
      roles=("hod", "principal"), writes=True)
def issue_eligibility_override(db, agents, user, args):
    return agents["eligibility_agent"].override(
        db, usn=args.get("usn"), exam=args.get("exam"),
        reason=args.get("reason"), decided_by=user.username)
```

> The three agent methods (`AttendanceAgent.mark`, `TimetableAgent.apply_change`, `EligibilityAgent.override`) do not exist yet. Implement each as a minimal, transactional method on its agent, returning `{"applied": bool, "changed": [...], "detail": str}`. Read the existing read-path methods in the same file first and match their style, session handling and return shape.

- [ ] **Step 6: Run the full suite — the guard refactor touches every tool**

```bash
python -m pytest tests -q
```

Expected: all previously-passing tests still pass, plus the 4 new ones. `execute()` changed behaviour for *every* caller, so a regression here is the signal that matters most in this task.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/tools.py backend/app/agents/attendance.py backend/app/agents/timetable.py backend/app/agents/eligibility.py tests/test_write_tools.py
git commit -m "v5: three write tools, every capability routed through the guard

Role checks moved out of execute() and into guard.authorise, so there is
one authorisation path and every outcome is logged. Adds mark_attendance,
apply_timetable_change and issue_eligibility_override, each marked
writes=True so the graph knows to demand confirmation.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: LangGraph state and graph skeleton

**Files:**
- Create: `backend/app/graph/__init__.py`, `backend/app/graph/state.py`, `backend/app/graph/build.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Produces:
  - `TurnState` TypedDict with keys `messages`, `actor`, `turn_id`, `plan`, `outcomes`, `pending`, `answer`, `replans`
  - `build_graph(checkpointer=None) -> CompiledGraph`
  - `get_checkpointer()` — `PostgresSaver` when `MAWOS_DATABASE_URL` is Postgres, else `InMemorySaver`

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph.py`:

```python
"""The graph must compile and must bound re-planning at N=1 (D9)."""
from backend.app.graph.build import build_graph
from backend.app.graph.state import MAX_REPLANS, TurnState


def test_replan_depth_is_one():
    """D9 fixes re-plan depth at N=1. A deeper value is a decision that
    requires a recorded measurement, not a code edit."""
    assert MAX_REPLANS == 1


def test_state_declares_the_required_keys():
    required = {"messages", "actor", "turn_id", "plan",
                "outcomes", "pending", "answer", "replans"}
    assert required <= set(TurnState.__annotations__)


def test_graph_compiles_without_a_provider():
    """No credential must not prevent the graph from building -- degradation
    is visible, not fatal."""
    g = build_graph()
    assert g is not None
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_graph.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.graph'`

- [ ] **Step 3: Create the state module**

Create `backend/app/graph/__init__.py` (empty) and `backend/app/graph/state.py`:

```python
"""LangGraph turn state.

One turn = one user utterance and everything the system does in response.
The state is checkpointed, so an interrupted confirmation survives a
restart -- a write proposal is not lost because a process died.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage

#: D9 fixes re-plan depth at N=1. Raising it is a recorded decision backed
#: by a measurement, never a code edit (docs/v4/OPEN_DECISIONS.md D9).
MAX_REPLANS = 1


class TurnState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], operator.add]
    actor: str                     # username
    turn_id: str
    plan: list[dict[str, Any]]     # serialised AgentTask list
    outcomes: Annotated[list[dict[str, Any]], operator.add]
    pending: dict[str, Any]        # the write awaiting confirmation, if any
    answer: str
    replans: int
```

- [ ] **Step 4: Create the graph builder with placeholder-free stub nodes**

Create `backend/app/graph/build.py`:

```python
"""Graph assembly.

Node bodies live in `nodes.py`; this module only wires topology and
persistence, so the shape of the turn stays readable in one screen.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .. import config
from .state import TurnState


def get_checkpointer():
    """Postgres when deployed, in-memory for tests and local SQLite runs."""
    if config.DATABASE_URL.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver
        saver = PostgresSaver.from_conn_string(config.DATABASE_URL)
        saver.setup()
        return saver
    from langgraph.checkpoint.memory import InMemorySaver
    return InMemorySaver()


def build_graph(checkpointer=None):
    from . import nodes

    g = StateGraph(TurnState)
    g.add_node("plan", nodes.plan)
    g.add_node("clarify", nodes.clarify)
    g.add_node("guard", nodes.guard_step)
    g.add_node("confirm", nodes.confirm)
    g.add_node("execute", nodes.execute_step)
    g.add_node("observe", nodes.observe)
    g.add_node("synthesize", nodes.synthesize)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", nodes.after_plan,
                            {"clarify": "clarify", "guard": "guard"})
    g.add_edge("clarify", END)                 # a NeedInfo STOPS the turn
    g.add_conditional_edges("guard", nodes.after_guard,
                            {"confirm": "confirm", "execute": "execute",
                             "synthesize": "synthesize"})
    g.add_edge("confirm", "execute")
    g.add_edge("execute", "observe")
    g.add_conditional_edges("observe", nodes.after_observe,
                            {"plan": "plan", "synthesize": "synthesize"})
    g.add_edge("synthesize", END)

    return g.compile(checkpointer=checkpointer or get_checkpointer())
```

- [ ] **Step 5: Create `nodes.py` with honest minimal bodies**

Create `backend/app/graph/nodes.py`. Each node is deliberately thin here; Task 8 fills in guard/confirm and Task 9 fills in execute/synthesize.

```python
"""Turn nodes. Kept small and individually testable -- the graph's value is
that each step is inspectable, which is lost if a node does three things.
"""
from __future__ import annotations

from .state import MAX_REPLANS, TurnState


def plan(state: TurnState) -> dict:
    """Ask the model for a plan. With no provider, emit an empty plan so the
    turn degrades to the deterministic tier rather than failing."""
    return {"plan": state.get("plan") or [], "replans": state.get("replans", 0)}


def after_plan(state: TurnState) -> str:
    return "clarify" if state.get("pending", {}).get("question") else "guard"


def clarify(state: TurnState) -> dict:
    q = state.get("pending", {}).get("question", "")
    return {"answer": q}


def guard_step(state: TurnState) -> dict:
    return {}


def after_guard(state: TurnState) -> str:
    if not state.get("plan"):
        return "synthesize"
    return "confirm" if state.get("pending", {}).get("write") else "execute"


def confirm(state: TurnState) -> dict:
    return {}


def execute_step(state: TurnState) -> dict:
    return {}


def observe(state: TurnState) -> dict:
    return {}


def after_observe(state: TurnState) -> str:
    if state.get("replans", 0) < MAX_REPLANS and not state.get("outcomes"):
        return "plan"
    return "synthesize"


def synthesize(state: TurnState) -> dict:
    return {"answer": state.get("answer", "")}
```

- [ ] **Step 6: Run the tests**

```bash
python -m pytest tests/test_graph.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/graph tests/test_graph.py
git commit -m "v5: LangGraph turn state and graph topology

plan -> clarify | guard -> confirm -> execute -> observe -> synthesize,
with re-plan bounded at N=1 per D9. Postgres checkpointing when deployed,
in-memory for tests. Node bodies are thin; the next two tasks fill them.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Guard node and `interrupt()` confirmation

**Files:**
- Modify: `backend/app/graph/nodes.py`
- Test: `tests/test_graph_confirm.py`

**Interfaces:**
- Consumes: `guard.authorise` (Task 4), `write_tool_names()` (Task 6), `Refusal` (Task 5)
- Produces: `guard_step` writes `outcomes` entries of kind `refusal` for denials and populates `pending["write"]`; `confirm` raises `interrupt()` and consumes `Command(resume={"approve": bool})`

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_confirm.py`:

```python
"""A write must pause for a human. LangGraph's interrupt() is the pause;
the guard decides whether the write may even be PROPOSED."""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.app.graph.build import build_graph


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


def test_write_plan_pauses_for_confirmation(db, agents, base_data):
    g = build_graph(checkpointer=InMemorySaver())
    state = {"actor": "hod.aiml", "turn_id": "t1",
             "plan": [{"capability": "mark_attendance",
                       "args": {"section": "A", "subject_code": "X",
                                "absentees": []},
                       "agent": "attendance_agent", "actor": "hod.aiml"}],
             "pending": {"write": True}}
    out = g.invoke(state, config=_cfg("t1"))
    assert g.get_state(_cfg("t1")).next, "graph should be paused, not finished"


def test_rejecting_the_confirmation_performs_no_write(db, agents, base_data):
    from backend.app.models import AttendanceRecord
    g = build_graph(checkpointer=InMemorySaver())
    state = {"actor": "hod.aiml", "turn_id": "t2",
             "plan": [{"capability": "mark_attendance",
                       "args": {"section": "A", "subject_code": "X",
                                "absentees": []},
                       "agent": "attendance_agent", "actor": "hod.aiml"}],
             "pending": {"write": True}}
    before = db.query(AttendanceRecord).count()
    g.invoke(state, config=_cfg("t2"))
    g.invoke(Command(resume={"approve": False}), config=_cfg("t2"))
    assert db.query(AttendanceRecord).count() == before
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_graph_confirm.py -v
```

Expected: FAIL — the graph completes instead of pausing, because `confirm` is still a no-op.

- [ ] **Step 3: Implement `guard_step` and `confirm`**

In `backend/app/graph/nodes.py`, replace the two stubs:

```python
def guard_step(state: TurnState) -> dict:
    """Authorise every planned task before anything runs. A denial becomes a
    Refusal outcome; it never becomes an exception and never silently
    disappears."""
    from ..agents.tools import write_tool_names
    from ..contracts import Refusal
    from ..database import SessionLocal
    from ..guard import authorise
    from ..models import User

    writes = set(write_tool_names())
    refusals, allowed, needs_confirm = [], [], False
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=state["actor"]).one()
        for task in state.get("plan", []):
            v = authorise(db, user, task["capability"], task.get("args", {}),
                          turn_id=state.get("turn_id"))
            if not v.allowed:
                refusals.append(Refusal(agent=task.get("agent", ""),
                                        reason_code=v.reason_code,
                                        detail=v.detail).model_dump())
                continue
            allowed.append(task)
            if task["capability"] in writes:
                needs_confirm = True
        db.commit()
    finally:
        db.close()

    pending = dict(state.get("pending") or {})
    pending["write"] = needs_confirm
    return {"plan": allowed, "outcomes": refusals, "pending": pending}


def confirm(state: TurnState) -> dict:
    """Pause for a human. The value passed to Command(resume=...) becomes
    this call's return value (LangGraph HITL)."""
    from langgraph.types import interrupt

    proposal = [{"capability": t["capability"], "args": t.get("args", {})}
                for t in state.get("plan", [])]
    decision = interrupt({"action": "confirm_write", "proposed": proposal,
                          "message": "Apply these changes?"})
    if not (decision or {}).get("approve"):
        return {"plan": [], "answer": "Cancelled. Nothing was changed."}
    return {}
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_graph_confirm.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run the full suite**

```bash
python -m pytest tests -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/nodes.py tests/test_graph_confirm.py
git commit -m "v5: guard node and interrupt-based write confirmation

The guard authorises every planned task before anything runs; denials
become Refusal outcomes rather than exceptions. Writes then pause on
LangGraph's interrupt() until a human approves. Rejecting the
confirmation clears the plan, so a declined write performs no write.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Trace persistence

**Files:**
- Create: `backend/app/trace.py`
- Modify: `backend/app/graph/nodes.py`
- Test: `tests/test_trace.py`

**Interfaces:**
- Produces: `record(db, turn_id: str, step: int, kind: str, actor: str, verdict: str = "", payload: dict | None = None, latency_ms: float = 0.0) -> None` and `steps_for(db, turn_id) -> list[TraceRecord]`
- `kind` must be one of `plan | delegate | tool | guard | gate | clarify | confirm | synthesise` (matching `TraceRecord`'s documented set)

- [ ] **Step 1: Write the failing test**

Create `tests/test_trace.py`:

```python
"""The trace is simultaneously the debugging story, the explainability
feature and the evaluation instrument -- so every step must land in order."""
import pytest

from backend.app import trace


def test_steps_are_returned_in_order(db, base_data):
    for i, kind in enumerate(["plan", "guard", "tool", "synthesise"]):
        trace.record(db, "turn-x", i, kind, actor="orchestrator_agent")
    db.commit()
    got = trace.steps_for(db, "turn-x")
    assert [r.kind for r in got] == ["plan", "guard", "tool", "synthesise"]
    assert [r.step for r in got] == [0, 1, 2, 3]


def test_unknown_kind_is_rejected(db, base_data):
    with pytest.raises(ValueError):
        trace.record(db, "turn-y", 0, "not-a-kind", actor="x")


def test_payload_roundtrips_as_json(db, base_data):
    trace.record(db, "turn-z", 0, "tool", actor="get_attendance",
                 payload={"pct": 71.0})
    db.commit()
    assert trace.steps_for(db, "turn-z")[0].payload_dict() == {"pct": 71.0}
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_trace.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.trace'`

- [ ] **Step 3: Implement**

Create `backend/app/trace.py`:

```python
"""Per-turn trace persistence.

`TraceRecord` is the evaluation instrument, not a log. A step that is not
recorded cannot be measured, and a number that cannot be regenerated may
not be reported (CLAUDE.md).
"""
from __future__ import annotations

import json

from .models import TraceRecord

KINDS = ("plan", "delegate", "tool", "guard", "gate",
         "clarify", "confirm", "synthesise")


def record(db, turn_id: str, step: int, kind: str, actor: str,
           verdict: str = "", payload: dict | None = None,
           latency_ms: float = 0.0) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown trace kind {kind!r}; expected one of {KINDS}")
    db.add(TraceRecord(turn_id=turn_id, step=step, kind=kind, actor=actor,
                       verdict=verdict, latency_ms=latency_ms,
                       payload=json.dumps(payload or {}, default=str)))


def steps_for(db, turn_id: str) -> list[TraceRecord]:
    return (db.query(TraceRecord)
              .filter_by(turn_id=turn_id)
              .order_by(TraceRecord.step)
              .all())
```

Add to `TraceRecord` in `backend/app/models.py`:

```python
    def payload_dict(self) -> dict:
        import json
        try:
            return json.loads(self.payload or "{}")
        except ValueError:
            return {}
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_trace.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Wire tracing into the guard and confirm nodes**

In `guard_step`, after each `authorise` call, add:

```python
            trace.record(db, state.get("turn_id", ""), len(refusals) + len(allowed),
                         "guard", actor=task["capability"],
                         verdict="allowed" if v.allowed else "denied",
                         payload={"reason_code": v.reason_code})
```

with `from .. import trace` at the top of the function's import block.

- [ ] **Step 6: Run the full suite and commit**

```bash
python -m pytest tests -q
git add backend/app/trace.py backend/app/models.py backend/app/graph/nodes.py tests/test_trace.py
git commit -m "v5: per-turn trace persistence

Every plan, guard verdict, tool call and synthesis step lands in
trace_records in order. This is the evaluation instrument, not a log -- an
unrecorded step cannot be measured.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: MCP server over the same guarded tools

The load-bearing property: an external LLM gets **no privilege the internal planner lacks**. The MCP server must call `tools.execute()`, never a tool function directly.

**Files:**
- Create: `backend/app/mcp_server.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Produces: `build_mcp_server(actor_username: str)` returning a configured `FastMCP` instance; `mcp_tool_names(role: str) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_mcp.py`:

```python
"""Guard parity: the same attack must produce the same verdict whether the
internal planner or an external MCP client drives the tools. A divergence
is a finding, not a bug to hide."""
from backend.app import mcp_server
from backend.app.agents import tools as toolreg
from backend.app.models import User


def test_mcp_exposes_only_role_permitted_tools(db, base_data):
    student_tools = set(mcp_server.mcp_tool_names("student"))
    assert "mark_attendance" not in student_tools
    assert "get_attendance" in student_tools


def test_mcp_denial_matches_internal_denial(db, agents, base_data):
    """Same actor, same capability, same verdict -- via both paths."""
    student = db.query(User).filter_by(role="student").first()
    internal = toolreg.execute(db, agents, student, "mark_attendance", {})
    external = mcp_server.call_as(db, agents, student, "mark_attendance", {})
    assert internal["reason_code"] == external["reason_code"]
    assert ("error" in internal) == ("error" in external)


def test_mcp_cannot_bypass_the_guard(db, agents, base_data):
    from backend.app.models import AttendanceRecord
    student = db.query(User).filter_by(role="student").first()
    before = db.query(AttendanceRecord).count()
    mcp_server.call_as(db, agents, student, "mark_attendance",
                       {"section": "A", "subject_code": "X", "absentees": []})
    assert db.query(AttendanceRecord).count() == before
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_mcp.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.mcp_server'`

- [ ] **Step 3: Implement**

Create `backend/app/mcp_server.py`:

```python
"""MCP surface.

Exposes MAWOS's capabilities to an external client (Claude Desktop,
ChatGPT) through exactly the same guarded path the internal planner uses.
`call_as` delegates to `tools.execute`, which calls `guard.authorise` --
there is no second authorisation path, and adding one would invalidate the
guard-parity claim this module exists to test.
"""
from __future__ import annotations

from .agents import get_agents
from .agents import tools as toolreg
from .database import SessionLocal
from .models import User


def mcp_tool_names(role: str) -> list[str]:
    return [t["name"] for t in toolreg.TOOLS.values() if role in t["roles"]]


def call_as(db, agents, user, name: str, args: dict) -> dict:
    """The single external entry point. Deliberately a thin delegation."""
    return toolreg.execute(db, agents, user, name, args or {})


def build_mcp_server(actor_username: str):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("mawos")
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=actor_username).one()
        role = user.role
    finally:
        db.close()

    for spec in list(toolreg.TOOLS.values()):
        if role not in spec["roles"]:
            continue

        def _make(tool_name: str):
            def _call(**kwargs) -> dict:
                session = SessionLocal()
                try:
                    actor = session.query(User).filter_by(
                        username=actor_username).one()
                    out = call_as(session, get_agents(), actor, tool_name, kwargs)
                    session.commit()
                    return out
                finally:
                    session.close()
            return _call

        server.add_tool(_make(spec["name"]), name=spec["name"],
                        description=spec["description"])
    return server
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/test_mcp.py -v
```

Expected: 3 passed. If `FastMCP.add_tool`'s signature differs in the installed `mcp` version, read `python -c "from mcp.server.fastmcp import FastMCP; help(FastMCP.add_tool)"` and adapt — do not work around it by calling tool functions directly, which would defeat the test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp_server.py tests/test_mcp.py
git commit -m "v5: MCP server over the same guarded tools

An external LLM gets no privilege the internal planner lacks: call_as
delegates to tools.execute, which calls guard.authorise. There is
deliberately no second authorisation path -- adding one would invalidate
the guard-parity claim these tests exist to check.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: Containerise and deploy

Deploy on day 3–4 of the schedule, not at the end. Deployment discovers problems; discover them early.

**Files:**
- Create: `Dockerfile`, `render.yaml`, `.dockerignore`
- Modify: `backend/app/config.py` (production JWT guard)

**Interfaces:**
- Produces: a container serving `uvicorn` on `$PORT`; `MAWOS_DATABASE_URL` and `GROQ_API_KEY` supplied by the host environment

- [ ] **Step 1: Refuse to boot in production with the dev JWT secret**

In `backend/app/config.py`, after `JWT_SECRET`:

```python
# A real secret is MUST-tier for the deployed instance
# (docs/v4/02_SCOPE.md). Failing loudly at boot beats shipping the
# published dev secret to a public URL.
ENV = os.getenv("MAWOS_ENV", "dev")
if ENV == "production" and JWT_SECRET == "mawos-dev-secret-change-in-prod":
    raise RuntimeError(
        "MAWOS_JWT_SECRET must be set to a real secret when MAWOS_ENV=production")
```

- [ ] **Step 2: Write the Dockerfile**

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render supplies $PORT; default keeps `docker run` usable locally.
ENV PORT=8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 3: Write `.dockerignore`**

```
.git
.venv
venv
__pycache__
*.pyc
mawos.db
mawos.db.*
node_modules
teacher-erp-with-timetable-simulation
evaluation/results
docs
.env
.env.*
```

- [ ] **Step 4: Write `render.yaml`**

```yaml
services:
  - type: web
    name: mawos
    runtime: docker
    plan: free
    healthCheckPath: /health
    envVars:
      - key: MAWOS_ENV
        value: production
      - key: MAWOS_JWT_SECRET
        generateValue: true
      - key: MAWOS_DATABASE_URL
        fromDatabase:
          name: mawos-db
          property: connectionString
      - key: GROQ_API_KEY
        sync: false          # set by hand in the dashboard; never in git
databases:
  - name: mawos-db
    plan: free
```

- [ ] **Step 5: Verify the container builds and serves locally**

```bash
docker build -t mawos:dev .
docker run --rm -e PORT=8000 -e MAWOS_ENV=dev -p 8000:8000 mawos:dev
curl -sf http://localhost:8000/health && echo " OK"
```

Expected: `/health` returns 200. If that route does not exist, add a minimal one to `backend/app/main.py` returning `{"status": "ok", "tier": llm_provider.active_provider()["label"]}` — Render's health check needs it and the active tier should be visible.

- [ ] **Step 6: Deploy and record the URL**

Push the branch, connect the repo in Render, set `GROQ_API_KEY` in the dashboard, deploy. Then add the live URL to `README.md`.

> Render free services spin down when idle (~50 s cold start). **Warm the service with one request before any demo.**

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore render.yaml backend/app/config.py README.md
git commit -m "v5: containerise and deploy to Render on Postgres

Production refuses to boot with the dev JWT secret. Migrations run on
container start. Postgres and the provider key come from the host
environment; no secret is in git.

Render free services spin down when idle -- warm before demos.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**

| Spec §7.1 MUST | Task |
|---|---|
| LangGraph runtime, full node chain | 7, 8 |
| PostgresSaver checkpointing | 7 (`get_checkpointer`) |
| Typed delegation contract | 5 |
| Deterministic guard, logs allowed + denied | 4 |
| 3 write tools with `interrupt()` confirmation | 6, 8 |
| End-to-end write cascade ≥3 agents | 6 (agent methods) + 8 |
| MCP server over the same guarded tools | 10 |
| D1 closed by measurement, M7 re-registered first | 1, 2 |
| Deployed on a public URL, on Postgres | 11 |
| Per-turn trace persisted | 9 |

**Known gaps, stated rather than hidden:**
- **Provenance gate wiring into synthesis** is not a task here. `backend/app/provenance.py` exists and is on by default; wiring it into the new `synthesize` node is a follow-up once that node produces real free text (currently a pass-through in Task 7).
- **The `synthesize` and `plan` nodes remain thin.** They become real once Task 2 names a provider. Their full implementation is deliberately deferred rather than written speculatively against an unchosen model.
- **SHOULD-tier items** — Next.js console, rooms as a decision variable, the degradation run, the MCP parity suite, GitHub Actions — are out of scope for this plan by spec §7.2 and belong to the teammate plans.

**Type consistency:** `authorise(db, user, capability, args, turn_id)` is used identically in Tasks 4, 6 and 8. `write_tool_names()` is defined in Task 6 and consumed in Task 8. `trace.record(...)` is defined in Task 9 and consumed in Task 9 Step 5. `GuardVerdict.reason_code` values match `guard.REASON_*` constants and the `reason_code` key returned by `execute()` in Task 6 and asserted in Task 10.

**Ordering constraint:** Task 2 Step 5 is a hard gate. Do not start Task 3 until D1's outcome is recorded in `OPEN_DECISIONS.md`, whichever way it went.
