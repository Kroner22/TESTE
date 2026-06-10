from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from .models import OddsTimeSeries, VolatilityMetrics, VolatilityRegime


def compute_volatility(
    series: OddsTimeSeries,
    large_move_threshold_pct: float = 2.0,
) -> VolatilityMetrics:
    if len(series.ticks) < 3:
        return VolatilityMetrics(
            event_id=series.event_id,
            market=series.market,
            overall_std=0.0,
            mean_absolute_change=0.0,
            max_single_move_pct=0.0,
            coefficient_variation=0.0,
            regime=VolatilityRegime.CALM,
            volatility_score=0.0,
            num_moves=0,
            large_moves_count=0,
            large_move_threshold_pct=large_move_threshold_pct,
        )

    ticks = series.ticks
    changes = []
    for i in range(1, len(ticks)):
        prev = float(ticks[i - 1].odd)
        curr = float(ticks[i].odd)
        if prev > 0:
            changes.append((curr - prev) / prev * 100)

    if not changes:
        return VolatilityMetrics(
            event_id=series.event_id,
            market=series.market,
            overall_std=0.0,
            mean_absolute_change=0.0,
            max_single_move_pct=0.0,
            coefficient_variation=0.0,
            regime=VolatilityRegime.CALM,
            volatility_score=0.0,
            num_moves=0,
            large_moves_count=0,
            large_move_threshold_pct=large_move_threshold_pct,
        )

    n = len(changes)
    mean = sum(changes) / n
    variance = sum((c - mean) ** 2 for c in changes) / n
    std = math.sqrt(variance)
    abs_changes = [abs(c) for c in changes]
    mean_abs = sum(abs_changes) / n
    max_move = max(abs_changes)
    cv = std / abs(mean) if abs(mean) > 1e-10 else std * 100
    large_moves = sum(1 for c in abs_changes if c > large_move_threshold_pct)
    score = _volatility_score(std, mean_abs, max_move, large_moves, n)
    regime = _classify_regime(score)

    return VolatilityMetrics(
        event_id=series.event_id,
        market=series.market,
        overall_std=round(std, 4),
        mean_absolute_change=round(mean_abs, 4),
        max_single_move_pct=round(max_move, 4),
        coefficient_variation=round(cv, 4),
        regime=regime,
        volatility_score=round(score, 4),
        num_moves=n,
        large_moves_count=large_moves,
        large_move_threshold_pct=large_move_threshold_pct,
    )


def _volatility_score(std: float, mean_abs: float, max_move: float, large_moves: int, n: int) -> float:
    std_norm = min(std / 5.0, 1.0)
    mac_norm = min(mean_abs / 3.0, 1.0)
    max_norm = min(max_move / 10.0, 1.0)
    dense_norm = min(large_moves / max(n, 1) * 10, 1.0)
    return (std_norm * 0.35 + mac_norm * 0.25 + max_norm * 0.25 + dense_norm * 0.15) * 100


def _classify_regime(score: float) -> VolatilityRegime:
    if score < 10:
        return VolatilityRegime.CALM
    if score < 30:
        return VolatilityRegime.NORMAL
    if score < 60:
        return VolatilityRegime.VOLATILE
    return VolatilityRegime.CHAOTIC


def cross_series_volatility(series_list: list[OddsTimeSeries]) -> dict[str, VolatilityMetrics]:
    return {s.outcome: compute_volatility(s) for s in series_list}
