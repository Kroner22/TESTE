from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .models import OddsTimeSeries, SteamMove, SteamStrength


def detect_steam_moves(
    series: OddsTimeSeries,
    min_change_pct: float = 1.0,
    min_velocity: float = 0.5,
    min_sustained_minutes: float = 2.0,
) -> list[SteamMove]:
    if len(series.ticks) < 3:
        return []

    ticks = series.ticks
    moves = []
    i = 0
    while i < len(ticks) - 2:
        window = _find_steam_window(
            ticks, i, min_change_pct, min_velocity, min_sustained_minutes
        )
        if window is None:
            i += 1
            continue
        start_idx, end_idx, change_pct, velocity, sustained = window
        start_tick = ticks[start_idx]
        end_tick = ticks[end_idx]
        duration = (end_tick.timestamp - start_tick.timestamp).total_seconds()

        strength = _classify_strength(change_pct, velocity, duration, sustained)

        if strength != SteamStrength.NONE:
            moves.append(SteamMove(
                event_id=series.event_id,
                market=series.market,
                outcome=series.outcome,
                bookmaker=series.bookmaker,
                start_odd=start_tick.odd,
                end_odd=end_tick.odd,
                start_time=start_tick.timestamp,
                end_time=end_tick.timestamp,
                duration_seconds=round(duration, 1),
                change_pct=round(change_pct, 4),
                strength=strength,
                velocity_pct_per_min=round(velocity, 4),
                sustained=sustained,
            ))
        i = end_idx + 1

    return moves


def _find_steam_window(ticks, start_idx: int, min_change: float, min_vel: float, min_sustained: float):
    for end in range(start_idx + 2, len(ticks)):
        first = float(ticks[start_idx].odd)
        last = float(ticks[end].odd)
        if first <= 0:
            continue
        change_pct = abs((last - first) / first * 100)

        duration = (ticks[end].timestamp - ticks[start_idx].timestamp).total_seconds()
        duration_min = duration / 60.0 if duration > 0 else 0.001

        velocity = change_pct / duration_min if duration_min > 0 else 0

        if change_pct >= min_change and velocity >= min_vel:
            sustained = duration_min >= min_sustained
            return start_idx, end, change_pct, velocity, sustained
    return None


def _classify_strength(change_pct: float, velocity: float, duration_sec: float, sustained: bool) -> SteamStrength:
    if not sustained:
        if change_pct > 5 and velocity > 10:
            return SteamStrength.EXTREME
        if change_pct > 3 and velocity > 5:
            return SteamStrength.STRONG
        if change_pct > 2 and velocity > 2:
            return SteamStrength.MODERATE
        if change_pct > 1 and velocity > 0.5:
            return SteamStrength.WEAK
        return SteamStrength.NONE

    if change_pct > 8 and velocity > 3:
        return SteamStrength.EXTREME
    if change_pct > 4 and velocity > 1.5:
        return SteamStrength.STRONG
    if change_pct > 2 and velocity > 0.8:
        return SteamStrength.MODERATE
    if change_pct > 1 and velocity > 0.5:
        return SteamStrength.WEAK
    return SteamStrength.NONE


def detect_steam_across_bookmakers(
    series_list: list[OddsTimeSeries],
    min_bookmakers: int = 2,
    **kwargs,
) -> list[SteamMove]:
    all_moves = []
    for series in series_list:
        moves = detect_steam_moves(series, **kwargs)
        concurrent = _filter_concurrent(moves, min_bookmakers)
        all_moves.extend(concurrent)
    return all_moves


def _filter_concurrent(moves: list[SteamMove], min_bk: int) -> list[SteamMove]:
    return [m for m in moves if m.strength != SteamStrength.NONE]
