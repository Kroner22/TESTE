from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .models import (
    OddsTimeSeries, OddsTick, MarketPressure, MoveDirection,
)


def analyze_pressure(
    series_list: list[OddsTimeSeries],
    min_ticks_per_series: int = 3,
) -> Optional[MarketPressure]:
    active = [s for s in series_list if len(s.ticks) >= min_ticks_per_series]
    if len(active) < 1:
        return None

    event_id = active[0].event_id
    market = active[0].market

    directional_scores = []
    accumulated = 0.0
    consistencies = []
    dominant_bms = []

    for s in active:
        d = _directional_pressure(s)
        if d is not None:
            directional_scores.append(d["bias"])
            accumulated += d["flow"]
            consistencies.append(d["consistency"])
            if d["is_dominant"]:
                dominant_bms.append(s.bookmaker)

    if not directional_scores:
        return None

    avg_bias = sum(directional_scores) / len(directional_scores)
    avg_consistency = sum(consistencies) / len(consistencies) if consistencies else 0.0
    pressure_val = abs(avg_bias) * avg_consistency

    direction = MoveDirection.UP if avg_bias > 0.1 else (
        MoveDirection.DOWN if avg_bias < -0.1 else MoveDirection.FLAT
    )
    significant = pressure_val > 0.3

    return MarketPressure(
        event_id=event_id,
        market=market,
        pressure_score=round(pressure_val, 4),
        directional_bias=round(avg_bias, 4),
        consistency=round(avg_consistency, 4),
        accumulated_flow=round(accumulated, 4),
        pressure_direction=direction,
        is_significant=significant,
        dominant_bookmakers=list(set(dominant_bms)),
    )


def _directional_pressure(series: OddsTimeSeries) -> Optional[dict]:
    ticks = series.ticks
    if len(ticks) < 3:
        return None

    changes = []
    for i in range(1, len(ticks)):
        prev = float(ticks[i - 1].odd)
        curr = float(ticks[i].odd)
        if prev > 0:
            changes.append((curr - prev) / prev * 100)

    if not changes:
        return None

    net = sum(changes)
    abs_total = sum(abs(c) for c in changes)

    if abs_total == 0:
        return None

    bias = net / abs_total
    n = len(changes)
    consistent = sum(1 for c in changes if c * net > 0) / n if net != 0 else 0.0
    is_dom = consistent > 0.6 and abs(bias) > 0.3

    return {
        "bias": bias,
        "flow": net,
        "consistency": consistent,
        "is_dominant": is_dom,
    }


def detect_steam_pressure(
    ticks: list[OddsTick],
    window_minutes: float = 5.0,
    acceleration_threshold: float = 2.0,
) -> bool:
    if len(ticks) < 3:
        return False
    window_start = ticks[-1].timestamp.timestamp() - window_minutes * 60
    recent = [t for t in ticks if t.timestamp.timestamp() >= window_start]
    if len(recent) < 3:
        return False

    velocities = []
    for i in range(1, len(recent)):
        prev = float(recent[i - 1].odd)
        curr = float(recent[i].odd)
        dt = (recent[i].timestamp - recent[i - 1].timestamp).total_seconds()
        if dt > 0 and prev > 0:
            velocities.append((curr - prev) / prev / dt * 3600)

    if len(velocities) < 2:
        return False

    accelerations = [velocities[i] - velocities[i - 1] for i in range(1, len(velocities))]
    return max(accelerations) > acceleration_threshold if accelerations else False
