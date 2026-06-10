"""Time-series cross-validation with purge and embargo."""

from typing import Callable, Optional
import pandas as pd
import numpy as np

from backend.domains.ml.models import TrainMetrics
from backend.domains.ml.evaluation.metrics import compute_metrics


class TimeSeriesCV:
    def __init__(self, n_folds: int = 5, purge_window: int = 0, embargo: int = 0):
        self.n_folds = n_folds
        self.purge_window = purge_window
        self.embargo = embargo

    def split(self, X: pd.DataFrame, y: pd.Series = None):
        n = len(X)
        fold_size = n // (self.n_folds + 1)
        for i in range(self.n_folds):
            train_end = (i + 1) * fold_size
            test_start = train_end + self.embargo
            test_end = min(test_start + fold_size, n) if i < self.n_folds - 1 else n

            train_indices = list(range(0, train_end - self.purge_window))
            test_indices = list(range(test_start, test_end))

            train_indices = [j for j in train_indices if j < test_start]
            test_indices = [j for j in test_indices if j < n and j not in train_indices]

            if len(train_indices) < 10 or len(test_indices) < 5:
                continue

            yield train_indices, test_indices


class PurgedCV:
    def __init__(self, n_folds: int = 5, purge_pct: float = 0.05, embargo_pct: float = 0.01):
        self.n_folds = n_folds
        self.purge_pct = purge_pct
        self.embargo_pct = embargo_pct

    def split(self, X: pd.DataFrame, y: pd.Series = None):
        n = len(X)
        purge_n = max(1, int(n * self.purge_pct))
        embargo_n = max(1, int(n * self.embargo_pct))
        cv = TimeSeriesCV(self.n_folds, purge_n, embargo_n)
        yield from cv.split(X, y)


def cross_validate_model(
    trainer,
    X: pd.DataFrame,
    y: pd.Series,
    cv: TimeSeriesCV,
) -> list[TrainMetrics]:
    results = []
    for fold, (train_idx, test_idx) in enumerate(cv.split(X, y)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        trainer.model = trainer._build_model(X_train.shape[1])
        trainer.model.fit(X_train, y_train)
        probs = trainer.model.predict_proba(X_test)
        preds = (probs >= 0.5).astype(int)

        metrics = compute_metrics(y_test, probs, preds)
        metrics.n_matches = len(y_test)
        results.append(metrics)

    return results
