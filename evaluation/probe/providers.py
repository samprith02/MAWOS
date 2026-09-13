"""Provider abstraction for the R0.5 viability probe.

One interface, three implementations. Nothing above this module is allowed
to know which provider it is talking to -- that is the whole point of
`docs/v4/03_LLM_LAYER.md`, and the probe is the first consumer of it.

A provider that cannot be reached reports `available=False` with the reason.
It is **never** silently skipped and its measures are **never** estimated:
per the R0.5 instruction, an untestable provider is recorded as untested.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class ToolCall:
    name: str
    arguments: dict
    raw_arguments: object = None
    parse_error: str | None = None
    #: Provider-specific data that must be echoed back on the next turn.
    #: Gemini 3.x thinking models require the `thoughtSignature` they issued
    #: with a functionCall to be returned with it, or the follow-up request
    #: is rejected with HTTP 400.
    meta: dict | None = None


@dataclass
class Reply:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None          # set => this counts as a hard failure
    error_kind: str | None = None     # timeout | http | transport | malformed | ratelimit


class Provider:
    """Base. `key_env` names the credential the implementation needs."""

    name = "base"
    kind = "base"
    key_env: str | None = None

    def availability(self) -> tuple[bool, str]:
        raise NotImplementedError

    def chat(self, messages, tools, seed, temperature=0.0,
             timeout=120.0) -> Reply:
        raise NotImplementedError

    def fingerprint(self) -> dict:
        return {"provider": self.name, "kind": self.kind}


# --------------------------------------------------------------------- Ollama
class OllamaProvider(Provider):
    kind = "local"

    def __init__(self, model: str, host: str | None = None,
                 num_ctx: int | None = None):
        self.model = model
        self.name = f"ollama:{model}"
        self.host = host or os.getenv("MAWOS_OLLAMA_HOST",
                                      "http://localhost:11434")
        self.num_ctx = num_ctx

    def availability(self) -> tuple[bool, str]:
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=10)
            if r.status_code != 200:
                return False, f"/api/tags returned HTTP {r.status_code}"
            names = {m.get("name") for m in r.json().get("models", [])}
            if self.model not in names:
                return False, f"model {self.model} not pulled"
            return True, "ok"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def chat(self, messages, tools, seed, temperature=0.0,
             timeout=120.0) -> Reply:
        options = {"temperature": temperature, "seed": seed}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": options}
        if tools:
            body["tools"] = tools
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{self.host}/api/chat", json=body, timeout=timeout)
        except httpx.TimeoutException as exc:
            return Reply(latency_ms=(time.perf_counter() - t0) * 1000,
                         error=str(exc)[:300], error_kind="timeout")
        except Exception as exc:
            return Reply(latency_ms=(time.perf_counter() - t0) * 1000,
                         error=f"{type(exc).__name__}: {exc}"[:300],
                         error_kind="transport")
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            kind = "ratelimit" if r.status_code == 429 else "http"
            return Reply(latency_ms=ms, error=f"HTTP {r.status_code}: "
                         f"{r.text[:200]}", error_kind=kind)
        try:
            payload = r.json()
        except Exception as exc:
            return Reply(latency_ms=ms, error=f"unparseable body: {exc}"[:300],
                         error_kind="malformed")
        msg = payload.get("message") or {}
        return Reply(
            content=(msg.get("content") or "").strip(),
            tool_calls=_normalise_ollama_calls(msg.get("tool_calls") or []),
            latency_ms=ms,
            prompt_tokens=payload.get("prompt_eval_count", 0),
            completion_tokens=payload.get("eval_count", 0),
        )

    def fingerprint(self) -> dict:
        fp = {"provider": self.name, "kind": self.kind, "model": self.model,
              "host": self.host, "num_ctx": self.num_ctx}
        try:
            fp["server_version"] = httpx.get(f"{self.host}/api/version",
                                             timeout=5).json().get("version")
        except Exception:
            pass
        return fp

    def residency(self) -> dict:
        """PROTOCOL §9.2 eligibility: latency is only comparable when the
        model is fully GPU-resident. Same check as `capture_llm.py`."""
        try:
            r = httpx.get(f"{self.host}/api/ps", timeout=5)
            for m in r.json().get("models", []):
                if self.model in (m.get("name"), m.get("model")):
                    total, vram = m.get("size", 0), m.get("size_vram", 0)
                    frac = vram / total if total else 0.0
                    return {"size_bytes": total, "vram_bytes": vram,
                            "gpu_fraction": frac,
                            "fully_resident": frac > 0.999}
        except Exception as exc:
            return {"error": str(exc)}
        return {"error": "model not listed by /api/ps"}


def _normalise_ollama_calls(calls) -> list[ToolCall]:
    out = []
    for c in calls:
        fn = c.get("function", {}) if isinstance(c, dict) else {}
        name = fn.get("name", "")
        args = fn.get("arguments")
        parsed, err = args, None
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except ValueError as exc:
                parsed, err = {}, f"arguments not valid JSON: {exc}"
        if not isinstance(parsed, dict):
            parsed, err = {}, f"arguments not an object: {type(args).__name__}"
        out.append(ToolCall(name=name, arguments=parsed, raw_arguments=args,
                            parse_error=err))
    return out


# ------------------------------------------------------- OpenAI-compatible
class OpenAICompatibleProvider(Provider):
    """Covers Groq, OpenRouter, Together, DeepSeek, a local vLLM, etc.

    Untested at R0.5: no credential for any of them was present in the
    environment. Implemented anyway so that testing one later is a config
    change, not a code change.
    """

    kind = "hosted"

    def __init__(self, model: str, base_url: str, key_env: str,
                 label: str | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.key_env = key_env
        self.name = label or f"openai-compat:{model}"

    def availability(self) -> tuple[bool, str]:
        if not os.getenv(self.key_env):
            return False, f"no credential: {self.key_env} is unset"
        try:
            r = httpx.get(f"{self.base_url}/models", timeout=15, headers={
                "Authorization": f"Bearer {os.environ[self.key_env]}"})
            if r.status_code == 401:
                return False, "credential rejected (HTTP 401)"
            if r.status_code != 200:
                return False, f"/models returned HTTP {r.status_code}"
            return True, "ok"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def chat(self, messages, tools, seed, temperature=0.0,
             timeout=120.0) -> Reply:
        body = {"model": self.model, "messages": messages,
                "temperature": temperature, "seed": seed}
        if tools:
            body["tools"] = tools
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body,
                           timeout=timeout, headers={
                               "Authorization":
                                   f"Bearer {os.environ[self.key_env]}"})
        except httpx.TimeoutException as exc:
            return Reply(latency_ms=(time.perf_counter() - t0) * 1000,
                         error=str(exc)[:300], error_kind="timeout")
        except Exception as exc:
            return Reply(latency_ms=(time.perf_counter() - t0) * 1000,
                         error=f"{type(exc).__name__}: {exc}"[:300],
                         error_kind="transport")
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            kind = "ratelimit" if r.status_code == 429 else "http"
            return Reply(latency_ms=ms,
                         error=f"HTTP {r.status_code}: {r.text[:200]}",
                         error_kind=kind)
        try:
            payload = r.json()
            choice = payload["choices"][0]["message"]
        except Exception as exc:
            return Reply(latency_ms=ms, error=f"unparseable body: {exc}"[:300],
                         error_kind="malformed")
        calls = []
        for c in choice.get("tool_calls") or []:
            fn = c.get("function", {})
            args, err = fn.get("arguments"), None
            parsed = args
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                except ValueError as exc:
                    parsed, err = {}, f"arguments not valid JSON: {exc}"
            if not isinstance(parsed, dict):
                parsed, err = {}, "arguments not an object"
            calls.append(ToolCall(fn.get("name", ""), parsed, args, err))
        usage = payload.get("usage") or {}
        return Reply(content=(choice.get("content") or "").strip(),
                     tool_calls=calls, latency_ms=ms,
                     prompt_tokens=usage.get("prompt_tokens", 0),
                     completion_tokens=usage.get("completion_tokens", 0))


# ------------------------------------------------------------------ shortlist
def _gemini():
    # Imported here, not at module scope: gemini.py imports Provider/Reply
    # from this module.
    from evaluation.probe.gemini import GeminiProvider
    return GeminiProvider(
        os.getenv("MAWOS_GEMINI_MODEL", "gemini-2.5-flash"),
        min_interval_s=float(os.getenv("MAWOS_GEMINI_PACING_S", "4.5")))


def shortlist() -> list[Provider]:
    """`03_LLM_LAYER.md` §4.4 requires one candidate from each class.

    The two hosted classes are constructed regardless of whether a
    credential exists, so that they appear in the result file as
    explicitly untested rather than quietly absent.
    """
    return [
        # class: local floor -- the models already pulled on this machine
        OllamaProvider("qwen2.5:7b-instruct"),
        OllamaProvider("qwen2.5:3b-instruct"),
        OllamaProvider("qwen2.5:1.5b-instruct"),
        # class: hosted frontier-tier
        _gemini(),
        # class: free-tier hosted, OpenAI-compatible
        OpenAICompatibleProvider("llama-3.3-70b-versatile",
                                 "https://api.groq.com/openai/v1",
                                 "GROQ_API_KEY", label="groq:llama-3.3-70b"),
    ]
