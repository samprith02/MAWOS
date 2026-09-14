"""Google AI Studio (Generative Language API) provider for the R0.5 probe.

Split into its own module because the mapping is non-trivial and getting it
wrong would corrupt the measurement rather than merely fail.

**Why the mapping matters.** An earlier draft flattened tool results into
plain user text. A model that cannot see a `functionResponse` re-calls the
same function, so the multi-step measure would have recorded an *adapter*
bug as a *model* failure. Function calls and their results are therefore
mapped to real `functionCall` / `functionResponse` parts.

**Credential handling.** The key is read from the environment at call time
and sent as an `x-goog-api-key` header — never placed in a URL, never
logged, never included in any error string, and never written to a result
file. `fingerprint()` reports the model and pacing, not the credential.
"""
from __future__ import annotations

import os
import time

import httpx

from evaluation.probe.providers import Provider, Reply, ToolCall

#: Fields Gemini's function-declaration schema rejects. Sending them yields a
#: 400 that looks like a model failure but is an adapter bug.
SCHEMA_DROP = {"additionalProperties", "$schema", "default", "examples",
               "title", "exclusiveMinimum", "exclusiveMaximum"}


def sanitise_schema(node):
    if isinstance(node, dict):
        return {k: sanitise_schema(v) for k, v in node.items()
                if k not in SCHEMA_DROP}
    if isinstance(node, list):
        return [sanitise_schema(v) for v in node]
    return node


def to_function_declarations(tools) -> list | None:
    """OpenAI-style tool list -> Gemini functionDeclarations.

    A declaration whose `properties` is empty is rejected by the API, so a
    zero-parameter tool has `parameters` omitted entirely. Three of the
    twelve MAWOS tools take no arguments, so without this the probe would
    fail on them for a reason that has nothing to do with the model.
    """
    decls = []
    for t in tools or []:
        fn = dict(t["function"])
        params = sanitise_schema(fn.get("parameters") or {})
        if params.get("properties"):
            if not params.get("required"):
                params.pop("required", None)
            fn["parameters"] = params
        else:
            fn.pop("parameters", None)
        decls.append(fn)
    return [{"functionDeclarations": decls}] if decls else None


def to_contents(messages) -> tuple[str, list]:
    """Chat messages -> (systemInstruction text, contents[])."""
    sys_txt = "\n".join(m["content"] for m in messages
                        if m["role"] == "system" and m.get("content"))
    contents = []
    for m in messages:
        role = m["role"]
        if role == "system":
            continue
        if role == "tool":
            contents.append({"role": "user", "parts": [{
                "functionResponse": {
                    "name": m.get("name", "tool"),
                    "response": {"result": m.get("content", "")}}}]})
            continue
        if role == "assistant":
            parts = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for c in m.get("tool_calls") or []:
                fn = c.get("function", {})
                part = {"functionCall": {"name": fn.get("name", ""),
                                         "args": fn.get("arguments") or {}}}
                # Gemini 3.x thinking models reject a follow-up turn whose
                # functionCall part is missing the thoughtSignature they
                # issued with it ("Function call is missing a
                # thought_signature in functionCall part"). Replay it.
                sig = ((c.get("_meta") or {}).get("thoughtSignature"))
                if sig:
                    part["thoughtSignature"] = sig
                parts.append(part)
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue
        contents.append({"role": "user",
                         "parts": [{"text": m.get("content") or ""}]})
    return sys_txt, contents


class GeminiProvider(Provider):
    """AI Studio provider with client-side pacing.

    Free AI Studio tiers are requests-per-minute limited. Without pacing,
    measure 9 (hard-failure rate) would record how hard this client hammers
    the endpoint rather than how reliable the provider is -- and
    `03_LLM_LAYER.md` §3.2 already requires rate governance as part of the
    architecture, so pacing is the deployed behaviour, not a thumb on the
    scale. The interval used is recorded in the result file, and any 429
    that still occurs is counted as a hard failure exactly as specified.
    """

    kind = "hosted"
    key_env = "GEMINI_API_KEY"
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, model: str, min_interval_s: float = 7.0,
                 max_rate_retries: int = 4, rate_backoff_s: float = 20.0):
        self.model = model
        self.name = f"gemini:{model}"
        self.min_interval_s = min_interval_s
        self.max_rate_retries = max_rate_retries
        self.rate_backoff_s = rate_backoff_s
        self._last_call = 0.0
        self._seed_supported: bool | None = None
        self._rate_limit_hits = 0        # 429s encountered (then retried)
        self._rate_limit_exhausted = 0   # 429s that survived every retry

    # ---------------------------------------------------------- credential
    def _headers(self) -> dict:
        return {"x-goog-api-key": os.environ[self.key_env]}

    def availability(self) -> tuple[bool, str]:
        if not os.getenv(self.key_env):
            return False, f"no credential: {self.key_env} is unset"
        try:
            r = httpx.get(f"{self.BASE}/models", headers=self._headers(),
                          timeout=30)
            if r.status_code in (401, 403):
                return False, f"credential rejected (HTTP {r.status_code})"
            if r.status_code != 200:
                return False, f"/models returned HTTP {r.status_code}"
            names = {m.get("name", "").split("/")[-1]
                     for m in r.json().get("models", [])}
            if self.model not in names:
                return False, (f"model {self.model!r} not offered to this key; "
                               f"{len(names)} models visible")
            return True, "ok"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def list_models(self) -> list[str]:
        r = httpx.get(f"{self.BASE}/models", headers=self._headers(),
                      timeout=30)
        r.raise_for_status()
        return sorted(
            m.get("name", "").split("/")[-1]
            for m in r.json().get("models", [])
            if "generateContent" in (m.get("supportedGenerationMethods") or []))

    # ---------------------------------------------------------------- chat
    def _pace(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def chat(self, messages, tools, seed, temperature=0.0,
             timeout=180.0) -> Reply:
        sys_txt, contents = to_contents(messages)
        gen_cfg = {"temperature": temperature}
        if self._seed_supported is not False:
            gen_cfg["seed"] = seed
        body = {"contents": contents, "generationConfig": gen_cfg}
        if sys_txt:
            body["systemInstruction"] = {"parts": [{"text": sys_txt}]}
        decls = to_function_declarations(tools)
        if decls:
            body["tools"] = decls

        url = f"{self.BASE}/models/{self.model}:generateContent"

        def _post():
            self._pace()
            t0 = time.perf_counter()
            try:
                r = httpx.post(url, headers=self._headers(), json=body,
                               timeout=timeout)
            except httpx.TimeoutException as exc:
                return None, (time.perf_counter() - t0) * 1000, \
                    ("timeout", str(exc)[:300])
            except Exception as exc:
                return None, (time.perf_counter() - t0) * 1000, \
                    ("transport", f"{type(exc).__name__}: {exc}"[:300])
            return r, (time.perf_counter() - t0) * 1000, None

        r, ms, err = _post()
        if err:
            return Reply(latency_ms=ms, error=err[1], error_kind=err[0])

        # If the API rejects `seed`, learn that once and retry without it,
        # rather than recording 75 spurious failures for an unsupported knob.
        if (r.status_code == 400 and self._seed_supported is None
                and "seed" in r.text.lower()):
            self._seed_supported = False
            gen_cfg.pop("seed", None)
            r, ms, err = _post()
            if err:
                return Reply(latency_ms=ms, error=err[1], error_kind=err[0])
        elif r.status_code == 200 and self._seed_supported is None:
            self._seed_supported = "seed" in gen_cfg

        # Bounded retry on 429. Rationale, stated so it can be audited: a
        # transient quota hit that kills an item would contaminate M2-M6
        # with an infrastructure artifact -- those measures would record
        # free-tier quota rather than model capability. `03_LLM_LAYER.md`
        # §3.2 already requires rate governance as part of the architecture,
        # so retrying is deployed behaviour. Every 429 is still counted and
        # reported; only a call that fails *after* the retries is a hard
        # failure for M9.
        attempt = 0
        while r.status_code == 429 and attempt < self.max_rate_retries:
            self._rate_limit_hits += 1
            attempt += 1
            time.sleep(self.rate_backoff_s * attempt)
            r, ms, err = _post()
            if err:
                return Reply(latency_ms=ms, error=err[1], error_kind=err[0])

        if r.status_code != 200:
            kind = "ratelimit" if r.status_code == 429 else "http"
            if kind == "ratelimit":
                self._rate_limit_exhausted += 1
            return Reply(latency_ms=ms,
                         error=f"HTTP {r.status_code}: {r.text[:300]}",
                         error_kind=kind)

        try:
            payload = r.json()
            cands = payload.get("candidates") or []
            if not cands:
                fb = (payload.get("promptFeedback") or {}).get("blockReason")
                return Reply(latency_ms=ms, error_kind="malformed",
                             error=f"no candidate (blockReason={fb})")
            cand = cands[0]
            parts = (cand.get("content") or {}).get("parts") or []
        except Exception as exc:
            return Reply(latency_ms=ms, error_kind="malformed",
                         error=f"unparseable body: {exc}"[:300])

        text, calls = "", []
        for p in parts:
            if "text" in p:
                text += p["text"]
            if "functionCall" in p:
                fc = p["functionCall"]
                args = fc.get("args") or {}
                meta = {}
                if p.get("thoughtSignature"):
                    meta["thoughtSignature"] = p["thoughtSignature"]
                calls.append(ToolCall(
                    fc.get("name", ""),
                    args if isinstance(args, dict) else {}, args,
                    None if isinstance(args, dict) else "args not an object",
                    meta or None))

        usage = payload.get("usageMetadata") or {}
        return Reply(content=text.strip(), tool_calls=calls, latency_ms=ms,
                     prompt_tokens=usage.get("promptTokenCount", 0),
                     completion_tokens=usage.get("candidatesTokenCount", 0))

    def fingerprint(self) -> dict:
        return {"provider": self.name, "kind": self.kind, "model": self.model,
                "min_interval_s": self.min_interval_s,
                "max_rate_retries": self.max_rate_retries,
                "rate_backoff_s": self.rate_backoff_s,
                "seed_parameter_supported": self._seed_supported,
                "rate_limit_429s_encountered": self._rate_limit_hits,
                "rate_limit_429s_unrecovered": self._rate_limit_exhausted}
