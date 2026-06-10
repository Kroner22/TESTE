from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Callable, Awaitable

from backend.app.log_config import get_logger

logger = get_logger(__name__)


class SurveyPoint:
    event_id: str
    market: str
    outcome: str
    provider: str
    odd: float
    timestamp: float
    latency_ms: float

    def __init__(self, event_id: str, market: str, outcome: str, provider: str, odd: float, timestamp: float, latency_ms: float = 0.0):
        self.event_id = event_id
        self.market = market
        self.outcome = outcome
        self.provider = provider
        self.odd = odd
        self.timestamp = timestamp
        self.latency_ms = latency_ms


class MarketConsensus:
    event_id: str
    market: str
    outcome: str
    consensus_odd: float
    confidence: float
    provider_count: int
    outlier_count: int
    deviation_pct: float
    provider_odds: dict[str, float]
    timestamp: float

    def __init__(self, event_id: str, market: str, outcome: str, consensus_odd: float, confidence: float, provider_count: int, outlier_count: int, deviation_pct: float, provider_odds: dict[str, float], timestamp: float):
        self.event_id = event_id
        self.market = market
        self.outcome = outcome
        self.consensus_odd = consensus_odd
        self.confidence = confidence
        self.provider_count = provider_count
        self.outlier_count = outlier_count
        self.deviation_pct = deviation_pct
        self.provider_odds = provider_odds
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "market": self.market,
            "outcome": self.outcome,
            "consensus_odd": round(self.consensus_odd, 4),
            "confidence": round(self.confidence, 4),
            "provider_count": self.provider_count,
            "outlier_count": self.outlier_count,
            "deviation_pct": round(self.deviation_pct, 4),
            "provider_odds": self.provider_odds,
            "timestamp": self.timestamp,
        }


class SharpMoveEvent:
    event_id: str
    market: str
    move_type: str
    magnitude_pct: float
    velocity_pct_per_min: float
    direction: str
    duration_seconds: float
    confidence: float

    def __init__(self, event_id: str, market: str, move_type: str, magnitude_pct: float, velocity_pct_per_min: float, direction: str, duration_seconds: float, confidence: float):
        self.event_id = event_id
        self.market = market
        self.move_type = move_type
        self.magnitude_pct = magnitude_pct
        self.velocity_pct_per_min = velocity_pct_per_min
        self.direction = direction
        self.duration_seconds = duration_seconds
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "market": self.market,
            "move_type": self.move_type,
            "magnitude_pct": round(self.magnitude_pct, 2),
            "velocity_pct_per_min": round(self.velocity_pct_per_min, 2),
            "direction": self.direction,
            "duration_seconds": round(self.duration_seconds, 1),
            "confidence": round(self.confidence, 2),
        }


class InconsistencyEvent:
    event_id: str
    market: str
    inconsistency_type: str
    severity: float
    provider_a: str
    provider_b: str
    odd_a: float
    odd_b: float
    deviation_pct: float

    def __init__(self, event_id: str, market: str, inconsistency_type: str, severity: float, provider_a: str, provider_b: str, odd_a: float, odd_b: float, deviation_pct: float):
        self.event_id = event_id
        self.market = market
        self.inconsistency_type = inconsistency_type
        self.severity = severity
        self.provider_a = provider_a
        self.provider_b = provider_b
        self.odd_a = odd_a
        self.odd_b = odd_b
        self.deviation_pct = deviation_pct

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "market": self.market,
            "inconsistency_type": self.inconsistency_type,
            "severity": round(self.severity, 2),
            "provider_a": self.provider_a,
            "provider_b": self.provider_b,
            "odd_a": round(self.odd_a, 4),
            "odd_b": round(self.odd_b, 4),
            "deviation_pct": round(self.deviation_pct, 2),
        }


class LatencySample:
    provider: str
    market: str
    latency_ms: float
    timestamp: float

    def __init__(self, provider: str, market: str, latency_ms: float, timestamp: float):
        self.provider = provider
        self.market = market
        self.latency_ms = latency_ms
        self.timestamp = timestamp


class MarketTruthService:
    """
    Multi-source reconciliation engine.

    Ingests SurveyPoints from all providers, computes weighted consensus,
    detects outliers, tracks sharp moves, models latency, and emits
    structured events for downstream (EV engine, WebSocket broadcast).
    """

    PROVIDER_WEIGHTS_DEFAULT: dict[str, float] = {
        "Betano": 1.0,
        "bet365": 0.95,
        "Sportingbet": 0.90,
        "Bwin": 0.90,
        "Betfair": 0.98,
    }

    def __init__(self):
        self._provider_weights: dict[str, float] = dict(self.PROVIDER_WEIGHTS_DEFAULT)

        self._consensus_history: dict[str, list[MarketConsensus]] = defaultdict(list)
        self._consensus_window_size = 10

        self._latency_samples: dict[str, list[LatencySample]] = defaultdict(list)
        self._latency_window_size = 100

        self._provider_reliability: dict[str, float] = defaultdict(lambda: 1.0)
        self._reliability_decay = 0.95

        self._broadcast_callback: Optional[Callable[[dict], Awaitable[None]]] = None

    def set_broadcast_callback(self, callback: Callable[[dict], Awaitable[None]]):
        self._broadcast_callback = callback

    def set_provider_weight(self, provider: str, weight: float):
        self._provider_weights[provider] = max(0.0, min(1.0, weight))

    def get_provider_weight(self, provider: str) -> float:
        return self._provider_weights.get(provider, 0.5)

    def record_survey_point(self, sp: SurveyPoint):
        self._record_latency(sp.provider, sp.market, sp.latency_ms)

    def reconcile(self, points: list[SurveyPoint]) -> Optional[MarketConsensus]:
        if not points:
            return None

        for sp in points:
            self.record_survey_point(sp)

        event_id = points[0].event_id
        market = points[0].market
        outcome = points[0].outcome

        weighted_sum = 0.0
        total_weight = 0.0
        provider_odds: dict[str, float] = {}

        for sp in points:
            w = self._provider_weight(sp.provider)
            weighted_sum += sp.odd * w
            total_weight += w
            provider_odds[sp.provider] = sp.odd

        if total_weight <= 0:
            return None

        consensus_odd = weighted_sum / total_weight

        deviations = [abs(sp.odd - consensus_odd) / consensus_odd * 100 for sp in points]
        mean_dev = sum(deviations) / len(deviations) if deviations else 0.0
        std_dev = (sum((d - mean_dev) ** 2 for d in deviations) / len(deviations)) ** 0.5 if len(deviations) > 1 else 0.0
        outliers = sum(1 for d in deviations if abs(d - mean_dev) > 2 * std_dev) if std_dev > 0 else 0

        provider_count = len(points)
        reliability_product = 1.0
        for sp in points:
            reliability_product *= self._provider_reliability.get(sp.provider, 1.0)
        confidence = reliability_product ** (1.0 / max(1, provider_count)) if provider_count > 0 else 0.5
        confidence = max(0.1, min(1.0, confidence))
        if std_dev > 0:
            confidence *= max(0.1, 1.0 - (std_dev / 10.0))

        result = MarketConsensus(
            event_id=event_id,
            market=market,
            outcome=outcome,
            consensus_odd=consensus_odd,
            confidence=round(confidence, 4),
            provider_count=provider_count,
            outlier_count=outliers,
            deviation_pct=round(mean_dev, 4),
            provider_odds=provider_odds,
            timestamp=time.time(),
        )

        self._consensus_history[self._key(event_id, market, outcome)].append(result)
        h = self._consensus_history[self._key(event_id, market, outcome)]
        if len(h) > self._consensus_window_size:
            self._consensus_history[self._key(event_id, market, outcome)] = h[-self._consensus_window_size:]

        return result

    def detect_sharp_move(self, event_id: str, market: str, outcome: str) -> Optional[SharpMoveEvent]:
        key = self._key(event_id, market, outcome)
        history = self._consensus_history.get(key, [])
        if len(history) < 3:
            return None

        recent = history[-3:]
        t0 = recent[0]
        t2 = recent[-1]

        duration = t2.timestamp - t0.timestamp
        if duration <= 0:
            return None

        magnitude_pct = abs((t2.consensus_odd - t0.consensus_odd) / t0.consensus_odd * 100)
        velocity = magnitude_pct / (duration / 60.0) if duration > 0 else 0
        direction = "up" if t2.consensus_odd > t0.consensus_odd else "down"

        provider_count = len(set(t2.provider_odds.keys()) & set(t0.provider_odds.keys()))
        provider_agreement = self._compute_provider_agreement(t0, t2)

        if magnitude_pct > 3.0 and velocity > 2.0:
            return SharpMoveEvent(
                event_id=event_id, market=market, move_type="steam",
                magnitude_pct=magnitude_pct, velocity_pct_per_min=velocity,
                direction=direction, duration_seconds=duration,
                confidence=min(1.0, (magnitude_pct / 5.0) * provider_agreement),
            )

        if magnitude_pct > 1.5 and provider_agreement < 0.3 and provider_count >= 2:
            return SharpMoveEvent(
                event_id=event_id, market=market, move_type="reverse_line",
                magnitude_pct=magnitude_pct, velocity_pct_per_min=velocity,
                direction=direction, duration_seconds=duration,
                confidence=min(1.0, (1.0 - provider_agreement) * 2),
            )

        return None

    def detect_inconsistency(self, points: list[SurveyPoint]) -> Optional[InconsistencyEvent]:
        if len(points) < 2:
            return None

        consensus = self.reconcile(points)
        if not consensus:
            return None

        worst_dev = 0.0
        worst_pair = (None, None)
        worst_odds = (0.0, 0.0)

        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                a, b = points[i], points[j]
                if a.odd <= 0 or b.odd <= 0:
                    continue
                dev = abs(a.odd - b.odd) / ((a.odd + b.odd) / 2) * 100
                if dev > worst_dev:
                    worst_dev = dev
                    worst_pair = (a.provider, b.provider)
                    worst_odds = (a.odd, b.odd)

        if worst_dev > 3.0:
            return InconsistencyEvent(
                event_id=points[0].event_id,
                market=points[0].market,
                inconsistency_type="provider_divergence",
                severity=min(1.0, worst_dev / 10.0),
                provider_a=worst_pair[0],
                provider_b=worst_pair[1],
                odd_a=worst_odds[0],
                odd_b=worst_odds[1],
                deviation_pct=round(worst_dev, 2),
            )

        return None

    def detect_latency_arbitrage(self, points: list[SurveyPoint], max_stale_seconds: float = 5.0) -> Optional[InconsistencyEvent]:
        if len(points) < 2:
            return None

        now = time.time()
        freshest = max(sp.timestamp for sp in points)
        stalest = min(sp.timestamp for sp in points)
        age_gap = now - stalest

        if age_gap < max_stale_seconds:
            return None

        freshest_pt = next(sp for sp in points if sp.timestamp == freshest)
        stalest_pt = next(sp for sp in points if sp.timestamp == stalest)

        if freshest_pt.odd <= 0 or stalest_pt.odd <= 0:
            return None

        dev = abs(freshest_pt.odd - stalest_pt.odd) / ((freshest_pt.odd + stalest_pt.odd) / 2) * 100
        gap_seconds = freshest - stalest

        if dev > 1.0 and gap_seconds > 1.0:
            return InconsistencyEvent(
                event_id=freshest_pt.event_id,
                market=freshest_pt.market,
                inconsistency_type="latency_arbitrage_window",
                severity=min(1.0, dev / 5.0),
                provider_a=freshest_pt.provider,
                provider_b=stalest_pt.provider,
                odd_a=freshest_pt.odd,
                odd_b=stalest_pt.odd,
                deviation_pct=round(dev, 2),
            )

        return None

    def _compute_provider_agreement(self, a: MarketConsensus, b: MarketConsensus) -> float:
        common = set(a.provider_odds.keys()) & set(b.provider_odds.keys())
        if not common:
            return 0.0

        total_dir = 0
        for p in common:
            diff_a = a.provider_odds[p] - a.consensus_odd
            diff_b = b.provider_odds[p] - b.consensus_odd
            if (diff_a > 0 and diff_b > 0) or (diff_a < 0 and diff_b < 0):
                total_dir += 1

        return total_dir / len(common)

    def get_latency_stats(self, provider: str) -> dict:
        samples = self._latency_samples.get(provider, [])
        if not samples:
            return {"provider": provider, "avg_ms": 0, "median_ms": 0, "p95_ms": 0, "samples": 0}

        latencies = sorted(s.latency_ms for s in samples)
        n = len(latencies)
        return {
            "provider": provider,
            "avg_ms": round(sum(latencies) / n, 1),
            "median_ms": round(latencies[n // 2], 1),
            "p95_ms": round(latencies[int(n * 0.95)], 1),
            "samples": n,
        }

    def get_latency_heatmap(self) -> list[dict]:
        providers = list(self._latency_samples.keys())
        all_markets: set[str] = set()
        for samples in self._latency_samples.values():
            for s in samples:
                all_markets.add(s.market)

        rows = []
        for p in providers:
            row = {"provider": p}
            for m in sorted(all_markets):
                relevant = [s.latency_ms for s in self._latency_samples[p] if s.market == m]
                row[m] = round(sum(relevant) / len(relevant), 1) if relevant else 0
            rows.append(row)

        return rows

    def get_provider_speed_ranking(self) -> list[dict]:
        rankings = []
        for p in self._latency_samples:
            stats = self.get_latency_stats(p)
            if stats["samples"] > 0:
                rankings.append(stats)

        rankings.sort(key=lambda r: r["avg_ms"])
        return rankings

    def get_best_early_signal_source(self) -> Optional[str]:
        rankings = self.get_provider_speed_ranking()
        return rankings[0]["provider"] if rankings else None

    def _provider_weight(self, provider: str) -> float:
        base = self._provider_weights.get(provider, 0.5)
        reliability = self._provider_reliability.get(provider, 1.0)
        return base * reliability

    def _record_latency(self, provider: str, market: str, latency_ms: float):
        self._latency_samples[provider].append(LatencySample(
            provider=provider, market=market, latency_ms=latency_ms, timestamp=time.time()
        ))
        if len(self._latency_samples[provider]) > self._latency_window_size:
            self._latency_samples[provider] = self._latency_samples[provider][-self._latency_window_size:]

    def update_reliability(self, provider: str, was_outlier: bool):
        current = self._provider_reliability[provider]
        if was_outlier:
            self._provider_reliability[provider] = current * 0.9
        else:
            self._provider_reliability[provider] = min(1.0, current * 1.02)

    def _key(self, event_id: str, market: str, outcome: str) -> str:
        return f"{event_id}:{market}:{outcome}"
