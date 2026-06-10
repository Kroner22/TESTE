"""
core.py — Core arbitrage detection mathematics.

2-way arbitrage (e.g., tennis moneyline):
  Condition:  1/o1 + 1/o2 < 1
  Profit%:    (1 - S_i) / S_i   where S_i = sum(1/oi)

3-way arbitrage (e.g., soccer 1X2):
  Condition:  1/o1 + 1/o2 + 1/o3 < 1
  Profit%:    (1 - S_i) / S_i

With commission (bookmaker fee):
  effective_odd = odd / (1 + commission)
  or equivalently: adjusted_implied = 1/odd * (1 + commission)

Multi-bookmaker arbitrage:
  Pick the best odd for each outcome across all bookmakers,
  then check if those best odds create an arbitrage.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from .models import (
    ArbOpportunity, ArbOutcome, ArbType, ArbGrade,
    BookmakerOdds, ArbFilter,
)


def implied_probability(odd: Decimal) -> Decimal:
    """P = 1 / odd. Returns 0 for invalid odds."""
    if odd <= Decimal("1"):
        return Decimal("0")
    return Decimal("1") / odd


def total_implied(odds: list[Decimal]) -> Decimal:
    """Sum of implied probabilities. Total < 1 means arbitrage."""
    return sum(implied_probability(o) for o in odds)


def eff_odd(odd: Decimal, commission: Decimal) -> Decimal:
    """Effective odd after commission: odd / (1 + commission)."""
    return odd / (Decimal("1") + commission)


def arb_profit_pct(odds: list[Decimal], commissions: Optional[list[Decimal]] = None) -> Decimal:
    """
    Profit percentage from arbitrage.
    
    If sum(1/oi) < 1, profit% = (1 - sum) / sum.
    Returns negative if no arb exists.
    """
    if commissions:
        effective = [eff_odd(o, c) for o, c in zip(odds, commissions)]
        s = total_implied(effective)
    else:
        s = total_implied(odds)

    if s <= Decimal("0"):
        return Decimal("0")

    return (Decimal("1") - s) / s


def has_arb(odds: list[Decimal], commissions: Optional[list[Decimal]] = None) -> bool:
    """Check if a set of odds creates an arbitrage opportunity."""
    return arb_profit_pct(odds, commissions) > Decimal("0")


def best_odds_across_bookmakers(
    odds_by_outcome: dict[str, list[BookmakerOdds]],
) -> dict[str, BookmakerOdds]:
    """
    For each outcome, pick the bookmaker offering the best effective odd.
    Returns {outcome: best BookmakerOdds}.
    """
    best: dict[str, BookmakerOdds] = {}
    for outcome, bookmaker_odds_list in odds_by_outcome.items():
        best_bo = max(
            bookmaker_odds_list,
            key=lambda bo: eff_odd(bo.odd, bo.commission),
            default=None,
        )
        if best_bo is not None:
            best[outcome] = best_bo
    return best


def grade_arbitrage(profit_pct: Decimal) -> ArbGrade:
    if profit_pct >= Decimal("0.05"):
        return ArbGrade.ELITE
    elif profit_pct >= Decimal("0.03"):
        return ArbGrade.STRONG
    elif profit_pct >= Decimal("0.015"):
        return ArbGrade.SOLID
    elif profit_pct >= Decimal("0.005"):
        return ArbGrade.MARGINAL
    return ArbGrade.NOISE


def detect_2way_arb(
    event_id: str,
    sport: str,
    home_team: str,
    away_team: str,
    market: str,
    odds_by_outcome: dict[str, list[BookmakerOdds]],
    total_stake: Optional[Decimal] = None,
    filter_config: Optional[ArbFilter] = None,
) -> Optional[ArbOpportunity]:
    """
    Detect a 2-way arbitrage opportunity.
    
    Args:
        odds_by_outcome: {"home": [BookmakerOdds, ...], "away": [BookmakerOdds, ...]}
        total_stake: Stake to distribute (None = 100)
        filter_config: Optional filter criteria
    
    Returns:
        ArbOpportunity if found, None otherwise.
    """
    if len(odds_by_outcome) < 2:
        return None

    best_odds = best_odds_across_bookmakers(odds_by_outcome)
    if len(best_odds) < 2:
        return None

    outcomes = list(best_odds.keys())
    odds_list = [best_odds[o].odd for o in outcomes[:2]]
    commissions = [best_odds[o].commission for o in outcomes[:2]]

    if not has_arb(odds_list, commissions):
        return None

    profit_pct = arb_profit_pct(odds_list, commissions)

    if filter_config and profit_pct < filter_config.min_profit_pct:
        return None

    if total_stake is None:
        total_stake = Decimal("100")

    stakes = distribute_equal_profit(
        odds_list, commissions, total_stake
    )

    legs = []
    for i, outcome in enumerate(outcomes[:2]):
        bo = best_odds[outcome]
        leg = ArbOutcome(
            bookmaker=bo.bookmaker,
            outcome=outcome,
            odd=bo.odd,
            stake=stakes[i],
            return_amount=stakes[i] * bo.odd,
            max_stake=bo.max_stake,
            commission=bo.commission,
            effective_odd=eff_odd(bo.odd, bo.commission),
        )
        legs.append(leg)

    guaranteed_return = min(l.return_amount for l in legs)
    profit = guaranteed_return - total_stake
    is_actionable = all(
        l.max_stake is None or l.stake <= l.max_stake
        for l in legs
    ) if filter_config is None or filter_config.require_actionable else True

    return ArbOpportunity(
        event_id=event_id,
        sport=sport,
        home_team=home_team,
        away_team=away_team,
        market=market,
        arb_type=ArbType.TWO_WAY,
        legs=legs,
        total_stake=total_stake,
        guaranteed_return=guaranteed_return,
        profit=profit,
        profit_pct=profit_pct,
        grade=grade_arbitrage(profit_pct),
        is_actionable=is_actionable,
    )


def detect_3way_arb(
    event_id: str,
    sport: str,
    home_team: str,
    away_team: str,
    market: str,
    odds_by_outcome: dict[str, list[BookmakerOdds]],
    total_stake: Optional[Decimal] = None,
    filter_config: Optional[ArbFilter] = None,
) -> Optional[ArbOpportunity]:
    """Detect a 3-way arbitrage (e.g., soccer 1X2)."""
    if len(odds_by_outcome) < 3:
        return detect_2way_arb(
            event_id, sport, home_team, away_team, market,
            odds_by_outcome, total_stake, filter_config,
        )

    best_odds = best_odds_across_bookmakers(odds_by_outcome)
    if len(best_odds) < 3:
        return None

    outcomes = list(best_odds.keys())
    odds_list = [best_odds[o].odd for o in outcomes[:3]]
    commissions = [best_odds[o].commission for o in outcomes[:3]]

    if not has_arb(odds_list, commissions):
        return None

    profit_pct = arb_profit_pct(odds_list, commissions)

    if filter_config and profit_pct < filter_config.min_profit_pct:
        return None

    if total_stake is None:
        total_stake = Decimal("100")

    stakes = distribute_equal_profit(
        odds_list, commissions, total_stake
    )

    legs = []
    for i, outcome in enumerate(outcomes[:3]):
        bo = best_odds[outcome]
        leg = ArbOutcome(
            bookmaker=bo.bookmaker,
            outcome=outcome,
            odd=bo.odd,
            stake=stakes[i],
            return_amount=stakes[i] * bo.odd,
            max_stake=bo.max_stake,
            commission=bo.commission,
            effective_odd=eff_odd(bo.odd, bo.commission),
        )
        legs.append(leg)

    guaranteed_return = min(l.return_amount for l in legs)
    profit = guaranteed_return - total_stake
    is_actionable = all(
        l.max_stake is None or l.stake <= l.max_stake
        for l in legs
    ) if filter_config is None or filter_config.require_actionable else True

    return ArbOpportunity(
        event_id=event_id,
        sport=sport,
        home_team=home_team,
        away_team=away_team,
        market=market,
        arb_type=ArbType.THREE_WAY,
        legs=legs,
        total_stake=total_stake,
        guaranteed_return=guaranteed_return,
        profit=profit,
        profit_pct=profit_pct,
        grade=grade_arbitrage(profit_pct),
        is_actionable=is_actionable,
    )


def distribute_equal_profit(
    odds: list[Decimal],
    commissions: Optional[list[Decimal]] = None,
    total_stake: Decimal = Decimal("100"),
) -> list[Decimal]:
    """
    Distribute stake so that each outcome returns the same amount.

    For each leg i:
      implied_i = (1 + commission_i) / odd_i
      weight_i = implied_i / sum(implied)
      stake_i = total_stake * weight_i
    """
    if commissions is None:
        commissions = [Decimal("0")] * len(odds)

    implieds = []
    for odd, comm in zip(odds, commissions):
        imp = (Decimal("1") + comm) / odd
        implieds.append(imp)

    total_imp = sum(implieds)
    if total_imp <= Decimal("0"):
        return [Decimal("0")] * len(odds)

    stakes = []
    for imp in implieds:
        s = total_stake * imp / total_imp
        stakes.append(s.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return stakes


def scan_for_arbitrage(
    markets: dict[str, dict[str, list[BookmakerOdds]]],
    total_stake: Decimal = Decimal("100"),
    filter_config: Optional[ArbFilter] = None,
) -> list[ArbOpportunity]:
    """
    Scan multiple markets for arbitrage opportunities.
    
    Args:
        markets: {
            "event_id:sport:home:away:market": {
                "outcome1": [BookmakerOdds, ...],
                "outcome2": [BookmakerOdds, ...],
            }
        }
    """
    opportunities = []
    for key, odds_by_outcome in markets.items():
        parts = key.split(":")
        event_id = parts[0]
        sport = parts[1] if len(parts) > 1 else ""
        home_team = parts[2] if len(parts) > 2 else ""
        away_team = parts[3] if len(parts) > 3 else ""
        market = parts[4] if len(parts) > 4 else "h2h"

        n_outcomes = len(odds_by_outcome)

        if n_outcomes >= 3:
            arb = detect_3way_arb(
                event_id, sport, home_team, away_team, market,
                odds_by_outcome, total_stake, filter_config,
            )
        elif n_outcomes >= 2:
            arb = detect_2way_arb(
                event_id, sport, home_team, away_team, market,
                odds_by_outcome, total_stake, filter_config,
            )
        else:
            arb = None

        if arb is not None:
            opportunities.append(arb)

    opportunities.sort(key=lambda o: o.profit_pct, reverse=True)
    return opportunities
