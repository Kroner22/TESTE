from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.app.log_config import get_logger
from .models import BacktestResult, PerformanceMetrics, ValidationResult
from .metrics import compute_metrics
from .validator import validate_backtest
from .analyzer import BacktestAnalyzer

logger = get_logger(__name__)


def generate_report(
    result: BacktestResult,
    num_trials: int = 1000,
    num_parameters: int = 4,
    bootstrap_samples: int = 10000,
    alpha: float = 0.05,
) -> dict:
    metrics = compute_metrics(result)
    validation = validate_backtest(
        result,
        num_trials=num_trials,
        num_parameters=num_parameters,
        bootstrap_samples=bootstrap_samples,
        alpha=alpha,
    )
    analyzer = BacktestAnalyzer(result)
    analysis = analyzer.summary()

    report = {
        "report_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "config_label": result.config.label,
            "config": {
                "min_ev": result.config.min_ev,
                "min_confidence": result.config.min_confidence,
                "max_risk_level": result.config.max_risk_level,
                "min_value_grade": result.config.min_value_grade,
                "strategy_type": result.config.strategy_type.value,
                "kelly_fraction": result.config.kelly_fraction,
                "max_stake_pct": result.config.max_stake_pct,
                "fixed_stake": result.config.fixed_stake,
            },
        },
        "summary": {
            "passed_validation": validation.passed,
            "total_bets": metrics.total_bets,
            "winning_bets": metrics.winning_bets,
            "losing_bets": metrics.losing_bets,
            "hit_rate": metrics.hit_rate,
            "total_staked": metrics.total_staked,
            "total_profit": metrics.total_profit,
            "roi_pct": metrics.roi_pct,
            "profit_factor": metrics.profit_factor,
            "initial_bankroll": metrics.initial_bankroll,
            "final_bankroll": metrics.final_bankroll,
            "bankroll_multiple": metrics.bankroll_multiple,
        },
        "risk_metrics": {
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "max_drawdown_duration_days": metrics.max_drawdown_duration_days,
            "avg_drawdown_pct": metrics.avg_drawdown_pct,
            "ulcer_index": metrics.ulcer_index,
            "sharpe_ratio": metrics.sharpe_ratio,
            "sortino_ratio": metrics.sortino_ratio,
            "calmar_ratio": metrics.calmar_ratio,
        },
        "statistical_validation": {
            "t_statistic": validation.t_statistic,
            "p_value": validation.p_value,
            "is_significant": validation.is_significant,
            "bootstrap_sharpe_mean": validation.bootstrap_sharpe_mean,
            "bootstrap_sharpe_ci_lower": validation.bootstrap_sharpe_ci_lower,
            "bootstrap_sharpe_ci_upper": validation.bootstrap_sharpe_ci_upper,
            "bootstrap_roi_mean": validation.bootstrap_roi_mean,
            "bootstrap_roi_ci_lower": validation.bootstrap_roi_ci_lower,
            "bootstrap_roi_ci_upper": validation.bootstrap_roi_ci_upper,
            "deflated_sharpe_ratio": validation.deflated_sharpe_ratio,
            "overfitting_risk": validation.overfitting_risk,
            "has_overfit": validation.has_overfit,
        },
        "predictive_power": {
            "r2_predicted_vs_realized": metrics.predicted_vs_realized_r2,
            "information_coefficient": metrics.information_coefficient,
            "realized_ev": metrics.realized_ev,
            "realized_ev_std": metrics.realized_ev_std,
        },
        "segmented_analysis": analysis,
        "validation_detail": {
            "passed_min_bets": validation.passed_min_bets,
            "passed_min_sharpe": validation.passed_min_sharpe,
            "passed_positive_roi": validation.passed_positive_roi,
            "passed_dsr": validation.passed_dsr,
            "passed_significance": validation.passed_significance,
        },
    }

    return report
