"""Per-query instrumentation for RQ1 and RQ4.

FROZEN AT P0. Do not edit without a dated entry in evaluation/PROTOCOL.md.

The central distinction the primary research question rests on is:

    "the model **could not** use the tool"   (it was never exposed, or the
                                              role guard rejected the call)
                        vs
    "the model **did not attempt** the tool" (it was exposed, permitted,
                                              and the model declined)

A harness that records only final accuracy collapses these two into one
number and cannot answer RQ1 at all. Everything below exists to keep them
apart.

Derivation rules are deliberately mechanical. Where a judgement call was
unavoidable it is stated here and applied uniformly, so the rule can be
criticised as a whole rather than being invisible:

  * **Correctness is strict and first-call.** A trial is correct iff the
    *first* tool the model attempts is the gold tool. This matches v2's
    definition, which is what keeps the frozen baseline comparable. Later
    recovery is captured separately in `gold_attempted`.

  * **Clarifying vs silent abstention** is decided by whether the reply
    contains a question mark. This is crude. It is also deterministic,
    language-independent within English, and preregisterable — the
    alternative, an LLM judge, introduces a second model's failure modes
    into the measurement of the first. The limitation is recorded in
    PROTOCOL.md under threats to validity.

  * **A blocked call still counts as an attempt.** The model tried; the
    guard stopped it. Attempt and permission are different variables and
    are never merged.
"""
import json
from dataclasses import asdict, dataclass, field

#: Outcome taxonomy. Exhaustive and mutually exclusive.
OUTCOMES = ("correct", "wrong_tool", "abstained", "error")

#: Abstention taxonomy.
ABSTENTIONS = ("none", "clarifying", "silent")


@dataclass
class TrialRecord:
    """One (task, condition, persona, model, seed) cell.

    The seven fields the primary RQ depends on are marked [RQ1].
    """

    # ---- cell identity
    task_id: str
    condition: str            # tool-space size, or a 2x2 cell label
    persona_role: str         # the role the query was asked under
    model: str
    seed: int
    split: str                # "dev" | "test"

    # ---- the query and its frozen gold answer
    query: str
    gold_tool: str
    gold_intent: str
    stratum: str

    # ---- [RQ1] exposure vs attempt: the research object
    gold_tool_exposed: bool = False          # [1] was it even offered?
    exposed_tools: list[str] = field(default_factory=list)
    attempted_tools: list[str] = field(default_factory=list)  # [2] in order
    gold_attempted: bool = False             # [3] tried at any point
    blocked_calls: list[str] = field(default_factory=list)    # [4] guard said no
    abstention: str = "none"                 # [5] none|clarifying|silent
    first_tool: str | None = None            # [6] strict-scoring subject
    outcome: str = "error"                   # [7] correct|wrong_tool|abstained|error

    #: Selection correctness and task success are DIFFERENT variables and
    #: are never merged. A model can select the gold tool correctly and
    #: still fail the task because the role guard blocked the call — it
    #: chose right and got nothing. Scoring that as plain "correct" would
    #: inflate accuracy with trials that returned no data at all.
    task_success: bool = False

    # ---- secondary
    reply_text: str = ""
    n_tool_rounds: int = 0
    latency_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None

    # ------------------------------------------------------------------
    @property
    def could_not(self) -> bool:
        """The model was prevented: not exposed, or every attempt blocked."""
        if not self.gold_tool_exposed:
            return True
        return bool(self.blocked_calls) and not self.attempted_tools_allowed

    @property
    def attempted_tools_allowed(self) -> list[str]:
        return [t for t in self.attempted_tools if t not in self.blocked_calls]

    @property
    def did_not_attempt(self) -> bool:
        """Exposed, permitted, and still not tried. The interesting cell."""
        return self.gold_tool_exposed and not self.gold_attempted

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


def classify_abstention(reply_text: str, attempted: list[str]) -> str:
    """none if any tool was attempted; else clarifying (asks) or silent."""
    if attempted:
        return "none"
    return "clarifying" if "?" in (reply_text or "") else "silent"


def score(record: TrialRecord) -> TrialRecord:
    """Fill the derived fields. Idempotent; safe to call once per trial."""
    record.gold_tool_exposed = record.gold_tool in record.exposed_tools
    record.gold_attempted = record.gold_tool in record.attempted_tools
    record.first_tool = record.attempted_tools[0] if record.attempted_tools else None
    record.abstention = classify_abstention(record.reply_text,
                                            record.attempted_tools)

    if record.error:
        record.outcome = "error"
    elif not record.attempted_tools:
        record.outcome = "abstained"
    elif record.first_tool == record.gold_tool:
        record.outcome = "correct"
    else:
        record.outcome = "wrong_tool"

    # Selection can be correct while the task still failed: the guard may
    # have rejected the call, so no data ever reached the model.
    record.task_success = (record.outcome == "correct"
                           and record.gold_tool not in record.blocked_calls)
    return record


def summarise(records: list[TrialRecord]) -> dict:
    """Aggregate one condition. Accuracy, abstention and 'declined' stay split.

    `declined_despite_exposure` is the RQ1 quantity: the model had the gold
    tool in front of it, was permitted to call it, and did not. Reporting
    it merged into accuracy is the mistake this whole module prevents.
    """
    n = len(records)
    if n == 0:
        return {"n": 0}
    exposed = [r for r in records if r.gold_tool_exposed]
    return {
        "n": n,
        # selection_accuracy: did it pick the right tool first?
        # task_success_rate: did it pick right AND actually get the data?
        # These diverge exactly when the role guard blocks a correct pick,
        # which is a permission finding, not a language-understanding one.
        "selection_accuracy": sum(r.outcome == "correct" for r in records) / n,
        "task_success_rate": sum(r.task_success for r in records) / n,
        "wrong_tool_rate": sum(r.outcome == "wrong_tool" for r in records) / n,
        "abstention_rate": sum(r.outcome == "abstained" for r in records) / n,
        "abstention_clarifying": sum(r.abstention == "clarifying"
                                     for r in records) / n,
        "abstention_silent": sum(r.abstention == "silent" for r in records) / n,
        "error_rate": sum(r.outcome == "error" for r in records) / n,
        "gold_exposed_rate": len(exposed) / n,
        "gold_attempted_rate": sum(r.gold_attempted for r in records) / n,
        # the RQ1 measurement, over the subset where exposure held
        "declined_despite_exposure": (
            sum(r.did_not_attempt for r in exposed) / len(exposed)
            if exposed else None),
        "blocked_call_rate": sum(bool(r.blocked_calls) for r in records) / n,
        "mean_latency_ms": sum(r.latency_ms for r in records) / n,
    }
