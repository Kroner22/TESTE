"""Trainer orchestrator — trains models with CV, hyperopt, and artifact saving."""

import os
import json
from typing import Optional
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from backend.domains.ml.models import (
    TrainConfig, TrainMetrics, ModelType, TargetType, CalibrationMethod,
)
from backend.domains.ml.models.xgboost_model import XGBoostModel
from backend.domains.ml.models.lightgbm_model import LightGBMModel
from backend.domains.ml.models.sklearn_ensemble import SklearnModel
from backend.domains.ml.models.ensemble import EnsembleModel
from backend.domains.ml.pipeline.validator import TimeSeriesCV, cross_validate_model
from backend.domains.ml.evaluation.metrics import compute_metrics, compute_profit_metrics
from backend.domains.ml.evaluation.calibration import calibrate_predictions
from backend.domains.ml.pipeline.feature_pipeline import FeaturePipeline


class ModelTrainer:
    def __init__(self, config: TrainConfig):
        self.config = config
        self.model = None
        self.scaler = StandardScaler()
        self.feature_pipeline = None

    def _build_model(self, n_features: int):
        if self.config.model_type == ModelType.XGBOOST:
            return XGBoostModel(
                n_features=n_features,
                random_state=self.config.random_state,
            )
        elif self.config.model_type == ModelType.LIGHTGBM:
            return LightGBMModel(
                n_features=n_features,
                random_state=self.config.random_state,
            )
        elif self.config.model_type in (ModelType.RANDOM_FOREST,
                                         ModelType.GRADIENT_BOOSTING,
                                         ModelType.LOGISTIC):
            return SklearnModel(
                model_type=self.config.model_type,
                random_state=self.config.random_state,
            )
        return XGBoostModel(n_features=n_features, random_state=self.config.random_state)

    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        feature_pipeline: Optional[FeaturePipeline] = None,
    ) -> tuple[TrainMetrics, object]:
        self.feature_pipeline = feature_pipeline

        split_idx = int(len(X) * (1 - self.config.test_size))
        X_train = X.iloc[:split_idx]
        X_test = X.iloc[split_idx:]
        y_train = y.iloc[:split_idx]
        y_test = y.iloc[split_idx:]

        val_idx = int(len(X_train) * (1 - self.config.validation_size))
        X_train_final = X_train.iloc[:val_idx]
        X_val = X_train.iloc[val_idx:]
        y_train_final = y_train.iloc[:val_idx]
        y_val = y_train.iloc[val_idx:]

        self.model = self._build_model(X_train.shape[1])

        numeric_cols = X_train.select_dtypes(include=[np.number]).columns
        self.scaler.fit(X_train_final[numeric_cols])
        X_train_scaled = X_train_final.copy()
        X_train_scaled[numeric_cols] = self.scaler.transform(X_train_final[numeric_cols])
        X_val_scaled = X_val.copy()
        X_val_scaled[numeric_cols] = self.scaler.transform(X_val[numeric_cols])
        X_test_scaled = X_test.copy()
        X_test_scaled[numeric_cols] = self.scaler.transform(X_test[numeric_cols])

        self.model.fit(X_train_scaled, y_train_final, X_val_scaled, y_val)

        val_probs = self.model.predict_proba(X_val_scaled)
        test_probs = self.model.predict_proba(X_test_scaled)
        test_preds = (test_probs >= 0.5).astype(int)

        if self.config.calibrate:
            cal_method = self.config.calibration_method
            test_probs = calibrate_predictions(y_val, val_probs, test_probs, cal_method)

        metrics = compute_metrics(y_test, test_probs, test_preds)

        if "home_odd" in X_test.columns and "away_odd" in X_test.columns:
            profit = compute_profit_metrics(
                y_test.values, test_probs,
                home_odds=X_test["home_odd"].values if "home_odd" in X_test else None,
                away_odds=X_test["away_odd"].values if "away_odd" in X_test else None,
            )
            metrics.sharpe_ratio = profit.get("sharpe_ratio")
            metrics.max_drawdown = profit.get("max_drawdown")
            metrics.roi = profit.get("roi")

        metrics.n_matches = len(y_test)

        if self.config.save_artifacts and self.config.artifact_path:
            self._save_artifacts(X_train_scaled.columns.tolist())

        return metrics, self.model

    def train_with_cv(self, X, y) -> tuple[list[TrainMetrics], object]:
        cv = TimeSeriesCV(n_folds=self.config.n_folds)
        results = cross_validate_model(self, X, y, cv)
        self.model = self._build_model(X.shape[1])
        self.model.fit(X, y)
        return results, self.model

    def _save_artifacts(self, feature_names: list[str]):
        path = self.config.artifact_path
        if not path:
            return
        os.makedirs(path, exist_ok=True)
        meta = {
            "model_type": self.config.model_type.value,
            "target_type": self.config.target_type.value,
            "n_features": len(feature_names),
            "feature_names": feature_names,
            "train_config": {k: str(v) for k, v in self.config.__dict__.items()},
        }
        with open(os.path.join(path, "model_metadata.json"), "w") as f:
            json.dump(meta, f, indent=2, default=str)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("model not trained")
        numeric_cols = X.select_dtypes(include=[np.number]).columns
        X_scaled = X.copy()
        X_scaled[numeric_cols] = self.scaler.transform(X[numeric_cols])
        return self.model.predict_proba(X_scaled)
