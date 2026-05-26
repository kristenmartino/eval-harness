"""
LLM-as-judge for pairwise preference (Task B) and faithfulness (Task D).

Cross-vendor judge selection per spec §2 Task B (v0.2 Edit 1):
  - Sonnet 4.6 judges non-Anthropic-containing pairs (21 of 36 at 9 models)
  - GPT-4o judges Anthropic-containing pairs (15 of 36 at 9 models)
  - 50-pair overlap also judged by GPT-4o for cross-judge calibration

The verdict format is constrained for stable parsing across judge models:
three labeled lines (VERDICT / FACTUALITY_A / FACTUALITY_B) followed by a
1-2 sentence justification. Missing or unparseable lines default to TIE/None
— the raw output is always preserved on JudgeVerdict for review.

Bradley-Terry ranking from verdicts is in /eval/bradley_terry.py.
"""

import re
from dataclasses import dataclass

from adapters.base import ModelAdapter, SamplingParams


PAIRWISE_PROMPT = """You are evaluating two summaries of the same news article.

Source article:
{article}

Summary A:
{summary_a}

Summary B:
{summary_b}

Compare on:
1. Faithfulness — does the summary contain only claims supported by the source article?
2. Coverage — does the summary capture the article's key points?
3. Clarity — is the summary well-written and unambiguous?

Output exactly three labeled lines first, then 1-2 sentences justifying:

VERDICT: <A | B | TIE>
FACTUALITY_A: <pass | fail>
FACTUALITY_B: <pass | fail>

Where:
- VERDICT is your overall preference (TIE if no preference)
- FACTUALITY_A is "pass" if Summary A contains only claims supported by the source article, "fail" if it contains unsupported claims
- FACTUALITY_B is the same check applied to Summary B"""


JUDGE_PARAMS = SamplingParams(temperature=0.0, max_tokens=300)


# Regex patterns for tolerant parsing — case-insensitive, tolerant of bold/code/whitespace
VERDICT_RE = re.compile(r"^\s*\*?\*?\s*VERDICT\s*:\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)
FACTUALITY_A_RE = re.compile(r"^\s*\*?\*?\s*FACTUALITY[_ ]?A\s*:\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)
FACTUALITY_B_RE = re.compile(r"^\s*\*?\*?\s*FACTUALITY[_ ]?B\s*:\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)


def is_anthropic_model(model_id: str) -> bool:
    """Identify Anthropic models from model_id. Used for cross-vendor selection."""
    base = model_id.split(":")[0].lower()
    return "haiku" in base or "sonnet" in base or "claude" in base


def select_judge(
    model_id_a: str,
    model_id_b: str,
    sonnet_adapter: ModelAdapter,
    gpt4o_adapter: ModelAdapter,
) -> ModelAdapter:
    """Cross-vendor judge selection per spec §2 Task B.

    Rule: if either side of the pair is Anthropic, GPT-4o judges (avoids
    Anthropic-judging-Anthropic self-preference). Otherwise Sonnet judges.
    """
    if is_anthropic_model(model_id_a) or is_anthropic_model(model_id_b):
        return gpt4o_adapter
    return sonnet_adapter


@dataclass(frozen=True)
class JudgeVerdict:
    winner: str          # "A", "B", or "TIE"
    factuality_a: str    # "pass", "fail", or None (unparseable)
    factuality_b: str    # "pass", "fail", or None (unparseable)
    rationale: str
    judge_id: str
    raw_output: str


def parse_verdict(text: str) -> tuple:
    """Extract (winner, factuality_a, factuality_b, rationale) from judge output.

    All three labeled fields default to TIE/None if unparseable. The full
    rationale is whatever non-labeled text remains (used for spot-checking).
    """
    winner = "TIE"
    factuality_a = None
    factuality_b = None

    m = VERDICT_RE.search(text)
    if m:
        v = m.group(1).upper().strip('"\'`*.,!?')
        if v in ("A", "B", "TIE"):
            winner = v

    m = FACTUALITY_A_RE.search(text)
    if m:
        v = m.group(1).lower().strip('"\'`*.,!?')
        if v in ("pass", "fail"):
            factuality_a = v

    m = FACTUALITY_B_RE.search(text)
    if m:
        v = m.group(1).lower().strip('"\'`*.,!?')
        if v in ("pass", "fail"):
            factuality_b = v

    # Rationale = everything except the three labeled lines
    rationale_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.lstrip("*`").strip().upper()
        if (upper.startswith("VERDICT:")
                or upper.startswith("FACTUALITY_A:") or upper.startswith("FACTUALITY A:")
                or upper.startswith("FACTUALITY_B:") or upper.startswith("FACTUALITY B:")):
            continue
        rationale_lines.append(stripped)

    return winner, factuality_a, factuality_b, " ".join(rationale_lines)


def judge_pair(
    judge: ModelAdapter,
    article: str,
    summary_a: str,
    summary_b: str,
) -> JudgeVerdict:
    """Run one pairwise comparison. The judge adapter is selected by the caller
    via select_judge() — this function is judge-agnostic."""
    prompt = PAIRWISE_PROMPT.format(article=article, summary_a=summary_a, summary_b=summary_b)
    completion = judge.complete(prompt, JUDGE_PARAMS)
    winner, factuality_a, factuality_b, rationale = parse_verdict(completion.text)
    return JudgeVerdict(
        winner=winner,
        factuality_a=factuality_a,
        factuality_b=factuality_b,
        rationale=rationale,
        judge_id=judge.model_id,
        raw_output=completion.text,
    )
