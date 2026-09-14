"""Runtime LLM adapter for v5.

One OpenAI-compatible client serves every candidate D1 considered (Groq,
OpenRouter, GitHub Models), mirroring `evaluation/probe/providers.py`'s
OpenAICompatibleProvider. Swapping provider for the degradation run is a
config change, never a code change.

A missing credential is NOT fatal. It degrades the system to the
deterministic tier, which stays the primary tier by design -- the lexicon
answers ~90% of queries and is never called a fallback (CLAUDE.md).

D1 (the provider) is OPEN, not closed. The configured default
(config.LLM_MODEL / config.LLM_LABEL) was measured INELIGIBLE by the R0.5
gate: M2 correct-tool 75.0% against a >=85% threshold, deterministic across
all 3 seeds (evaluation/results/v5_gates/r05_provider_hosted.{json,md}).
It is wired in anyway as a deliberate, recorded project decision -- see
docs/v4/OPEN_DECISIONS.md, D1, "Runtime default configured to the failing
candidate (2026-09-14)". Do not read this module's existence as D1 having
closed.
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
