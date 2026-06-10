from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from .models import OddsTimeSeries, LiquidityEstimate, LiquidityClass


def estimate_liquidity(
    series: OddsTimeSeries,
    min_ticks: int = 5,
) -> LiquidityEstimate:
    ticks = series.ticks
    if len(ticks) < min_ticks:
        return LiquidityEstimate(
            event_id=series.event_id,
            market=series.market,
            outcome=series.outcome,
            liquidity_class=LiquidityClass.FRAGILE,
            depth_score=0.0,
            avg_tick_size=0.0,
            max_delta_between_ticks=0.0,
            implied_depth=0.0,
            spread_volatility_ratio=0.0,
            confidence=0.0,
        )

    deltas = []
    for i in range(1, len(ticks)):
        prev = float(ticks[i - 1].odd)
        curr = float(ticks[i].odd)
        if prev > 0:
            deltas.append(abs(curr - prev) / prev * 100)

    if not deltas:
        return LiquidityEstimate(
            event_id=series.event_id,
            market=series.market,
            outcome=series.outcome,
            liquidity_class=LiquidityClass.FRAGILE,
            depth_score=0.0,
            avg_tick_size=0.0,
            max_delta_between_ticks=0.0,
            implied_depth=0.0,
            spread_volatility_ratio=0.0,
            confidence=0.0,
        )

    avg_tick = sum(deltas) / len(deltas)
    max_delta = max(deltas)
    n = len(deltas)
    mean_d = sum(deltas) / n
    variance = sum((d - mean_d) ** 2 for d in deltas) / n
    std_d = math.sqrt(variance)

    # Implied depth: inverse of avg tick size (smaller moves = deeper market)
    implied_depth = (1.0 / avg_tick) if avg_tick > 0 else 0.0
    implied_depth = min(implied_depth, 100.0)

    # Spread-volatility ratio: how much noise vs signal
    sv_ratio = std_d / avg_tick if avg_tick > 0 else 0.0

    depth_score = _depth_score(avg_tick, implied_depth, sv_ratio, len(ticks))
    lq_class = _classify_liquidity(depth_score)
    confidence = min(1.0, len(ticks) / 50.0)

    return LiquidityEstimate(
        event_id=series.event_id,
        market=series.market,
        outcome=series.outcome,
        liquidity_class=lq_class,
        depth_score=round(depth_score, 4),
        avg_tick_size=round(avg_tick, 4),
        max_delta_between_ticks=round(max_delta, 4),
        implied_depth=round(implied_depth, 4),
        spread_volatility_ratio=round(sv_ratio, 4),
        confidence=round(confidence, 4),
    )


def _depth_score(avg_tick: float, implied_depth: float, sv_ratio: float, n_ticks: int) -> float:
    tick_score = 1.0 - min(avg_tick / 2.0, 1.0)
    depth_score = min(implied_depth / 20.0, 1.0)
    sv_score = 1.0 - min(sv_ratio / 3.0, 1.0)
    n_score = min(n_ticks / 100.0, 1.0)
    return (tick_score * 0.3 + depth_score * 0.3 + sv_score * 0.2 + n_score * 0.2) * 100


def _classify_liquidity(score: float) -> LiquidityClass:
    if score >= 70:
        return LiquidityClass.DEEP
    if score >= 40:
        return LiquidityClass.MODERATE
    if score >= 20:
        return LiquidityClass.THIN
    return LiquidityClass.FRAGILE


def aggregate_liquidity(estimates: list[LiquidityEstimate]) -> dict[str, float]:
    if not estimates:
        return {}
    weighted = {}
    for est in estimates:
        key = est.liquidity_class.value
        weighted[key] = weighted.get(key, 0) + est.depth_score * est.confidence
    total = sum(weighted.values())
    if total > 0:
        return {k: v / total * 100 for k, v in weighted.items()}
    return {}
