"""P4 — the confidence-gated hybrid router.

The lexicon answers every query. Its margin (top-1 minus top-2 intent
score) is its own confidence. Only when that margin is at or below τ is
the query escalated to the LLM, whose tool choice then replaces the
lexicon's.

Why this replaces v2's behaviour
--------------------------------
v2 chose a tier on **Ollama reachability**: LLM if the daemon answered,
keyword otherwise. That is an availability switch, not a routing policy —
with Ollama up, every query paid the full LLM cost, including the ~90%
the lexicon already answers correctly and faster.

Two measurements motivate the change, both in `evaluation/results/`:

* `v3_gates/p05_gate.json` — AUC(margin → lexicon error) = **0.983**. The
  lexicon's confidence is an almost perfect detector of its own failures.
  It fails when nothing matches and it silently falls back to
  `profile_query`.
* `v3_gates/p4_router.json` — the whole τ curve. Every lexicon error the
  3B can repair sits at **margin 0**. Escalating anything above that
  fixes nothing further and only breaks answers the lexicon had right.

So τ = 0 is not a tuned number so much as a structural one: escalate
exactly the queries where the keyword classifier matched nothing.

Honesty about what is established
---------------------------------
On dev the hybrid scores 94.8% against the lexicon's 89.8%. Dev is
contaminated by construction — the lexicon was tuned on these queries —
and neither the bootstrap CI nor McNemar clears conventional
significance at n=108. The dev numbers chose τ. They are not the result.
The held-out evaluation (P5) is, and it runs **once** against the frozen
config beside this file.
"""
import json
import time
from pathlib import Path

from . import llm

CONFIG_PATH = Path(__file__).with_name("router_config.json")


def _load() -> dict:
    """Frozen at P4 by evaluation/tune_router.py. Never tuned at runtime."""
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


_CFG = _load()
TAU: float = _CFG["tau"]


class Decision:
    """Why the router did what it did — logged, and shown in the UI."""

    def __init__(self, tier: str, margin: float, escalated: bool,
                 reason: str, fallback_from: str | None = None):
        self.tier = tier                    # "lexicon" | "llm"
        self.margin = margin
        self.escalated = escalated
        self.reason = reason
        self.fallback_from = fallback_from  # set when escalation failed

    def as_dict(self) -> dict:
        return {"tier": self.tier, "margin": self.margin,
                "tau": TAU, "escalated": self.escalated,
                "reason": self.reason, "fallback_from": self.fallback_from}


def should_escalate(margin: float) -> bool:
    """The entire policy. `margin <= tau`, exactly as tuned and as scored.

    Ties escalate together because a deployed router sets a threshold, not
    a quota — the same reason the tuning curve only reports achievable
    operating points.
    """
    return margin <= TAU


def decide(query: str) -> tuple[llm.IntentResult, Decision]:
    """Classify with the lexicon and decide whether the LLM is needed.

    Returns the lexicon's own result regardless, so the caller always has
    a usable answer if escalation is impossible or fails.
    """
    r = llm.classify_keyword(query)
    if not should_escalate(r.margin):
        return r, Decision("lexicon", r.margin, False,
                           f"margin {r.margin:.2f} > tau {TAU:.2f}")
    if not llm.check_ollama():
        return r, Decision("lexicon", r.margin, False,
                           "escalation warranted but no LLM available",
                           fallback_from="llm")
    return r, Decision("llm", r.margin, True,
                       f"margin {r.margin:.2f} <= tau {TAU:.2f}")


def expected_cost_ms(escalation_rate: float, llm_ms: float,
                     lexicon_ms: float = 0.06) -> float:
    """Mean per-query cost of the policy. Used by the evaluation harness."""
    return escalation_rate * llm_ms + lexicon_ms


class Stats:
    """Live escalation rate, so the deployed rate can be compared to dev.

    A deployed rate far from the dev 10.2% means real traffic does not
    look like the benchmark — which is a finding about the benchmark, and
    worth surfacing rather than hiding.
    """

    def __init__(self):
        self.total = 0
        self.escalated = 0
        self.escalation_failed = 0
        self._started = time.time()

    def record(self, d: Decision) -> None:
        self.total += 1
        self.escalated += d.escalated
        self.escalation_failed += d.fallback_from is not None

    def as_dict(self) -> dict:
        rate = self.escalated / self.total if self.total else 0.0
        return {"queries": self.total, "escalated": self.escalated,
                "escalation_rate": rate,
                "escalation_rate_dev": _CFG["dev_escalation_rate"],
                "escalation_failed": self.escalation_failed,
                "tau": TAU, "model": _CFG["model"],
                "uptime_s": round(time.time() - self._started, 1)}


stats = Stats()
