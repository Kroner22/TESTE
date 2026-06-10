"""XGBoost model wrapper with early stopping and hyperopt support."""

from typing import Optional
import numpy as np
import pandas as pd

try:
    import xgboost as xgb
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False


class XGBoostModel:
    def __init__(
        self,
        n_features: int = 0,
        random_state: int = 42,
        early_stopping_rounds: int = 50,
        n_estimators: int = 1000,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        min_child_weight: int = 3,
        gamma: float = 0.1,
        reg_alpha: float = 0.1,
        reg_lambda: float = 1.0,
        scale_pos_weight: float = 1.0,
    ):
        if not _HAS_XGB:
            raise ImportError("xgboost is required")
        self.params = {
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "min_child_weight": min_child_weight,
            "gamma": gamma,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "scale_pos_weight": scale_pos_weight,
            "eval_metric": "logloss",
            "objective": "binary:logistic",
            "seed": random_state,
            "verbosity": 0,
        }
        self.n_estimators = n_estimators
        self.early_stopping_rounds = early_stopping_rounds
        self.model = None

    def fit(self, X, y, X_val=None, y_val=None):
        eval_set = [(X, y)]
        if X_val is not None and y_val is not None:
            eval_set.append((X_val, y_val))

        self.model = xgb.XGBClassifier(
            **self.params,
            n_estimators=self.n_estimators,
            early_stopping_rounds=self.early_stopping_rounds if X_val is not None else None,
            verbosity=0,
        )
        self.model.fit(
            X, y,
            eval_set=eval_set,
            verbose=False,
        )
        return self

    def predict_proba(self, X) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("model not fitted")
        probs = self.model.predict_proba(X)
        return probs[:, 1] if probs.ndim == 2 and probs.shape[1] == 2 else probs

    def get_feature_importance(self, feature_names: list[str] | None = None):
        if self.model is None:
            return {}
        importance = self.model.feature_importances_
        if feature_names and len(feature_names) == len(importance):
            return dict(zip(feature_names, importance))
        return {f"f{i}": v for i, v in enumerate(importance)}

    def hyperopt_objective(self, trial, X_train, y_train, X_val, y_val):
        param = {
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 7),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }
        model = xgb.XGBClassifier(**{**self.params, **param}, n_estimators=200, verbosity=0)
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        preds = model.predict_proba(X_val)[:, 1]
        from sklearn.metrics import log_loss
        return log_loss(y_val, preds)
