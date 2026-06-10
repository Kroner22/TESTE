"""Online inference pipeline: feature → model → calibration → output."""

from typing import Optional
import numpy as np
import pandas as pd

from backend.domains.ml.models import (
    PredictionResult, ModelType, CalibrationMethod,
)
from backend.domains.ml.pipeline.feature_pipeline import FeaturePipeline
from backend.domains.ml.models.xgboost_model import XGBoostModel
from backend.domains.ml.models.lightgbm_model import LightGBMModel
from backend.domains.ml.models.sklearn_ensemble import SklearnModel
from backend.domains.ml.models.ensemble import BlendingEnsemble, StackingEnsemble
from backend.domains.ml.evaluation.calibration import calibrate_predictions


class MatchPredictor:
    def __init__(
        self,
        feature_pipeline: Optional[FeaturePipeline] = None,
        model=None,
        scaler=None,
        calibration_method: CalibrationMethod = CalibrationMethod.PLATT,
    ):
        self.feature_pipeline = feature_pipeline
        self.model = model
        self.scaler = scaler
        self.calibration_method = calibration_method
        self.model_version: Optional[str] = None
        self.calibration_data: Optional[dict] = None

    def predict(self, match_data: pd.DataFrame) -> list[PredictionResult]:
        if self.model is None:
            raise RuntimeError("no model loaded")

        if self.feature_pipeline is not None:
            features = self.feature_pipeline.transform(match_data)
        else:
            features = match_data

        if self.scaler is not None:
            numeric_cols = features.select_dtypes(include=[np.number]).columns
            features[numeric_cols] = self.scaler.transform(features[numeric_cols])

        probs = self.model.predict_proba(features)

        results = []
        for i in range(len(match_data)):
            row = match_data.iloc[i] if len(match_data) > 0 else match_data
            home_prob = float(probs[i]) if probs.ndim == 1 else float(probs[i])

            home_odd = row.get("home_odd", np.nan)
            away_odd = row.get("away_odd", np.nan)
            draw_odd = row.get("draw_odd", np.nan)

            implied_h = 1.0 / home_odd if home_odd > 1 else None
            implied_a = 1.0 / away_odd if away_odd > 1 else None
            implied_d = 1.0 / draw_odd if draw_odd > 1 else None

            away_prob = 1.0 - home_prob
            draw_prob = 0.0

            ev = None
            if home_odd > 1 and home_prob > 0:
                ev = home_prob * home_odd - 1.0

            results.append(PredictionResult(
                match_id=str(row.get("match_id", f"match_{i}")),
                home_win_prob=round(home_prob, 4),
                away_win_prob=round(away_prob, 4),
                draw_prob=round(draw_prob, 4) if draw_prob else None,
                implied_home=round(implied_h, 4) if implied_h else None,
                implied_away=round(implied_a, 4) if implied_a else None,
                implied_draw=round(implied_d, 4) if implied_d else None,
                expected_value=round(ev, 4) if ev is not None else None,
                model_confidence=self._compute_confidence(probs[i]),
                model_version=self.model_version,
                features_used=features.shape[1] if features is not None else 0,
            ))

        return results

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("no model loaded")
        return self.model.predict_proba(X)

    def explain(self, match_data: pd.DataFrame, feature_names: Optional[list[str]] = None):
        try:
            import shap
            if self.feature_pipeline is not None:
                features = self.feature_pipeline.transform(match_data)
            else:
                features = match_data

            explainer = shap.TreeExplainer(self.model.model) if hasattr(self.model, "model") else None
            if explainer is None:
                return {"error": "SHAP not supported for this model type"}

            shap_values = explainer.shap_values(features)
            names = feature_names or features.columns.tolist()
            return {
                "shap_values": shap_values.tolist() if hasattr(shap_values, "tolist") else shap_values,
                "feature_names": names,
                "base_value": float(explainer.expected_value),
            }
        except ImportError:
            return {"error": "shap not installed"}
        except Exception as e:
            return {"error": str(e)}

    def _compute_confidence(self, prob: float) -> float:
        return 2.0 * abs(prob - 0.5)

    def set_calibration(self, y_val, val_probs):
        self.calibration_data = {"y_val": y_val, "val_probs": val_probs}

    def calibrate(self, test_probs: np.ndarray) -> np.ndarray:
        if self.calibration_data is None:
            return test_probs
        return calibrate_predictions(
            self.calibration_data["y_val"],
            self.calibration_data["val_probs"],
            test_probs,
            self.calibration_method,
        )


class ModelLoader:
    @staticmethod
    def from_artifacts(path: str):
        import json
        import os

        metadata_path = os.path.join(path, "model_metadata.json")
        if not os.path.exists(metadata_path):
            raise FileNotFoundError(f"metadata not found at {metadata_path}")

        with open(metadata_path) as f:
            meta = json.load(f)

        model_type = ModelType(meta["model_type"])
        n_features = meta["n_features"]

        if model_type == ModelType.XGBOOST:
            model = XGBoostModel(n_features=n_features)
        elif model_type == ModelType.LIGHTGBM:
            model = LightGBMModel(n_features=n_features)
        else:
            model = SklearnModel(model_type=model_type)

        return model
