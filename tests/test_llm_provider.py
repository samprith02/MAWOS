"""The runtime adapter must be provider-agnostic and must never crash the
app when no credential is present -- degradation is visible, not fatal
(docs/v4/03_LLM_LAYER.md fallback ladder).

These tests must pass regardless of whether a real GROQ_API_KEY is present
in the environment (e.g. from a developer's .env) -- monkeypatch always
sets/removes the variable explicitly rather than relying on ambient state.
"""
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
