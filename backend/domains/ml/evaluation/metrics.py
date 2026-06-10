"""Statistical metrics for model evaluation."""

from typing import Optional
import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss, log_loss, roc_auc_score, average_precision_score,
    accuracy_score, precision_score, recall_score, f1_score,
    mean_squared_error, r2_score,
)

from backend.domains.ml.models import TrainMetrics


def brier(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    return float(brier_score_loss(y_true, y_prob))


def auc_roc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    try:
        return float(roc_auc_score(y_true, y_prob))
    except ValueError:
        return 0.5


def auc_pr(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    try:
        return float(average_precision_score(y_true, y_prob))
    except ValueError:
        return 0.5


def compute_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    y_pred: Optional[np.ndarray] = None,
) -> TrainMetrics:
    if y_pred is None:
        y_pred = (y_prob >= 0.5).astype(int)

    metrics = TrainMetrics()
    metrics.brier = brier(y_true, y_prob)
    metrics.log_loss = float(log_loss(y_true, y_prob))
    metrics.auc_roc = auc_roc(y_true, y_prob)
    metrics.auc_pr = auc_pr(y_true, y_prob)
    metrics.accuracy = float(accuracy_score(y_true, y_pred))
    metrics.precision = float(precision_score(y_true, y_pred, zero_division=0))
    metrics.recall = float(recall_score(y_true, y_pred, zero_division=0))
    metrics.f1 = float(f1_score(y_true, y_pred, zero_division=0))
    metrics.mse = float(mean_squared_error(y_true, y_prob))
    metrics.n_matches = len(y_true)

    y_prob_clipped = np.clip(y_prob, 1e-15, 1 - 1e-15)
    metrics.calibration_intercept = float(
        np.mean(y_true) - np.mean(y_prob_clipped)
    )
    ece = calibration_ece(y_true, y_prob_clipped)
    metrics.ece = ece

    return metrics


def calibration_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)
    ece = 0.0
    for i in range(n_bins):
        mask = bin_indices == i
        if mask.sum() == 0:
            continue
        bin_acc = y_true[mask].mean()
        bin_conf = y_prob[mask].mean()
        ece += mask.sum() * abs(bin_acc - bin_conf)
    return ece / len(y_true)


def profit_curve(y_true: np.ndarray, y_prob: np.ndarray,
                 odds: np.ndarray) -> np.ndarray:
    sorted_idx = np.argsort(-y_prob)
    cum_profit = np.zeros(len(y_true))
    for i, idx in enumerate(sorted_idx):
        if i == 0:
            cum_profit[i] = (odds[idx] - 1) if y_true[idx] == 1 else -1
        else:
            prev = cum_profit[i - 1]
            cum_profit[i] = prev + ((odds[idx] - 1) if y_true[idx] == 1 else -1)
    return cum_profit


def compute_profit_metrics(y_true: np.ndarray, y_prob: np.ndarray,
                           home_odds: Optional[np.ndarray] = None,
                           away_odds: Optional[np.ndarray] = None,
                           threshold: float = 0.5,
                           stake: float = 1.0) -> dict:
    preds = (y_prob >= threshold).astype(int)
    correct = preds == y_true

    if home_odds is not None and away_odds is not None:
        odds_used = np.where(preds == 1, home_odds, away_odds)
    else:
        odds_used = np.full_like(y_prob, 2.0)

    payout = np.where(correct, odds_used, 0.0) * stake
    profit = payout - stake
    total_profit = profit.sum()
    roi = total_profit / (stake * len(y_true)) if len(y_true) > 0 else 0.0

    betting_profits = profit[profit != 0]
    if len(betting_profits) > 1:
        sharpe = betting_profits.mean() / (betting_profits.std() + 1e-10)
    else:
        sharpe = 0.0

    cumulative = np.cumsum(profit)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = cumulative - running_max
    max_dd = drawdown.min() if len(drawdown) > 0 else 0.0

    return {
        "roi": float(roi),
        "total_profit": float(total_profit),
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(max_dd),
        "n_bets": int(preds.sum()),
        "win_rate": float(correct[preds == 1].mean()) if preds.sum() > 0 else 0.0,
    }
