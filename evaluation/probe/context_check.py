"""Context-window capability check for R0.5.

`docs/v4/03_LLM_LAYER.md` §2.1 makes **context >= 32k tokens** a mandatory
requirement. That is a property of the model *and* of the machine it runs
on: Ollama sized this host's default at `num_ctx=4096` from 6.0 GiB of
VRAM (server log, 2026-08-31), so the requirement cannot be assumed from
the model card -- a 7B that advertises 32k is useless here if allocating
32k pushes its weights out of VRAM and latency collapses.

For each model and each requested context this measures:
  * whether the call succeeds at all,
  * the model's GPU residency afterwards (`/api/ps`: size_vram / size),
  * round-trip latency on a fixed short prompt.

Run separately from the main probe so the two never compete for the GPU.

    python evaluation/probe/context_check.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from evaluation.probe import providers as prov  # noqa: E402

HOST = "http://localhost:11434"
CONTEXTS = (4096, 8192, 16384, 32768)
MODELS = ("qwen2.5:1.5b-instruct", "qwen2.5:3b-instruct",
          "qwen2.5:7b-instruct")
PROMPT = "Reply with the single word: ready."
OUT = ROOT / "evaluation" / "results" / "v4_gates" / "r05_context.json"

REQUIRED_CTX = 32768  # §2.1


def unload(model: str) -> None:
    """Free VRAM between measurements so each one starts from the same state."""
    try:
        httpx.post(f"{HOST}/api/generate",
                   json={"model": model, "keep_alive": 0}, timeout=30)
    except Exception:
        pass
    time.sleep(2)


def measure(model: str, num_ctx: int) -> dict:
    unload(model)
    p = prov.OllamaProvider(model, num_ctx=num_ctx)
    t0 = time.perf_counter()
    reply = p.chat([{"role": "user", "content": PROMPT}], None, seed=11,
                   temperature=0.0, timeout=180.0)
    ms = (time.perf_counter() - t0) * 1000
    res = p.residency()
    return {
        "model": model, "num_ctx": num_ctx,
        "ok": reply.error is None,
        "error": reply.error, "error_kind": reply.error_kind,
        "latency_ms": round(ms, 1),
        "gpu_fraction": res.get("gpu_fraction"),
        "fully_resident": res.get("fully_resident"),
        "vram_bytes": res.get("vram_bytes"),
        "size_bytes": res.get("size_bytes"),
        "reply": (reply.content or "")[:80],
    }


def main() -> None:
    rows = []
    for model in MODELS:
        for ctx in CONTEXTS:
            r = measure(model, ctx)
            rows.append(r)
            frac = r["gpu_fraction"]
            print(f"{model:26s} ctx={ctx:6d} "
                  f"{'ok ' if r['ok'] else 'ERR'} "
                  f"{r['latency_ms']:8.0f}ms "
                  f"gpu={frac if frac is None else f'{frac:.0%}':>6} "
                  f"{'RESIDENT' if r['fully_resident'] else 'SPILLED'}")
            if not r["ok"]:
                print(f"    {r['error']}")

    verdict = {}
    for model in MODELS:
        at_req = [r for r in rows
                  if r["model"] == model and r["num_ctx"] == REQUIRED_CTX]
        r = at_req[0] if at_req else None
        verdict[model] = {
            "meets_32k_requirement": bool(r and r["ok"]),
            "fully_resident_at_32k": bool(r and r["fully_resident"]),
            "latency_ms_at_32k": r["latency_ms"] if r else None,
            "largest_fully_resident_ctx": max(
                [x["num_ctx"] for x in rows
                 if x["model"] == model and x["ok"] and x["fully_resident"]],
                default=None),
        }
        v = verdict[model]
        print(f"\n{model}: 32k works={v['meets_32k_requirement']} "
              f"resident={v['fully_resident_at_32k']} "
              f"largest resident ctx={v['largest_fully_resident_ctx']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "required_ctx": REQUIRED_CTX, "host": HOST,
        "prompt": PROMPT, "measurements": rows, "verdict": verdict,
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
