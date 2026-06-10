from __future__ import annotations

import math
import random
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from backend.app.log_config import get_logger
from .models import BacktestResult, ValidationResult, PerformanceMetrics
from .metrics import compute_metrics

logger = get_logger(__name__)


def validate_backtest(
    result: BacktestResult,
    num_trials: int = 1000,
    num_parameters: int = 4,
    bootstrap_samples: int = 10000,
    alpha: float = 0.05,
) -> ValidationResult:
    """
    Full statistical validation of a backtest result.

    Includes:
    - Bootstrap confidence intervals for Sharpe and ROI
    - Deflated Sharpe Ratio
    - p-value for mean profit > 0
    - Overfitting detection via return comparison
    """
    metrics = compute_metrics(result, num_trials=num_trials, num_parameters=num_parameters)

    profits = [float(b.profit) for b in result.bets]

    # ── Bootstrap ────────────────────────────────────────────────
    bootstrap_sharpe, bootstrap_ci_sharpe = _bootstrap_sharpe(
        result, n_samples=bootstrap_samples, alpha=alpha
    )
    bootstrap_roi, bootstrap_ci_roi = _bootstrap_roi(
        result, n_samples=bootstrap_samples, alpha=alpha
    )

    # ── Tests ────────────────────────────────────────────────────
    t_stat = metrics.t_statistic
    p_value = metrics.p_value
    is_significant = p_value < alpha

    # ── Overfitting ─────────────────────────────────────────────
    dsr = metrics.deflated_sharpe_ratio
    overfitting_risk = metrics.overfitting_risk

    has_overfit = overfitting_risk in ("medium", "high")

    # ── Minimum requirements ─────────────────────────────────────
    passed_min_bets = result.total_bets >= 100
    passed_min_sharpe = metrics.sharpe_ratio > 0.5
    passed_positive_roi = metrics.roi_pct > 0
    passed_dsr = dsr > 0.5

    passed = (
        passed_min_bets
        and passed_min_sharpe
        and passed_positive_roi
        and passed_dsr
        and not has_overfit
        and is_significant
    )

    return ValidationResult(
        passed=passed,
        confidence_level=1 - alpha,
        t_statistic=t_stat,
        p_value=p_value,
        is_significant=is_significant,
        bootstrap_sharpe_mean=bootstrap_sharpe,
        bootstrap_sharpe_ci_lower=bootstrap_ci_sharpe[0],
        bootstrap_sharpe_ci_upper=bootstrap_ci_sharpe[1],
        bootstrap_roi_mean=bootstrap_roi,
        bootstrap_roi_ci_lower=bootstrap_ci_roi[0],
        bootstrap_roi_ci_upper=bootstrap_ci_roi[1],
        deflated_sharpe_ratio=dsr,
        num_trials=num_trials,
        num_parameters=num_parameters,
        overfitting_risk=overfitting_risk,
        has_overfit=has_overfit,
        passed_min_bets=passed_min_bets,
        passed_min_sharpe=passed_min_sharpe,
        passed_positive_roi=passed_positive_roi,
        passed_dsr=passed_dsr,
        passed_significance=is_significant,
    )


def _bootstrap_sharpe(
    result: BacktestResult,
    n_samples: int = 10000,
    alpha: float = 0.05,
) -> tuple[float, tuple[float, float]]:
    """Bootstrap the Sharpe ratio."""
    profits = [float(b.profit) for b in result.bets]
    if len(profits) < 10:
        return 0.0, (0.0, 0.0)

    sharpe_values = []
    mean = sum(profits) / len(profits)
    for _ in range(n_samples):
        sample = [random.choice(profits) for _ in range(len(profits))]
        sample_mean = sum(sample) / len(sample)
        sample_std = _std(sample)
        if sample_std > 0:
            sharpe_values.append(sample_mean / sample_std * math.sqrt(365))

    if not sharpe_values:
        return 0.0, (0.0, 0.0)

    boot_mean = sum(sharpe_values) / len(sharpe_values)
    sorted_s = sorted(sharpe_values)
    lower_idx = int(n_samples * alpha / 2)
    upper_idx = int(n_samples * (1 - alpha / 2))
    lower = sorted_s[max(0, lower_idx)]
    upper = sorted_s[min(len(sorted_s) - 1, upper_idx)]
    return boot_mean, (lower, upper)


def _bootstrap_roi(
    result: BacktestResult,
    n_samples: int = 10000,
    alpha: float = 0.05,
) -> tuple[float, tuple[float, float]]:
    """Bootstrap ROI."""
    if result.total_bets == 0:
        return 0.0, (0.0, 0.0)

    returns = [float(b.profit / b.stake) if b.stake > 0 else 0.0 for b in result.bets]
    if len(returns) < 10:
        return 0.0, (0.0, 0.0)

    roi_values = []
    for _ in range(n_samples):
        sample = [random.choice(returns) for _ in range(len(returns))]
        roi_values.append(sum(sample) / len(sample) * 100)

    if not roi_values:
        return 0.0, (0.0, 0.0)

    boot_mean = sum(roi_values) / len(roi_values)
    sorted_r = sorted(roi_values)
    lower_idx = int(n_samples * alpha / 2)
    upper_idx = int(n_samples * (1 - alpha / 2))
    lower = sorted_r[max(0, lower_idx)]
    upper = sorted_r[min(len(sorted_r) - 1, upper_idx)]
    return boot_mean, (lower, upper)


def _std(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
