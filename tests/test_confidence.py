"""Tests for confidence module."""

import pytest
from backend.domains.value.confidence import (
    sample_size_factor,
    model_confidence_factor,
    historical_accuracy_factor,
    edge_stability_factor,
    compute_confidence,
)


class TestSampleSizeFactor:
    def test_no_samples(self):
        assert sample_size_factor(0) == 0.05

    def test_at_inflection_point(self):
        assert sample_size_factor(50) == pytest.approx(0.5, rel=1e-1)

    def test_large_sample(self):
        assert sample_size_factor(200) > 0.95


class TestModelConfidenceFactor:
    def test_high_model_prob(self):
        assert model_confidence_factor(0.90) == 1.0

    def test_default_confidence(self):
        assert model_confidence_factor(0.5) == 1.0

    def test_low_model_prob(self):
        assert model_confidence_factor(0.1) == 0.2

    def test_with_brier_score(self):
        # Brier=0.10 → confidence = 0.90
        assert model_confidence_factor(0.80, brier_score=0.10) == pytest.approx(0.90, rel=1e-2)


class TestHistoricalAccuracyFactor:
    def test_no_bets_regresses_to_prior(self):
        assert historical_accuracy_factor(0.0, 0) == 0.5

    def test_high_accuracy_builds_confidence(self):
        assert historical_accuracy_factor(0.70, 100) > 0.65

    def test_small_sample_strongly_regressed(self):
        assert historical_accuracy_factor(0.90, 5) < 0.70


class TestEdgeStabilityFactor:
    def test_stable_edge(self):
        assert edge_stability_factor([0.15, 0.14, 0.16, 0.145, 0.155]) > 0.75

    def test_unstable_edge(self):
        assert edge_stability_factor([0.30, -0.10, 0.50, -0.20, 0.40]) < 0.5

    def test_insufficient_samples(self):
        assert edge_stability_factor([0.10, 0.20]) == 0.5


class TestComputeConfidence:
    def test_high_confidence_scenario(self):
        conf = compute_confidence(
            sample_size=200,
            model_prob=0.85,
            historical_accuracy=0.72,
            total_bets=150,
            edge_estimates=[0.12, 0.13, 0.11, 0.125, 0.135, 0.12, 0.11, 0.13],
        )
        assert conf > 0.70

    def test_low_confidence_scenario(self):
        conf = compute_confidence(
            sample_size=5,
            model_prob=0.51,
            historical_accuracy=0.48,
            total_bets=3,
            edge_estimates=[0.5, -0.3, 0.8, -0.5, 0.6],
        )
        assert conf < 0.50

    def test_no_data(self):
        conf = compute_confidence()
        # sample=0 gives low (but non-zero) prior; other factors contribute ~0.5-1.0
        assert 0.05 <= conf <= 0.6

    def test_custom_weights(self):
        weights = {"sample": 1.0, "model": 0.0, "historical": 0.0, "stability": 0.0}
        conf = compute_confidence(sample_size=200, weights=weights)
        assert conf > 0.80
