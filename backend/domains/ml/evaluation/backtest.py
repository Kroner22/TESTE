"""Historical backtesting engine with walk-forward validation."""

from typing import Optional, Callable
import pandas as pd
import numpy as np

from backend.domains.ml.models import TrainMetrics, BacktestResult
from backend.domains.ml.evaluation.metrics import compute_metrics, compute_profit_metrics
from backend.domains.ml.pipeline.validator import TimeSeriesCV


class BacktestEngine:
    def __init__(self, n_windows: int = 5, window_size: int = 200, step_size: int = 50):
        self.n_windows = n_windows
        self.window_size = window_size
        self.step_size = step_size

    def run(self, model_trainer, X: pd.DataFrame, y: pd.Series,
            home_odds: Optional[np.ndarray] = None,
            away_odds: Optional[np.ndarray] = None) -> BacktestResult:
        result = BacktestResult()
        n = len(X)
        metrics_list = []

        for w in range(self.n_windows):
            train_end = (w + 1) * self.step_size + self.window_size
            if train_end >= n:
                break
            test_start = min(train_end + 1, n - 1)
            test_end = min(test_start + self.step_size, n)

            if test_end - test_start < 10:
                break

            X_train = X.iloc[:train_end]
            y_train = y.iloc[:train_end]
            X_test = X.iloc[test_start:test_end]
            y_test = y.iloc[test_start:test_end]

            model_trainer.model = model_trainer._build_model(X_train.shape[1])
            model_trainer.model.fit(X_train, y_train)
            probs = model_trainer.model.predict_proba(X_test)
            preds = (probs >= 0.5).astype(int)

            metrics = compute_metrics(y_test.values, probs, preds)

            if home_odds is not None and away_odds is not None:
                h_odds = home_odds[test_start:test_end]
                a_odds = away_odds[test_start:test_end]
                profit = compute_profit_metrics(y_test.values, probs, h_odds, a_odds)
                metrics.sharpe_ratio = profit.get("sharpe_ratio")
                metrics.max_drawdown = profit.get("max_drawdown")
                metrics.roi = profit.get("roi")

            metrics.n_matches = len(y_test)
            metrics_list.append(metrics)

        if not metrics_list:
            return result

        result.window_metrics = metrics_list
        result.n_windows = len(metrics_list)

        agg = TrainMetrics()
        agg.brier = np.mean([m.brier for m in metrics_list])
        agg.log_loss = np.mean([m.log_loss for m in metrics_list])
        agg.auc_roc = np.mean([m.auc_roc for m in metrics_list])
        agg.auc_pr = np.mean([m.auc_pr for m in metrics_list])
        agg.accuracy = np.mean([m.accuracy for m in metrics_list])
        agg.n_matches = sum(m.n_matches for m in metrics_list)
        result.aggregate = agg

        if len(metrics_list) >= 3:
            briers = [m.brier for m in metrics_list]
            result.stability_score = 1.0 - min(1.0, np.std(briers) / max(np.mean(briers), 0.01))
            result.degradation_rate = (
                (briers[-1] - briers[0]) / max(briers[0], 0.001)
                if briers[0] > 0 else 0.0
            )

        return result


class RollingSharpe:
    def __init__(self, window: int = 50):
        self.window = window

    def compute(self, returns: np.ndarray) -> np.ndarray:
        rolling = pd.Series(returns).rolling(self.window)
        sharpe = rolling.mean() / rolling.std().clip(lower=1e-10)
        return sharpe.values
