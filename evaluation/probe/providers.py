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

    Client-side pacing and 429 retry, added 2026-09-14 for the first real
    run of this class (Groq): free hosted tiers are requests-per-minute
    limited (Groq's is 30/min), and without pacing measure 9 (hard-failure
    rate) records how hard this client hammers the endpoint rather than
    provider reliability -- exactly the reasoning already applied to
    `GeminiProvider` below, mirrored here rather than re-derived. Every 429
    that survives the retries is still counted as a hard failure exactly
    as specified; pacing reduces spurious failures, it does not hide real
    ones.
    """

    kind = "hosted"

    #: Task 2a: exactly 2 retries on 429, sleep 5 s then 15 s -- a fixed
    #: schedule, not multiplied by attempt (unlike GeminiProvider's, which
    #: scales). Chosen deliberately smaller than Gemini's because Groq's
    #: free tier resets every 60 s (RPM, not RPD), so two bounded waits are
    #: enough to clear a transient hit without turning one stalled item
    #: into a multi-minute stall.
    RATE_BACKOFF_SCHEDULE_S = (5.0, 15.0)

    def __init__(self, model: str, base_url: str, key_env: str,
                 label: str | None = None, min_interval_s: float | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.key_env = key_env
        self.name = label or f"openai-compat:{model}"
        # Client-side pacing, same pattern as `GeminiProvider._pace()`.
        # Default 2.5 s: Groq's free tier is 30 req/min (2.0 s floor), so
        # 2.5 s leaves headroom. Overridable via MAWOS_OPENAI_PACING_S so a
        # different hosted candidate's tier can be paced without a code
        # change.
        self.min_interval_s = (min_interval_s if min_interval_s is not None
                                else float(os.getenv("MAWOS_OPENAI_PACING_S",
                                                      "2.5")))
        self.max_rate_retries = len(self.RATE_BACKOFF_SCHEDULE_S)
        self._last_call = 0.0
        self._rate_limit_hits = 0
        self._rate_limit_exhausted = 0

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

    def _pace(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    @staticmethod
    def _prepare_messages(messages: list[dict]) -> list[dict]:
        """Translate the harness's provider-agnostic message shape into a
        strictly OpenAI-compliant one.

        `run_item()` builds messages once and hands the same shape to every
        provider (Ollama, Gemini, this one). Ollama and Gemini both tolerate
        or translate `tool_calls[].function.arguments` as a raw dict; the
        real OpenAI Chat Completions schema Groq/OpenRouter/GitHub Models
        validate against does not -- it requires `arguments` to be a JSON
        *string*, and every `tool_calls[]` entry to carry `id`/`type`, with
        the following `role: tool` message echoing that `id` back as
        `tool_call_id`. Discovered live against Groq (HTTP 400, one field
        at a time: `arguments` must be a string, then `id` is missing).
        Handled here, not in `run_item()`, so Ollama's and Gemini's already
        -working translation of the same generic shape is untouched.
        """
        out: list[dict] = []
        pending_ids: list[str] = []
        for m in messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                new_calls = []
                ids = []
                for i, c in enumerate(m["tool_calls"]):
                    fn = c.get("function", {})
                    args = fn.get("arguments")
                    if not isinstance(args, str):
                        args = json.dumps(args if args is not None else {})
                    cid = (c.get("_meta") or {}).get("id") \
                        or f"call_{len(out)}_{i}"
                    ids.append(cid)
                    new_calls.append({"id": cid, "type": "function",
                                      "function": {"name": fn.get("name", ""),
                                                   "arguments": args}})
                out.append({"role": "assistant",
                           "content": m.get("content") or "",
                           "tool_calls": new_calls})
                pending_ids = list(ids)
            elif m.get("role") == "tool":
                nm = {k: v for k, v in m.items() if k != "_meta"}
                if pending_ids:
                    nm["tool_call_id"] = pending_ids.pop(0)
                out.append(nm)
            else:
                out.append(m)
        return out

    def chat(self, messages, tools, seed, temperature=0.0,
             timeout=120.0) -> Reply:
        body = {"model": self.model,
                "messages": self._prepare_messages(messages),
                "temperature": temperature, "seed": seed}
        if tools:
            body["tools"] = tools

        def _post():
            self._pace()
            t0 = time.perf_counter()
            try:
                resp = httpx.post(f"{self.base_url}/chat/completions",
                                  json=body, timeout=timeout, headers={
                                      "Authorization":
                                          f"Bearer {os.environ[self.key_env]}"})
            except httpx.TimeoutException as exc:
                return None, (time.perf_counter() - t0) * 1000, \
                    ("timeout", str(exc)[:300])
            except Exception as exc:
                return None, (time.perf_counter() - t0) * 1000, \
                    ("transport", f"{type(exc).__name__}: {exc}"[:300])
            return resp, (time.perf_counter() - t0) * 1000, None

        r, ms, err = _post()
        if err:
            return Reply(latency_ms=ms, error=err[1], error_kind=err[0])

        # Bounded retry on 429 -- same rationale and shape as
        # `GeminiProvider.chat()`: a transient free-tier quota hit must not
        # contaminate M2-M6 with an infrastructure artifact. Every 429 is
        # counted; only a call that still fails after the retries is a hard
        # failure for M9.
        attempt = 0
        while r is not None and r.status_code == 429 \
                and attempt < self.max_rate_retries:
            self._rate_limit_hits += 1
            time.sleep(self.RATE_BACKOFF_SCHEDULE_S[attempt])
            attempt += 1
            r, ms, err = _post()
            if err:
                return Reply(latency_ms=ms, error=err[1], error_kind=err[0])

        if r.status_code != 200:
            kind = "ratelimit" if r.status_code == 429 else "http"
            if kind == "ratelimit":
                self._rate_limit_exhausted += 1
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
            calls.append(ToolCall(fn.get("name", ""), parsed, args, err,
                                  meta={"id": c.get("id")}))
        usage = payload.get("usage") or {}
        return Reply(content=(choice.get("content") or "").strip(),
                     tool_calls=calls, latency_ms=ms,
                     prompt_tokens=usage.get("prompt_tokens", 0),
                     completion_tokens=usage.get("completion_tokens", 0))

    def fingerprint(self) -> dict:
        fp = super().fingerprint()
        fp.update(model=self.model, base_url=self.base_url,
                  min_interval_s=self.min_interval_s,
                  rate_limit_hits=self._rate_limit_hits,
                  rate_limit_exhausted=self._rate_limit_exhausted)
        return fp


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
        # `llama-3.3-70b-versatile` -- the model this candidate was chosen
        # under -- was retired from Groq's catalog some time before this
        # 2026-09-14 run (confirmed live: GET /v1/models lists no
        # `llama-3.3*` model at all; a chat request against it returns
        # HTTP 404 model_not_found on every single call). Per
        # `03_LLM_LAYER.md` §4.4, "[e]xact vendors are chosen at R0.5 from
        # what is actually available ... at that time" -- the CLASS (a
        # free-tier hosted, tool-calling-capable model on Groq) is what is
        # frozen, not this specific string. Substituted with
        # `openai/gpt-oss-120b`: the largest model in Groq's current
        # catalog that supports the OpenAI-style `tools` parameter
        # (confirmed via the live /models listing's `supported_features`),
        # comfortably clears the >=32k context requirement (131072), and
        # is still free-tier. The label changes to `groq:gpt-oss-120b` so
        # results are never misattributed to a model that was never
        # actually called.
        OpenAICompatibleProvider("openai/gpt-oss-120b",
                                 "https://api.groq.com/openai/v1",
                                 "GROQ_API_KEY", label="groq:gpt-oss-120b"),
        OpenAICompatibleProvider("meta-llama/llama-3.3-70b-instruct",
                                 "https://openrouter.ai/api/v1",
                                 "OPENROUTER_API_KEY",
                                 label="openrouter:llama-3.3-70b"),
        OpenAICompatibleProvider("gpt-4o-mini",
                                 "https://models.inference.ai.azure.com",
                                 "GITHUB_MODELS_TOKEN",
                                 label="github-models:gpt-4o-mini"),
    ]
