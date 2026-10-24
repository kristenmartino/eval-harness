"""Statistical helpers and pointwise support scoring.

Includes seeded bootstrap intervals, paired deltas, agreement tests, nugget
recall, and support checks for generated answer units. A caller supplies the
judge adapter; this module does not choose or calibrate judges. Malformed
judgments receive zero support credit.
"""

import math
import random
import re

from adapters.base import SamplingParams
from utils import percentile

JUDGE_PARAMS = SamplingParams(temperature=0.0, max_tokens=200)


# --------------------------------------------------------------------------- #
# (a) Bootstrap
# --------------------------------------------------------------------------- #

def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def seeded_bootstrap_ci(values, statistic=None, *, n_boot=1000, seed=1234,
                        lo=2.5, hi=97.5):
    """Percentile bootstrap CI for `statistic` (default: mean) over `values`,
    seeded for reproducibility. Reuses utils.percentile — the same primitive the
    Task-A bootstrap uses — generalized to any statistic. At small n, intervals
    can be degenerate and should not be treated as reliability guarantees."""
    statistic = statistic or _mean
    n = len(values)
    if n == 0:
        return {"point": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        boots.append(statistic(sample))
    return {
        "point": round(statistic(values), 4),
        "lo": round(percentile(boots, lo), 4),
        "hi": round(percentile(boots, hi), 4),
        "n": n,
    }


def paired_delta_ci(before, after, *, n_boot=1000, seed=1234, lo=2.5, hi=97.5):
    """95% CI on the paired delta (after − before) over matched items, via a
    paired bootstrap that resamples matched-pair indices together (§7a). Use for
    a version-vs-baseline continuous metric on identical scenarios."""
    if len(before) != len(after):
        raise ValueError(f"paired inputs must match: {len(before)} != {len(after)}")
    n = len(before)
    if n == 0:
        return {"delta": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        boots.append(_mean([after[i] for i in idx]) - _mean([before[i] for i in idx]))
    return {
        "delta": round(_mean(after) - _mean(before), 4),
        "lo": round(percentile(boots, lo), 4),
        "hi": round(percentile(boots, hi), 4),
        "n": n,
        "excludes_zero": percentile(boots, lo) > 0 or percentile(boots, hi) < 0,
    }


# --------------------------------------------------------------------------- #
# (b) Agreement + paired binary test
# --------------------------------------------------------------------------- #

def cohens_kappa(rater_a, rater_b) -> float:
    """Cohen's kappa between two raters over paired categorical labels. Used to
    calibrate the pointwise judge against a human-gold subset (§4) — agreement,
    which is necessary but NOT sufficient for validity (premortem #3)."""
    if len(rater_a) != len(rater_b):
        raise ValueError(f"raters must match length: {len(rater_a)} != {len(rater_b)}")
    n = len(rater_a)
    if n == 0:
        return 0.0
    po = sum(1 for a, b in zip(rater_a, rater_b) if a == b) / n
    labels = set(rater_a) | set(rater_b)
    pe = 0.0
    for lab in labels:
        pa = sum(1 for a in rater_a if a == lab) / n
        pb = sum(1 for b in rater_b if b == lab) / n
        pe += pa * pb
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return round((po - pe) / (1 - pe), 4)


def mcnemar_exact(b: int, c: int) -> dict:
    """Exact (binomial) two-sided McNemar test on discordant pairs (§7a). b, c are
    the off-diagonal counts (candidate right/baseline wrong, and vice-versa).
    Exact because b+c is small at this scale. Returns the raw counts too — they
    ALWAYS print, because at n≈20 the p-value alone is uninformative."""
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n": 0, "p_value": 1.0}
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    p = min(1.0, 2 * tail)
    return {"b": b, "c": c, "n": n, "p_value": round(p, 4)}


# --------------------------------------------------------------------------- #
# (c) Pointwise judge mode + the pointwise scorers
# --------------------------------------------------------------------------- #

_LABELS = ("support", "partial", "not_support")
_MK = r"[*`_]*"
_LABEL_RE = re.compile(
    rf"^\s*{_MK}\s*LABEL\s*{_MK}\s*:\s*{_MK}\s*([a-z_]+)", re.IGNORECASE | re.MULTILINE)

POINTWISE_PROMPT = """You are checking whether a STATEMENT is supported by the CONTEXT.

CONTEXT:
{context}

STATEMENT:
{statement}

Answer with exactly one line:
LABEL: <support | partial | not_support>
where "support" = fully entailed by the context, "partial" = partly supported,
"not_support" = unsupported or contradicted."""


def parse_pointwise(text: str) -> str:
    """Extract the label. malformed → not_support (conservative abstain, spec §4
    — an unparseable judgment must not be scored as support)."""
    m = _LABEL_RE.search(text or "")
    if not m:
        return "not_support"
    v = m.group(1).lower().strip("_")
    for lab in _LABELS:
        if v == lab or v == lab.replace("_", ""):
            return lab
    return "not_support"


def pointwise_label(judge, statement: str, context: str) -> str:
    """One pointwise judgment via `judge` (any ModelAdapter). Key-free tests
    drive this with a Scripted/Mock adapter."""
    prompt = POINTWISE_PROMPT.format(context=context, statement=statement)
    completion = judge.complete(prompt, JUDGE_PARAMS)
    return parse_pointwise(completion.text)


_CREDIT = {"support": 1.0, "partial": 0.5, "not_support": 0.0}


def nugget_recall(judge, answer: str, nuggets) -> dict:
    """Vital-weighted nugget recall (RAGAS FactualCorrectness / TREC
    AutoNuggetizer, reimplemented in stdlib). `nuggets`: list of
    {text, weight: 'vital'|'okay'}. vital→1.0, okay→0.5; partial support→half
    credit. Primary answer-correctness signal (spec §4)."""
    weight = {"vital": 1.0, "okay": 0.5}
    total_w, got_w = 0.0, 0.0
    per = []
    vital_hits, vital_total = 0, 0
    for nug in nuggets:
        w = weight.get(nug.get("weight", "okay"), 0.5)
        label = pointwise_label(judge, nug["text"], answer)
        credit = _CREDIT[label]
        total_w += w
        got_w += w * credit
        if nug.get("weight") == "vital":
            vital_total += 1
            vital_hits += 1 if label == "support" else 0
        per.append({"text": nug["text"], "weight": nug.get("weight"), "label": label})
    recall = (got_w / total_w) if total_w else 0.0
    return {
        "recall": round(recall, 4),
        "vital_recall": round(vital_hits / vital_total, 4) if vital_total else 1.0,
        "per_nugget": per,
    }


def citation_faithfulness(judge, claims, cited_context: str) -> dict:
    """Mean support credit over ALL claims: full=1, partial=0.5, unsupported=0.

    Missing claims or context score zero. Callers must supply claims from the
    generated answer and the text of the sources actually cited.
    """
    supported, not_supported, partial = 0, 0, 0
    per = []
    for claim in claims:
        label = pointwise_label(judge, claim, cited_context) if cited_context.strip() else "not_support"
        if label == "support":
            supported += 1
        elif label == "partial":
            partial += 1
        else:
            not_supported += 1
        per.append({"claim": claim, "label": label})
    denom = supported + partial + not_supported
    faithfulness = ((supported + 0.5 * partial) / denom) if denom else 0.0
    return {
        "faithfulness": round(faithfulness, 4),
        "supported": supported,
        "not_supported": not_supported,
        "partial": partial,
        "per_claim": per,
    }


def answer_claims(answer: str) -> list:
    """Conservative sentence/clause units from the actual answer, without filtering.

    This is deterministic segmentation, not atomic factual-claim extraction.
    The judge must support the entire unit, including any compound assertion.
    """
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", answer or "") if s.strip()]


def answer_correctness(judge, answer: str, nuggets,
                       reference_context: str = None) -> dict:
    """F1 of nugget recall and support of the generated answer's claim units.

    Reference context is required for precision and a passing correctness gate.
    Recall alone remains reportable but cannot establish factual correctness.
    Partial support receives half credit and fails the strict correctness gate.
    """
    claims = answer_claims(answer)
    rec = nugget_recall(judge, answer, nuggets)
    recall = rec["recall"]
    if reference_context is None:
        precision = None
        f1 = recall
        prec_block = None
    else:
        prec_block = citation_faithfulness(judge, claims, reference_context)
        precision = prec_block["faithfulness"]
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fully_supported = bool(claims) and prec_block is not None and \
        prec_block["not_supported"] == 0 and prec_block["partial"] == 0
    gate = (rec["vital_recall"] == 1.0) and fully_supported
    return {
        "recall": recall,
        "vital_recall": rec["vital_recall"],
        "precision": precision,
        "f1": round(f1, 4),
        "correct": gate,
        "nuggets": rec["per_nugget"],
        "precision_detail": prec_block,
        "claims": claims,
    }
