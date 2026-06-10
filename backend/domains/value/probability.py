"""
probability.py — Implied probability, overround removal, fair odds.

Mathematical foundations:

  1. Implied Probability:          P_i = 1 / odd_i
  
  2. Market Overround (margin):    M = (sum P_i) - 1
  
  3. Fair Probability (3 methods):
     
     a) BASIC (proportional scaling):
        P_fair_i = P_i / (1 + M)
        
        Simplest. Assumes margin is distributed proportionally.
        Used by most retail platforms. Fast, O(n).
        
     b) POWER (logarithmic):
        Find k such that sum(P_i^k) = 1
        P_fair_i = P_i^k / sum(P_i^k)
        
        More accurate for markets with very different odds.
        Used by Pinnacle. Solved via binary search, O(n log precision).
        
     c) SHIN (1993):
        Shin's model accounts for favorite-longshot bias:
        - Favorites are overbet → their odds are worse than fair
        - Longshots are underbet → their odds are better than fair
        
        P_fair_i = (sqrt(z^2 + 4*(1-z)*P_i^2) - z) / (2*(1-z))
        where z = overround parameter (0 <= z <= 1), solved iteratively.
        
        Most accurate academically. Preferred for sharp markets.
        Solved via root-finding, O(n * iterations).
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .models import OverroundMethod, FairProbabilities


def implied_probability(odd: float) -> float:
    """P = 1 / odd. Returns 0.0 for invalid odds."""
    if odd <= 1.0:
        return 0.0
    return 1.0 / odd


def market_overround(odds: list[float]) -> float:
    """M = (sum 1/odd_i) - 1. Returns 0.0 for invalid inputs."""
    if not odds or any(o <= 1.0 for o in odds):
        return 0.0
    return sum(1.0 / o for o in odds) - 1.0


def compute_fair_probabilities(
    odds: dict[str, float],
    method: OverroundMethod = OverroundMethod.BASIC,
    power_k: Optional[float] = None,
    shin_tolerance: float = 1e-8,
    shin_max_iter: int = 1000,
) -> FairProbabilities:
    """
    Compute fair probabilities from market odds.

    Args:
        odds:      {"home": 2.10, "away": 3.40, "draw": 3.25}
        method:    BASIC, POWER, or SHIN
        power_k:   k parameter for POWER method (auto-solved if None)
    
    Returns:
        FairProbabilities with each outcome's fair probability.
    """
    values = list(odds.values())
    outcomes = list(odds.keys())

    if any(v <= 1.0 for v in values):
        return FairProbabilities(
            outcomes={k: 0.0 for k in outcomes},
            overround=0.0, method=method,
            fair_odds={k: 0.0 for k in outcomes},
        )

    M = market_overround(values)
    implied = {k: 1.0 / v for k, v in odds.items()}

    if method == OverroundMethod.BASIC:
        fair = _basic(implied, M)

    elif method == OverroundMethod.POWER:
        k = power_k if power_k is not None else _solve_power_k(values)
        fair = _power(implied, k)

    elif method == OverroundMethod.SHIN:
        z = _solve_shin_z(implied, shin_tolerance, shin_max_iter)
        fair = _shin(implied, z)
        # Normalize to ensure exact sum = 1
        total = sum(fair.values())
        if total > 0:
            fair = {k: v / total for k, v in fair.items()}

    else:
        fair = _basic(implied, M)

    fair_odds = {k: 1.0 / p if p > 0 else 0.0 for k, p in fair.items()}

    return FairProbabilities(
        outcomes=fair,
        overround=M,
        method=method,
        fair_odds=fair_odds,
    )


def _basic(implied: dict[str, float], M: float) -> dict[str, float]:
    """P_fair = P / (1 + M). Proportional scaling."""
    total = sum(implied.values())
    return {k: p / total for k, p in implied.items()}


def _power(implied: dict[str, float], k_param: float) -> dict[str, float]:
    """P_fair = P^k / sum(P^k). Log scaling."""
    powered = {k: p ** k_param for k, p in implied.items()}
    total = sum(powered.values())
    if total == 0:
        return {k: 0.0 for k in implied}
    return {k: v / total for k, v in powered.items()}


def _shin(implied: dict[str, float], z: float) -> dict[str, float]:
    """
    Shin's formula — returns unnormalized fair probabilities.
    
    P_fair_i = (sqrt(z^2 + 4*(1-z)*P_i^2) - z) / (2*(1-z))
    
    When z=0: P_fair_i = P_i (raw implied, sum = 1 + M)
    When z=1: P_fair_i = P_i^2 (max insider adjustment)
    
    These sum to 1 only when z is at the correct value (solved by _solve_shin_z).
    """
    fair = {}
    for outcome, p in implied.items():
        discriminant = z * z + 4.0 * (1.0 - z) * p * p
        if discriminant < 0:
            fair[outcome] = 0.0
        else:
            sqrt_disc = discriminant ** 0.5
            if 1.0 - z == 0:
                fair[outcome] = p
            else:
                fair[outcome] = (sqrt_disc - z) / (2.0 * (1.0 - z))

    return fair


def _solve_power_k(odds: list[float], tolerance: float = 1e-6) -> float:
    """
    Binary search for k such that sum(1/odd_i^k) = 1.
    
    When k=1: sum(P_i) = 1 + M (includes margin)
    When k->0: sum(P_i^0) = n (all equal)
    When k->inf: sum(P_i^inf) = 1 (dominant outcome)
    
    We want the k where sum(P_i^k) = 1 (no margin).
    """
    implied = [1.0 / o for o in odds]
    lo, hi = 0.01, 2.0

    for _ in range(100):
        mid = (lo + hi) / 2.0
        total = sum(p ** mid for p in implied)
        if abs(total - 1.0) < tolerance:
            return mid
        if total > 1.0:
            lo = mid
        else:
            hi = mid

    return (lo + hi) / 2.0


def _solve_shin_z(
    implied: dict[str, float],
    tolerance: float = 1e-8,
    max_iter: int = 1000,
) -> float:
    """
    Solve for Shin's z parameter.
    
    The z parameter represents the fraction of betting volume
    attributable to insider trading / favorite-longshot bias.
    
    0 <= z <= 1
    z = 0 → no insider trading (fair market)
    z = 1 → all betting is insider trading
    
    Solved by finding z where:
    sum(P_implied) = 1 + M(z)   [self-consistency condition]
    
    Simplified: iterate z until fair probabilities sum to 1.
    """
    implied_list = list(implied.values())
    z_lo, z_hi = 0.0, 1.0

    for _ in range(max_iter):
        z_mid = (z_lo + z_hi) / 2.0
        fair = _shin(implied, z_mid)
        total_prob = sum(fair.values())

        if abs(total_prob - 1.0) < tolerance:
            return z_mid
        if total_prob > 1.0:
            z_hi = z_mid
        else:
            z_lo = z_mid

        if z_hi - z_lo < tolerance:
            break

    return (z_lo + z_hi) / 2.0


def best_odds_across_bookmakers(
    odds_by_bookmaker: dict[str, dict[str, float]],
) -> dict[str, float]:
    """
    For each outcome, pick the highest odd across all bookmakers.
    
    Input:
        {"pinnacle": {"home": 2.10, "away": 3.40},
         "bet365":   {"home": 2.05, "away": 3.50}}
    
    Output:
        {"home": 2.10, "away": 3.50}   # best of both
    """
    best: dict[str, float] = {}
    for book, outcomes in odds_by_bookmaker.items():
        for outcome, odd in outcomes.items():
            if outcome not in best or odd > best[outcome]:
                best[outcome] = odd
    return best


def implied_from_decimal(odd: float) -> float:
    """Single decimal odd → implied probability."""
    return implied_probability(odd)


def decimal_from_implied(prob: float) -> float:
    """Fair probability → decimal odd."""
    if prob <= 0.0 or prob >= 1.0:
        return 0.0
    return round(1.0 / prob, 2)
