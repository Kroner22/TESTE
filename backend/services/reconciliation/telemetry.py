from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from backend.app.database import SessionLocal, ProviderTelemetryRecord
from backend.app.log_config import get_logger

logger = get_logger(__name__)


class TelemetryEvent:
    provider_name: str
    event: str
    healthy: bool
    failure_count: int
    success_count: int
    consecutive_failures: int
    latency_ms: Optional[float]
    details: Optional[str]
    timestamp: float

    def __init__(self, provider_name: str, event: str, healthy: bool = True,
                 failure_count: int = 0, success_count: int = 0,
                 consecutive_failures: int = 0, latency_ms: Optional[float] = None,
                 details: Optional[str] = None):
        self.provider_name = provider_name
        self.event = event
        self.healthy = healthy
        self.failure_count = failure_count
        self.success_count = success_count
        self.consecutive_failures = consecutive_failures
        self.latency_ms = latency_ms
        self.details = details
        self.timestamp = time.time()


class ProviderTelemetry:
    """
    Provider telemetry and monitoring system.

    Tracks:
    - Provider failures with timestamps
    - Reconnection attempts and success rate
    - Latency spikes (P95 > 2x median)
    - Dropped updates (consecutive failures without recovery)
    - Reconciliation conflicts (provider divergences)
    - Per-provider health over time
    """

    LATENCY_SPIKE_THRESHOLD = 2.0
    MAX_DROPPED_BEFORE_ALERT = 3

    def __init__(self):
        self._events: list[TelemetryEvent] = []
        self._max_events = 1000
        self._latency_history: dict[str, list[float]] = defaultdict(list)
        self._failure_streaks: dict[str, int] = defaultdict(int)
        self._reconnect_attempts: dict[str, int] = defaultdict(int)
        self._reconnect_successes: dict[str, int] = defaultdict(int)
        self._dropped_updates: dict[str, int] = defaultdict(int)
        self._conflicts: dict[str, int] = defaultdict(int)

    def record_provider_event(self, provider: str, event: str, healthy: bool = True,
                              failure_count: int = 0, success_count: int = 0,
                              consecutive_failures: int = 0, latency_ms: Optional[float] = None,
                              details: Optional[str] = None):
        te = TelemetryEvent(
            provider_name=provider,
            event=event,
            healthy=healthy,
            failure_count=failure_count,
            success_count=success_count,
            consecutive_failures=consecutive_failures,
            latency_ms=latency_ms,
            details=details,
        )
        self._events.append(te)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

        if latency_ms is not None:
            self._latency_history[provider].append(latency_ms)
            if len(self._latency_history[provider]) > 500:
                self._latency_history[provider] = self._latency_history[provider][-500:]

        if event == "failure":
            self._failure_streaks[provider] += 1
            self._dropped_updates[provider] += 1
        elif event == "success":
            self._failure_streaks[provider] = 0
        elif event == "reconnect_attempt":
            self._reconnect_attempts[provider] += 1
        elif event == "reconnected":
            self._reconnect_successes[provider] += 1
        elif event == "conflict":
            self._conflicts[provider] += 1

        # Persist to DB
        self._persist(te)

    def record_latency(self, provider: str, latency_ms: float):
        self._latency_history[provider].append(latency_ms)
        if len(self._latency_history[provider]) > 500:
            self._latency_history[provider] = self._latency_history[provider][-500:]

    def get_latency_stats(self, provider: str) -> dict:
        samples = self._latency_history.get(provider, [])
        if not samples:
            return {"avg": 0, "median": 0, "p95": 0, "min": 0, "max": 0, "n": 0}
        sorted_s = sorted(samples)
        n = len(sorted_s)
        return {
            "avg": round(sum(sorted_s) / n, 1),
            "median": round(sorted_s[n // 2], 1),
            "p95": round(sorted_s[int(n * 0.95)], 1),
            "min": round(sorted_s[0], 1),
            "max": round(sorted_s[-1], 1),
            "n": n,
        }

    def get_latency_spikes(self, provider: str) -> list[float]:
        stats = self.get_latency_stats(provider)
        median = stats["median"]
        if median <= 0:
            return []
        return [l for l in self._latency_history.get(provider, [])
                if l > median * self.LATENCY_SPIKE_THRESHOLD]

    def get_reconnect_rate(self, provider: str) -> float:
        attempts = self._reconnect_attempts.get(provider, 0)
        successes = self._reconnect_successes.get(provider, 0)
        return successes / max(attempts, 1)

    def get_reconnect_summary(self, provider: str) -> dict:
        return {
            "attempts": self._reconnect_attempts.get(provider, 0),
            "successes": self._reconnect_successes.get(provider, 0),
            "rate": round(self.get_reconnect_rate(provider), 2),
        }

    def get_dropped_updates(self, provider: str) -> int:
        return self._dropped_updates.get(provider, 0)

    def get_conflicts(self, provider: str) -> int:
        return self._conflicts.get(provider, 0)

    def get_summary(self, provider: str) -> dict:
        return {
            "latency": self.get_latency_stats(provider),
            "reconnect": self.get_reconnect_summary(provider),
            "dropped_updates": self.get_dropped_updates(provider),
            "conflicts": self.get_conflicts(provider),
            "current_streak": self._failure_streaks.get(provider, 0),
        }

    def get_all_summaries(self) -> dict[str, dict]:
        providers = set()
        for te in self._events:
            providers.add(te.provider_name)
        return {p: self.get_summary(p) for p in providers}

    def _persist(self, event: TelemetryEvent):
        db = SessionLocal()
        try:
            rec = ProviderTelemetryRecord(
                provider_name=event.provider_name,
                event=event.event,
                healthy=event.healthy,
                failure_count=event.failure_count,
                success_count=event.success_count,
                consecutive_failures=event.consecutive_failures,
                latency_ms=event.latency_ms,
                details=event.details,
            )
            db.add(rec)
            db.commit()
        except Exception as e:
            logger.warning("telemetry_persist_failed", error=str(e))
        finally:
            db.close()
