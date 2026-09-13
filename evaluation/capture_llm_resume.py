"""Checkpointed driver around capture_llm.py, for a session where the
background process running the capture keeps getting killed by something
outside this codebase (confirmed not the GPU/driver -- `nvidia-smi` and
`sc query nvlddmkm` were both healthy at every kill; see the 2026-08-25
session notes). Three unmodified `capture_llm.py --models 1.5b,7b` runs
died at 33 min, 5 min, then 2 min respectively, each losing everything
because that script only writes output after the *entire* interleaved
sweep finishes.

This wrapper is additive, not a fork: it imports `capture_llm`'s own
functions (`one_call`, `warm_up`, `gpu_residency`, `runtime_fingerprint`,
`bench_users`, `_package`, `SEEDS`, `TEMPERATURE`) and drives the exact
same interleaved order PROTOCOL.md §10 specifies -- models cycle inside
the seed loop, not model-then-model -- the only change is a checkpoint
file written after every (seed, model) block, and a skip-if-already-done
check on startup so a kill only costs the one block in flight, not the
whole run.

    python evaluation/capture_llm_resume.py --models 1.5b,7b

Safe to re-run after any interruption -- it resumes from
`evaluation/results/v3_gates/_p6_checkpoint.json` and deletes it once
every model's file has been written.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation import capture_llm as cl  # noqa: E402

CKPT = ROOT / "evaluation" / "results" / "v3_gates" / "_p6_checkpoint.json"
OUT_DIR = cl.OUT_DIR


def load_ckpt() -> dict:
    if CKPT.exists():
        return json.loads(CKPT.read_text(encoding="utf-8"))
    return {"records": {}, "residency": {}, "load_ms": {}}


def save_ckpt(state: dict) -> None:
    CKPT.parent.mkdir(parents=True, exist_ok=True)
    CKPT.write_text(json.dumps(state), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="3b")
    args = ap.parse_args()
    models = [cl.ALIASES.get(m.strip(), m.strip()) for m in args.models.split(",")]

    db = cl.SessionLocal()
    try:
        users = cl.bench_users(db)
        tasks = cl.get_tasks("dev")
        missing = {t.asker_role for t in tasks} - set(users)
        if missing:
            sys.exit(f"no benchmark user for role(s): {missing}")

        state = load_ckpt()
        done = {(s, m) for m in models for s in cl.SEEDS
                if f"{s}:{m}" in state["records"]}
        print(f"resuming: {len(done)}/{len(cl.SEEDS) * len(models)} "
              f"(seed, model) blocks already checkpointed")

        CHUNK = 11   # 99 is divisible by 11 -- ~30-50s of work per checkpoint
        for seed in cl.SEEDS:
            for model in models:
                key = f"{seed}:{model}"
                if key in state["records"] and len(state["records"][key]) >= len(tasks):
                    print(f"  skip {model} seed {seed} (checkpointed, complete)")
                    continue
                block = state["records"].setdefault(key, [])
                start_i = len(block)   # resume mid-block, not just at block start

                if f"{seed}:{model}:warmed" not in state.get("warmed", {}):
                    first = tasks[0]
                    wu_user = users.get(first.asker_role) or users["student"]
                    load_ms = cl.warm_up(model, first, wu_user)
                    state["load_ms"].setdefault(model, []).append(load_ms)
                    state.setdefault("warmed", {})[f"{seed}:{model}:warmed"] = True
                    save_ckpt(state)
                if model not in state["residency"]:
                    res = cl.gpu_residency(model)
                    state["residency"][model] = res
                    flag = ("" if res.get("fully_resident")
                            else f"  <-- only {res.get('gpu_fraction', 0):.0%} GPU")
                    print(f"{model} residency {res.get('gpu_fraction', 0):.0%} GPU{flag}")
                    save_ckpt(state)

                t0 = time.perf_counter()
                for i, task in enumerate(tasks[start_i:], start_i + 1):
                    user = users.get(task.asker_role) or users["student"]
                    rec = cl.one_call(model, task, user, seed)
                    block.append(json.loads(rec.to_json()))
                    if i % CHUNK == 0 or i == len(tasks):
                        save_ckpt(state)
                        print(f"  {model} seed {seed}: {i}/{len(tasks)} "
                              f"checkpointed", flush=True)
                print(f"  {model} seed {seed}: done in "
                      f"{(time.perf_counter() - t0) / 60:.1f} min", flush=True)

        for model in models:
            all_records = []
            for seed in cl.SEEDS:
                all_records.extend(state["records"][f"{seed}:{model}"])
            # cl._package expects TrialRecord-like objects with .seed/.error/
            # .latency_ms attributes for summarise(); reconstruct minimally.
            from evaluation.benchmark.instrumentation import TrialRecord
            recs = [TrialRecord(**{k: v for k, v in r.items()}) for r in all_records]
            packaged = cl._package(model, recs, state["residency"][model],
                                   state["load_ms"][model])
            packaged["generated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            packaged["capture_order"] = ("interleaved per PROTOCOL.md §10, "
                                         "via capture_llm_resume.py checkpointing "
                                         "(background-process instability this "
                                         "session, disclosed 2026-08-25)")
            out = OUT_DIR / f"{model.replace(':', '_').replace('.', '-')}.json"
            out.write_text(json.dumps(packaged, indent=2), encoding="utf-8")
            print(f"wrote {out}")
    finally:
        db.close()

    # Reaching here means the double loop above ran to completion without
    # being killed, so every (seed, model) block for `models` is done.
    CKPT.unlink(missing_ok=True)
    print("all blocks complete -- checkpoint file removed")


if __name__ == "__main__":
    main()
