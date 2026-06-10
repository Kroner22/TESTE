from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .models import (
    MarketRealitySnapshot, SteamMove, SteamStrength,
    MarketDistortion, DistortionType, BookmakerBehaviorReport,
    VolatilityRegime, LiquidityClass,
)
from .tracker import OddsTracker
from .drift import analyze_drift, detect_market_direction
from .steam import detect_steam_moves, detect_steam_across_bookmakers
from .volatility import compute_volatility, cross_series_volatility
from .liquidity import estimate_liquidity, aggregate_liquidity
from .pressure import analyze_pressure, detect_steam_pressure
from .momentum import compute_momentum, momentum_divergence
from .sensitivity import analyze_sensitivity
from .bookmaker import analyze_bookmaker, compare_bookmaker_pairs


@dataclass
class MarketRealityConfig:
    min_ticks_for_analysis: int = 5
    steam_min_change_pct: float = 1.0
    steam_min_velocity: float = 0.5
    steam_min_sustained_minutes: float = 2.0
    volatility_large_move_threshold: float = 2.0
    liquidity_min_ticks: int = 5
    pressure_min_ticks_per_series: int = 3
    momentum_short_window: int = 3
    momentum_long_window: int = 8
    sensitivity_min_ticks: int = 5
    bookmaker_min_ticks: int = 3
    distortion_max_steam_moves: int = 5


class MarketRealityEngine:
    """
    Orchestrator for the Market Reality Engine.

    Coordinates odds tracking, drift analysis, steam detection,
    volatility measurement, liquidity estimation, pressure analysis,
    momentum computation, sensitivity assessment, and bookmaker
    behavior profiling.
    """

    def __init__(self, config: Optional[MarketRealityConfig] = None):
        self.config = config or MarketRealityConfig()
        self.tracker = OddsTracker()
        self._scan_events: set[str] = set()

    def record_tick(
        self,
        event_id: str,
        market: str,
        outcome: str,
        bookmaker: str,
        odd: Decimal,
        timestamp: Optional[datetime] = None,
        is_opening: bool = False,
        is_closing: bool = False,
    ) -> None:
        self.tracker.record_tick(
            event_id=event_id,
            market=market,
            outcome=outcome,
            bookmaker=bookmaker,
            odd=odd,
            timestamp=timestamp,
            is_opening=is_opening,
            is_closing=is_closing,
        )
        self._scan_events.add(event_id)

    def snapshot(self, event_id: str, market: str) -> Optional[MarketRealitySnapshot]:
        series_list = self.tracker.get_series_for_market(event_id, market)
        if not series_list:
            return None

        snap = MarketRealitySnapshot(
            event_id=event_id,
            market=market,
            timestamp=datetime.now(timezone.utc),
        )

        cfg = self.config

        # Drift
        for s in series_list:
            drift = analyze_drift(s)
            if drift is not None:
                snap.drift = drift
                break

        # Steam
        steam_moves = []
        for s in series_list:
            moves = detect_steam_moves(
                s,
                min_change_pct=cfg.steam_min_change_pct,
                min_velocity=cfg.steam_min_velocity,
                min_sustained_minutes=cfg.steam_min_sustained_minutes,
            )
            steam_moves.extend(moves)
        steam_moves.sort(key=lambda m: m.magnitude, reverse=True)
        snap.steam_moves = steam_moves[:cfg.distortion_max_steam_moves]

        # Volatility
        vol_results = cross_series_volatility(series_list)
        if vol_results:
            scores = [v.volatility_score for v in vol_results.values()]
            regimes = [v.regime for v in vol_results.values()]
            snap.volatility = compute_volatility(series_list[0])

        # Liquidity
        liquidities = [estimate_liquidity(s) for s in series_list]
        if liquidities:
            snap.liquidity = max(liquidities, key=lambda l: l.confidence)

        # Pressure
        snap.pressure = analyze_pressure(
            series_list,
            min_ticks_per_series=cfg.pressure_min_ticks_per_series,
        )

        # Momentum
        for s in series_list:
            m = compute_momentum(s, short_window=cfg.momentum_short_window, long_window=cfg.momentum_long_window)
            if m is not None:
                snap.momentum = m
                break

        # Sensitivity
        snap.sensitivity = analyze_sensitivity(
            series_list,
            min_ticks=cfg.sensitivity_min_ticks,
        )

        # Distortions
        snap.distortions = self._detect_distortions(series_list, steam_moves)

        return snap

    def full_report(self, event_id: str, market: str) -> Optional[dict]:
        snap = self.snapshot(event_id, market)
        if snap is None:
            return None

        series_list = self.tracker.get_series_for_market(event_id, market)

        directions = detect_market_direction(series_list)
        divergences_list = momentum_divergence(series_list)
        bk_report = analyze_bookmaker(series_list, min_ticks=self.config.bookmaker_min_ticks)
        lq_agg = aggregate_liquidity(
            [estimate_liquidity(s) for s in series_list]
        ) if series_list else {}

        return {
            "event_id": event_id,
            "market": market,
            "timestamp": snap.timestamp.isoformat(),
            "snapshot": {
                "drift": snap.drift,
                "volatility": snap.volatility,
                "liquidity": snap.liquidity,
                "pressure": snap.pressure,
                "momentum": snap.momentum,
                "sensitivity": snap.sensitivity,
                "distortions": snap.distortions,
                "steam_moves": snap.steam_moves,
            },
            "aggregates": {
                "market_directions": {k: v.value for k, v in directions.items()},
                "momentum_divergences": divergences_list,
                "liquidity_distribution": lq_agg,
            },
            "bookmakers": {
                "report": bk_report,
                "comparisons": compare_bookmaker_pairs(bk_report.profiles),
            },
            "series_summary": {
                "num_series": len(series_list),
                "bookmakers": list(set(s.bookmaker for s in series_list)),
                "outcomes": list(set(s.outcome for s in series_list)),
            },
        }

    def _detect_distortions(
        self,
        series_list: list,
        steam_moves: list[SteamMove],
    ) -> list[MarketDistortion]:
        distortions = []
        now = datetime.now(timezone.utc)

        # Distortion: strong steam moves
        strong_steams = [s for s in steam_moves if s.strength in (SteamStrength.STRONG, SteamStrength.EXTREME)]
        if strong_steams:
            involved = list(set(s.bookmaker for s in strong_steams))
            severity = max(s.magnitude for s in strong_steams) / 10.0
            distortions.append(MarketDistortion(
                event_id=strong_steams[0].event_id,
                market=strong_steams[0].market,
                distortion_type=DistortionType.OVERREACTION,
                severity=min(severity, 1.0),
                description=f"Strong steam move detected across {len(involved)} bookmaker(s)",
                detected_at=now,
                confidence=min(severity, 1.0),
                involved_bookmakers=involved,
            ))

        # Distortion: thin liquidity + high volatility
        if len(series_list) >= 1:
            lq = estimate_liquidity(series_list[0])
            vol = compute_volatility(series_list[0])
            if lq.liquidity_class in (LiquidityClass.THIN, LiquidityClass.FRAGILE) and vol.regime in (VolatilityRegime.VOLATILE, VolatilityRegime.CHAOTIC):
                distortions.append(MarketDistortion(
                    event_id=series_list[0].event_id,
                    market=series_list[0].market,
                    distortion_type=DistortionType.ARTIFICIAL,
                    severity=min(vol.volatility_score / 100.0 * (1 - lq.depth_score / 100.0), 1.0),
                    description="Thin liquidity with high volatility — possible artificial pricing",
                    detected_at=now,
                    confidence=0.6,
                    involved_bookmakers=[series_list[0].bookmaker],
                ))

        # Distortion: conflicting directions across bookmakers
        if len(series_list) >= 3:
            directions = set()
            for s in series_list:
                d = analyze_drift(s)
                if d:
                    directions.add(d.direction.value)
            if len(directions) >= 2:
                bks = list(set(s.bookmaker for s in series_list))
                distortions.append(MarketDistortion(
                    event_id=series_list[0].event_id,
                    market=series_list[0].market,
                    distortion_type=DistortionType.LINE_MISMATCH,
                    severity=0.4,
                    description=f"Conflicting drift directions across bookmakers: {directions}",
                    detected_at=now,
                    confidence=0.5,
                    involved_bookmakers=bks,
                ))

        return distortions

    def clear_event(self, event_id: str) -> int:
        removed = self.tracker.remove_series(event_id)
        self._scan_events.discard(event_id)
        return removed

    def clear_all(self):
        self.tracker.clear()
        self._scan_events.clear()

    @property
    def tracked_events(self) -> list[str]:
        return list(self._scan_events)
