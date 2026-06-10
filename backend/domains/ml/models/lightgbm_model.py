"""LightGBM model wrapper with early stopping and categorical feature support."""

from typing import Optional
import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False


class LightGBMModel:
    def __init__(
        self,
        n_features: int = 0,
        random_state: int = 42,
        early_stopping_rounds: int = 50,
        n_estimators: int = 1000,
        max_depth: int = -1,
        num_leaves: int = 31,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        min_child_samples: int = 20,
        reg_alpha: float = 0.0,
        reg_lambda: float = 0.0,
        class_weight: str = "balanced",
    ):
        if not _HAS_LGB:
            raise ImportError("lightgbm is required")
        self.params = {
            "max_depth": max_depth,
            "num_leaves": num_leaves,
            "learning_rate": learning_rate,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "min_child_samples": min_child_samples,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "class_weight": class_weight,
            "objective": "binary",
            "metric": "binary_logloss",
            "boosting_type": "gbdt",
            "seed": random_state,
            "verbosity": -1,
        }
        self.n_estimators = n_estimators
        self.early_stopping_rounds = early_stopping_rounds
        self.model = None
        self._feature_names = None

    def fit(self, X, y, X_val=None, y_val=None, categorical_feature: list[str] | None = None):
        self._feature_names = X.columns.tolist() if hasattr(X, "columns") else None
        cat_feat = categorical_feature or "auto"

        train_data = lgb.Dataset(X, label=y, categorical_feature=cat_feat)
        valid_sets = [train_data]
        valid_names = ["train"]

        if X_val is not None and y_val is not None:
            val_data = lgb.Dataset(X_val, label=y_val,
                                    categorical_feature=cat_feat,
                                    reference=train_data)
            valid_sets.append(val_data)
            valid_names.append("validation")

        self.model = lgb.train(
            self.params,
            train_data,
            num_boost_round=self.n_estimators,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=[
                lgb.early_stopping(self.early_stopping_rounds),
                lgb.log_evaluation(0),
            ],
        )
        return self

    def predict_proba(self, X) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("model not fitted")
        return self.model.predict(X, num_iteration=self.model.best_iteration)

    def get_feature_importance(self, feature_names: list[str] | None = None):
        if self.model is None:
            return {}
        names = feature_names or self._feature_names
        importance = self.model.feature_importance(importance_type="gain")
        if names and len(names) == len(importance):
            return dict(zip(names, importance))
        return {f"f{i}": v for i, v in enumerate(importance)}

    def hyperopt_objective(self, trial, X_train, y_train, X_val, y_val):
        param = {
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "max_depth": trial.suggest_int("max_depth", 3, 15),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }
        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        model = lgb.train(
            {**self.params, **param}, train_data,
            num_boost_round=200,
            valid_sets=[val_data],
            callbacks=[lgb.early_stopping(20), lgb.log_evaluation(0)],
        )
        preds = model.predict(X_val)
        from sklearn.metrics import log_loss
        return log_loss(y_val, preds)
