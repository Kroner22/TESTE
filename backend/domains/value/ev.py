"""
ev.py — Expected Value calculator with confidence intervals.

Mathematical foundation:

  EV = (P_fair × odd) - 1
  
  Interpretation:
    EV = 0.05 → for each $1 bet, expected profit is $0.05
    EV < 0   → negative expected value (reject)
    
  Confidence Interval via Standard Error:
    SE = sqrt((P_fair × (1 - P_fair)) / n)
    
    95% CI: EV ± 1.96 × SE × odd
    
    If the entire CI is above 0, the edge is statistically significant.
    
  Edge classification:
    ELITE:      EV > 10%
    STRONG:     EV > 5%
    SOLID:      EV > 3% AND significant at 95% CI
    SPECULATIVE: EV > 1% (not necessarily significant)
    NOISE:      EV <= 1%
"""

import math

from .models import ValueGrade


def compute_expected_value(
    fair_probability: float,
    decimal_odd: float,
) -> float:
    """EV = (P_fair × odd) - 1"""
    if fair_probability <= 0 or decimal_odd <= 1.0:
        return 0.0
    return (fair_probability * decimal_odd) - 1.0


def ev_confidence_interval(
    ev: float,
    fair_probability: float,
    decimal_odd: float,
    sample_size: int = 100,
    z_score: float = 1.96,
) -> tuple[float, float]:
    """
    EV confidence interval using normal approximation.
    
    SE = sqrt(P × (1-P) / n) × odd
    CI = EV ± z × SE
    
    Args:
        ev: expected value
        fair_probability: estimated true probability
        decimal_odd: market odd
        sample_size: number of historical observations
        z_score: 1.96 for 95% CI, 2.576 for 99% CI
    
    Returns:
        (lower_bound, upper_bound)
    """
    if sample_size < 1 or fair_probability <= 0 or fair_probability >= 1:
        return (ev, ev)

    se = math.sqrt((fair_probability * (1.0 - fair_probability)) / sample_size)
    se_ev = se * decimal_odd
    return (ev - z_score * se_ev, ev + z_score * se_ev)


def is_statistically_significant(
    ev: float,
    fair_probability: float,
    decimal_odd: float,
    sample_size: int = 100,
    alpha: float = 0.05,
) -> bool:
    """True if entire lower CI > 0 (statistically significant edge)."""
    z = {0.05: 1.96, 0.01: 2.576, 0.10: 1.645}.get(alpha, 1.96)
    lo, _ = ev_confidence_interval(ev, fair_probability, decimal_odd,
                                    sample_size, z)
    return lo > 0


def classify_value_grade(
    ev: float,
    confidence: float,
    significant: bool = False,
) -> ValueGrade:
    """Classify value opportunity by EV size and confidence."""
    if ev > 0.10 and confidence >= 0.9:
        return ValueGrade.ELITE
    if ev > 0.05 and confidence >= 0.8:
        return ValueGrade.STRONG
    if ev > 0.03 and (confidence >= 0.7 or significant):
        return ValueGrade.SOLID
    if ev > 0.01:
        return ValueGrade.SPECULATIVE
    return ValueGrade.NOISE


def edge_pct(ev: float) -> float:
    """Express EV as percentage."""
    return round(ev * 100, 2)
