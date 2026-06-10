from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from backend.app.log_config import get_logger
from .models import BacktestResult, PerformanceMetrics
from .metrics import compute_metrics, _compute_drawdown, _monthly_returns

logger = get_logger(__name__)


class BacktestAnalyzer:
    """
    Segmented analysis of backtest results.

    Slices the bet list by sport, market, bookmaker, grade,
    EV bucket, confidence bucket, month, and hour-of-day.
    """

    def __init__(self, result: BacktestResult):
        self.result = result
        self.bets = result.bets
        self.total_metrics = compute_metrics(result)

    def by_sport(self) -> dict[str, PerformanceMetrics]:
        return self._slice("sport")

    def by_market(self) -> dict[str, PerformanceMetrics]:
        return self._slice("market")

    def by_bookmaker(self) -> dict[str, PerformanceMetrics]:
        return self._slice("bookmaker")

    def by_grade(self) -> dict[str, PerformanceMetrics]:
        return self._slice("value_grade")

    def by_ev_bucket(self) -> dict[str, PerformanceMetrics]:
        buckets = defaultdict(list)
        for b in self.bets:
            ev = float(b.predicted_ev)
            if ev < -5:
                key = "< -5%"
            elif ev < 0:
                key = "-5% to 0%"
            elif ev < 2:
                key = "0% to 2%"
            elif ev < 5:
                key = "2% to 5%"
            elif ev < 10:
                key = "5% to 10%"
            else:
                key = "> 10%"
            buckets[key].append(b)
        return self._compute_slices(buckets)

    def by_confidence(self) -> dict[str, PerformanceMetrics]:
        buckets = defaultdict(list)
        for b in self.bets:
            c = b.confidence_score
            if c < 0.4:
                key = "0-40%"
            elif c < 0.6:
                key = "40-60%"
            elif c < 0.8:
                key = "60-80%"
            else:
                key = "80-100%"
            buckets[key].append(b)
        return self._compute_slices(buckets)

    def by_month(self) -> dict[str, PerformanceMetrics]:
        buckets = defaultdict(list)
        for b in self.bets:
            key = b.placed_at.strftime("%Y-%m")
            buckets[key].append(b)
        return self._compute_slices(buckets)

    def by_hour(self) -> dict[str, PerformanceMetrics]:
        buckets = defaultdict(list)
        for b in self.bets:
            key = str(b.placed_at.hour)
            buckets[key].append(b)
        return self._compute_slices(buckets)

    def by_risk_level(self) -> dict[str, PerformanceMetrics]:
        return self._slice("risk_level")

    def summary(self) -> dict:
        """Return a dict with all segmentations."""
        return {
            "total": self.total_metrics,
            "by_sport": self.by_sport(),
            "by_market": self.by_market(),
            "by_bookmaker": self.by_bookmaker(),
            "by_grade": self.by_grade(),
            "by_ev_bucket": self.by_ev_bucket(),
            "by_confidence": self.by_confidence(),
            "by_month": self.by_month(),
            "by_hour": self.by_hour(),
            "by_risk_level": self.by_risk_level(),
        }

    # ─── Internal ────────────────────────────────────────────────

    def _slice(self, attr: str) -> dict[str, PerformanceMetrics]:
        buckets = defaultdict(list)
        for b in self.bets:
            key = getattr(b, attr, "unknown")
            buckets[key].append(b)
        return self._compute_slices(buckets)

    def _compute_slices(
        self, buckets: dict[str, list]
    ) -> dict[str, PerformanceMetrics]:
        result: dict[str, PerformanceMetrics] = {}
        for key, bet_list in sorted(buckets.items()):
            if len(bet_list) < 5:
                continue
            # Build a minimal BacktestResult for compute_metrics
            sub = BacktestResult(
                config=self.result.config,
                initial_bankroll=self.result.initial_bankroll,
                final_bankroll=0,
                winning_bets=sum(1 for b in bet_list if b.is_winner),
                losing_bets=sum(1 for b in bet_list if not b.is_winner),
                gross_profit=sum(b.profit for b in bet_list if b.is_winner),
                gross_loss=abs(sum(b.profit for b in bet_list if not b.is_winner)),
                total_bets=len(bet_list),
                total_staked=sum(b.stake for b in bet_list),
                total_profit=sum(b.profit for b in bet_list),
                bets=bet_list,
                start_date=min(b.placed_at for b in bet_list),
                end_date=max(b.placed_at for b in bet_list),
                equity_curve=[(b.placed_at, 1000 + sum(
                    float(x.profit) for x in bet_list[:i+1]
                )) for i, b in enumerate(bet_list)],
                cumulative_returns=[float(b.profit) for b in bet_list],
                running_bankroll=[],
            )
            result[key] = compute_metrics(sub)
        return result
