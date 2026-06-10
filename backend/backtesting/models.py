from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class BetResult(str, Enum):
    WIN = "win"
    LOSS = "loss"
    PENDING = "pending"
    VOID = "void"


class StrategyType(str, Enum):
    EV_THRESHOLD = "ev_threshold"
    KELLY = "kelly"
    CONFIDENCE_FILTERED = "confidence_filtered"
    RISK_ADJUSTED = "risk_adjusted"
    GRADE_FILTERED = "grade_filtered"


@dataclass
class HistoricalBet:
    bet_id: str
    event_id: str
    sport: str
    market: str
    bookmaker: str
    outcome: str
    odd: Decimal
    stake: Decimal
    result: BetResult
    actual_return: Decimal  # odd if win, 0 if loss
    profit: Decimal
    predicted_ev: Decimal        # EV predicted before the event
    predicted_prob: Decimal      # fair probability predicted
    implied_prob: Decimal        # bookmaker implied probability
    confidence_score: float      # 0-1
    risk_level: str              # LOW/MEDIUM/HIGH/EXTREME
    value_grade: str             # ELITE/STRONG/SOLID/SPECULATIVE/NOISE
    kelly_fraction: float
    event_date: datetime
    placed_at: datetime
    settled_at: Optional[datetime] = None

    @property
    def roi(self) -> float:
        """Return on investment for this single bet."""
        if self.stake <= 0:
            return 0.0
        return float(self.profit / self.stake * 100)

    @property
    def is_winner(self) -> bool:
        return self.result == BetResult.WIN

    @property
    def is_valid(self) -> bool:
        return self.result in (BetResult.WIN, BetResult.LOSS)


@dataclass
class BacktestConfig:
    strategy_type: StrategyType = StrategyType.EV_THRESHOLD
    min_ev: float = 5.0
    min_confidence: float = 0.0
    max_risk_level: str = "EXTREME"
    min_value_grade: str = "SPECULATIVE"
    kelly_fraction: float = 0.25
    fixed_stake: Optional[float] = None
    max_stake_pct: float = 0.05      # max 5% of bankroll per bet
    use_grade_filter: bool = True
    use_risk_filter: bool = True
    use_confidence_filter: bool = True
    allowed_sports: Optional[list[str]] = None
    allowed_markets: Optional[list[str]] = None
    excluded_bookmakers: Optional[list[str]] = None

    @property
    def label(self) -> str:
        parts = [self.strategy_type.value]
        if self.min_ev > 0:
            parts.append(f"ev≥{self.min_ev}%")
        if self.kelly_fraction < 1:
            parts.append(f"kelly_{self.kelly_fraction}")
        return "_".join(parts)


@dataclass
class BacktestResult:
    config: BacktestConfig
    total_bets: int = 0
    winning_bets: int = 0
    losing_bets: int = 0
    void_bets: int = 0
    total_staked: Decimal = Decimal("0")
    total_profit: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")
    cumulative_returns: list[float] = field(default_factory=list)
    running_bankroll: list[float] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    bets: list[HistoricalBet] = field(default_factory=list)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    initial_bankroll: float = 1000.0
    final_bankroll: float = 1000.0


@dataclass
class PerformanceMetrics:
    """All computed performance metrics from a backtest."""
    # Core metrics
    total_bets: int = 0
    winning_bets: int = 0
    losing_bets: int = 0
    hit_rate: float = 0.0
    hit_rate_stderr: float = 0.0

    # Profitability
    total_staked: float = 0.0
    total_profit: float = 0.0
    roi_pct: float = 0.0
    roi_std: float = 0.0
    profit_factor: float = 0.0
    avg_profit_per_bet: float = 0.0
    median_profit_per_bet: float = 0.0

    # Risk
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    avg_drawdown_pct: float = 0.0
    ulcer_index: float = 0.0

    # Risk-adjusted
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Statistical
    realized_ev: float = 0.0
    realized_ev_std: float = 0.0
    predicted_vs_realized_r2: float = 0.0
    information_coefficient: float = 0.0
    t_statistic: float = 0.0
    p_value: float = 0.0
    is_significant: bool = False

    # Overfitting
    deflated_sharpe_ratio: float = 0.0
    num_trials: int = 1
    num_min_parameters: int = 1
    sharpe_std_error: float = 0.0
    overfitting_risk: str = "low"

    # Bankroll
    initial_bankroll: float = 1000.0
    final_bankroll: float = 1000.0
    peak_bankroll: float = 1000.0
    bankroll_multiple: float = 1.0

    # Time
    backtest_days: int = 0
    bets_per_day: float = 0.0
    best_month_pct: float = 0.0
    worst_month_pct: float = 0.0
    profitable_months_pct: float = 0.0

    # Strategy parameters
    config_label: str = ""


@dataclass
class SegmentMetrics:
    segment: str
    value: str
    metrics: PerformanceMetrics


@dataclass
class ValidationResult:
    """Result of statistical validation checks."""
    passed: bool
    confidence_level: float = 0.95
    t_statistic: float = 0.0
    p_value: float = 1.0
    is_significant: bool = False
    bootstrap_sharpe_mean: float = 0.0
    bootstrap_sharpe_ci_lower: float = 0.0
    bootstrap_sharpe_ci_upper: float = 0.0
    bootstrap_roi_mean: float = 0.0
    bootstrap_roi_ci_lower: float = 0.0
    bootstrap_roi_ci_upper: float = 0.0
    deflated_sharpe_ratio: float = 0.0
    num_trials: int = 1000
    num_parameters: int = 4
    overfitting_risk: str = "low"
    has_overfit: bool = False
    passed_min_bets: bool = False
    passed_min_sharpe: bool = False
    passed_positive_roi: bool = False
    passed_dsr: bool = False
    passed_significance: bool = False


@dataclass
class BacktestReport:
    overall: PerformanceMetrics
    by_sport: list[SegmentMetrics] = field(default_factory=list)
    by_market: list[SegmentMetrics] = field(default_factory=list)
    by_bookmaker: list[SegmentMetrics] = field(default_factory=list)
    by_grade: list[SegmentMetrics] = field(default_factory=list)
    by_month: list[SegmentMetrics] = field(default_factory=list)
    by_ev_bucket: list[SegmentMetrics] = field(default_factory=list)
    by_risk_level: list[SegmentMetrics] = field(default_factory=list)
    by_confidence_bucket: list[SegmentMetrics] = field(default_factory=list)
    comparisons: list[tuple[str, PerformanceMetrics]] = field(default_factory=list)

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    n_bets_total: int = 0
    n_strategies_tested: int = 1
    best_strategy: Optional[str] = None
