from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .models import (
    ClvGrade, ClvRecord, ClvSnapshot, TimingEfficiency,
)


def compute_clv(
    captured_odd: Decimal,
    closing_odd: Decimal,
    captured_prob: Optional[float] = None,
    closing_prob: Optional[float] = None,
) -> tuple[float, float]:
    """
    CLV = (captured_odd - closing_odd) / closing_odd  (odds space)
    CLV = closing_prob - captured_prob                (prob space)

    Returns (clv_odds, clv_prob) as floats.
    Positive CLV means you beat the closing line.
    """
    captured_f = float(captured_odd)
    closing_f = float(closing_odd)

    clv_odds = (captured_f - closing_f) / closing_f if closing_f > 0 else 0.0

    prob_captured = captured_prob or (1.0 / captured_f if captured_f > 1 else 0.0)
    prob_closing = closing_prob or (1.0 / closing_f if closing_f > 1 else 0.0)
    clv_prob = prob_closing - prob_captured

    return clv_odds, clv_prob


def classify_clv(clv_pct: float) -> ClvGrade:
    if clv_pct > 3.0:
        return ClvGrade.ELITE
    if clv_pct > 1.5:
        return ClvGrade.STRONG
    if clv_pct > 0.5:
        return ClvGrade.POSITIVE
    if clv_pct > -0.5:
        return ClvGrade.NEUTRAL
    if clv_pct > -1.5:
        return ClvGrade.NEGATIVE
    if clv_pct > -3.0:
        return ClvGrade.BAD
    return ClvGrade.CATASTROPHIC


def classify_timing(
    captured_at: datetime,
    closed_at: datetime,
    opening_at: datetime,
    odds_movement: float,
) -> TimingEfficiency:
    total_window = (closed_at - opening_at).total_seconds()
    capture_offset = (captured_at - opening_at).total_seconds()

    if total_window <= 0:
        return TimingEfficiency.OPTIMAL

    progress = capture_offset / total_window if total_window > 0 else 0.5

    if progress < 0.15:
        return TimingEfficiency.EARLY
    if progress < 0.70:
        return TimingEfficiency.OPTIMAL
    if progress < 0.95:
        return TimingEfficiency.LATE
    return TimingEfficiency.DEAD


def compute_hours_between(t1: datetime, t2: datetime) -> float:
    return abs((t2 - t1).total_seconds()) / 3600.0


def compute_odds_movement(opening: Decimal, closing: Decimal) -> float:
    if float(opening) <= 0:
        return 0.0
    return (float(closing) - float(opening)) / float(opening) * 100.0


def build_clv_record(
    event_id: str,
    market: str,
    outcome: str,
    bookmaker: str,
    captured_odd: Decimal,
    captured_at: datetime,
    closing_odd: Decimal,
    closed_at: datetime,
    opening_odd: Decimal,
    opening_at: datetime,
    captured_prob: Optional[float] = None,
    closing_prob: Optional[float] = None,
    model_edge: Optional[float] = None,
    simulated_ev: Optional[float] = None,
    simulated_kelly: Optional[float] = None,
) -> ClvRecord:
    clv_odds, clv_prob = compute_clv(
        captured_odd, closing_odd, captured_prob, closing_prob,
    )
    clv_pct = clv_odds * 100.0
    movement = compute_odds_movement(opening_odd, closing_odd)

    cap_prob = captured_prob or (1.0 / float(captured_odd) if float(captured_odd) > 1 else 0.0)
    cls_prob = closing_prob or (1.0 / float(closing_odd) if float(closing_odd) > 1 else 0.0)

    return ClvRecord(
        event_id=event_id,
        market=market,
        outcome=outcome,
        bookmaker=bookmaker,
        captured_odd=captured_odd,
        captured_prob=cap_prob,
        captured_at=captured_at,
        closing_odd=closing_odd,
        closing_prob=cls_prob,
        closed_at=closed_at,
        opening_odd=opening_odd,
        opening_at=opening_at,
        clv=clv_odds,
        clv_pct=clv_pct,
        timing_efficiency=classify_timing(captured_at, closed_at, opening_at, movement),
        hours_to_close=compute_hours_between(captured_at, closed_at),
        grade=classify_clv(clv_pct),
        odds_movement=movement,
        simulated_ev=simulated_ev or 0.0,
        simulated_kelly=simulated_kelly,
        model_edge=model_edge,
    )


def compute_implied_prob(odd: Decimal) -> float:
    return 1.0 / float(odd) if float(odd) > 1 else 0.0


def detect_leak(records: list[ClvRecord], threshold_pct: float = 0.3) -> list[dict]:
    leaks: list[dict] = []
    for r in records:
        captured_p = compute_implied_prob(r.captured_odd)
        closing_p = compute_implied_prob(r.closing_odd)
        opening_p = compute_implied_prob(r.opening_odd)

        opening_odd_f = float(r.opening_odd)
        captured_odd_f = float(r.captured_odd)

        # Late entry: opening was significantly better than our entry
        # opening odd > captured odd by at least 5%
        if opening_odd_f > captured_odd_f * 1.05 and closing_p > captured_p:
            leaks.append({
                "event_id": r.event_id,
                "bookmaker": r.bookmaker,
                "outcome": r.outcome,
                "opening_prob": opening_p,
                "captured_prob": captured_p,
                "closing_prob": closing_p,
                "type": "late_entry",
                "clv_pct": r.clv_pct,
            })

        # Market leak: odds moved against us significantly
        if r.clv_pct < -threshold_pct and r.simulated_ev > 0.05:
            leaks.append({
                "event_id": r.event_id,
                "bookmaker": r.bookmaker,
                "outcome": r.outcome,
                "type": "false_positive_ev",
                "ev": r.simulated_ev,
                "clv_pct": r.clv_pct,
                "movement": r.odds_movement,
            })

    return leaks


def compute_clv_from_snapshots(
    captured: ClvSnapshot,
    closing: ClvSnapshot,
    opening: Optional[ClvSnapshot] = None,
) -> ClvRecord:
    opening_snap = opening or captured
    return build_clv_record(
        event_id=captured.event_id,
        market=captured.market,
        outcome=captured.outcome,
        bookmaker=captured.bookmaker,
        captured_odd=captured.odd,
        captured_at=captured.timestamp,
        closing_odd=closing.odd,
        closed_at=closing.timestamp,
        opening_odd=opening_snap.odd,
        opening_at=opening_snap.timestamp,
    )
