"""Ensemble methods: stacking, blending, BMA, threshold optimization."""

from typing import Optional, Callable
import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import LogisticRegression
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

from backend.domains.ml.models import EnsembleConfig, CalibrationMethod
from backend.domains.ml.evaluation.calibration import calibrate_predictions


class StackingEnsemble:
    def __init__(self, config: Optional[EnsembleConfig] = None):
        self.config = config or EnsembleConfig()
        self.base_models: list[tuple[str, object]] = []
        self.meta_model = None
        self._fitted = False

    def add_model(self, name: str, model):
        self.base_models.append((name, model))

    def fit(self, X_train, y_train, X_val, y_val):
        val_preds = []
        for name, model in self.base_models:
            model.fit(X_train, y_train, X_val, y_val)
            p = model.predict_proba(X_val)
            val_preds.append(p)
        meta_X = np.column_stack(val_preds)

        if self.config.meta_learner == "logistic":
            self.meta_model = LogisticRegression(C=1.0, penalty="l2", solver="lbfgs", max_iter=1000)
        else:
            self.meta_model = LogisticRegression(C=1.0, penalty="l2", solver="lbfgs", max_iter=1000)
        self.meta_model.fit(meta_X, y_val)
        self._fitted = True
        return self

    def predict_proba(self, X) -> np.ndarray:
        if not self._fitted or self.meta_model is None:
            raise RuntimeError("ensemble not fitted")
        base_preds = []
        for name, model in self.base_models:
            p = model.predict_proba(X)
            base_preds.append(p)
        meta_X = np.column_stack(base_preds)
        return self.meta_model.predict_proba(meta_X)[:, 1]


class BlendingEnsemble:
    def __init__(self, weights: Optional[dict[str, float]] = None):
        self.weights = weights or {}
        self.models: dict[str, object] = {}
        self._fitted = False

    def add_model(self, name: str, model, weight: float = 1.0):
        self.models[name] = model
        if name not in self.weights:
            self.weights[name] = weight

    def fit(self, X_train, y_train, X_val=None, y_val=None):
        for name, model in self.models.items():
            model.fit(X_train, y_train, X_val, y_val)
        self._fitted = True
        return self

    def predict_proba(self, X) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("ensemble not fitted")
        total = np.zeros(len(X))
        weight_sum = sum(self.weights.values())
        for name, model in self.models.items():
            w = self.weights.get(name, 1.0) / weight_sum
            total += w * model.predict_proba(X)
        return total

    def optimize_weights(self, X_val, y_val, metric: Callable = None):
        from scipy.optimize import minimize

        if metric is None:
            from sklearn.metrics import log_loss
            metric = lambda y, p: log_loss(y, p)

        n = len(self.models)
        names = list(self.models.keys())
        preds = [self.models[n].predict_proba(X_val) for n in names]

        def objective(w):
            w = np.abs(w) / np.sum(np.abs(w))
            blended = sum(w[i] * preds[i] for i in range(n))
            return metric(y_val, blended)

        result = minimize(objective, np.ones(n) / n, method="Nelder-Mead",
                          options={"maxiter": 1000, "xatol": 1e-8})
        opt_weights = np.abs(result.x) / np.sum(np.abs(result.x))
        for i, name in enumerate(names):
            self.weights[name] = opt_weights[i]
        return self.weights


class ThresholdOptimizer:
    def __init__(self, metric: str = "profit"):
        self.metric = metric
        self.best_threshold = 0.5

    def optimize(self, y_true, y_prob, home_odds=None, away_odds=None) -> float:
        thresholds = np.arange(0.05, 0.95, 0.01)
        best_score = -np.inf

        for t in thresholds:
            preds = (y_prob >= t).astype(int)
            if self.metric == "profit" and home_odds is not None and away_odds is not None:
                correct = preds == y_true
                payout = np.where(correct, np.where(preds == 1, home_odds, away_odds), 0)
                score = payout.sum() / len(y_true) - 1.0
            elif self.metric == "f1":
                from sklearn.metrics import f1_score
                score = f1_score(y_true, preds, zero_division=0)
            elif self.metric == "precision":
                from sklearn.metrics import precision_score
                score = precision_score(y_true, preds, zero_division=0)
            else:
                from sklearn.metrics import accuracy_score
                score = accuracy_score(y_true, preds)

            if score > best_score:
                best_score = score
                self.best_threshold = t

        return self.best_threshold
