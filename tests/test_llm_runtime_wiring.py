"""The hosted provider is actually wired into the runtime — v5 spec §3.3,
step 5 ("only then wire the winner into the runtime").

Why this file exists
--------------------
`llm_provider.py` was built by Task 3 and then consumed by nothing: a grep
for `get_chat_model` found zero call sites under `backend/app`, and
`router.decide()` still gated escalation on `llm.check_ollama()`. The
deployed instance therefore reported "Local LLM not detected — lexicon
only" while holding a valid `GROQ_API_KEY`, because it was looking for a
daemon that cannot exist on Render. Every test here fails against that
state, which is the only reason to trust them.

The load-bearing distinction these tests protect
------------------------------------------------
*Whether* a query escalates is the P4 policy (`margin <= tau`) and is
frozen. *Whether an escalation can be served* is availability. v5 changed
only the second. `test_escalation_policy_is_untouched_by_the_provider_swap`
is the guard on that line.
"""
import json

import pytest

from backend.app import config, llm, router


# --------------------------------------------------------------- P4 policy
def test_escalation_policy_is_untouched_by_the_provider_swap():
    """The provider swap must not move tau or the rule that reads it.

    `router_config.json` is a frozen instrument (PROTOCOL §9.3) and is
    hashed by `evaluation/freeze_manifest.py`. If wiring a hosted provider
    ever requires editing it, the wiring is wrong.
    """
    cfg = router._load()
    assert cfg["tau"] == router.TAU
    assert cfg["escalate_when"] == "margin <= tau"
    assert router.should_escalate(router.TAU)
    assert not router.should_escalate(router.TAU + 0.5)
    # The frozen record still names the model tau was SELECTED against.
    # It is deliberately not the model now serving traffic.
    assert cfg["model"] == "qwen2.5:3b-instruct"


def test_router_escalates_via_hosted_tier_without_ollama(monkeypatch):
    """THE REGRESSION. A low-margin query must escalate when the hosted
    provider is up and Ollama is absent — which is exactly the deployed
    configuration, and exactly what `check_ollama()` gating got wrong."""
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: True)
    monkeypatch.setattr(llm, "check_ollama", lambda force=False: False)
    _, decision = router.decide("qwertyuiop zxcvbnm")
    assert decision.margin == 0.0          # the policy says escalate
    assert decision.escalated is True      # and availability now agrees
    assert decision.tier == "llm"
    assert decision.fallback_from is None


def test_router_degrades_visibly_when_no_tier_is_reachable(monkeypatch):
    """Degradation must stay *visible* — a lexicon answer that silently
    replaces a warranted escalation is indistinguishable from a confident
    lexicon hit, which would corrupt the escalation-rate statistic."""
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: False)
    monkeypatch.setattr(llm, "check_ollama", lambda force=False: False)
    _, decision = router.decide("qwertyuiop zxcvbnm")
    assert decision.escalated is False
    assert decision.tier == "lexicon"
    assert decision.fallback_from == "llm"


def test_high_confidence_queries_never_escalate_even_with_a_provider(monkeypatch):
    """Lexicon-first is the whole point: a provider being available must
    not pull confident queries onto the LLM. That was the v2 defect."""
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: True)
    _, decision = router.decide("What is my attendance percentage?")
    assert decision.escalated is False
    assert decision.tier == "lexicon"


def test_stats_report_serving_and_tuned_models_separately(monkeypatch):
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: True)
    d = router.Stats().as_dict()
    assert d["model_tuned_against"] == "qwen2.5:3b-instruct"
    assert d["model_serving"] == config.LLM_LABEL
    assert d["model_serving"] != d["model_tuned_against"]


# ------------------------------------------------------------- tier report
def test_active_tier_names_the_hosted_provider(monkeypatch):
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: True)
    t = llm.active_tier()
    assert t["available"] is True
    assert t["kind"] == "hosted"
    assert t["label"] == config.LLM_LABEL
    assert "ollama" not in t["label"].lower()


def test_active_tier_falls_back_to_local_then_to_none(monkeypatch):
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: False)
    monkeypatch.setattr(llm, "check_ollama", lambda force=False: True)
    assert llm.active_tier()["kind"] == "local"
    monkeypatch.setattr(llm, "check_ollama", lambda force=False: False)
    t = llm.active_tier()
    assert t["kind"] == "none" and t["available"] is False
    assert t["label"] == "lexicon-only"


def test_ai_mode_payload_names_the_provider(monkeypatch):
    """The badge reads these two fields. `ai_mode` keeps its v3 values so
    the SPA needs no migration; `ai_provider` is what stops the UI from
    asserting "Ollama" on an instance that has never had one."""
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: True)
    payload = llm.ai_mode()
    assert payload == {"ai_mode": "llm", "ai_provider": config.LLM_LABEL}
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: False)
    monkeypatch.setattr(llm, "check_ollama", lambda force=False: False)
    assert llm.ai_mode()["ai_mode"] == "lexicon"


def test_check_hosted_is_false_and_silent_without_a_credential(monkeypatch):
    """No credential must mean no network call at all — the app has to boot
    on a machine with no outbound access."""
    monkeypatch.setattr(llm, "_hosted_available", None, raising=False)
    monkeypatch.delenv(config.LLM_API_KEY_ENV, raising=False)

    def _explode(*a, **k):
        raise AssertionError("check_hosted made a network call with no key")

    monkeypatch.setattr(llm.httpx, "get", _explode)
    assert llm.check_hosted(force=True) is False


def test_check_hosted_rejects_a_credential_the_provider_refuses(monkeypatch):
    """A key that is SET but REJECTED must report unavailable. Reporting
    "available" off mere key presence would light the badge for a tier the
    system cannot serve."""
    monkeypatch.setenv(config.LLM_API_KEY_ENV, "not-a-real-key")

    class _Resp:
        status_code = 401

    monkeypatch.setattr(llm.httpx, "get", lambda *a, **k: _Resp())
    assert llm.check_hosted(force=True) is False


# ------------------------------------------------- OpenAI schema translation
# Each rule below was an observed HTTP 400 from Groq during the D1 probe.

def _assistant_turn():
    """The exact shape `orchestrator._handle_llm` appends after round 1."""
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": "get_attendance",
                                         "arguments": {"usn": "1VT23AI049"}},
                            "_meta": {"id": "call_abc123"}}]}


def test_tool_call_arguments_are_serialised_to_a_json_string():
    out = llm._to_openai_messages([_assistant_turn()])
    call = out[0]["tool_calls"][0]
    assert isinstance(call["function"]["arguments"], str)
    assert json.loads(call["function"]["arguments"]) == {"usn": "1VT23AI049"}


def test_every_tool_call_carries_id_and_type():
    call = llm._to_openai_messages([_assistant_turn()])[0]["tool_calls"][0]
    assert call["type"] == "function"
    assert call["id"] == "call_abc123"


def test_tool_result_echoes_the_providers_call_id():
    """Rule 3, and the one that breaks multi-round conversations. The
    orchestrator's `role: tool` message carries no id of its own, so it has
    to be paired here or round 2 is rejected."""
    msgs = [_assistant_turn(),
            {"role": "tool", "name": "get_attendance", "content": "{}"}]
    out = llm._to_openai_messages(msgs)
    assert out[1]["tool_call_id"] == "call_abc123"


def test_messages_without_tool_calls_pass_through_unchanged():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    assert llm._to_openai_messages(msgs) == msgs


def test_openai_reply_is_normalised_to_the_shape_the_orchestrator_reads():
    reply = llm._from_openai_message({
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "call_xyz", "type": "function",
                        "function": {"name": "get_fees",
                                     "arguments": '{"usn": "1VT23AI037"}'}}]})
    call = reply["tool_calls"][0]
    assert call["function"]["arguments"] == {"usn": "1VT23AI037"}
    assert call["_meta"]["id"] == "call_xyz"
    assert reply["content"] == ""


@pytest.mark.parametrize("bad", ["", "not json", "[1,2]", None])
def test_malformed_tool_arguments_degrade_to_an_empty_dict(bad):
    """A 75%-correct-tool model (D1's measured M2) will produce malformed
    arguments. That must reach the guard as `{}` and be refused there — it
    must never raise out of the LLM layer."""
    reply = llm._from_openai_message({
        "tool_calls": [{"id": "c", "function": {"name": "get_fees",
                                                "arguments": bad}}]})
    assert reply["tool_calls"][0]["function"]["arguments"] == {}


def test_round_trip_preserves_the_id_across_a_full_turn():
    """The integration invariant: a provider id survives reply → append →
    tool result → next request. Losing it is an HTTP 400 on round 2."""
    reply = llm._from_openai_message({
        "tool_calls": [{"id": "call_round_trip", "type": "function",
                        "function": {"name": "get_marks", "arguments": "{}"}}]})
    prepared = llm._to_openai_messages(
        [{"role": "user", "content": "marks?"}, reply,
         {"role": "tool", "name": "get_marks", "content": "{}"}])
    assert prepared[1]["tool_calls"][0]["id"] == "call_round_trip"
    assert prepared[2]["tool_call_id"] == "call_round_trip"


# ----------------------------------------------------------------- dispatch
def test_chat_prefers_hosted_even_when_ollama_is_also_running(monkeypatch):
    """A developer with Ollama still resident must be served by the same
    tier the deployed instance uses, or local testing proves nothing."""
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: True)
    monkeypatch.setattr(llm, "check_ollama", lambda force=False: True)
    monkeypatch.setattr(llm, "chat_hosted", lambda m, t=None: {"tier": "hosted"})
    monkeypatch.setattr(llm, "chat_ollama", lambda m, t=None: {"tier": "local"})
    assert llm.chat([], None) == {"tier": "hosted"}


def test_chat_returns_none_when_no_tier_is_available(monkeypatch):
    monkeypatch.setattr(llm, "check_hosted", lambda force=False: False)
    monkeypatch.setattr(llm, "check_ollama", lambda force=False: False)
    assert llm.chat([], None) is None


def test_hosted_failures_return_none_rather_than_raising(monkeypatch):
    """HTTP 429 is expected on a free tier under demo load. It must degrade
    to the lexicon answer, not surface as a 500."""
    monkeypatch.setenv(config.LLM_API_KEY_ENV, "k")

    def _rate_limited(*a, **k):
        raise RuntimeError("HTTP 429 Too Many Requests")

    monkeypatch.setattr(llm.httpx, "post", _rate_limited)
    assert llm.chat_hosted([{"role": "user", "content": "hi"}]) is None


# ------------------------------------------------------------- the SPA path
def test_the_deterministic_tier_is_unchanged_by_all_of_the_above():
    """The lexicon is a frozen instrument. Nothing in this wiring touches
    it, and this test is what proves the claim rather than asserting it."""
    r = llm.classify_keyword("What is my attendance percentage?")
    assert r.tool == "get_attendance"
    assert r.method == "keyword"
    assert r.margin > router.TAU
