"""
KeywordJudge — a deterministic, key-free pointwise judge for Tier-B smoke + CI.

It implements the ModelAdapter interface (so it drops into eval/stats.pointwise_*
unchanged), parses the CONTEXT and STATEMENT out of the pointwise prompt, and
labels support / partial / not_support by content-word overlap. It is NOT a real
judge — it is a stand-in so the Tier-B judged-scoring path (nugget recall,
citation faithfulness, answer correctness) runs and is testable WITHOUT API keys.
The real Tier-B nightly swaps in a cross-vendor LLM judge behind this same
interface.
"""

from adapters.base import Completion

_STOPWORDS = frozenset(
    "a an the of to in on for and or is are was were be been being with by at as "
    "it its this that from what which how does did do not no than across two new".split()
)


def _tokens(text: str) -> set:
    out = set()
    for raw in (text or "").lower().split():
        tok = "".join(ch for ch in raw if ch.isalnum())
        if tok and tok not in _STOPWORDS:
            out.add(tok)
    return out


def _section(prompt: str, start: str, end: str) -> str:
    i = prompt.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = prompt.find(end, i)
    return prompt[i:(j if j >= 0 else len(prompt))].strip()


class KeywordJudge:
    """Deterministic pointwise judge. `support_at`/`partial_at` are the overlap
    fractions (of the statement's content words covered by the context) at which
    it returns support / partial."""

    def __init__(self, model_id: str = "keyword-judge-v1",
                 support_at: float = 0.6, partial_at: float = 0.3):
        self.model_id = model_id
        self._support_at = support_at
        self._partial_at = partial_at

    def complete(self, prompt: str, params) -> Completion:
        context = _section(prompt, "CONTEXT:", "STATEMENT:")
        statement = _section(prompt, "STATEMENT:", "Answer with")
        s_tokens = _tokens(statement)
        frac = (len(s_tokens & _tokens(context)) / len(s_tokens)) if s_tokens else 0.0
        if frac >= self._support_at:
            label = "support"
        elif frac >= self._partial_at:
            label = "partial"
        else:
            label = "not_support"
        text = f"LABEL: {label}"
        return Completion(
            text=text,
            input_tokens=len(prompt) // 4,
            output_tokens=2,
            latency_ms=0.0,
            model_id=self.model_id,
            raw_metadata={"keyword_judge": True, "overlap": round(frac, 3)},
        )
