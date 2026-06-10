from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .models import OddsTimeSeries, OddsMomentum


def compute_momentum(
    series: OddsTimeSeries,
    short_window: int = 3,
    long_window: int = 8,
) -> Optional[OddsMomentum]:
    if len(series.ticks) < long_window + 1:
        return None

    ticks = series.ticks
    vals = [float(t.odd) for t in ticks]

    # Rate of change
    roc = (vals[-1] - vals[-long_window]) / vals[-long_window] * 100 if vals[-long_window] > 0 else 0

    # Moving averages
    short_ma = sum(vals[-short_window:]) / short_window
    long_ma = sum(vals[-long_window:]) / long_window

    # Acceleration: change in velocity
    v1 = vals[-short_window] - vals[-long_window] if len(vals) >= long_window + short_window else 0
    v2 = vals[-1] - vals[-short_window]
    accel = v2 - v1

    # Duration of current trend
    duration_min = _trend_duration(ticks)

    # Velocities
    dt = (ticks[-1].timestamp - ticks[-long_window].timestamp).total_seconds()
    recent_vel = roc / (dt / 60.0) if dt > 0 else 0

    # Smoothed velocity (EMA-like)
    diffs = []
    for i in range(1, len(vals)):
        diffs.append(vals[i] - vals[i - 1])
    alpha = 0.3
    smoothed = diffs[0] if diffs else 0.0
    for d in diffs[1:]:
        smoothed = alpha * d + (1 - alpha) * smoothed

    strength = _momentum_strength(abs(roc), abs(accel), recent_vel)

    return OddsMomentum(
        event_id=series.event_id,
        market=series.market,
        outcome=series.outcome,
        momentum_value=round(roc, 4),
        acceleration=round(accel, 4),
        duration_minutes=round(duration_min, 2),
        is_rising=roc > 0,
        strength=strength,
        recent_velocity=round(recent_vel, 4),
        smoothed_velocity=round(smoothed, 4),
    )


def _trend_duration(ticks: list) -> float:
    if len(ticks) < 3:
        return 0.0
    vals = [float(t.odd) for t in ticks]
    end_val = vals[-1]
    direction = end_val - vals[-2]
    if abs(direction) < 1e-6:
        return 0.0

    trend_start = len(ticks) - 1
    for i in range(len(ticks) - 2, -1, -1):
        if (end_val - vals[i]) * direction < 0:
            trend_start = i
            break

    if trend_start >= len(ticks) - 1:
        return 0.0
    return (ticks[-1].timestamp - ticks[trend_start].timestamp).total_seconds() / 60.0


def _momentum_strength(abs_roc: float, abs_accel: float, velocity: float) -> str:
    score = abs_roc * 0.4 + abs_accel * 0.3 + abs(velocity) * 0.3
    if score < 1:
        return "weak"
    if score < 3:
        return "moderate"
    if score < 8:
        return "strong"
    return "extreme"


def momentum_divergence(
    series_list: list[OddsTimeSeries],
) -> list[dict]:
    divergences = []
    for s in series_list:
        m = compute_momentum(s)
        if m is None:
            continue
        if m.momentum_value > 2 and m.acceleration < -1:
            divergences.append({
                "outcome": s.outcome,
                "type": "bearish_divergence",
                "momentum": m.momentum_value,
                "acceleration": m.acceleration,
            })
        elif m.momentum_value < -2 and m.acceleration > 1:
            divergences.append({
                "outcome": s.outcome,
                "type": "bullish_divergence",
                "momentum": m.momentum_value,
                "acceleration": m.acceleration,
            })
    return divergences
