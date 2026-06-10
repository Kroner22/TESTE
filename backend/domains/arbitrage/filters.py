"""
filters.py — Opportunity filtering and ranking pipeline.

Applies configurable filters to arbitrage opportunities to surface
only the most actionable, profitable, and safe bets.

Filter chain (applied in order):
  1. Commission     — Max acceptable commission per leg
  2. Profit %       — Min/max guaranteed profit percentage
  3. Stake limits   — Respects max_stake per leg
  4. Bookmaker      — Include/exclude specific bookmakers
  5. Actionable     — Only opportunities that can actually be executed
  6. Duplicate      — Remove near-duplicate opportunities
  7. Ranking        — Sort by combined score (profit, liquidity, speed)
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .models import ArbOpportunity, ArbFilter, ArbGrade, ArbOutcome


@dataclass
class FilterResult:
    kept: list[ArbOpportunity] = field(default_factory=list)
    removed: list[tuple[ArbOpportunity, str]] = field(default_factory=list)
    n_input: int = 0
    n_output: int = 0


def filter_by_commission(
    opportunities: list[ArbOpportunity],
    max_commission: Decimal = Decimal("0.05"),
) -> list[ArbOpportunity]:
    """Remove opportunities where any leg exceeds max_commission."""
    result = []
    for opp in opportunities:
        if any(leg.commission > max_commission for leg in opp.legs):
            continue
        result.append(opp)
    return result


def filter_by_profit_pct(
    opportunities: list[ArbOpportunity],
    min_pct: Decimal = Decimal("0.005"),
    max_pct: Optional[Decimal] = None,
) -> list[ArbOpportunity]:
    """Filter by guaranteed profit percentage."""
    result = []
    for opp in opportunities:
        if opp.profit_pct < min_pct:
            continue
        if max_pct is not None and opp.profit_pct > max_pct:
            continue
        result.append(opp)
    return result


def filter_by_grade(
    opportunities: list[ArbOpportunity],
    min_grade: ArbGrade = ArbGrade.MARGINAL,
) -> list[ArbOpportunity]:
    """Filter by minimum arbitrage grade."""
    grade_order = [
        ArbGrade.NOISE, ArbGrade.MARGINAL, ArbGrade.SOLID,
        ArbGrade.STRONG, ArbGrade.ELITE,
    ]
    min_idx = grade_order.index(min_grade)
    return [
        opp for opp in opportunities
        if grade_order.index(opp.grade) >= min_idx
    ]


def filter_actionable(
    opportunities: list[ArbOpportunity],
) -> list[ArbOpportunity]:
    """Keep only opportunities that are actionable."""
    return [opp for opp in opportunities if opp.is_actionable]


def filter_by_stake(
    opportunities: list[ArbOpportunity],
    min_stake_per_leg: Optional[Decimal] = None,
    max_stake_per_leg: Optional[Decimal] = None,
) -> list[ArbOpportunity]:
    """Filter by stake constraints per leg."""
    if min_stake_per_leg is None and max_stake_per_leg is None:
        return list(opportunities)

    result = []
    for opp in opportunities:
        valid = True
        for leg in opp.legs:
            if min_stake_per_leg is not None and leg.stake < min_stake_per_leg:
                valid = False
                break
            if max_stake_per_leg is not None and leg.stake > max_stake_per_leg:
                valid = False
                break
            if leg.max_stake is not None and leg.stake > leg.max_stake:
                valid = False
                break
        if valid:
            result.append(opp)
    return result


def deduplicate(
    opportunities: list[ArbOpportunity],
    tolerance_pct: Decimal = Decimal("0.001"),
) -> list[ArbOpportunity]:
    """
    Remove near-duplicate opportunities for the same event.
    When duplicates exist, keep the one with highest profit.
    """
    kept: dict[str, ArbOpportunity] = {}
    for opp in opportunities:
        existing = kept.get(opp.event_id)
        if existing is None:
            kept[opp.event_id] = opp
        elif opp.profit_pct > existing.profit_pct + tolerance_pct:
            kept[opp.event_id] = opp
    return list(kept.values())


def rank_opportunities(
    opportunities: list[ArbOpportunity],
) -> list[ArbOpportunity]:
    """
    Rank by composite score: profit_pct * liquidity_factor.

    Higher profit → higher rank.
    Higher total_stake supported → higher rank (liquidity).
    """
    def score(opp: ArbOpportunity) -> float:
        pct = float(opp.profit_pct)
        total_max = sum(
            float(l.max_stake or 10000)
            for l in opp.legs
        )
        liquidity_factor = min(1.0, total_max / 10000.0)
        return pct * liquidity_factor

    return sorted(opportunities, key=score, reverse=True)


def apply_filter_chain(
    opportunities: list[ArbOpportunity],
    filter_config: ArbFilter,
    min_grade: ArbGrade = ArbGrade.MARGINAL,
) -> FilterResult:
    """Apply the full filter pipeline in order."""
    removed: list[tuple[ArbOpportunity, str]] = []

    n_input = len(opportunities)

    opportunities, r = _track_removed(
        opportunities, filter_by_commission,
        "commission_exceeded", filter_config.max_commission,
    )
    removed.extend(r)

    opportunities, r = _track_removed(
        opportunities, filter_by_profit_pct,
        "below_min_profit", filter_config.min_profit_pct, None,
    )
    removed.extend(r)

    opportunities, r = _track_removed(
        opportunities, filter_by_grade,
        "below_min_grade", min_grade,
    )
    removed.extend(r)

    if filter_config.require_actionable:
        opportunities, r = _track_removed(
            opportunities, filter_actionable,
            "not_actionable",
        )
        removed.extend(r)

    opportunities, r = _track_removed(
        opportunities, filter_by_stake,
        "stake_constraints", filter_config.min_stake_per_leg,
        filter_config.max_stake_per_leg,
    )
    removed.extend(r)

    opportunities = deduplicate(opportunities)
    opportunities = rank_opportunities(opportunities)

    return FilterResult(
        kept=opportunities,
        removed=removed,
        n_input=n_input,
        n_output=len(opportunities),
    )


def _track_removed(
    items: list,
    filter_fn,
    reason: str,
    *args,
) -> tuple[list, list[tuple, str]]:
    """Apply a filter and track which items were removed."""
    if not items:
        return [], []

    before = set(items)
    filtered = filter_fn(items, *args) if args else filter_fn(items)
    after = set(filtered)

    removed = [(item, reason) for item in (before - after)]
    return list(filtered), removed
