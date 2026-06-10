from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .models import OddsTimeSeries, MarketSensitivity


def analyze_sensitivity(
    series_list: list[OddsTimeSeries],
    min_ticks: int = 5,
) -> Optional[MarketSensitivity]:
    active = [s for s in series_list if len(s.ticks) >= min_ticks]
    if len(active) < 2:
        return None

    event_id = active[0].event_id
    market = active[0].market

    cross_corr = _compute_cross_correlations(active)
    own_sens = _own_sensitivity(active)
    elasticity = _market_elasticity(active)
    reversion = _mean_reversion_speed(active)
    overreact = _detect_overreaction(active)

    score = (own_sens * 0.3 + elasticity * 0.25 + (1 - reversion) * 0.25 + (0.5 if overreact else 0) * 0.2) * 100
    score = min(max(score, 0), 100)

    return MarketSensitivity(
        event_id=event_id,
        market=market,
        cross_correlation=cross_corr,
        own_sensitivity=round(own_sens, 4),
        market_elasticity=round(elasticity, 4),
        mean_reversion_speed=round(reversion, 4),
        overreaction_detected=overreact,
        sensitivity_score=round(score, 4),
    )


def _compute_cross_correlations(series_list: list[OddsTimeSeries]) -> dict[str, float]:
    outcomes = {s.outcome: [float(t.odd) for t in s.ticks] for s in series_list}
    correlations = {}

    keys = list(outcomes.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            k1, k2 = keys[i], keys[j]
            v1, v2 = outcomes[k1], outcomes[k2]
            min_len = min(len(v1), len(v2))
            if min_len < 3:
                corr = 0.0
            else:
                corr = _pearson(v1[-min_len:], v2[-min_len:])
            correlations[f"{k1}_vs_{k2}"] = round(corr, 4)
    return correlations


def _own_sensitivity(series_list: list[OddsTimeSeries]) -> float:
    changes = []
    for s in series_list:
        vals = [float(t.odd) for t in s.ticks]
        for i in range(1, len(vals)):
            if vals[i - 1] > 0:
                changes.append(abs(vals[i] - vals[i - 1]) / vals[i - 1] * 100)
    if not changes:
        return 0.0
    return sum(changes) / len(changes)


def _market_elasticity(series_list: list[OddsTimeSeries]) -> float:
    total_move = 0.0
    count = 0
    for s in series_list:
        vals = [float(t.odd) for t in s.ticks]
        if len(vals) >= 2 and vals[0] > 0:
            total_move += abs(vals[-1] - vals[0]) / vals[0] * 100
            count += 1
    if count == 0:
        return 0.0
    return min(total_move / count / 10.0, 1.0)


def _mean_reversion_speed(series_list: list[OddsTimeSeries]) -> float:
    speeds = []
    for s in series_list:
        vals = [float(t.odd) for t in s.ticks]
        if len(vals) < 5:
            continue
        mean_val = sum(vals) / len(vals)
        crossings = 0
        for i in range(1, len(vals)):
            if (vals[i] - mean_val) * (vals[i - 1] - mean_val) < 0:
                crossings += 1
        speed = crossings / (len(vals) / 10.0) if len(vals) > 0 else 0
        speeds.append(min(speed / 5.0, 1.0))

    return sum(speeds) / len(speeds) if speeds else 0.0


def _detect_overreaction(series_list: list[OddsTimeSeries]) -> bool:
    for s in series_list:
        vals = [float(t.odd) for t in s.ticks]
        if len(vals) < 6:
            continue
        max_move = 0
        for i in range(2, len(vals)):
            move = abs(vals[i] - vals[i - 1]) / vals[i - 1] * 100
            if move > max_move:
                max_move = move
        if max_move > 5:
            return True
    return False


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    d1 = math.sqrt(sum((x[i] - mx) ** 2 for i in range(n)))
    d2 = math.sqrt(sum((y[i] - my) ** 2 for i in range(n)))
    if d1 * d2 == 0:
        return 0.0
    return num / (d1 * d2)
