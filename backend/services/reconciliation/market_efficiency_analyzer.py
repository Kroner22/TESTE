from __future__ import annotations

import math
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from backend.app.log_config import get_logger
from backend.domains.clv.models import ClvRecord

logger = get_logger(__name__)


class OverfittingIndicator:
    score: float
    severity: str
    description: str

    def __init__(self, score: float, severity: str, description: str):
        self.score = score
        self.severity = severity
        self.description = description

    def to_dict(self) -> dict:
        return {"score": round(self.score, 3), "severity": self.severity, "description": self.description}


class TimingLagMetric:
    avg_delay_seconds: float
    optimal_entry_pct: float
    late_entry_pct: float
    clv_decay_per_hour: float
    best_entry_window: str

    def __init__(self):
        self.avg_delay_seconds = 0.0
        self.optimal_entry_pct = 0.0
        self.late_entry_pct = 0.0
        self.clv_decay_per_hour = 0.0
        self.best_entry_window = ""


class MarketEfficiencyAnalysis:
    overfitting: Optional[OverfittingIndicator]
    timing_lag: TimingLagMetric
    persistent_edge: bool
    edge_confidence: float
    false_positive_rate: float
    corrected_rate: float
    market_speed_ms: float
    verdict: str

    def __init__(self):
        self.overfitting = None
        self.timing_lag = TimingLagMetric()
        self.persistent_edge = False
        self.edge_confidence = 0.0
        self.false_positive_rate = 0.0
        self.corrected_rate = 0.0
        self.market_speed_ms = 0.0
        self.verdict = ""

    def to_dict(self) -> dict:
        return {
            "overfitting": self.overfitting.to_dict() if self.overfitting else None,
            "timing_lag": {
                "avg_delay_seconds": round(self.timing_lag.avg_delay_seconds, 1),
                "optimal_entry_pct": round(self.timing_lag.optimal_entry_pct, 1),
                "late_entry_pct": round(self.timing_lag.late_entry_pct, 1),
                "clv_decay_per_hour": round(self.timing_lag.clv_decay_per_hour, 4),
                "best_entry_window": self.timing_lag.best_entry_window,
            },
            "persistent_edge": self.persistent_edge,
            "edge_confidence": round(self.edge_confidence, 2),
            "false_positive_rate": round(self.false_positive_rate, 1),
            "corrected_rate": round(self.corrected_rate, 1),
            "market_speed_ms": round(self.market_speed_ms, 1),
            "verdict": self.verdict,
        }


class MarketEfficiencyAnalyzer:
    """
    Analyzes market efficiency by detecting:

    1. OVERFITTING:
       - EV consistently positive but CLV negative -> model sees value that market doesn't confirm
       - High EV confidence + low CLV realization -> false positive detection
       - Ratio of EV>0 opportunities that actually materialize as CLV>0

    2. TIMING LAG:
       - Delay between opportunity detection and market correction
       - Does the market move BEFORE the system can act?
       - CLV decay as function of entry delay

    3. PERSISTENT EDGE:
       - Is CLV consistently positive over time? (rolling average)
       - Or is it random noise around zero?
       - Statistical significance test (t-test against zero)

    4. FALSE POSITIVE ANALYSIS:
       - What % of EV>5% opportunities actually become CLV>0?
       - What's the cost of false positives?
       - Are certain sports/markets more prone to false signals?
    """

    def __init__(self):
        self._analyses: list[MarketEfficiencyAnalysis] = []
        self._last_analysis = 0.0
        self._analysis_interval = 60.0
        self._broadcast_callback = None

    def set_broadcast_callback(self, callback):
        self._broadcast_callback = callback

    def analyze(self, clv_records: list[ClvRecord]) -> MarketEfficiencyAnalysis:
        analysis = MarketEfficiencyAnalysis()

        if len(clv_records) < 5:
            analysis.verdict = f"Amostra insuficiente ({len(clv_records)} registros, mínimo 5)"
            return analysis

        clvs = [r.clv_pct for r in clv_records]
        evs = [r.simulated_ev for r in clv_records]
        positive_clv = [c for c in clvs if c > 0]
        negative_clv = [c for c in clvs if c < 0]
        n = len(clvs)
        n_pos = len(positive_clv)
        n_neg = len(negative_clv)

        # Overfitting detection
        ev_positive_rate = sum(1 for e in evs if e > 0) / n * 100
        clv_positive_rate = n_pos / n * 100
        false_positive = sum(1 for i, e in enumerate(evs) if e > 0.05 and clvs[i] <= 0) / max(1, sum(1 for e in evs if e > 0.05)) * 100
        corrected = sum(1 for i, e in enumerate(evs) if e <= 0 and clvs[i] > 0) / max(1, sum(1 for e in evs if e <= 0)) * 100

        analysis.false_positive_rate = false_positive
        analysis.corrected_rate = corrected

        overfit_gap = ev_positive_rate - clv_positive_rate
        if overfit_gap > 30:
            overfit_score = min(1.0, overfit_gap / 100)
            analysis.overfitting = OverfittingIndicator(
                score=overfit_score,
                severity="ALTA",
                description=f"Gap EV→CLV de {overfit_gap:.1f}pp — modelo vê valor que o mercado não confirma. {false_positive:.0f}% dos EV>5% falham.",
            )
        elif overfit_gap > 15:
            analysis.overfitting = OverfittingIndicator(
                score=overfit_gap / 100,
                severity="MODERADA",
                description=f"Gap EV→CLV de {overfit_gap:.1f}pp — sobreajuste parcial detectado.",
            )
        else:
            analysis.overfitting = OverfittingIndicator(
                score=max(0, overfit_gap / 100),
                severity="BAIXA",
                description=f"Gap EV→CLV de {overfit_gap:.1f}pp — dentro da faixa aceitável.",
            )

        # Timing lag analysis
        if n > 1:
            analysis.timing_lag.avg_delay_seconds = statistics.mean([
                (r.closed_at - r.captured_at).total_seconds()
                for r in clv_records if hasattr(r, "closed_at") and hasattr(r, "captured_at")
            ])
        else:
            analysis.timing_lag.avg_delay_seconds = 0.0

        timing_map = defaultdict(list)
        for r in clv_records:
            timing_map[r.timing_efficiency.value].append(r.clv_pct)

        optimal = timing_map.get("EARLY", []) + timing_map.get("OPTIMAL", [])
        late = timing_map.get("LATE", []) + timing_map.get("DEAD", [])
        analysis.timing_lag.optimal_entry_pct = len(optimal) / n * 100
        analysis.timing_lag.late_entry_pct = len(late) / n * 100

        if optimal and late:
            avg_optimal_clv = statistics.mean(optimal)
            avg_late_clv = statistics.mean(late)
            analysis.timing_lag.clv_decay_per_hour = (
                (avg_optimal_clv - avg_late_clv) / analysis.timing_lag.avg_delay_seconds * 3600
                if analysis.timing_lag.avg_delay_seconds > 0 else 0
            )

        if analysis.timing_lag.optimal_entry_pct > analysis.timing_lag.late_entry_pct:
            analysis.timing_lag.best_entry_window = "EARLY_OPTIMAL"
        else:
            analysis.timing_lag.best_entry_window = "LATE"

        # Persistent edge detection
        if n_pos > 0 and n_neg > 0:
            from scipy import stats as scipy_stats
            try:
                _, p_value = scipy_stats.ttest_ind(positive_clv, negative_clv, alternative="greater")
                analysis.persistent_edge = p_value < 0.05
                analysis.edge_confidence = 1.0 - p_value if p_value < 1 else 0.0
            except Exception:
                analysis.persistent_edge = n_pos > n_neg * 2
                analysis.edge_confidence = n_pos / n if n > 0 else 0.0
        else:
            analysis.persistent_edge = False
            analysis.edge_confidence = 0.0

        # Market speed
        analysis.market_speed_ms = analysis.timing_lag.avg_delay_seconds * 1000

        # Verdict
        if analysis.persistent_edge and analysis.edge_confidence > 0.8 and analysis.overfitting.score < 0.3:
            analysis.verdict = "EDGE REAL DETECTADO — CLV consistentemente positivo, sem evidência de sobreajuste. O modelo captura valor real no mercado."
        elif analysis.persistent_edge and analysis.overfitting.score > 0.3:
            analysis.verdict = "EDGE PARCIAL — CLV positivo mas com sobreajuste significativo. Filtrar oportunidades de maior confiança."
        elif not analysis.persistent_edge and analysis.false_positive_rate > 50:
            analysis.verdict = "SEM EDGE — Alta taxa de falso positivo ({false_positive:.0f}%). O modelo identifica valor que o mercado consistentemente rejeita. Revisar fair probability."
        elif analysis.timing_lag.late_entry_pct > 60:
            analysis.verdict = "ATRASO ESTRUTURAL — {analysis.timing_lag.late_entry_pct:.0f}% das entradas são tardias. O mercado move antes do sistema detectar."
        else:
            analysis.verdict = "INCONCLUSIVO — Mais dados necessários para determinar a existência de edge."

        # Apply formatting
        analysis.verdict = analysis.verdict.format(false_positive=false_positive, analysis=analysis)

        self._analyses.append(analysis)
        if len(self._analyses) > 100:
            self._analyses = self._analyses[-100:]

        logger.info("market_efficiency_analyzed", n=n, persistent=analysis.persistent_edge,
                    overfit=analysis.overfitting.score, verdict=analysis.verdict[:60])

        if self._broadcast_callback:
            import asyncio
            asyncio.ensure_future(self._broadcast_callback({
                "type": "efficiency_analysis",
                "data": analysis.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        return analysis

    def get_latest(self) -> Optional[MarketEfficiencyAnalysis]:
        return self._analyses[-1] if self._analyses else None

    def get_history(self) -> list[MarketEfficiencyAnalysis]:
        return list(self._analyses)
