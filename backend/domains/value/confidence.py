"""
confidence.py — Confidence score engine.

The confidence score quantifies how much we trust a value detection.
It is a weighted combination of 4 factors:

  1. Sample Size Factor (0.0 - 1.0):
     Logistic scaling: 1 / (1 + e^(-k × (n - n0)))
     where n = number of historical observations
           n0 = inflection point (default 50)
           k = steepness (default 0.05)
     → 0.5 at 50 samples, 0.88 at 100, 0.99 at 200
    
  2. Model Confidence Factor (0.0 - 1.0):
     Directly from ML model's prediction confidence.
     Uses calibration-adjusted confidence (Brier score).
     If no model available, defaults to 0.5.
    
  3. Historical Accuracy Factor (0.0 - 1.0):
     How accurate the model/system has been historically.
     Weighted by recency (exponential decay with λ = 0.1).
    
  4. Edge Stability Factor (0.0 - 1.0):
     Coefficient of variation of the edge estimate.
     Stable edges (low CV) → high confidence.
     Volatile edges (high CV) → low confidence.

Final score: weighted geometric mean of the 4 factors.
"""

import math
from typing import Optional


def sample_size_factor(n: int, n0: float = 50.0, k: float = 0.05) -> float:
    """Logistic scaling: 1 / (1 + e^(-k*(n - n0)))"""
    if n <= 0:
        return 0.05  # minimal prior confidence with no observed data
    return 1.0 / (1.0 + math.exp(-k * (n - n0)))


def model_confidence_factor(
    model_prob: float,
    brier_score: Optional[float] = None,
) -> float:
    """
    Converts model probability output to a confidence score.
    
    If Brier score available: confidence = 1 - min(brier, 1.0)
    Otherwise: confidence = model_prob / 0.5 (capped at 1.0)
    """
    if brier_score is not None:
        return max(0.0, 1.0 - min(brier_score, 1.0))
    return min(1.0, model_prob / 0.5) if model_prob > 0 else 0.5


def historical_accuracy_factor(
    accuracy: float,
    total_bets: int,
    decay_lambda: float = 0.1,
) -> float:
    """
    Accuracy weighted by sample size and recency.
    
    For small samples, regress toward 0.5 (prior).
    accuracy_weight = 1 - 1/(1 + total_bets/20)
    """
    if total_bets == 0:
        return 0.5
    weight = 1.0 - 1.0 / (1.0 + total_bets / 20.0)
    return 0.5 * (1.0 - weight) + accuracy * weight


def edge_stability_factor(
    edge_estimates: list[float],
) -> float:
    """
    Coefficient of variation (CV) = std / mean.
    
    Stable edge:   CV < 0.5   → factor ~1.0
    Moderate:      CV 0.5-1.5 → factor 0.5-0.8
    Unstable:      CV > 2.0   → factor < 0.3
    """
    if not edge_estimates or len(edge_estimates) < 3:
        return 0.5

    mean_ev = sum(edge_estimates) / len(edge_estimates)
    if mean_ev == 0:
        return 0.3

    variance = sum((x - mean_ev) ** 2 for x in edge_estimates) / (len(edge_estimates) - 1)
    std = math.sqrt(variance)
    cv = std / mean_ev if mean_ev != 0 else 99.0

    # Logistic decay
    return 1.0 / (1.0 + math.exp(0.8 * (cv - 1.5)))


def compute_confidence(
    sample_size: int = 0,
    model_prob: float = 0.5,
    brier_score: Optional[float] = None,
    historical_accuracy: Optional[float] = None,
    total_bets: int = 0,
    edge_estimates: Optional[list[float]] = None,
    weights: Optional[dict[str, float]] = None,
) -> float:
    """
    Composite confidence score (0.0 - 1.0).
    
    Default weights (if not provided):
      sample:       0.30
      model:        0.25
      historical:   0.25
      stability:    0.20
    
    Uses geometric mean to penalize any single low factor.
    """
    w = weights or {"sample": 0.30, "model": 0.25,
                    "historical": 0.25, "stability": 0.20}

    factors = {
        "sample": sample_size_factor(sample_size),
        "model": model_confidence_factor(model_prob, brier_score),
        "historical": historical_accuracy_factor(
            historical_accuracy if historical_accuracy is not None else 0.5,
            total_bets,
        ),
        "stability": edge_stability_factor(edge_estimates or []),
    }

    # Weighted geometric mean
    weighted_log = sum(w[k] * math.log(max(factors[k], 1e-6))
                       for k in factors if k in w)
    total_weight = sum(w.values())
    return math.exp(weighted_log / total_weight) if total_weight > 0 else 0.5
