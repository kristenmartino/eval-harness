"""
Bradley-Terry ranking from pairwise judge verdicts.

Given pairwise verdicts (model A beats B, A loses to B, or tie), compute global
strength parameters via the MM (Minorization-Maximization) algorithm. Ties count
as 0.5 wins on each side.

Reference: Hunter (2004), "MM algorithms for generalized Bradley-Terry models."
MM converges reliably and is the practical choice for BT in the no-covariates case.

Output is normalized so the geometric mean of strengths = 1 (for identifiability
— BT is invariant to multiplicative scaling).
"""

import math
from collections import defaultdict


def fit_bradley_terry(verdicts: list, max_iter: int = 1000, tol: float = 1e-7) -> dict:
    """Fit BT model from pairwise verdicts.

    verdicts: list of dicts with keys 'model_a', 'model_b', 'winner' ('A' | 'B' | 'TIE').
    Returns: {model_id: strength} normalized so geometric mean = 1.
    """
    wins = defaultdict(float)
    models = set()
    for v in verdicts:
        a, b, w = v["model_a"], v["model_b"], v["winner"]
        models.add(a)
        models.add(b)
        if w == "A":
            wins[(a, b)] += 1.0
        elif w == "B":
            wins[(b, a)] += 1.0
        else:  # TIE
            wins[(a, b)] += 0.5
            wins[(b, a)] += 0.5

    models = sorted(models)
    if len(models) < 2:
        return {m: 1.0 for m in models}

    pi = {m: 1.0 for m in models}
    total_wins = {m: sum(wins.get((m, j), 0) for j in models if j != m) for m in models}

    for _ in range(max_iter):
        new_pi = {}
        for i in models:
            num = total_wins[i]
            denom = 0.0
            for j in models:
                if j == i:
                    continue
                n_ij = wins.get((i, j), 0) + wins.get((j, i), 0)
                if n_ij == 0:
                    continue
                denom += n_ij / (pi[i] + pi[j])
            new_pi[i] = (num / denom) if denom > 0 else pi[i]

        # Normalize so geometric mean of positive strengths = 1
        valid = [p for p in new_pi.values() if p > 0]
        if valid:
            log_mean = sum(math.log(p) for p in valid) / len(valid)
            scale = math.exp(log_mean)
            new_pi = {m: (p / scale if p > 0 else p) for m, p in new_pi.items()}

        max_change = max(abs(new_pi[m] - pi[m]) for m in models)
        pi = new_pi
        if max_change < tol:
            break

    return pi


def rank_models(strengths: dict) -> list:
    """Return list of (model_id, strength) tuples sorted by descending strength."""
    return sorted(strengths.items(), key=lambda x: -x[1])
