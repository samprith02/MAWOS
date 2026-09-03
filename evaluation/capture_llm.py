"""Capture LLM tool-selection under the frozen protocol.

    python evaluation/capture_llm.py --models qwen2.5:3b-instruct
    python evaluation/capture_llm.py --models 1.5b,3b,7b     # the P6 sweep

Writes evaluation/results/v3_llm/<model>.json — one record per
(task, seed), using the frozen TrialRecord schema.

Two jobs, same harness:

  * **Close the P0 provenance gap.** v2 reported the LLM tier from a single
    run and only in aggregate; P0.5's realised curve had to be
    reconstructed from a published misroute list. This produces the real
    per-query vector at 3 seeds.

  * **Run the P6 sweep** across 1.5B / 3B / 7B under identical conditions,
    so a difference between models is a model difference.

What is held frozen across every model, per PROTOCOL.md §9.2: the system
prompt (imported from the orchestrator, not restated here), the tool
descriptions, temperature 0.1, seeds 0/1/2, the task set, the scoring
rules. Nothing in this file may be tuned per model.

Scoring matches v2: **strictly the first tool the model selects.** That is
what makes the frozen baseline comparable, and it means one chat call per
query rather than a multi-round loop.

Tools are deliberately **never executed**. Selection scoring does not need
results, and execution would mutate the database — `get_hall_ticket` and
`get_scholarship` both commit. Whether the role guard would have blocked a
call is therefore determined statically from the registry's `roles`, which
is exactly the check `toolreg.execute` performs.
"""
import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app import config  # noqa: E402
from backend.app.agents import tools as toolreg  # noqa: E402
from backend.app.agents.orchestrator import SYSTEM_PROMPT  # noqa: E402
from backend.app.database import SessionLocal  # noqa: E402
from backend.app.models import User  # noqa: E402
from evaluation.benchmark.instrumentation import TrialRecord, score, summarise  # noqa: E402
from evaluation.benchmark.tasks import tasks as get_tasks  # noqa: E402

OUT_DIR = ROOT / "evaluation" / "results" / "v3_llm"
SHIPPED_DB = ROOT / "mawos.db"

SEEDS = [0, 1, 2]              # PROTOCOL.md §7
TEMPERATURE = 0.1              # PROTOCOL.md §7 — matches v2, do not change
ALIASES = {"1.5b": "qwen2.5:1.5b-instruct",
           "3b": "qwen2.5:3b-instruct",
           "7b": "qwen2.5:7b-instruct"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bench_users(db) -> dict:
    """One representative user per role, matching v2's benchmark personas."""
    users = {}
    student = db.query(User).filter_by(username="4MT23AI049").first()
    if student:
        users["student"] = student
    for role in ("faculty", "hod", "principal", "admin"):
        u = db.query(User).filter_by(role=role).first()
        if u:
            users[role] = u
    return users


def gpu_residency(model: str) -> dict:
    """Eligibility check from PROTOCOL.md §9.2: must be fully GPU-resident.

    A partially offloaded model measures the offload rather than the model,
    and latency is a primary metric.
    """
    try:
        r = httpx.get(f"{config.OLLAMA_HOST}/api/ps", timeout=5)
        for m in r.json().get("models", []):
            if m.get("name") == model or m.get("model") == model:
                total = m.get("size", 0)
                vram = m.get("size_vram", 0)
                frac = vram / total if total else 0.0
                return {"size_bytes": total, "vram_bytes": vram,
                        "gpu_fraction": frac, "fully_resident": frac > 0.999}
    except Exception as exc:
        return {"error": str(exc)}
    return {"error": "model not listed by /api/ps"}


def runtime_fingerprint(model: str) -> dict:
    """PROTOCOL.md §10.1 — mandatory on every result file.

    Added because the v2↔v3 equivalence check failed with the divergence
    concentrated entirely in *whether a tool call was emitted at all* —
    the signature of a change in the runtime's tool-calling path. v2 had
    not recorded its Ollama version, so the hypothesis could not be
    tested and the two runs cannot be differenced. Never again.
    """
    out = {"ollama_version": None, "model_digest": None,
           "num_ctx": "ollama default, unmodified"}
    try:
        out["ollama_version"] = httpx.get(
            f"{config.OLLAMA_HOST}/api/version", timeout=5).json().get("version")
    except Exception as exc:
        out["ollama_version"] = f"unavailable: {exc}"
    try:
        r = httpx.post(f"{config.OLLAMA_HOST}/api/show",
                       json={"model": model}, timeout=10).json()
        out["model_digest"] = (r.get("details") or {}).get("quantization_level")
        out["parameter_size"] = (r.get("details") or {}).get("parameter_size")
        out["model_family"] = (r.get("details") or {}).get("family")
    except Exception as exc:
        out["model_digest"] = f"unavailable: {exc}"
    return out


def one_call(model: str, task, user, seed: int) -> TrialRecord:
    """A single tool-selection trial. Never executes the selected tool."""
    detail = f"USN {user.usn}" if user.usn else f"dept {user.dept_code or 'ALL'}"
    schemas = toolreg.schemas_for_role(user.role)
    exposed = [s["function"]["name"] for s in schemas]

    rec = TrialRecord(
        task_id=task.id, condition="v2-role-scoped", persona_role=user.role,
        model=model, seed=seed, split="dev", query=task.query,
        gold_tool=task.gold_tool, gold_intent=task.gold_intent,
        stratum=task.stratum, exposed_tools=exposed)

    body = {"model": model, "stream": False, "tools": schemas,
            "options": {"temperature": TEMPERATURE, "seed": seed},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(
                    role=user.role, name=user.display_name, detail=detail)},
                {"role": "user", "content": task.query}]}

    t0 = time.perf_counter()
    try:
        r = httpx.post(f"{config.OLLAMA_HOST}/api/chat", json=body,
                       timeout=config.OLLAMA_TIMEOUT_S * 8)
        r.raise_for_status()
        payload = r.json()
        msg = payload.get("message", {})
        rec.reply_text = (msg.get("content") or "").strip()
        rec.attempted_tools = [c.get("function", {}).get("name", "")
                               for c in (msg.get("tool_calls") or [])]
        # Static permission check — identical to toolreg.execute's guard.
        rec.blocked_calls = [
            n for n in rec.attempted_tools
            if n in toolreg.TOOLS and user.role not in toolreg.TOOLS[n]["roles"]]
        rec.prompt_tokens = payload.get("prompt_eval_count")
        rec.completion_tokens = payload.get("eval_count")
        rec.n_tool_rounds = 1
    except Exception as exc:
        rec.error = f"{type(exc).__name__}: {exc}"
    rec.latency_ms = (time.perf_counter() - t0) * 1000
    return score(rec)


def warm_up(model: str, task, user) -> float:
    """One discarded call, so model-load time never lands in a measurement.

    PROTOCOL.md §10 requires warm-ups be discarded and load time reported
    separately. Ollama loads a model on first use and evicts it when
    another is requested, so every (model, seed) block pays a load cost
    that has nothing to do with the model's inference speed.
    """
    t0 = time.perf_counter()
    one_call(model, task, user, seed=0)
    return (time.perf_counter() - t0) * 1000


def run_sweep(models: list[str], db, users: dict, tasks) -> dict:
    """Interleave models within each seed, per PROTOCOL.md §10.

    Running each model to completion in turn would put the last model on
    the hottest chassis, confounding model size with thermal state on a
    laptop. Cycling models inside the seed loop spreads thermal drift
    across all of them instead. The cost is 9 model loads rather than 3,
    which is exactly what the discarded warm-up above absorbs.
    """
    records: dict[str, list] = {m: [] for m in models}
    residency: dict[str, dict] = {}
    load_ms: dict[str, list] = {m: [] for m in models}

    for seed in SEEDS:
        for model in models:
            first = tasks[0]
            wu_user = users.get(first.asker_role) or users["student"]
            load_ms[model].append(warm_up(model, first, wu_user))
            if model not in residency:
                residency[model] = gpu_residency(model)
                res = residency[model]
                flag = ("" if res.get("fully_resident")
                        else f"  <-- only {res.get('gpu_fraction', 0):.0%} GPU")
                print(f"\n{model} residency "
                      f"{res.get('gpu_fraction', 0):.0%} GPU{flag}")

            t0 = time.perf_counter()
            for i, task in enumerate(tasks, 1):
                user = users.get(task.asker_role) or users["student"]
                records[model].append(one_call(model, task, user, seed))
                if i % 36 == 0:
                    print(f"  {model} seed {seed}: {i}/{len(tasks)}", flush=True)
            s = summarise([r for r in records[model] if r.seed == seed])
            print(f"  {model} seed {seed}: {(time.perf_counter()-t0)/60:.1f} min · "
                  f"selection {s['selection_accuracy']:.1%} · "
                  f"abstain {s['abstention_rate']:.1%} · "
                  f"{s['mean_latency_ms']:.0f} ms/query", flush=True)

    return {m: _package(m, records[m], residency[m], load_ms[m])
            for m in models}


def _package(model: str, records: list, residency: dict, load_ms: list) -> dict:
    per_seed = [summarise([r for r in records if r.seed == s]) for s in SEEDS]

    def band(key):
        vals = [p[key] for p in per_seed if p.get(key) is not None]
        return {"mean": statistics.mean(vals),
                "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0}

    errors = sum(1 for r in records if r.error)
    if errors:
        print(f"  WARNING: {errors} call failures — see the records file")

    return {
        "model": model, "seeds": SEEDS, "temperature": TEMPERATURE,
        "condition": "v2-role-scoped",
        "gpu_residency": residency,
        "runtime": runtime_fingerprint(model),   # §10.1, mandatory
        "call_failures": errors,
        # reported separately, never inside per-query latency (§10)
        "warmup_load_ms": {"mean": statistics.mean(load_ms),
                           "runs": load_ms},
        "interleaved": True,
        "bands": {k: band(k) for k in
                  ("selection_accuracy", "task_success_rate", "wrong_tool_rate",
                   "abstention_rate", "abstention_clarifying",
                   "abstention_silent", "declined_despite_exposure",
                   "blocked_call_rate", "mean_latency_ms")},
        "per_seed": per_seed,
        "latency_median_ms": statistics.median(r.latency_ms for r in records),
        "latency_p95_ms": sorted(r.latency_ms for r in records)[
            int(0.95 * len(records))],
        "records": [json.loads(r.to_json()) for r in records],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="3b",
                    help="comma-separated; 1.5b/3b/7b aliases accepted")
    args = ap.parse_args()
    models = [ALIASES.get(m.strip(), m.strip()) for m in args.models.split(",")]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db_before = sha256(SHIPPED_DB)
    tasks = get_tasks("dev")
    db = SessionLocal()
    try:
        users = bench_users(db)
        missing = {t.asker_role for t in tasks} - set(users)
        if missing:
            sys.exit(f"no benchmark user for role(s): {missing}")
        print(f"MAWOS v3 LLM capture · {len(tasks)} dev tasks × "
              f"{len(SEEDS)} seeds × {len(models)} model(s), interleaved")
        print(f"personas: " + ", ".join(f"{r}={u.username}"
                                        for r, u in sorted(users.items())))
        results = run_sweep(models, db, users, tasks)
        for model, result in results.items():
            out = OUT_DIR / f"{model.replace(':', '_').replace('.', '-')}.json"
            result["generated"] = datetime.now().isoformat(timespec="seconds")
            out.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"  wrote {out}")
            res = result["gpu_residency"] or {}
            if res.get("fully_resident") is False:
                print(f"  INELIGIBLE per PROTOCOL §9.2: only "
                      f"{res.get('gpu_fraction', 0):.1%} GPU-resident")
    finally:
        db.close()

    if sha256(SHIPPED_DB) != db_before:
        sys.exit("ABORT: the shipped database changed. Tools must never be "
                 "executed by this harness — investigate.")
    print("\nshipped db verified unchanged")


if __name__ == "__main__":
    main()
