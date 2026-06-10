"""Tests for monitoring: drift, performance tracking."""

import numpy as np
import pandas as pd
import pytest

from backend.domains.ml.monitoring.drift import (
    population_stability_index, kolmogorov_smirnov, feature_drift_score,
    DriftDetector, classify_drift_severity,
)
from backend.domains.ml.monitoring.performance import PerformanceTracker, AlertManager
from backend.domains.ml.models import DriftSeverity


class TestPopulationStabilityIndex:
    def test_identical_distributions(self):
        x = np.random.randn(1000)
        psi = population_stability_index(x, x)
        assert psi == pytest.approx(0.0, abs=0.1)

    def test_different_distributions(self):
        x = np.random.randn(1000)
        y = np.random.randn(1000) + 2.0
        psi = population_stability_index(x, y)
        assert psi > 0.2


class TestKS:
    def test_identical(self):
        x = np.random.randn(100)
        stat, p = kolmogorov_smirnov(x, x)
        assert p > 0.05

    def test_different(self):
        x = np.random.randn(100)
        y = np.random.randn(100) + 5.0
        stat, p = kolmogorov_smirnov(x, y)
        assert stat > 0.3


class TestFeatureDriftScore:
    def test_known_shift(self):
        ref = np.random.randn(100)
        cur = np.random.randn(100) + 3.0
        score = feature_drift_score(ref, cur)
        assert 0 <= score <= 1.0

    def test_insufficient_data(self):
        assert feature_drift_score(np.array([1, 2]), np.array([3, 4])) >= 0
        assert feature_drift_score(np.array([]), np.array([])) == 0.0


class TestClassifyDrift:
    def test_no_drift(self):
        sev = classify_drift_severity(0.05, 0.05, 0, 10)
        assert sev == DriftSeverity.NONE

    def test_moderate_drift(self):
        sev = classify_drift_severity(0.3, 0.3, 3, 10)
        assert sev == DriftSeverity.MODERATE

    def test_severe_drift(self):
        sev = classify_drift_severity(0.6, 0.5, 5, 10)
        assert sev == DriftSeverity.SEVERE


class TestDriftDetector:
    def test_no_reference_returns_no_drift(self):
        dd = DriftDetector()
        report = dd.detect(pd.DataFrame({"f1": [1, 2, 3]}))
        assert report.severity == DriftSeverity.NONE

    def test_detects_drift_with_reference(self):
        dd = DriftDetector(psi_threshold=0.1, ks_threshold=0.1)
        ref_X = pd.DataFrame({"f1": np.random.randn(200)})
        dd.set_reference(ref_X, np.random.rand(200))

        cur_X = pd.DataFrame({"f1": np.random.randn(200) + 3.0})
        report = dd.detect(cur_X, np.random.rand(200) + 0.3)
        assert report.severity in (DriftSeverity.LOW, DriftSeverity.MODERATE,
                                   DriftSeverity.SEVERE)

    def test_psi_method(self):
        dd = DriftDetector()
        dd.set_reference(None, np.random.rand(100))
        psi = dd.psi(np.random.rand(50))
        assert psi >= 0


class TestPerformanceTracker:
    def test_log_prediction(self):
        pt = PerformanceTracker(window=10)
        pt.log_prediction(1.0, 0.85)
        pt.log_prediction(0.0, 0.30)
        assert len(pt.metrics_history) == 2

    def test_current_metrics(self):
        pt = PerformanceTracker(window=10)
        for i in range(10):
            pt.log_prediction(1.0 if i % 2 == 0 else 0.0,
                              0.8 if i % 2 == 0 else 0.2)
        metrics = pt.current_metrics()
        assert metrics.brier < 0.1

    def test_alert_on_bad_performance(self):
        pt = PerformanceTracker(window=5, alert_threshold_brier=0.1)
        for i in range(5):
            pt.log_prediction(float(i % 2), 0.0)
        assert len(pt.alerts) > 0

    def test_summary(self):
        pt = PerformanceTracker(window=5)
        for i in range(5):
            pt.log_prediction(float(i % 2), 0.5)
        summary = pt.summary()
        assert "n_predictions" in summary
        assert "n_alerts" in summary


class TestAlertManager:
    def test_throttling(self):
        am = AlertManager(min_alert_interval=3600)
        assert am.should_alert("test")
        assert not am.should_alert("test")  # throttled

    def test_reset(self):
        am = AlertManager()
        am.should_alert("test")
        am.reset("test")
        assert am.should_alert("test")
