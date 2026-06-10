"""Data drift and concept drift detection for production monitoring."""

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, chi2_contingency
from typing import Optional

from backend.domains.ml.models import DriftReport, DriftSeverity


def population_stability_index(expected: np.ndarray, actual: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    expected_binned = np.histogram(expected, bins=bins)[0] + 1e-10
    actual_binned = np.histogram(actual, bins=bins)[0] + 1e-10

    expected_pct = expected_binned / expected_binned.sum()
    actual_pct = actual_binned / actual_binned.sum()

    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return float(psi)


def kolmogorov_smirnov(expected: np.ndarray, actual: np.ndarray) -> tuple[float, float]:
    stat, p_value = ks_2samp(expected, actual)
    return float(stat), float(p_value)


def feature_drift_score(reference: np.ndarray, current: np.ndarray) -> float:
    if reference.ndim > 1:
        reference = reference.ravel()
    if current.ndim > 1:
        current = current.ravel()
    if len(reference) < 10 or len(current) < 10:
        return 0.0
    stat, _ = ks_2samp(reference, current)
    return float(stat)


def classify_drift_severity(psi: float, ks_stat: float, n_drifted: int, n_total: int) -> DriftSeverity:
    if psi < 0.1 and ks_stat < 0.1 and n_drifted / max(n_total, 1) < 0.1:
        return DriftSeverity.NONE
    if psi < 0.25 and ks_stat < 0.2 and n_drifted / max(n_total, 1) < 0.2:
        return DriftSeverity.LOW
    if psi < 0.5 and ks_stat < 0.4 and n_drifted / max(n_total, 1) < 0.4:
        return DriftSeverity.MODERATE
    return DriftSeverity.SEVERE


class DriftDetector:
    def __init__(self, psi_threshold: float = 0.25, ks_threshold: float = 0.2,
                 drift_feature_pct: float = 0.3):
        self.psi_threshold = psi_threshold
        self.ks_threshold = ks_threshold
        self.drift_feature_pct = drift_feature_pct
        self.reference_data: Optional[pd.DataFrame] = None
        self.reference_predictions: Optional[np.ndarray] = None

    def set_reference(self, X: pd.DataFrame, y_prob: Optional[np.ndarray] = None):
        self.reference_data = X
        self.reference_predictions = y_prob

    def detect(self, X_current: pd.DataFrame,
               y_prob_current: Optional[np.ndarray] = None) -> DriftReport:
        report = DriftReport()

        if self.reference_data is None:
            report.severity = DriftSeverity.NONE
            return report

        if y_prob_current is not None and self.reference_predictions is not None:
            report.psi = population_stability_index(
                self.reference_predictions, y_prob_current
            )
            report.ks_statistic, report.ks_p_value = kolmogorov_smirnov(
                self.reference_predictions, y_prob_current
            )

        common_cols = [c for c in self.reference_data.columns if c in X_current.columns]
        drift_scores = {}
        for col in common_cols:
            if self.reference_data[col].dtype.kind in ("i", "f"):
                ref = self.reference_data[col].values
                cur = X_current[col].values
                score = feature_drift_score(ref, cur)
                drift_scores[col] = score

        report.feature_drift_scores = drift_scores
        report.drifted_features = [
            k for k, v in drift_scores.items()
            if v > self.ks_threshold
        ]

        report.severity = classify_drift_severity(
            report.psi, report.ks_statistic,
            len(report.drifted_features), len(drift_scores),
        )

        if y_prob_current is not None and self.reference_predictions is not None:
            report.model_confidence_drop = max(
                0, self.reference_predictions.mean() - y_prob_current.mean()
            )

        if report.severity in (DriftSeverity.MODERATE, DriftSeverity.SEVERE):
            report.recommendation = "retrain model recommended"
        elif report.severity == DriftSeverity.LOW:
            report.recommendation = "monitor closely"
        else:
            report.recommendation = "no action needed"

        return report

    def psi(self, current_probs: np.ndarray) -> float:
        if self.reference_predictions is None:
            return 0.0
        return population_stability_index(self.reference_predictions, current_probs)

    def has_drifted(self, current_probs: np.ndarray,
                    X_current: pd.DataFrame) -> bool:
        report = self.detect(X_current, current_probs)
        return report.severity in (DriftSeverity.MODERATE, DriftSeverity.SEVERE)
