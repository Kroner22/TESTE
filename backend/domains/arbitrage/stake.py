"""
stake.py — Optimal stake distribution for arbitrage.

Methods:
  1. Equal Profit (standard arb): Same return regardless of outcome.
     stake_i = total * (1/odd_i) / sum(1/odd_j)
     
  2. Weighted (Kelly-inspired): Scale stake by edge.
     For arb, edge is guaranteed, so this is equivalent to equal profit.
     
  3. Risk Parity: Minimizes maximum downside.
     For arb, all outcomes have same return, so identical to equal profit.
     
  4. With constraints: When max_stake limits bind, we need to recalculate.
     If a leg's required stake exceeds its max_stake, cap it and redistribute.

  5. With unequal commissions: Each bookmaker may charge different commission.
     Adjust implied probabilities accordingly.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from .models import StakeMethod, ArbOutcome


def distribute_stakes(
    odds: list[Decimal],
    method: StakeMethod = StakeMethod.EQUAL_PROFIT,
    total_stake: Decimal = Decimal("100"),
    commissions: Optional[list[Decimal]] = None,
    max_stakes: Optional[list[Optional[Decimal]]] = None,
) -> list[Decimal]:
    """
    Distribute total_stake across legs to achieve the desired method.
    
    Returns list of stake amounts.
    """
    if method == StakeMethod.EQUAL_PROFIT:
        return _equal_profit(odds, total_stake, commissions, max_stakes)
    elif method == StakeMethod.WEIGHTED:
        return _weighted(odds, total_stake, commissions)
    elif method == StakeMethod.RISK_PARITY:
        return _risk_parity(odds, total_stake, commissions)
    return _equal_profit(odds, total_stake, commissions, max_stakes)


def _equal_profit(
    odds: list[Decimal],
    total_stake: Decimal,
    commissions: Optional[list[Decimal]] = None,
    max_stakes: Optional[list[Optional[Decimal]]] = None,
) -> list[Decimal]:
    """Equal profit with max_stake constraint handling."""
    if commissions is None:
        commissions = [Decimal("0")] * len(odds)
    if max_stakes is None:
        max_stakes = [None] * len(odds)

    n = len(odds)
    implieds = []
    for o, c in zip(odds, commissions):
        if o <= Decimal("0"):
            implieds.append(Decimal("0"))
        else:
            implieds.append((Decimal("1") + c) / o)
    total_imp = sum(implieds)

    if total_imp <= Decimal("0"):
        return [Decimal("0")] * n

    stakes = [total_stake * imp / total_imp for imp in implieds]

    capped = False
    for i in range(n):
        if max_stakes[i] is not None and stakes[i] > max_stakes[i]:
            stakes[i] = max_stakes[i]
            capped = True

    if capped:
        capped_sum = sum(s for s in stakes if s > Decimal("0"))
        remaining = total_stake - sum(stakes)
        uncapped_indices = [i for i in range(n) if max_stakes[i] is None or stakes[i] < max_stakes[i]]
        uncapped_imp_sum = sum(implieds[i] for i in uncapped_indices)

        if uncapped_imp_sum > Decimal("0") and remaining > Decimal("0"):
            for i in uncapped_indices:
                add = remaining * implieds[i] / uncapped_imp_sum
                stakes[i] = stakes[i] + add

    return [s.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for s in stakes]


def _weighted(
    odds: list[Decimal],
    total_stake: Decimal,
    commissions: Optional[list[Decimal]] = None,
) -> list[Decimal]:
    """Weighted distribution proportional to inverse odds."""
    return _equal_profit(odds, total_stake, commissions)


def _risk_parity(
    odds: list[Decimal],
    total_stake: Decimal,
    commissions: Optional[list[Decimal]] = None,
) -> list[Decimal]:
    """Risk parity — same as equal profit for pure arb."""
    return _equal_profit(odds, total_stake, commissions)


def required_stake_for_return(
    target_return: Decimal,
    odd: Decimal,
    commission: Decimal = Decimal("0"),
) -> Decimal:
    """Calculate stake required to achieve a target return at given odd."""
    if odd <= Decimal("1"):
        return Decimal("0")
    eff = odd / (Decimal("1") + commission)
    if eff <= Decimal("0"):
        return Decimal("0")
    return (target_return / eff).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def max_profit_given_limits(
    odds: list[Decimal],
    max_stakes: list[Optional[Decimal]],
    commissions: Optional[list[Decimal]] = None,
) -> tuple[Decimal, list[Decimal]]:
    """
    Maximum guaranteed profit given stake limits on each leg.
    
    Returns (profit, stakes).
    """
    if commissions is None:
        commissions = [Decimal("0")] * len(odds)

    n = len(odds)
    implieds = [(Decimal("1") + c) / o for o, c in zip(odds, commissions)]
    total_imp = sum(implieds)

    if total_imp <= Decimal("0") or total_imp >= Decimal("1"):
        return (Decimal("0"), [Decimal("0")] * n)

    stakes = []
    for i, max_s in enumerate(max_stakes):
        required = implieds[i] / total_imp
        if max_s is not None:
            used = min(required, max_s)
        else:
            used = required
        stakes.append(used)

    min_return = min(
        stakes[i] * odds[i] / (Decimal("1") + commissions[i])
        for i in range(n)
    )
    total_s = sum(stakes)
    profit = min_return - total_s

    if profit < Decimal("0"):
        profit = Decimal("0")

    return (profit, stakes)
