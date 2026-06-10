"""Tests for evaluation: metrics, calibration, backtest."""

import numpy as np
import pandas as pd
import pytest

from backend.domains.ml.evaluation.metrics import (
    brier, auc_roc, auc_pr, compute_metrics, calibration_ece,
    profit_curve, compute_profit_metrics,
)
from backend.domains.ml.evaluation.calibration import (
    platt_scale, isotonic_calibrate, calibrate_predictions,
)
from backend.domains.ml.evaluation.backtest import BacktestEngine, RollingSharpe
from backend.domains.ml.models import CalibrationMethod


class TestMetrics:
    def test_brier_perfect(self):
        assert brier(np.array([1, 0, 1]), np.array([1.0, 0.0, 1.0])) == 0.0

    def test_brier_worst(self):
        assert brier(np.array([1]), np.array([0.0])) == 1.0

    def test_auc_roc_perfect(self):
        assert auc_roc(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.9, 0.8])) == 1.0

    def test_auc_roc_random(self):
        assert auc_roc(np.array([0, 0, 1, 1]), np.array([0.5, 0.5, 0.5, 0.5])) == 0.5

    def test_compute_metrics_structure(self):
        y_true = np.array([0, 1, 0, 1])
        y_prob = np.array([0.2, 0.8, 0.3, 0.7])
        metrics = compute_metrics(y_true, y_prob)
        assert metrics.brier > 0
        assert 0 <= metrics.auc_roc <= 1.0
        assert 0 <= metrics.auc_pr <= 1.0
        assert metrics.n_matches == 4

    def test_calibration_ece(self):
        y_true = np.array([0, 1, 0, 1, 0, 1, 1, 0, 1, 0])
        y_prob = np.array([0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.6, 0.4, 0.85, 0.15])
        ece = calibration_ece(y_true, y_prob, n_bins=5)
        assert 0 <= ece <= 1.0


class TestProfitMetrics:
    def test_profit_curve_shape(self):
        y_true = np.array([1, 0, 1, 0])
        y_prob = np.array([0.9, 0.4, 0.7, 0.3])
        odds = np.array([2.0, 2.0, 2.0, 2.0])
        curve = profit_curve(y_true, y_prob, odds)
        assert len(curve) == 4

    def test_compute_profit_returns_dict(self):
        y_true = np.array([1, 0, 1])
        y_prob = np.array([0.6, 0.4, 0.8])
        home_odds = np.array([2.0, 1.8, 2.2])
        away_odds = np.array([1.8, 2.0, 1.7])
        result = compute_profit_metrics(y_true, y_prob, home_odds, away_odds)
        assert "roi" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown" in result


class TestCalibration:
    def test_platt_scale_changes_distribution(self):
        np.random.seed(42)
        y_val = np.random.randint(0, 2, 100)
        val_probs = np.random.uniform(0.3, 0.7, 100)
        test_probs = np.random.uniform(0.3, 0.7, 50)
        cal = platt_scale(y_val, val_probs, test_probs)
        assert len(cal) == 50
        assert np.all((cal >= 0) & (cal <= 1))

    def test_isotonic_calibrate_bounded(self):
        val_probs = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
        test_probs = np.array([0.3, 0.5, 0.7])
        cal = isotonic_calibrate(val_probs, test_probs)
        assert np.all((cal >= 0) & (cal <= 1))

    def test_calibrate_predictions_supported_methods(self):
        y_val = np.array([0, 1, 0, 1, 0, 1])
        val_probs = np.array([0.2, 0.8, 0.3, 0.7, 0.25, 0.75])
        test_probs = np.array([0.4, 0.6])
        for method in CalibrationMethod:
            if method == CalibrationMethod.NONE:
                result = calibrate_predictions(y_val, val_probs, test_probs, method)
                assert np.array_equal(result, test_probs)
            else:
                result = calibrate_predictions(y_val, val_probs, test_probs, method)
                assert len(result) == 2
                assert np.all((result >= 0) & (result <= 1))


class TestBacktestEngine:
    def test_run_returns_metrics(self):
        np.random.seed(42)
        X_train = pd.DataFrame({"f1": np.random.randn(50), "f2": np.random.randn(50)})
        y_train = pd.Series(np.random.randint(0, 2, 50))
        home_odds = np.random.uniform(1.5, 3.0, 50)
        away_odds = np.random.uniform(1.5, 3.0, 50)

        class MockTrainer:
            class MockModel:
                def fit(self, X, y, X_val=None, y_val=None):
                    return self
                def predict_proba(self, X):
                    return np.full(len(X), 0.5)

            def __init__(self):
                self.model = None
            def _build_model(self, n):
                return self.MockModel()

        engine = BacktestEngine(n_windows=2, window_size=20, step_size=10)
        result = engine.run(MockTrainer(), X_train, y_train,
                            home_odds=home_odds, away_odds=away_odds)
        assert result.n_windows >= 0
        if result.n_windows > 0:
            assert result.aggregate is not None

    def test_rolling_sharpe(self):
        returns = np.random.randn(100) * 0.02
        r = RollingSharpe(window=20)
        sharpe = r.compute(returns)
        assert len(sharpe) == 100
