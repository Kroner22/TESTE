"""Tests for model wrappers and ensemble."""

import numpy as np
import pandas as pd
import pytest

from backend.domains.ml.models.ensemble import (
    BlendingEnsemble, ThresholdOptimizer,
)
from backend.domains.ml.models import ModelType


class MockModel:
    def __init__(self, bias=0.5, noise=0.1):
        self.bias = bias
        self.noise = noise
        self._fitted = False

    def fit(self, X, y, X_val=None, y_val=None):
        self._fitted = True
        return self

    def predict_proba(self, X):
        n = len(X)
        return np.full(n, self.bias) + np.random.randn(n) * self.noise


class TestBlendingEnsemble:
    def test_uniform_weights(self):
        ensemble = BlendingEnsemble()
        ensemble.add_model("m1", MockModel(bias=0.6))
        ensemble.add_model("m2", MockModel(bias=0.7))

        X = pd.DataFrame({"f1": [1, 2, 3]})
        y = np.array([1, 0, 1])  # not used by mock
        ensemble.fit(X, y)

        probs = ensemble.predict_proba(X)
        assert len(probs) == 3
        assert np.all((probs >= 0) & (probs <= 1))

    def test_weighted_average(self):
        ensemble = BlendingEnsemble(weights={"m1": 2.0, "m2": 1.0})
        m1 = MockModel(bias=0.5, noise=0)
        m2 = MockModel(bias=0.8, noise=0)
        ensemble.add_model("m1", m1)
        ensemble.add_model("m2", m2)

        X_test = pd.DataFrame({"f1": [1.0]})
        y = np.array([1])
        ensemble.fit(X_test, y)

        probs = ensemble.predict_proba(X_test)
        expected = (2 * 0.5 + 1 * 0.8) / 3
        assert abs(probs[0] - expected) < 0.02

    def test_not_fitted_raises(self):
        ensemble = BlendingEnsemble()
        with pytest.raises(RuntimeError):
            ensemble.predict_proba(pd.DataFrame({"f1": [1]}))


class TestThresholdOptimizer:
    def test_optimize_profit_returns_threshold(self):
        np.random.seed(42)
        y_true = np.random.randint(0, 2, 100)
        y_prob = np.random.uniform(0.3, 0.7, 100)
        home_odds = np.random.uniform(1.5, 3.0, 100)
        away_odds = np.random.uniform(1.5, 3.0, 100)

        opt = ThresholdOptimizer(metric="profit")
        threshold = opt.optimize(y_true, y_prob, home_odds, away_odds)
        assert 0.05 <= threshold <= 0.95

    def test_optimize_f1(self):
        y_true = np.array([0, 0, 1, 1, 0, 1])
        y_prob = np.array([0.1, 0.2, 0.8, 0.7, 0.3, 0.9])
        opt = ThresholdOptimizer(metric="f1")
        threshold = opt.optimize(y_true, y_prob)
        assert 0.05 <= threshold <= 0.95
