"""
hedge.py — Hedge position management and calculation.

A hedge is a position taken to offset risk on an existing bet.
The goal is to lock in profit (or minimize loss) regardless of outcome.

Types:
  1. Pre-match hedge: Back the opposite outcome before the event starts.
  2. Live hedge: Take a position during the event when odds shift.
  3. Cash-out simulation: Calculate fair cash-out value.

Mathematical principle:
  If you have a bet at odd_o on outcome A for stake S_o,
  and you want to guarantee profit by betting on outcome B at odd_h:
  
  For guaranteed return R on both outcomes:
    If A wins: return = S_o * odd_o
    If B wins: return = S_h * odd_h
    
  For equal return:
    S_h = S_o * odd_o / odd_h (if B is a direct opposite)
    
  Locked profit = S_o * odd_o - S_o - S_h
                 = S_o * (odd_o - 1) - S_h
  
  Locked profit % = locked_profit / (S_o + S_h)
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from .models import HedgePosition


def hedge_stake(
    original_stake: Decimal,
    original_odd: Decimal,
    hedge_odd: Decimal,
) -> Decimal:
    """
    Calculate stake on hedge bet to lock in equal return.
    
    S_h = S_o * odd_o / odd_h
    
    Returns stake on hedge bet rounded to 2 decimals.
    """
    if hedge_odd <= Decimal("1") or original_odd <= Decimal("1"):
        return Decimal("0")
    stake = original_stake * original_odd / hedge_odd
    return stake.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def locked_profit(
    original_stake: Decimal,
    original_odd: Decimal,
    hedge_stake_amount: Decimal,
    hedge_odd: Decimal,
    hedge_commission: Decimal = Decimal("0"),
) -> Decimal:
    """
    Calculate guaranteed profit after hedging.
    
    Profit = min(return_A, return_B) - total_stake
    """
    return_a = original_stake * original_odd
    return_b = hedge_stake_amount * hedge_odd / (Decimal("1") + hedge_commission)
    guaranteed = min(return_a, return_b)
    total = original_stake + hedge_stake_amount
    profit = guaranteed - total
    return profit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def locked_profit_pct(
    original_stake: Decimal,
    original_odd: Decimal,
    hedge_odd: Decimal,
    hedge_commission: Decimal = Decimal("0"),
) -> Decimal:
    """Locked profit as percentage of total stake."""
    hs = hedge_stake(original_stake, original_odd, hedge_odd)
    profit = locked_profit(original_stake, original_odd, hs, hedge_odd, hedge_commission)
    total = original_stake + hs
    if total <= Decimal("0"):
        return Decimal("0")
    return (profit / total * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def cash_out_value(
    original_stake: Decimal,
    original_odd: Decimal,
    current_odd: Decimal,
    current_commission: Decimal = Decimal("0"),
) -> Decimal:
    """
    Fair cash-out value for an open position.
    
    If current_odd > original_odd (odds drifted against you),
    cash-out value is lower (the market thinks you're more likely to lose).
    
    Formula: fair_value = S_o * (odd_o / odd_cur)
    
    The bookmaker's offer is typically fair_value - margin.
    """
    if current_odd <= Decimal("1"):
        return Decimal("0")
    gross = original_stake * original_odd / current_odd
    net = gross / (Decimal("1") + current_commission)
    return net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def partial_hedge(
    original_stake: Decimal,
    original_odd: Decimal,
    hedge_odd: Decimal,
    desired_profit_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Calculate a partial hedge to lock in a specific profit percentage.
    
    Returns (hedge_stake, locked_profit).
    """
    full_hs = hedge_stake(original_stake, original_odd, hedge_odd)

    lo, hi = Decimal("0"), full_hs
    target = original_stake * desired_profit_pct / Decimal("100")

    for _ in range(50):
        mid = (lo + hi) / Decimal("2")
        profit = locked_profit(original_stake, original_odd, mid, hedge_odd, Decimal("0"))
        if abs(profit - target) < Decimal("0.01"):
            return (mid.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), profit)
        if profit < target:
            lo = mid
        else:
            hi = mid

    result = (lo + hi) / Decimal("2")
    profit = locked_profit(original_stake, original_odd, result, hedge_odd, Decimal("0"))
    return (
        result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        profit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
    )


def evaluate_hedge(position: HedgePosition) -> HedgePosition:
    """Compute hedge stake and locked profit for a position."""
    hs = hedge_stake(position.original_stake, position.original_odd, position.current_hedge_odd)
    profit = locked_profit(
        position.original_stake, position.original_odd, hs, position.current_hedge_odd
    )
    position.hedge_stake = hs
    position.lock_profit = profit
    position.is_locked = profit > Decimal("0")
    return position
