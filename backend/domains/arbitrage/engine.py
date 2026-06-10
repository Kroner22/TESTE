"""
engine.py — Arbitrage detection orchestrator.

Central coordinator that:
  1. Accepts raw odds data from multiple sources
  2. Runs detection algorithms (2-way, 3-way)
  3. Applies filter chain
  4. Computes optimal stake distribution
  5. Tracks history and generates alerts for new opportunities
  6. Provides a unified interface for the API layer
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from .models import (
    ArbOpportunity, ArbScanResult, ArbFilter, ArbGrade,
    BookmakerOdds, StakeMethod,
)
from .core import scan_for_arbitrage
from .stake import distribute_stakes
from .filters import apply_filter_chain, rank_opportunities
from .monitor import ScanManager


@dataclass
class EngineConfig:
    sports: list[str] = field(default_factory=lambda: [
        "soccer", "basketball", "tennis", "american_football",
    ])
    total_stake: Decimal = Decimal("100")
    stake_method: StakeMethod = StakeMethod.EQUAL_PROFIT
    filter_config: ArbFilter = field(default_factory=ArbFilter)
    min_grade: ArbGrade = ArbGrade.MARGINAL
    scan_interval_seconds: float = 5.0
    memory_cleanup_seconds: int = 300
    enable_alerts: bool = True
    min_profit_for_alert: Decimal = Decimal("0.01")


@dataclass
class EngineSnapshot:
    """Point-in-time snapshot of the engine's state."""
    opportunities: list[ArbOpportunity] = field(default_factory=list)
    filtered_count: int = 0
    total_count: int = 0
    total_profit_pct: Decimal = Decimal("0")
    best_opportunity: Optional[ArbOpportunity] = None
    n_elite: int = 0
    n_strong: int = 0
    n_solid: int = 0
    n_marginal: int = 0
    last_scan_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ArbitrageEngine:
    """
    Central arbitrage detection engine.

    Usage:
        engine = ArbitrageEngine(config=EngineConfig())
        engine.register_feed(my_feed)

        # On-demand scan
        result = engine.scan()

        # Or start background scanning
        engine.start_background_scanning()
        # ... later ...
        snapshot = engine.snapshot()
        engine.stop()
    """

    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()
        self._scan_manager: Optional[ScanManager] = None
        self._alert_handlers: list[Callable[[ArbOpportunity], None]] = []
        self._last_snapshot: Optional[EngineSnapshot] = None

        self._all_time_best: Optional[ArbOpportunity] = None
        self._total_scans: int = 0
        self._total_opportunities_found: int = 0

    def register_alert_handler(
        self, handler: Callable[[ArbOpportunity], None]
    ) -> None:
        self._alert_handlers.append(handler)

    def register_feed(self, feed) -> None:
        """Register a BookmakerFeed."""
        if self._scan_manager is None:
            self._scan_manager = ScanManager(
                feeds=[feed],
                filter_config=self.config.filter_config,
                total_stake=self.config.total_stake,
            )
        else:
            self._scan_manager.feeds.append(feed)

    def scan(self, markets: Optional[dict] = None) -> ArbScanResult:
        """
        Perform a single synchronous scan.
        
        If markets is provided, uses that data directly.
        Otherwise uses registered feeds.
        """
        if markets is not None:
            opportunities = scan_for_arbitrage(
                markets, self.config.total_stake, self.config.filter_config,
            )
        elif self._scan_manager is not None:
            scan_result = self._scan_manager.scan_once()
            opportunities = scan_result.opportunities
        else:
            return ArbScanResult()

        result = apply_filter_chain(
            opportunities, self.config.filter_config, self.config.min_grade,
        )
        filtered = result.kept

        self._total_scans += 1
        self._total_opportunities_found += len(opportunities)

        if self.config.enable_alerts and self._alert_handlers:
            for opp in filtered:
                if opp.profit_pct >= self.config.min_profit_for_alert:
                    for handler in self._alert_handlers:
                        handler(opp)

        if filtered:
            best = filtered[0]
            if self._all_time_best is None or best.profit_pct > self._all_time_best.profit_pct:
                self._all_time_best = best

        best_odds = max(
            (o.odd for opp in filtered for o in opp.legs),
            default=Decimal("0"),
        )

        return ArbScanResult(
            n_opportunities=len(filtered),
            opportunities=filtered,
            scan_duration_ms=0.0,
            n_comparisons=len(opportunities),
            n_markets_scanned=len(opportunities),
        )

    def start_background_scanning(self) -> None:
        """Start background scan loop (requires registered feeds)."""
        if self._scan_manager is None:
            raise RuntimeError(
                "No feeds registered. Call register_feed() first."
            )
        self._scan_manager.start(self.config.scan_interval_seconds)

    def stop_background_scanning(self) -> None:
        if self._scan_manager is not None:
            self._scan_manager.stop()

    def snapshot(self) -> EngineSnapshot:
        """Current state snapshot."""
        if self._scan_manager is not None:
            opportunities = self._scan_manager.latest_results
        else:
            opportunities = []

        result = apply_filter_chain(
            opportunities, self.config.filter_config, self.config.min_grade,
        )
        filtered = result.kept

        n_elite = sum(1 for o in filtered if o.grade == ArbGrade.ELITE)
        n_strong = sum(1 for o in filtered if o.grade == ArbGrade.STRONG)
        n_solid = sum(1 for o in filtered if o.grade == ArbGrade.SOLID)
        n_marginal = sum(1 for o in filtered if o.grade == ArbGrade.MARGINAL)

        total_pct = (
            sum(o.profit_pct for o in filtered) / Decimal(max(len(filtered), 1))
        )

        best = filtered[0] if filtered else None

        snapshot = EngineSnapshot(
            opportunities=filtered,
            filtered_count=len(filtered),
            total_count=len(opportunities),
            total_profit_pct=total_pct,
            best_opportunity=best,
            n_elite=n_elite,
            n_strong=n_strong,
            n_solid=n_solid,
            n_marginal=n_marginal,
        )
        self._last_snapshot = snapshot
        return snapshot

    def recalculate_stakes(
        self,
        opportunity: ArbOpportunity,
        total_stake: Optional[Decimal] = None,
        method: Optional[StakeMethod] = None,
    ) -> ArbOpportunity:
        """Recalculate stake distribution for an opportunity."""
        odds = [leg.odd for leg in opportunity.legs]
        commissions = [leg.commission for leg in opportunity.legs]
        max_stakes = [leg.max_stake for leg in opportunity.legs]

        ts = total_stake or self.config.total_stake
        m = method or self.config.stake_method

        stakes = distribute_stakes(odds, m, ts, commissions, max_stakes)

        for i, leg in enumerate(opportunity.legs):
            leg.stake = stakes[i]
            leg.return_amount = stakes[i] * leg.odd

        opportunity.total_stake = ts
        opportunity.guaranteed_return = min(
            l.return_amount for l in opportunity.legs
        )
        opportunity.profit = opportunity.guaranteed_return - ts
        return opportunity
