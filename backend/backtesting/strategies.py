from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .models import (
    HistoricalBet, BetResult, BacktestConfig, StrategyType,
)


class Strategy:
    """
    Base class for backtest strategies.

    A strategy defines which bets to accept and how much to stake.
    """

    def __init__(self, config: BacktestConfig):
        self.config = config

    def should_accept(self, bet: HistoricalBet) -> bool:
        """Apply all filters to decide if this bet is accepted."""
        if self.config.min_ev > 0 and float(bet.predicted_ev) < self.config.min_ev:
            return False
        if self.config.use_confidence_filter and bet.confidence_score < self.config.min_confidence:
            return False
        if self.config.use_risk_filter:
            risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "EXTREME": 3}
            max_risk = risk_order.get(self.config.max_risk_level.upper(), 3)
            bet_risk = risk_order.get(bet.risk_level.upper(), 3)
            if bet_risk > max_risk:
                return False
        if self.config.use_grade_filter:
            grade_order = {"ELITE": 0, "STRONG": 1, "SOLID": 2, "SPECULATIVE": 3, "NOISE": 4}
            min_grade = grade_order.get(self.config.min_value_grade.upper(), 4)
            bet_grade = grade_order.get(bet.value_grade.upper(), 4)
            if bet_grade > min_grade:
                return False
        if self.config.allowed_sports and bet.sport not in self.config.allowed_sports:
            return False
        if self.config.allowed_markets and bet.market not in self.config.allowed_markets:
            return False
        if self.config.excluded_bookmakers and bet.bookmaker in self.config.excluded_bookmakers:
            return False
        return True

    def compute_stake(
        self,
        bet: HistoricalBet,
        bankroll: Decimal,
    ) -> Decimal:
        """Compute stake based on strategy type."""
        if self.config.fixed_stake is not None:
            return Decimal(str(self.config.fixed_stake))

        if self.config.strategy_type == StrategyType.KELLY:
            return self._kelly_stake(bet, bankroll)

        if self.config.strategy_type == StrategyType.RISK_ADJUSTED:
            return self._risk_adjusted_stake(bet, bankroll)

        pct = min(self.config.max_stake_pct, self.config.kelly_fraction * 0.25 + 0.01)
        return bankroll * Decimal(str(pct))

    def _kelly_stake(self, bet: HistoricalBet, bankroll: Decimal) -> Decimal:
        """Full Kelly criterion: f* = (p * b - q) / b where b = (odd - 1)."""
        b = bet.odd - Decimal("1")
        if b <= 0:
            return Decimal("0")
        p = bet.predicted_prob
        q = Decimal("1") - p
        f = (p * b - q) / b
        f = max(Decimal("0"), f)
        f = f * Decimal(str(self.config.kelly_fraction))
        max_stake = bankroll * Decimal(str(self.config.max_stake_pct))
        return min(f * bankroll, max_stake)

    def _risk_adjusted_stake(self, bet: HistoricalBet, bankroll: Decimal) -> Decimal:
        """Kelly stake discounted by risk level."""
        base = self._kelly_stake(bet, bankroll)
        risk_discounts = {"LOW": 1.0, "MEDIUM": 0.7, "HIGH": 0.4, "EXTREME": 0.1}
        discount = risk_discounts.get(bet.risk_level.upper(), 0.5)
        return base * Decimal(str(discount))


class StrategyOptimizer:
    """
    Hyperparameter search over strategy configurations.
    Tests all combinations and ranks by Sharpe ratio.
    """

    def __init__(
        self,
        ev_thresholds: Optional[list[float]] = None,
        confidence_thresholds: Optional[list[float]] = None,
        kelly_fractions: Optional[list[float]] = None,
        grade_filters: Optional[list[str]] = None,
        risk_filters: Optional[list[str]] = None,
    ):
        self.ev_thresholds = ev_thresholds or [0, 2, 5, 10, 20]
        self.confidence_thresholds = confidence_thresholds or [0, 0.3, 0.5, 0.7]
        self.kelly_fractions = kelly_fractions or [0.0, 0.1, 0.25, 0.5, 1.0]
        self.grade_filters = grade_filters or ["NOISE", "SPECULATIVE", "SOLID", "STRONG", "ELITE"]
        self.risk_filters = risk_filters or ["LOW", "MEDIUM", "HIGH", "EXTREME"]

    def generate_configs(self) -> list[BacktestConfig]:
        configs = []
        for ev in self.ev_thresholds:
            for conf in self.confidence_thresholds:
                for kelly in self.kelly_fractions:
                    for grade in self.grade_filters:
                        for risk in self.risk_filters:
                            configs.append(BacktestConfig(
                                strategy_type=StrategyType.EV_THRESHOLD if ev > 0 else StrategyType.GRADE_FILTERED,
                                min_ev=ev,
                                min_confidence=conf,
                                kelly_fraction=kelly,
                                min_value_grade=grade,
                                max_risk_level=risk,
                            ))
        return configs

    def top_configs(
        self,
        results: list[tuple[BacktestConfig, "PerformanceMetrics"]],
        n: int = 10,
    ) -> list[tuple[BacktestConfig, "PerformanceMetrics"]]:
        ranked = sorted(
            [(c, m) for c, m in results if m.total_bets >= 30],
            key=lambda x: x[1].sharpe_ratio,
            reverse=True,
        )
        return ranked[:n]
