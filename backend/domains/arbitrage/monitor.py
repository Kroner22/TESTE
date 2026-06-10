"""
monitor.py — Market scanning, polling, and live monitoring.

Scans bookmaker odds feeds in real time, detects new arbitrage
opportunities, and tracks historical arb data for performance analysis.

Architecture:
  - ScanManager: High-level orchestrator for periodic scanning.
  - BookmakerFeed: Adapter interface for different bookmaker APIs.
  - ScanWorker: Runs scan cycles in background threads.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from threading import Lock, Thread
from time import monotonic
from typing import Callable, Optional

from .models import ArbOpportunity, ArbScanResult, BookmakerOdds, ArbFilter
from .core import scan_for_arbitrage


class ScanStatus(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class ScanCycle:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    duration_ms: float = 0.0
    n_opportunities: int = 0
    error: Optional[str] = None


@dataclass
class ArbMemory:
    """
    Tracks previously detected opportunities to avoid duplicates
    and measure opportunity duration/lifetime.
    """
    event_id: str
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    best_profit_pct: Decimal = Decimal("0")
    n_scans_seen: int = 1

    def update(self, profit_pct: Decimal) -> None:
        self.last_seen = datetime.now(timezone.utc)
        self.best_profit_pct = max(self.best_profit_pct, profit_pct)
        self.n_scans_seen += 1

    @property
    def lifetime_seconds(self) -> float:
        return (self.last_seen - self.first_seen).total_seconds()


class BookmakerFeed(ABC):
    """Abstract adapter for bookmaker odds feeds."""

    @abstractmethod
    def fetch_markets(
        self,
        sports: Optional[list[str]] = None,
    ) -> dict[str, dict[str, list[BookmakerOdds]]]:
        """
        Fetch current odds across all monitored markets.
        
        Returns: {
            "event_id:sport:home:away:market": {
                "outcome_name": [BookmakerOdds(...), ...],
                ...
            },
            ...
        }
        """
        ...

    @abstractmethod
    def name(self) -> str:
        ...


class ScanManager:
    """
    Manages periodic scanning of bookmaker feeds for arbitrage.
    
    Usage:
        mgr = ScanManager(feeds=[feed1, feed2], filter_config=my_filter)
        mgr.start(interval_seconds=5.0)
        # ... later ...
        results = mgr.latest_results
        mgr.stop()
    """

    def __init__(
        self,
        feeds: list[BookmakerFeed],
        filter_config: Optional[ArbFilter] = None,
        on_opportunity: Optional[Callable[[ArbOpportunity], None]] = None,
        total_stake: Decimal = Decimal("100"),
    ):
        self.feeds = feeds
        self.filter_config = filter_config or ArbFilter()
        self.on_opportunity = on_opportunity
        self.total_stake = total_stake

        self._lock = Lock()
        self._thread: Optional[Thread] = None
        self._running = False
        self._interval = 5.0

        self._latest_results: list[ArbOpportunity] = []
        self._seen: dict[str, ArbMemory] = {}
        self._scan_cycles: list[ScanCycle] = []
        self._status = ScanStatus.IDLE

    @property
    def latest_results(self) -> list[ArbOpportunity]:
        with self._lock:
            return list(self._latest_results)

    @property
    def status(self) -> ScanStatus:
        return self._status

    @property
    def scan_history(self) -> list[ScanCycle]:
        return list(self._scan_cycles)

    @property
    def memory(self) -> dict[str, ArbMemory]:
        with self._lock:
            return dict(self._seen)

    def start(self, interval_seconds: float = 5.0) -> None:
        if self._running:
            return
        self._running = True
        self._interval = interval_seconds
        self._thread = Thread(target=self._scan_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def scan_once(self) -> ArbScanResult:
        """Perform a single scan cycle synchronously."""
        start = monotonic()
        cycle = ScanCycle()
        self._status = ScanStatus.SCANNING

        try:
            market_data: dict[str, dict[str, list[BookmakerOdds]]] = {}
            n_comparisons = 0
            n_markets = 0

            for feed in self.feeds:
                feed_markets = feed.fetch_markets()
                for key, outcomes in feed_markets.items():
                    if key not in market_data:
                        market_data[key] = {}
                        n_markets += 1
                    for outcome, odds_list in outcomes.items():
                        if outcome not in market_data[key]:
                            market_data[key][outcome] = []
                        existing = {bo.bookmaker for bo in market_data[key][outcome]}
                        for bo in odds_list:
                            if bo.bookmaker not in existing:
                                market_data[key][outcome].append(bo)
                                n_comparisons += 1

            opportunities = scan_for_arbitrage(
                market_data, self.total_stake, self.filter_config,
            )

            with self._lock:
                now = datetime.now(timezone.utc)
                for opp in opportunities:
                    if opp.event_id in self._seen:
                        self._seen[opp.event_id].update(opp.profit_pct)
                    else:
                        self._seen[opp.event_id] = ArbMemory(
                            event_id=opp.event_id,
                            first_seen=now,
                            last_seen=now,
                            best_profit_pct=opp.profit_pct,
                        )

                if self.on_opportunity:
                    for opp in opportunities:
                        self.on_opportunity(opp)

                self._latest_results = opportunities

            elapsed = (monotonic() - start) * 1000
            cycle.finished_at = datetime.now(timezone.utc)
            cycle.duration_ms = elapsed
            cycle.n_opportunities = len(opportunities)
            self._scan_cycles.append(cycle)
            self._status = ScanStatus.IDLE

            return ArbScanResult(
                n_opportunities=len(opportunities),
                opportunities=opportunities,
                scan_duration_ms=elapsed,
                n_comparisons=n_comparisons,
                n_markets_scanned=n_markets,
            )

        except Exception as e:
            elapsed = (monotonic() - start) * 1000
            cycle.finished_at = datetime.now(timezone.utc)
            cycle.duration_ms = elapsed
            cycle.error = str(e)
            self._scan_cycles.append(cycle)
            self._status = ScanStatus.ERROR

            return ArbScanResult(
                n_opportunities=0,
                opportunities=[],
                scan_duration_ms=elapsed,
                n_comparisons=0,
                n_markets_scanned=0,
            )

    def cleanup_stale_memory(self, max_age_seconds: int = 300) -> int:
        """Remove events not seen in max_age_seconds."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=max_age_seconds)
        stale = [eid for eid, mem in self._seen.items() if mem.last_seen < cutoff]
        with self._lock:
            for eid in stale:
                del self._seen[eid]
        return len(stale)

    def _scan_loop(self) -> None:
        while self._running:
            self.scan_once()
            import time
            time.sleep(self._interval)
