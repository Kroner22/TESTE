from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class ClvGrade(str, Enum):
    ELITE = "ELITE"             # CLV > 3%
    STRONG = "STRONG"           # CLV > 1.5%
    POSITIVE = "POSITIVE"       # CLV > 0%
    NEUTRAL = "NEUTRAL"         # CLV ~ 0%
    NEGATIVE = "NEGATIVE"       # CLV < 0%
    BAD = "BAD"                 # CLV < -1.5%
    CATASTROPHIC = "CATASTROPHIC"  # CLV < -3%


class TimingEfficiency(str, Enum):
    EARLY = "EARLY"             # Captured before steam
    OPTIMAL = "OPTIMAL"         # Near best price
    LATE = "LATE"               # After steam moved
    DEAD = "DEAD"               # After closing


@dataclass
class ClvRecord:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    captured_odd: Decimal
    captured_prob: float
    captured_at: datetime
    closing_odd: Decimal
    closing_prob: float
    closed_at: datetime
    opening_odd: Decimal
    opening_at: datetime
    clv: float
    clv_pct: float
    timing_efficiency: TimingEfficiency
    hours_to_close: float
    grade: ClvGrade
    odds_movement: float
    simulated_ev: float
    simulated_kelly: Optional[float] = None
    model_edge: Optional[float] = None


@dataclass
class ClvSnapshot:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    odd: Decimal
    prob: float
    timestamp: datetime
    is_opening: bool = False
    is_closing: bool = False
    version: int = 0


@dataclass
class BookmakerClvStats:
    bookmaker: str
    n_bets: int
    avg_clv_pct: float
    median_clv_pct: float
    std_clv_pct: float
    positive_rate: float
    elite_rate: float
    catastrophic_rate: float
    avg_timing_score: float
    best_outcome: str
    worst_outcome: str


@dataclass
class ClvCorrelation:
    pearson_r: float
    spearman_rho: float
    p_value: float
    interpretation: str


@dataclass
class TimingAnalysis:
    avg_hours_to_close: float
    early_pct: float
    optimal_pct: float
    late_pct: float
    dead_pct: float
    best_timing_clv: float
    worst_timing_clv: float
    early_avg_clv: float
    late_avg_clv: float


@dataclass
class ClvDistribution:
    total_records: int
    mean_clv: float
    median_clv: float
    std_clv: float
    min_clv: float
    max_clv: float
    positive_count: int
    positive_pct: float
    negative_count: int
    negative_pct: float
    neutral_count: int
    grade_distribution: dict[ClvGrade, int]
    positive_sum_clv: float
    negative_sum_clv: float


@dataclass
class ClvReport:
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    n_records: int = 0
    n_events: int = 0
    n_bookmakers: int = 0
    overall_clv: float = 0.0
    overall_clv_pct: float = 0.0
    distribution: Optional[ClvDistribution] = None
    by_bookmaker: list[BookmakerClvStats] = field(default_factory=list)
    correlation: Optional[ClvCorrelation] = None
    timing: Optional[TimingAnalysis] = None
    model_quality: str = ""
    verdict: str = ""
    recommendations: list[str] = field(default_factory=list)
