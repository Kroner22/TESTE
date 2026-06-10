from __future__ import annotations

import math
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from backend.app.log_config import get_logger
from backend.domains.clv.models import ClvRecord, ClvReport

logger = get_logger(__name__)


class ValidationMetrics:
    total_entries: int
    closed_entries: int
    open_entries: int
    avg_clv_pct: float
    median_clv_pct: float
    positive_rate: float
    avg_ev: float
    ev_clv_correlation: float
    avg_timing_hours: float
    optimal_timing_rate: float
    avg_detection_delay_ms: float
    market_efficiency_score: float
    model_accuracy_score: float
    profit_simulation_roi: float
    total_kelly_stake: float
    sharpe_ratio: float

    def __init__(self):
        self.total_entries = 0
        self.closed_entries = 0
        self.open_entries = 0
        self.avg_clv_pct = 0.0
        self.median_clv_pct = 0.0
        self.positive_rate = 0.0
        self.avg_ev = 0.0
        self.ev_clv_correlation = 0.0
        self.avg_timing_hours = 0.0
        self.optimal_timing_rate = 0.0
        self.avg_detection_delay_ms = 0.0
        self.market_efficiency_score = 0.0
        self.model_accuracy_score = 0.0
        self.profit_simulation_roi = 0.0
        self.total_kelly_stake = 0.0
        self.sharpe_ratio = 0.0

    def to_dict(self) -> dict:
        return {
            "total_entries": self.total_entries,
            "closed_entries": self.closed_entries,
            "open_entries": self.open_entries,
            "avg_clv_pct": round(self.avg_clv_pct, 2),
            "median_clv_pct": round(self.median_clv_pct, 2),
            "positive_rate": round(self.positive_rate, 1),
            "avg_ev": round(self.avg_ev, 4),
            "ev_clv_correlation": round(self.ev_clv_correlation, 4),
            "avg_timing_hours": round(self.avg_timing_hours, 1),
            "optimal_timing_rate": round(self.optimal_timing_rate, 1),
            "avg_detection_delay_ms": round(self.avg_detection_delay_ms, 1),
            "market_efficiency_score": round(self.market_efficiency_score, 2),
            "model_accuracy_score": round(self.model_accuracy_score, 2),
            "profit_simulation_roi": round(self.profit_simulation_roi, 2),
            "total_kelly_stake": round(self.total_kelly_stake, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
        }


class ValidationReportGenerator:
    """
    Generates comprehensive validation reports comparing
    model predictions against real market outcomes.

    Metrics:
    - CLV real vs esperado
    - EV accuracy score
    - Market efficiency score
    - Detection delay (latência de captura)
    - Profit simulation (paper trading ROI)
    """

    def __init__(self):
        self._reports: list[ValidationMetrics] = []
        self._last_generate = 0.0

    def generate(self, clv_records: list[ClvRecord], open_count: int) -> ValidationMetrics:
        metrics = ValidationMetrics()
        metrics.total_entries = len(clv_records) + open_count
        metrics.closed_entries = len(clv_records)
        metrics.open_entries = open_count

        if clv_records:
            clvs = [r.clv_pct for r in clv_records]
            evs = [r.simulated_ev for r in clv_records]
            hours = [r.hours_to_close for r in clv_records]

            metrics.avg_clv_pct = statistics.mean(clvs)
            metrics.median_clv_pct = statistics.median(clvs)
            metrics.positive_rate = sum(1 for c in clvs if c > 0) / len(clvs) * 100
            metrics.avg_ev = statistics.mean(evs)

            pos_clv = [c for c in clvs if c > 0]
            neg_clv = [c for c in clvs if c < 0]
            total_clv = sum(clvs)

            # EV-CLV correlation
            if len(clvs) > 1:
                try:
                    from scipy import stats as scipy_stats
                    r, _ = scipy_stats.pearsonr(evs, clvs)
                    metrics.ev_clv_correlation = r
                except Exception:
                    metrics.ev_clv_correlation = 0.0

            # Timing
            metrics.avg_timing_hours = statistics.mean(hours)
            optimal = sum(1 for r in clv_records if r.timing_efficiency.value in ("EARLY", "OPTIMAL"))
            metrics.optimal_timing_rate = optimal / len(clv_records) * 100

            # Detection delay (simulated from latency)
            delays = [abs(r.odds_movement) * 1000 for r in clv_records if r.odds_movement != 0]
            metrics.avg_detection_delay_ms = statistics.mean(delays) if delays else 0

            # Market efficiency score
            # How much of our EV translated to real CLV
            if metrics.avg_ev != 0:
                metrics.market_efficiency_score = metrics.avg_clv_pct / (metrics.avg_ev * 100)

            # Model accuracy: CLV positive rate weighted by magnitude
            if total_clv != 0:
                accuracy_num = sum(c for c in clvs if c > 0)
                metrics.model_accuracy_score = accuracy_num / abs(total_clv) if total_clv != 0 else 0

            # Paper trading PnL simulation
            # Kelly stake = 1% per bet, PnL = (captured_prob * (odd - 1) - (1 - captured_prob)) * stake
            pnls = []
            stakes = []
            for r in clv_records:
                stake = 0.01
                odd = float(r.captured_odd)
                prob = r.captured_prob
                actual_prob = 1.0 / float(r.closing_odd) if float(r.closing_odd) > 1 else 0.0

                pnl = stake * (odd - 1) if actual_prob > prob else -stake
                pnls.append(pnl)
                stakes.append(stake)

                metrics.total_kelly_stake += stake

            if pnls:
                metrics.profit_simulation_roi = sum(pnls) / len(pnls) * 100

                # Sharpe ratio
                if len(pnls) > 1 and statistics.stdev(pnls) > 0:
                    metrics.sharpe_ratio = statistics.mean(pnls) / statistics.stdev(pnls) * (252 ** 0.5)

        self._reports.append(metrics)
        if len(self._reports) > 100:
            self._reports = self._reports[-100:]

        logger.info("validation_report_generated",
                    entries=metrics.total_entries, clv=metrics.avg_clv_pct,
                    roi=metrics.profit_simulation_roi, sharpe=metrics.sharpe_ratio)
        return metrics

    def get_latest(self) -> Optional[ValidationMetrics]:
        return self._reports[-1] if self._reports else None

    def get_history(self) -> list[ValidationMetrics]:
        return list(self._reports)
