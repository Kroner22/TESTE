from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class BetOutcome(str, Enum):
    WIN = "win"
    LOSS = "loss"


class EdgeSignal(str, Enum):
    TRUE_EDGE = "TRUE_EDGE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    CORRECTLY_AVOIDED = "CORRECTLY_AVOIDED"
    MODEL_BLIND_SPOT = "MODEL_BLIND_SPOT"


class SystemEdgeClass(str, Enum):
    STRONG_EDGE = "STRONG_EDGE"
    WEAK_EDGE = "WEAK_EDGE"
    NO_EDGE = "NO_EDGE"
    INCONCLUSIVE = "INCONCLUSIVE"


class Recommendation(str, Enum):
    SCALE = "SCALE"
    FIX = "FIX"
    KILL = "KILL"


@dataclass
class ClvValidationBet:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    entry_odd: Decimal
    closing_odd: Decimal
    captured_at: datetime
    closed_at: datetime
    simulated_ev: float
    clv_pct: float
    bet_result: BetOutcome
    profit: float
    stake: float
    edge_signal: EdgeSignal
    grade: str
    odds_range: str
    sport: str
    timing: str

    @property
    def is_winner(self) -> bool:
        return self.bet_result == BetOutcome.WIN

    @property
    def roi(self) -> float:
        if self.stake <= 0:
            return 0.0
        return self.profit / self.stake * 100.0

    @property
    def ev_aligned_with_clv(self) -> bool:
        return (self.simulated_ev > 0) == (self.clv_pct > 0)


@dataclass
class ClvValidationMetrics:
    n_bets: int = 0
    n_wins: int = 0
    n_losses: int = 0
    hit_rate: float = 0.0
    total_staked: float = 0.0
    total_profit: float = 0.0
    roi_pct: float = 0.0
    clv_adjusted_roi: float = 0.0
    avg_clv_pct: float = 0.0
    median_clv_pct: float = 0.0
    avg_ev: float = 0.0
    ev_clv_pearson: float = 0.0
    ev_clv_spearman: float = 0.0
    ev_clv_p_value: float = 1.0
    efficiency_score: float = 0.0
    edge_quality_score: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    edge_decay_slope: float = 0.0
    edge_decay_interpretation: str = ""
    true_edge_pct: float = 0.0
    false_positive_pct: float = 0.0
    blind_spot_pct: float = 0.0
    correctly_avoided_pct: float = 0.0
    sharpe_ratio: float = 0.0
    t_statistic: float = 0.0
    p_value: float = 1.0
    is_significant: bool = False
    system_edge_class: SystemEdgeClass = SystemEdgeClass.INCONCLUSIVE
    recommendation: Recommendation = Recommendation.FIX


@dataclass
class SegmentAnalysis:
    segment: str
    value: str
    n_bets: int
    roi_pct: float
    clv_pct: float
    hit_rate: float
    efficiency: float
    edge_quality: float


@dataclass
class ClvValidationReport:
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: ClvValidationMetrics = field(default_factory=ClvValidationMetrics)
    bets: list[ClvValidationBet] = field(default_factory=list)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    by_sport: list[SegmentAnalysis] = field(default_factory=list)
    by_bookmaker: list[SegmentAnalysis] = field(default_factory=list)
    by_odds_range: list[SegmentAnalysis] = field(default_factory=list)
    by_grade: list[SegmentAnalysis] = field(default_factory=list)
    by_month: list[SegmentAnalysis] = field(default_factory=list)
    by_edge_signal: list[SegmentAnalysis] = field(default_factory=list)
    charts_ev_vs_clv: list[dict] = field(default_factory=list)
    charts_equity: list[dict] = field(default_factory=list)
    charts_edge_decay: list[dict] = field(default_factory=list)
    charts_distribution: list[dict] = field(default_factory=list)
    verdict: str = ""
    summary_text: str = ""
