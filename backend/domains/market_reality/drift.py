from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .models import (
    OddsTimeSeries, DriftAnalysis, DriftType, MoveDirection,
)


def analyze_drift(series: OddsTimeSeries) -> Optional[DriftAnalysis]:
    if len(series.ticks) < 2:
        return None

    opening = series.opening_odd
    closing = series.closing_odd
    if not opening:
        return None

    if closing:
        drift_pct = float((closing - opening) / opening * 100)
    else:
        drift_pct = 0.0

    ticks = series.ticks
    mid = len(ticks) // 2
    early_vol = _volatility_of_slice(ticks[:mid])
    late_vol = _volatility_of_slice(ticks[mid:])

    reversals = _count_reversals(ticks)
    has_reversal = reversals > 0

    drift_type = _classify_drift(drift_pct, reversals, early_vol, late_vol)

    clv = series.closing_line_value()

    return DriftAnalysis(
        event_id=series.event_id,
        market=series.market,
        outcome=series.outcome,
        opening_odd=opening,
        closing_odd=closing,
        drift_pct=round(drift_pct, 4),
        drift_type=drift_type,
        closing_line_value_pct=round(clv, 4) if clv is not None else None,
        early_volatility=round(early_vol, 4),
        late_volatility=round(late_vol, 4),
        reversal_detected=has_reversal,
        num_reversals=reversals,
    )


def _volatility_of_slice(ticks: list) -> float:
    if len(ticks) < 3:
        return 0.0
    changes = []
    for i in range(1, len(ticks)):
        prev = float(ticks[i - 1].odd)
        curr = float(ticks[i].odd)
        if prev > 0:
            changes.append(abs((curr - prev) / prev * 100))
    if not changes:
        return 0.0
    mean = sum(changes) / len(changes)
    variance = sum((c - mean) ** 2 for c in changes) / len(changes)
    return math.sqrt(variance)


def _count_reversals(ticks: list) -> int:
    if len(ticks) < 3:
        return 0
    diffs = []
    for i in range(1, len(ticks)):
        d = float(ticks[i].odd) - float(ticks[i - 1].odd)
        if abs(d) > 0:
            diffs.append(d)

    reversals = 0
    for i in range(1, len(diffs)):
        if diffs[i] * diffs[i - 1] < 0:
            reversals += 1
    return reversals


def _classify_drift(drift_pct: float, reversals: int, early_vol: float, late_vol: float) -> DriftType:
    if abs(drift_pct) < 0.2 and reversals <= 1:
        return DriftType.NONE

    if reversals >= 3:
        return DriftType.REVERSAL

    if late_vol > early_vol * 1.5 and late_vol > 0.5:
        return DriftType.LATE

    if early_vol > late_vol * 1.5 and early_vol > 0.5:
        return DriftType.EARLY

    return DriftType.SUSTAINED


def calculate_closing_line_value(
    opening_odd: Decimal,
    closing_odd: Decimal,
) -> Optional[float]:
    if opening_odd <= 0 or closing_odd <= 0:
        return None
    return float((closing_odd - opening_odd) / opening_odd * 100)


def detect_market_direction(series: list[OddsTimeSeries]) -> dict[str, MoveDirection]:
    directions = {}
    for s in series:
        analysis = analyze_drift(s)
        if analysis:
            directions[s.outcome] = analysis.direction
    return directions
