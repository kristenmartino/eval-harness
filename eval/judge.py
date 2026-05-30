"""
LLM-as-judge for pairwise preference (Task B) and faithfulness (Task D).

Cross-vendor judge selection per spec §2 Task B (v0.2 Edit 1):
  - Sonnet 4.6 judges non-Anthropic-containing pairs (21 of 36 at 9 models)
  - GPT-4o judges Anthropic-containing pairs (15 of 36 at 9 models)
  - 50-pair overlap also judged by GPT-4o for cross-judge calibration

The verdict format is constrained for stable parsing across judge models:
three labeled lines (VERDICT / FACTUALITY_A / FACTUALITY_B) followed by a
1-2 sentence justification. A `parse_status` field records whether parsing
fully succeeded so downstream aggregation can exclude or separately report
malformed verdicts — a parse failure must NOT be silently counted as a
genuine TIE (that would bias rankings toward ties for a flaky judge). The
raw output is always preserved on JudgeVerdict for review.

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


# Regex patterns for tolerant parsing — case-insensitive, tolerant of markdown
# emphasis (**bold**, `code`, _italics_) and whitespace anywhere around the
# label and between the colon and the value, so "**VERDICT:** A" parses.
_MK = r"[*`_]*"  # optional markdown emphasis run
VERDICT_RE = re.compile(
    rf"^\s*{_MK}\s*VERDICT\s*{_MK}\s*:\s*{_MK}\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)
FACTUALITY_A_RE = re.compile(
    rf"^\s*{_MK}\s*FACTUALITY[_ ]?A\s*{_MK}\s*:\s*{_MK}\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)
FACTUALITY_B_RE = re.compile(
    rf"^\s*{_MK}\s*FACTUALITY[_ ]?B\s*{_MK}\s*:\s*{_MK}\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)


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
    parse_status: str = "ok"  # see parse_verdict() for the value set


# parse_status values, ordered most→least complete.
PARSE_OK = "ok"                      # verdict + both factuality lines parsed
PARSE_MISSING_FACTUALITY = "missing_factuality"  # verdict ok, ≥1 factuality missing
PARSE_MISSING_VERDICT = "missing_verdict"        # verdict missing (winner→TIE fallback)
PARSE_MALFORMED = "malformed"        # nothing parsed at all


def parse_verdict(text: str) -> tuple:
    """Extract (winner, factuality_a, factuality_b, rationale, parse_status).

    `winner` still falls back to "TIE" when the VERDICT line is absent so
    existing consumers keep working, but `parse_status` flags that fallback so
    a flaky judge's unparseable output is NOT scored as a genuine tie. The
    rationale is whatever non-labeled text remains (used for spot-checking).
    """
    winner = None
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

    # Classify before applying the TIE fallback.
    verdict_ok = winner is not None
    factuality_ok = factuality_a is not None and factuality_b is not None
    if verdict_ok and factuality_ok:
        parse_status = PARSE_OK
    elif verdict_ok:
        parse_status = PARSE_MISSING_FACTUALITY
    elif factuality_a is not None or factuality_b is not None:
        parse_status = PARSE_MISSING_VERDICT
    else:
        parse_status = PARSE_MALFORMED

    if winner is None:
        winner = "TIE"

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

    return winner, factuality_a, factuality_b, " ".join(rationale_lines), parse_status


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
    winner, factuality_a, factuality_b, rationale, parse_status = parse_verdict(completion.text)
    return JudgeVerdict(
        winner=winner,
        factuality_a=factuality_a,
        factuality_b=factuality_b,
        rationale=rationale,
        judge_id=judge.model_id,
        raw_output=completion.text,
        parse_status=parse_status,
    )
