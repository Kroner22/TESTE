"""Scikit-learn ensemble wrappers: RF, GradientBoosting, LogisticRegression."""

from typing import Optional
import numpy as np

try:
    from sklearn.ensemble import (
        RandomForestClassifier,
        GradientBoostingClassifier,
    )
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

from backend.domains.ml.models import ModelType


class SklearnModel:
    def __init__(
        self,
        model_type: ModelType = ModelType.LOGISTIC,
        random_state: int = 42,
        calibrate: bool = True,
    ):
        if not _HAS_SKLEARN:
            raise ImportError("scikit-learn is required")
        self.model_type = model_type
        self.random_state = random_state
        self.calibrate = calibrate
        self.model = None

    def _build_estimator(self):
        if self.model_type == ModelType.RANDOM_FOREST:
            return RandomForestClassifier(
                n_estimators=500, max_depth=12, min_samples_leaf=10,
                class_weight="balanced_subsample",
                random_state=self.random_state, n_jobs=-1,
            )
        elif self.model_type == ModelType.GRADIENT_BOOSTING:
            return GradientBoostingClassifier(
                n_estimators=300, max_depth=5, learning_rate=0.05,
                min_samples_leaf=20, subsample=0.8,
                random_state=self.random_state,
            )
        return LogisticRegression(
            C=1.0, penalty="l2", solver="lbfgs",
            max_iter=1000, class_weight="balanced",
            random_state=self.random_state,
        )

    def fit(self, X, y, X_val=None, y_val=None):
        base = self._build_estimator()
        if self.calibrate and X_val is not None and y_val is not None:
            base.fit(X, y)
            self.model = CalibratedClassifierCV(base, cv="prefit", method="sigmoid")
            self.model.fit(X_val, y_val)
        else:
            self.model = base.fit(X, y)
        return self

    def predict_proba(self, X) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("model not fitted")
        probs = self.model.predict_proba(X)
        return probs[:, 1] if probs.ndim == 2 and probs.shape[1] == 2 else probs

    def get_feature_importance(self, feature_names: list[str] | None = None):
        if self.model is None:
            return {}
        if hasattr(self.model, "feature_importances_"):
            imp = self.model.feature_importances_
            if feature_names and len(feature_names) == len(imp):
                return dict(zip(feature_names, imp))
            return {f"f{i}": v for i, v in enumerate(imp)}
        if hasattr(self.model, "coef_"):
            coef = self.model.coef_[0]
            if feature_names and len(feature_names) == len(coef):
                return dict(zip(feature_names, np.abs(coef)))
            return {f"f{i}": v for i, v in enumerate(np.abs(coef))}
        return {}
