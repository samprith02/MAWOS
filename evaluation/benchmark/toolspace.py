"""Tool-space construction for the RQ4 dose-response conditions.

FROZEN AT P0. Do not edit without a dated entry in evaluation/PROTOCOL.md.

RQ4 asks how the *size* of an agent's exposed tool space affects tool
selection, abstention and task success when everything else is held
constant. For that to be a real experiment, three things must be true of
every condition, and each is enforced here rather than trusted:

1. **The gold tool is always exposed.** Otherwise the condition measures
   answerability, not tool-space size. This is the defect that killed the
   original "10-agent vs 6-agent" design.

2. **Composition is fixed, not sampled freely.** Naively drawing the
   non-gold slots from a combined pool keeps the *expected* distractor
   share constant but lets its variance explode at small N — a 5-tool
   space could come out all-real or all-distractor by chance, so "size"
   would be partly confounded with "realism". The exact composition of
   every condition is therefore tabulated in `COMPOSITION` and frozen.

3. **Tool order is randomized per seed.** Models are position-sensitive
   over tool lists. Presenting tools in registry order at every size would
   let position bias masquerade as a size effect.

**Role scoping is deliberately NOT applied here.** Role-scoped exposure is
the independent variable of RQ1/E2; applying it inside the RQ4 arm as well
would re-create exactly the persona-x-toolspace confound that made v2's
14.8% uninterpretable. E5 varies size only. The persona is still the
task's natural `asker_role`, so first-person queries stay answerable — that
varies across tasks but identically within every condition, so it is
controlled by design.
"""
import hashlib
import random

from backend.app.agents import tools as toolreg

from . import distractors

# N -> (real non-gold count, distractor count). Gold is always the +1.
# Distractor share of the non-gold slots sits at 0.58 +/- 0.05 across the
# range, except at N=5 where integer granularity forces 0.50. The real
# pool caps at 11 non-gold tools (12 real tools after P2 minus the gold
# slot), which fixes the N=30 row exactly.
COMPOSITION: dict[int, tuple[int, int]] = {
    5:  (2, 2),
    9:  (3, 5),
    13: (5, 7),
    20: (8, 11),
    30: (11, 18),
}

#: The deployed system, kept as a separate labelled reference point rather
#: than folded into the dose-response curve — its composition (all real, no
#: distractors) differs from every curve condition, so plotting it on the
#: same axis would compare two different things.
#: Renamed from "13-real" at P2 (docs/RESEARCH_PLAN_V3.md §7.1): the
#: registry lost get_admissions_funnel, so the deployed system is 12 tools.
DEPLOYMENT_REFERENCE = "12-real"

SIZES = tuple(sorted(COMPOSITION))


def _real_schemas() -> dict[str, dict]:
    """Every real tool in Ollama schema form, ignoring role restrictions."""
    return {t["name"]: {"type": "function",
                        "function": {"name": t["name"],
                                     "description": t["description"],
                                     "parameters": t["parameters"]}}
            for t in toolreg.TOOLS.values()}


def _rng(task_id: str, condition: str, seed: int) -> random.Random:
    """Deterministic per-cell RNG, independent of iteration order.

    Seeding from a hash of the cell identity rather than from a global
    counter means a rerun of one condition reproduces byte-for-byte
    without rerunning the others.
    """
    key = f"{task_id}|{condition}|{seed}".encode()
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))


def build(task, condition, seed: int) -> list[dict]:
    """Construct the tool schema list presented to the model for one cell.

    `condition` is an int size from SIZES, or DEPLOYMENT_REFERENCE.
    Returns tool schemas in presentation order.
    """
    real = _real_schemas()
    if task.gold_tool not in real:
        raise ValueError(
            f"task {task.id} has gold_tool {task.gold_tool!r}, which is not "
            f"in the registry. Gold tools are registry-independent by "
            f"design, but a condition cannot expose a tool that has no "
            f"schema. Add a schema or fix the task.")

    rng = _rng(task.id, str(condition), seed)
    chosen = [real[task.gold_tool]]

    if condition == DEPLOYMENT_REFERENCE:
        chosen += [s for n, s in real.items() if n != task.gold_tool]
    else:
        n_real, n_distract = COMPOSITION[condition]
        real_pool = sorted(n for n in real if n != task.gold_tool)
        distract_pool = sorted(distractors.DISTRACTORS)
        if n_real > len(real_pool) or n_distract > len(distract_pool):
            raise ValueError(f"condition {condition} exceeds the available "
                             f"pool ({len(real_pool)} real, "
                             f"{len(distract_pool)} distractors)")
        chosen += [real[n] for n in rng.sample(real_pool, n_real)]
        picked = set(rng.sample(distract_pool, n_distract))
        chosen += [s for s in distractors.schemas()
                   if s["function"]["name"] in picked]

    rng.shuffle(chosen)          # position-bias control
    return chosen


def conditions() -> list:
    """Every E5 condition, curve points first, reference last."""
    return list(SIZES) + [DEPLOYMENT_REFERENCE]


def describe(condition) -> str:
    if condition == DEPLOYMENT_REFERENCE:
        return "12 tools, all real (deployed system reference)"
    n_real, n_distract = COMPOSITION[condition]
    return (f"{condition} tools = 1 gold + {n_real} real + {n_distract} "
            f"distractors (distractor share of non-gold slots "
            f"{n_distract / (n_real + n_distract):.3f})")
