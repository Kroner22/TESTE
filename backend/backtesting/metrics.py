from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from backend.app.log_config import get_logger
from .models import (
    BacktestResult, PerformanceMetrics,
)

logger = get_logger(__name__)


def compute_metrics(
    result: BacktestResult,
    num_trials: int = 1,
    num_parameters: int = 4,
) -> PerformanceMetrics:
    """Compute all performance metrics from a backtest result."""
    bets = result.bets
    if not bets:
        return PerformanceMetrics(config_label=result.config.label)

    n = len(bets)
    wins = result.winning_bets
    losses = result.losing_bets
    total_staked = float(result.total_staked)
    total_profit = float(result.total_profit)

    # ── Hit Rate ─────────────────────────────────────────────────
    hit_rate = wins / n if n > 0 else 0.0
    hit_rate_stderr = math.sqrt(hit_rate * (1 - hit_rate) / n) if n > 0 else 0.0

    # ── Profitability ────────────────────────────────────────────
    roi_pct = (total_profit / total_staked * 100) if total_staked > 0 else 0.0
    profits = [float(b.profit) for b in bets]
    roi_std = _std(profits) if profits else 0.0
    profit_factor = float(result.gross_profit / result.gross_loss) if result.gross_loss > 0 else float("inf")
    avg_profit = total_profit / n if n > 0 else 0.0
    sorted_profits = sorted(profits)
    median_profit = sorted_profits[n // 2] if sorted_profits else 0.0

    # ── Bankroll ─────────────────────────────────────────────────
    bankrolls = result.running_bankroll
    initial_bankroll = result.initial_bankroll
    final_bankroll = result.final_bankroll
    peak_bankroll = max(bankrolls) if bankrolls else initial_bankroll
    bankroll_multiple = final_bankroll / initial_bankroll if initial_bankroll > 0 else 1.0

    # ── Drawdown ─────────────────────────────────────────────────
    max_dd, max_dd_duration, avg_dd, ulcer = _compute_drawdown(bankrolls)
    max_drawdown_pct = max_dd * 100
    avg_drawdown_pct = avg_dd * 100

    # ── Risk-adjusted returns ────────────────────────────────────
    period_returns = _compute_period_returns(result.equity_curve, period_days=1)
    sharpe = _compute_sharpe(period_returns)
    sortino = _compute_sortino(period_returns)
    calmar = _compute_calmar(roi_pct / 100.0, max_dd)

    # ── Statistical validation ───────────────────────────────────
    realized_ev = _compute_realized_ev(bets)
    realized_ev_std = _std([float(b.profit / b.stake) if b.stake > 0 else 0 for b in bets])

    r2 = _compute_predicted_vs_actual_r2(bets)
    ic = _compute_information_coefficient(bets)

    t_stat, p_val = _one_sample_t_test(profits)
    is_sig = p_val < 0.05

    # ── Overfitting ──────────────────────────────────────────────
    sharpe_std_err = 1.0 / math.sqrt(n) if n > 0 else 1.0
    dsr = _deflated_sharpe_ratio(sharpe, num_trials, num_parameters, n)

    if dsr > 0.5:
        overfitting_risk = "low"
    elif dsr > 0.0:
        overfitting_risk = "medium"
    else:
        overfitting_risk = "high"

    # ── Time ─────────────────────────────────────────────────────
    backtest_days = 0
    bets_per_day = 0.0
    best_month_pct = 0.0
    worst_month_pct = 0.0
    profitable_months_pct = 0.0

    if result.start_date and result.end_date:
        backtest_days = max(1, (result.end_date - result.start_date).days)
        bets_per_day = n / backtest_days if backtest_days > 0 else 0.0

        monthly = _monthly_returns(result.equity_curve)
        if monthly:
            best_month_pct = max(monthly.values()) * 100
            worst_month_pct = min(monthly.values()) * 100
            profitable_months_pct = sum(1 for v in monthly.values() if v > 0) / len(monthly) * 100

    return PerformanceMetrics(
        total_bets=n,
        winning_bets=wins,
        losing_bets=losses,
        hit_rate=round(hit_rate, 4),
        hit_rate_stderr=round(hit_rate_stderr, 4),
        total_staked=round(total_staked, 2),
        total_profit=round(total_profit, 2),
        roi_pct=round(roi_pct, 4),
        roi_std=round(roi_std, 4),
        profit_factor=round(profit_factor, 4),
        avg_profit_per_bet=round(avg_profit, 2),
        median_profit_per_bet=round(median_profit, 2),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        max_drawdown_duration_days=max_dd_duration,
        avg_drawdown_pct=round(avg_drawdown_pct, 4),
        ulcer_index=round(ulcer, 4),
        sharpe_ratio=round(sharpe, 4),
        sortino_ratio=round(sortino, 4),
        calmar_ratio=round(calmar, 4),
        realized_ev=round(realized_ev, 4),
        realized_ev_std=round(realized_ev_std, 4),
        predicted_vs_realized_r2=round(r2, 4),
        information_coefficient=round(ic, 4),
        t_statistic=round(t_stat, 4),
        p_value=round(p_val, 6),
        is_significant=is_sig,
        deflated_sharpe_ratio=round(dsr, 4),
        num_trials=num_trials,
        num_min_parameters=num_parameters,
        sharpe_std_error=round(sharpe_std_err, 4),
        overfitting_risk=overfitting_risk,
        initial_bankroll=initial_bankroll,
        final_bankroll=round(final_bankroll, 2),
        peak_bankroll=round(peak_bankroll, 2),
        bankroll_multiple=round(bankroll_multiple, 4),
        backtest_days=backtest_days,
        bets_per_day=round(bets_per_day, 2),
        best_month_pct=round(best_month_pct, 4),
        worst_month_pct=round(worst_month_pct, 4),
        profitable_months_pct=round(profitable_months_pct, 2),
        config_label=result.config.label,
    )


# ─── Drawdown ────────────────────────────────────────────────────

def _compute_drawdown(
    bankrolls: list[float],
) -> tuple[float, int, float, float]:
    """
    Compute max drawdown, duration, avg drawdown, and ulcer index.
    
    Returns:
        (max_drawdown_pct, max_duration_days, avg_drawdown_pct, ulcer_index)
    """
    if not bankrolls:
        return 0.0, 0, 0.0, 0.0

    peak = bankrolls[0]
    max_dd = 0.0
    max_dd_start = 0
    max_dd_end = 0
    current_dd_start = 0
    total_dd = 0.0
    n_dd_periods = 0
    squared_dd_sum = 0.0

    for i, value in enumerate(bankrolls):
        if value > peak:
            peak = value
            current_dd_start = i

        dd = (peak - value) / peak if peak > 0 else 0.0
        if dd > 0:
            total_dd += dd
            n_dd_periods += 1
            squared_dd_sum += dd ** 2

        if dd > max_dd:
            max_dd = dd
            max_dd_start = current_dd_start
            max_dd_end = i

    avg_dd = total_dd / n_dd_periods if n_dd_periods > 0 else 0.0
    ulcer = math.sqrt(squared_dd_sum / len(bankrolls)) if bankrolls else 0.0
    max_duration = max_dd_end - max_dd_start

    return max_dd, max_duration, avg_dd, ulcer


# ─── Period Returns ──────────────────────────────────────────────

def _compute_period_returns(
    equity_curve: list[tuple[datetime, float]],
    period_days: int = 1,
) -> list[float]:
    """Break equity curve into period returns."""
    if len(equity_curve) < 2:
        return []
    returns = []
    prev_value = equity_curve[0][1]
    prev_time = equity_curve[0][0]
    for time, value in equity_curve[1:]:
        dt = (time - prev_time).total_seconds() / 86400
        if dt >= period_days:
            ret = (value - prev_value) / prev_value if prev_value > 0 else 0.0
            returns.append(ret)
            prev_value = value
            prev_time = time
    return returns


# ─── Sharpe / Sortino / Calmar ───────────────────────────────────

def _compute_sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    mean_excess = sum(excess) / len(excess)
    std_excess = _std(excess)
    if std_excess <= 0:
        return 0.0
    annualized = math.sqrt(365)  # daily returns → annual
    return mean_excess / std_excess * annualized


def _compute_sortino(returns: list[float], risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    mean_excess = sum(excess) / len(excess)
    downside = [r for r in excess if r < 0]
    if not downside:
        return float("inf") if mean_excess > 0 else 0.0
    downside_std = math.sqrt(sum(d * d for d in downside) / len(downside))
    if downside_std <= 0:
        return 0.0
    return mean_excess / downside_std * math.sqrt(365)


def _compute_calmar(annual_return: float, max_drawdown: float) -> float:
    if max_drawdown <= 0:
        return float("inf") if annual_return > 0 else 0.0
    return annual_return / max_drawdown


# ─── Statistical ─────────────────────────────────────────────────

def _compute_realized_ev(bets: list) -> float:
    """Average realized EV = average of (outcome_return / stake - 1)."""
    if not bets:
        return 0.0
    realized = []
    for b in bets:
        if b.stake > 0:
            realized.append(float(b.actual_return / b.stake - Decimal("1")))
    return sum(realized) / len(realized) if realized else 0.0


def _compute_predicted_vs_actual_r2(bets: list) -> float:
    """R² between predicted EV buckets and actual average return."""
    if len(bets) < 20:
        return 0.0
    buckets = defaultdict(list)
    for b in bets:
        ev = round(float(b.predicted_ev), 0)
        buckets[ev].append(float(b.actual_return / b.stake - Decimal("1")) if b.stake > 0 else 0.0)

    evs = []
    avg_actuals = []
    for ev in sorted(buckets.keys()):
        actuals = buckets[ev]
        if len(actuals) >= 5:
            evs.append(ev)
            avg_actuals.append(sum(actuals) / len(actuals))

    if len(evs) < 3:
        return 0.0

    mean_ev = sum(evs) / len(evs)
    mean_act = sum(avg_actuals) / len(avg_actuals)
    ss_res = sum((a - (mean_act / mean_ev * e if mean_ev != 0 else 0)) ** 2
                 for e, a in zip(evs, avg_actuals))
    ss_tot = sum((a - mean_act) ** 2 for a in avg_actuals)
    if ss_tot <= 0:
        return 0.0
    return max(0.0, 1.0 - ss_res / ss_tot)


def _compute_information_coefficient(bets: list) -> float:
    """Spearman correlation between predicted EV and actual return."""
    if len(bets) < 10:
        return 0.0
    from scipy.stats import spearmanr
    evs = [float(b.predicted_ev) for b in bets]
    returns = [float(b.actual_return / b.stake - Decimal("1")) if b.stake > 0 else 0.0 for b in bets]
    try:
        rho, _ = spearmanr(evs, returns)
        return rho if not math.isnan(rho) else 0.0
    except Exception:
        return 0.0


def _one_sample_t_test(sample: list[float]) -> tuple[float, float]:
    """One-sample t-test against mean=0."""
    n = len(sample)
    if n < 2:
        return 0.0, 1.0
    mean = sum(sample) / n
    std = _std(sample)
    if std <= 0:
        return 0.0, 1.0
    se = std / math.sqrt(n)
    t = mean / se
    from scipy.stats import t as t_dist
    try:
        p = 2 * (1 - t_dist.cdf(abs(t), df=n - 1))
    except Exception:
        p = 1.0
    return t, p


# ─── Overfitting ─────────────────────────────────────────────────

def _deflated_sharpe_ratio(
    sharpe: float,
    num_trials: int,
    num_parameters: int,
    n_observations: int,
) -> float:
    """
    Deflated Sharpe Ratio (Bailey et al.).
    
    Adjusts Sharpe for multiple testing and non-normality.
    """
    if n_observations < 10:
        return 0.0

    # Expected maximum Sharpe under null (approximation)
    gamma = 0.5772  # Euler-Mascheroni
    e_max_sr = math.sqrt(1.0 / n_observations) * (
        (1 - gamma) * norm_ppf(1 - 1.0 / max(num_trials, 2)) +
        gamma * norm_ppf(1 - 1.0 / (max(num_trials, 2) * math.e))
    )

    # Variance adjustment for non-normality
    try:
        from scipy.stats import skew, kurtosis
        sk = skew([1.0])
        ku = kurtosis([1.0])
    except Exception:
        sk = 0.0
        ku = 3.0

    var_sr = (1 - ku * sharpe + (ku - 1) * sharpe ** 2 / 4) / (n_observations - 1)
    var_sr = max(var_sr, 0.001)

    dsr = (sharpe - e_max_sr) / math.sqrt(var_sr) if var_sr > 0 else 0.0

    # Convert to probability
    try:
        from scipy.stats import norm
        return norm.cdf(dsr)
    except Exception:
        return min(1.0, max(0.0, dsr * 0.5 + 0.5))


def norm_ppf(q: float) -> float:
    """Approximate normal quantile function (Abramowitz & Stegun)."""
    if q <= 0: return -10.0
    if q >= 1: return 10.0
    try:
        from scipy.stats import norm
        return norm.ppf(q)
    except Exception:
        if q < 0.5:
            return -3.0
        return 3.0


# ─── Helpers ─────────────────────────────────────────────────────

def _monthly_returns(equity_curve: list[tuple[datetime, float]]) -> dict[str, float]:
    """Compute return for each calendar month."""
    monthly: dict[str, list[float]] = defaultdict(list)
    for dt, value in equity_curve:
        key = dt.strftime("%Y-%m")
        monthly[key].append(value)
    returns = {}
    for key, values in monthly.items():
        if len(values) >= 2:
            ret = (values[-1] - values[0]) / values[0] if values[0] > 0 else 0.0
            returns[key] = ret
    return returns


def _std(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)
