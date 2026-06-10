"""
kelly.py — Kelly Criterion for optimal stake sizing.

Mathematical foundation:

  Full Kelly:
    f* = (p × (b + 1) - 1) / b
       = (p × odd - 1) / (odd - 1)
       = EV / (odd - 1)
    
    where:
      p = probability of winning
      b = net odds received (odd - 1 in decimal)
      f* = fraction of bankroll to stake
    
  Properties:
    - Maximizes expected logarithm of wealth (long-term growth)
    - 1/4 Kelly: reduces volatility while retaining ~95% of growth
    - 1/2 Kelly: standard conservative approach
    - Full Kelly: theoretical maximum growth, high variance
    
  Expected Growth Rate:
    G = p × ln(1 + b × f) + (1-p) × ln(1 - f)
    
  Bankroll Protection:
    - Clamp to 25% max stake (no single bet > 25% of bankroll)
    - Minimum viable stake of 0.5% (below this, skip)
    - Negative EV → f* = 0 (no bet)
"""

import math
from typing import Optional

from .models import KellyResult


def full_kelly(probability: float, decimal_odd: float) -> float:
    """
    Full Kelly: f* = (p × odd - 1) / (odd - 1)
    
    Example:
      p = 0.55, odd = 2.10
      f* = (0.55 × 2.10 - 1) / (2.10 - 1)
         = (1.155 - 1) / 1.10
         = 0.155 / 1.10
         = 0.141 → 14.1% of bankroll
    """
    if probability <= 0.0 or probability >= 1.0 or decimal_odd <= 1.0:
        return 0.0

    net_odds = decimal_odd - 1.0
    if net_odds <= 0:
        return 0.0

    f = (probability * decimal_odd - 1.0) / net_odds
    return max(0.0, f)


def fractional_kelly(
    probability: float,
    decimal_odd: float,
    fraction: float = 0.5,
) -> float:
    """Fractional Kelly: applies a safety multiplier (1/2, 1/4, etc.)."""
    return full_kelly(probability, decimal_odd) * fraction


def expected_growth(
    probability: float,
    decimal_odd: float,
    stake_fraction: float,
) -> float:
    """
    G = p × ln(1 + b × f) + (1-p) × ln(1 - f)
    
    Expected logarithmic growth rate per bet.
    """
    if stake_fraction <= 0 or stake_fraction >= 1:
        return 0.0
    if probability <= 0 or probability >= 1:
        return 0.0

    net_odds = decimal_odd - 1.0
    win_term = probability * math.log(1.0 + net_odds * stake_fraction)
    lose_term = (1.0 - probability) * math.log(1.0 - stake_fraction)

    if math.isnan(win_term) or math.isnan(lose_term):
        return 0.0
    return win_term + lose_term


def compute_kelly(
    probability: float,
    decimal_odd: float,
    bankroll_pct_limit: float = 0.25,
    min_stake_pct: float = 0.005,
    kelly_fraction: float = 0.5,
) -> KellyResult:
    """
    Complete Kelly calculation with all standard fractions.
    
    Args:
        probability:      fair probability (0-1)
        decimal_odd:      market decimal odd
        bankroll_pct_limit: maximum single-bet fraction (default 25%)
        min_stake_pct:    minimum viable fraction (default 0.5%)
        kelly_fraction:   user's chosen fraction (0.25, 0.5, etc.)
    
    Returns:
        KellyResult with all fraction variants.
    """
    f_full = full_kelly(probability, decimal_odd)
    f_half = f_full * 0.5
    f_quarter = f_full * 0.25
    f_user = f_full * kelly_fraction

    # Clamp to bankroll limit
    recommended = min(f_user, bankroll_pct_limit)

    # Expected growth for recommended stake
    growth = expected_growth(probability, decimal_odd, recommended)

    is_viable = (recommended >= min_stake_pct and
                 compute_expected_value(probability, decimal_odd) > 0)

    return KellyResult(
        full_kelly=round(f_full, 4),
        half_kelly=round(f_half, 4),
        quarter_kelly=round(f_quarter, 4),
        fractional_kelly=round(f_user, 4),
        expected_growth=round(growth, 6),
        recommended_stake=round(recommended, 4),
        is_viable=is_viable,
    )


def compute_expected_value(probability: float, decimal_odd: float) -> float:
    """Local EV helper to avoid circular import."""
    if probability <= 0 or decimal_odd <= 1.0:
        return 0.0
    return (probability * decimal_odd) - 1.0


def half_kelly(probability: float, decimal_odd: float) -> float:
    return fractional_kelly(probability, decimal_odd, 0.5)


def quarter_kelly(probability: float, decimal_odd: float) -> float:
    return fractional_kelly(probability, decimal_odd, 0.25)
