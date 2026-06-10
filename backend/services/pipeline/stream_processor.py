from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

from backend.app.cache import Cache, get_cache
from backend.app.log_config import get_logger
from backend.services.pipeline.event_matcher import EventCandidate, EventMatcher
from backend.services.pipeline.odds_normalizer import (
    normalize_bookmaker, normalize_market, normalize_outcome, normalize_team,
    normalize_sport,
)
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig
from backend.services.storage.event_store import EventStore, StoredEvent
from backend.services.storage.odds_history import OddsHistoryStore, OddsSnapshot

logger = get_logger(__name__)


class ProviderMetrics:
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_events = 0
        self.total_odds_updates = 0
        self.total_latency_ms = 0.0
        self.last_error: Optional[str] = None
        self.last_success: Optional[datetime] = None

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.total_latency_ms / self.total_requests, 1)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return round(self.successful_requests / self.total_requests, 3)

    def record(self, latency_ms: float, success: bool):
        self.total_requests += 1
        self.total_latency_ms += latency_ms
        if success:
            self.successful_requests += 1
            self.last_success = datetime.now(timezone.utc)
        else:
            self.failed_requests += 1

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "successful": self.successful_requests,
            "failed": self.failed_requests,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "total_events": self.total_events,
            "total_odds_updates": self.total_odds_updates,
            "last_error": self.last_error,
            "last_success": self.last_success.isoformat() if self.last_success else None,
        }


class StreamProcessor:
    """
    Orchestrates the full ingestion pipeline:
    1. Fetch events from all active providers
    2. Match/normalize events
    3. Fetch odds
    4. Store in EventStore + OddsHistoryStore
    5. Broadcast to subscribers
    """

    def __init__(
        self,
        event_store: Optional[EventStore] = None,
        odds_history: Optional[OddsHistoryStore] = None,
        cache: Optional[Cache] = None,
        event_matcher: Optional[EventMatcher] = None,
    ):
        self.event_store = event_store or EventStore()
        self.odds_history = odds_history or OddsHistoryStore()
        self.cache = cache
        self.event_matcher = event_matcher or EventMatcher()
        self._providers: list[BaseProvider] = []
        self._provider_metrics: dict[str, ProviderMetrics] = {}
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._broadcast_callback = None
        self._total_cycles = 0

    def add_provider(self, provider: BaseProvider):
        self._providers.append(provider)
        self._provider_metrics[provider.name] = ProviderMetrics()

    def set_broadcast_callback(self, callback):
        self._broadcast_callback = callback

    async def start(self):
        if self._running:
            return
        self._running = True
        if not self._providers:
            logger.warning("stream_processor_no_providers")
        for provider in self._providers:
            task = asyncio.create_task(self._run_provider_cycle(provider))
            self._tasks.append(task)
        await asyncio.sleep(0)
        logger.info("stream_processor_started", providers=[p.name for p in self._providers])

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("stream_processor_stopped")

    async def _run_provider_cycle(self, provider: BaseProvider):
        metrics = self._provider_metrics[provider.name]

        while self._running:
            try:
                start = time.monotonic()
                events = await provider.fetch_events()
                latency = (time.monotonic() - start) * 1000

                if events:
                    matched = await self._process_events(provider.name, events)
                    metrics.total_events += len(matched)
                    metrics.record(latency, True)

                    for match in matched:
                        try:
                            odds = await provider.fetch_odds(match.provider_event_id)
                            if odds:
                                updates = await self._process_odds(odds, match.canonical_event_id)
                                metrics.total_odds_updates += len(updates)
                        except Exception as e:
                            logger.error("odds_fetch_error", provider=provider.name, error=str(e))

                    if self._broadcast_callback:
                        await self._broadcast_callback({
                            "type": "market_snapshot",
                            "data": {
                                "events": self.event_store.count(),
                                "odds_snapshots": self.odds_history.stats()["total_snapshots"],
                                "provider": provider.name,
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                self._total_cycles += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                metrics.record(0, False)
                metrics.last_error = str(e)
                logger.error("provider_cycle_error", provider=provider.name, error=str(e))

            await asyncio.sleep(max(1, provider.config.update_interval_seconds))

    async def _process_events(self, provider_name: str, events: list[OddsEvent]) -> list:
        from backend.services.pipeline.event_matcher import EventCandidate

        matched = []
        for event in events:
            candidate = EventCandidate(
                provider=provider_name,
                provider_event_id=event.event_id,
                sport=event.sport,
                home_team=event.home_team,
                away_team=event.away_team,
                start_time=event.start_time,
            )
            match = self.event_matcher.find_or_create(candidate)

            stored = StoredEvent(
                canonical_id=match.canonical_event_id,
                sport=match.sport,
                home_team=match.home_team,
                away_team=match.away_team,
                start_time=match.start_time,
                status=event.status,
                provider_ids={provider_name: event.event_id},
            )
            self.event_store.upsert(stored)
            matched.append(match)

        return matched

    async def _process_odds(self, odds: list[OddsUpdate], canonical_event_id: str) -> list[OddsSnapshot]:
        snapshots: list[OddsSnapshot] = []
        now = datetime.now(timezone.utc)

        for odd in odds:
            snap = OddsSnapshot(
                event_id=canonical_event_id,
                market=normalize_market(odd.market),
                outcome=normalize_outcome(odd.outcome),
                bookmaker=normalize_bookmaker(odd.bookmaker),
                odd=odd.odd,
                timestamp=now,
            )
            self.odds_history.append(snap)
            snapshots.append(snap)

        return snapshots

    def get_provider_metrics(self) -> dict[str, dict]:
        return {name: m.to_dict() for name, m in self._provider_metrics.items()}

    def get_global_stats(self) -> dict:
        return {
            "total_cycles": self._total_cycles,
            "active_providers": len(self._providers),
            "running": self._running,
            "event_store": self.event_store.stats(),
            "odds_history": self.odds_history.stats(),
            "event_matcher_known": self.event_matcher.get_known_count(),
        }
