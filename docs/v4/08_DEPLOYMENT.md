# 08 — Deployment Architecture

Covers R0 requirement **10**.

**Target:** a system that can be demonstrated from a URL by someone who is not sitting at the
development laptop — not one that only runs locally.

---

## 1. Why v3 is not deployable

| Property | Consequence |
|---|---|
| SQLite file at the repository root | Single-writer; the server holds the file, so a delete silently fails and leaves a contaminated DB — a footgun documented in `CLAUDE.md` because it has cost real time |
| 30 MB seeded database | Gitignored, so a fresh clone must reseed for ~60 s before it works |
| Local Ollama, portable Windows install | The demo depends on a specific laptop, a specific driver, and a manually started process |
| 2 GB model on a 6 GB laptop GPU | The `nvlddmkm` driver has dropped mid-session repeatedly; a 7B model only reached 81.7% GPU residency |
| `Base.metadata.create_all` only | No migration path; a deployed schema cannot evolve |
| JWT secret defaults to a literal string | `config.JWT_SECRET = "mawos-dev-secret-change-in-prod"` — unsafe on any public host |
| No rate limiting or CORS configuration | Unsafe on any public host |

The GPU point is worth stating plainly: this project has already lost days to driver dropouts
and had 14 consecutive background captures killed. **Betting the final demonstration purely on
local inference is the riskier choice, not the safer one** — which is why the fallback ladder
in `03_LLM_LAYER.md` §3 is mandatory in the architecture rather than a convenience.

---

## 2. Target topology

```
        ┌──────────────────────────┐
        │  Browser                 │
        └────────────┬─────────────┘
                     │ HTTPS
        ┌────────────▼─────────────┐
        │  Static frontend         │   existing SPA, served by the backend
        │  (or a static host)      │   in MVRS — a separate host is optional
        └────────────┬─────────────┘
                     │ REST + NDJSON
        ┌────────────▼─────────────┐
        │  FastAPI backend         │   container, free-tier PaaS or one small VM
        │  agents · guard · bus    │
        └──────┬─────────────┬─────┘
               │             │
   ┌───────────▼──┐   ┌──────▼─────────────────┐
   │ PostgreSQL   │   │  LLM provider          │
   │ managed free │   │  Tier 1 hosted         │
   │ tier         │   │  Tier 2 local (opt.)   │
   └──────────────┘   │  Tier 3 deterministic  │
                      └────────────────────────┘
```

**MVRS serves the frontend from the backend.** The SPA is static files behind
`StaticFiles` — exactly as today — so no second deployment target is needed. A separate
static host is a NICE-tier optimisation, not a requirement.

---

## 3. Component decisions

| Layer | Decision | Rationale |
|---|---|---|
| **Backend** | FastAPI, unchanged | Already correct. Add agent endpoints and NDJSON streaming |
| **Database** | **PostgreSQL** deployed, SQLite for local dev, in-memory SQLite for tests | Models are already SQLAlchemy; this is configuration plus Alembic. Eliminates the file-lock bug class entirely |
| **Migrations** | **Alembic** — MUST-tier | `create_all` plus a hand-written reseed helper cannot evolve a deployed database |
| **Frontend** | **Extend the existing vanilla SPA** | Three targeted panels deliver the demo. The Next.js rewrite is NICE-tier (`02_SCOPE.md` §2.3) and is not on the critical path |
| **LLM** | Env-selected provider behind the abstraction; key server-side only | Never in the browser, never in the repository, never in the client bundle |
| **Hosting** | Container on a free-tier PaaS, or one small VM | Free-tier feasible either way |
| **Secrets** | Environment variables; **startup fails if `JWT_SECRET` is unset in production** | A default secret on a public host is a real vulnerability, not a style issue |

**Why not the Next.js rewrite.** It is the largest single effort item in the whole rework and
sits on no claim. The three panels MVRS needs — chat with clarification and confirmation, the
agent-trace timeline, and the solver stream — are additions to a working 665-line SPA. Doing
the rewrite instead would consume roughly the effort of the entire agent runtime, which *is*
the contribution. It stays available as upside; see `OPEN_DECISIONS.md` §D4.

---

## 4. Configuration

Everything environment-driven, following the existing `config.py` pattern:

| Variable | Purpose | Production requirement |
|---|---|---|
| `MAWOS_DATABASE_URL` | SQLite or Postgres DSN | Postgres |
| `MAWOS_JWT_SECRET` | Token signing | **Must be set — no default** |
| `MAWOS_LLM_PROVIDER` | Which provider implementation | Set |
| `MAWOS_LLM_API_KEY` | Provider credential | Set, server-side only |
| `MAWOS_LLM_FALLBACK` | Tier-2 endpoint, optional | Optional |
| `MAWOS_INSTITUTION_CONFIG` | Path to `institution.yaml` | Set |
| `MAWOS_ENV` | `dev` / `prod` — gates the secret check and debug output | Set |
| `MAWOS_RATE_LIMIT` | Requests per minute per principal | Set |
| `MAWOS_CORS_ORIGINS` | Allowed origins | Set explicitly, never `*` |

---

## 5. Security posture

Appropriate for a research prototype handling synthetic data on a public URL. Stated
explicitly so the boundary is not overclaimed.

**In scope (MUST):**

1. Real JWT secret required in production; startup fails loudly without it.
2. **All authorisation through the guard layer**, which is deterministic and prompt-independent
   (`01_ARCHITECTURE.md` §7).
3. Rate limiting per principal — protects both the host and the LLM budget.
4. Explicit CORS origins.
5. LLM keys server-side only; never reachable from the client.
6. **Injected instructions in institutional data are treated as data.** Agents never receive
   the raw user message, and tool payloads are never interpreted as instructions. Tested by
   the adversarial suite (`06_BENCHMARK.md` §5).
7. Conversations are scoped records — a student cannot read another student's conversation.

**Explicitly out of scope**, and named as such in the write-up: password policy and reset
flows, MFA, audit-log tamper-resistance, encryption at rest, penetration testing, GDPR/DPDP
compliance machinery. The data is synthetic; the deployment is a demonstration.

---

## 6. Behaviour when the LLM provider is unavailable

This will be asked at the viva, so the answer is architectural rather than reassuring.

| Failure | Behaviour |
|---|---|
| Tier 1 times out or rate-limits | Circuit breaker drops to Tier 2 if configured, else Tier 3. Banner updates. Turn continues |
| No provider at all | Tier 3. **The ERP remains fully usable** — dashboards, timetable, attendance, eligibility, and every REST route are unaffected, because none of them call the LLM |
| Provider returns malformed tool calls | Retry once, then degrade. Malformed calls are logged, not silently dropped |
| Provider available but slow | Per-turn latency budget; on exceeding it the turn degrades and says so |

**The property that matters:** the LLM is a *language and planning* layer, not a dependency of
the institution's operation. Every guard check, every tool, and the provenance gate behave
identically at every tier. Only language understanding degrades — and the banner says so
rather than hiding it.

**Tier 3 never fabricates.** Per `03_LLM_LAYER.md` §3.1 rule 3, it resolves to a known action,
offers the corresponding UI control, or says plainly that the assistant is unavailable. It
does **not** produce a confident natural-language answer by pattern matching, which is v3's
behaviour and the single largest reason the current system reads as a toy.

---

## 7. Deployment flow

1. Container image built from the repository.
2. Alembic migrations run on start.
3. If the database is empty, seed from `institution.yaml` — deterministic, so the deployed
   institution is byte-identical to the local one.
4. Health endpoint reports: database reachable, active LLM tier, agent count, migration
   revision.
5. Smoke test against the deployed URL: log in as each role, load each dashboard, run one
   benchmark task per category, and **confirm the ladder degrades visibly with the provider
   disabled**.

---

## 8. Demonstration risk

| Risk | Mitigation |
|---|---|
| No internet at the venue | Rehearse the full demo at Tier 2 at least once, and record a fallback walkthrough |
| Provider rate limit during the demo | Response cache; a scripted demo path with pre-warmed answers; Tier 2 ready |
| Free-tier cold start | Warm the instance before the session |
| Free tier will not hold Postgres | Fall back to SQLite on a persistent volume — the models are agnostic. `OPEN_DECISIONS.md` §D11 |
| Host disappears | The container runs locally against the same config; the URL is a convenience, not a dependency |

**Standing rule:** the demonstration must be rehearsed end to end on the **local** tier at
least once before any review. If it cannot be demonstrated without internet, the fallback
ladder is not actually working and that is a defect to fix, not a risk to accept.
