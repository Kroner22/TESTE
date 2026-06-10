"""Tests for EV module — expected value and confidence intervals."""

import pytest
from backend.domains.value.ev import (
    compute_expected_value,
    ev_confidence_interval,
    is_statistically_significant,
    classify_value_grade,
    edge_pct,
)
from backend.domains.value.models import ValueGrade


class TestComputeExpectedValue:
    def test_positive_ev(self):
        # P=0.55, odd=2.10 → EV = 0.55*2.10 - 1 = 0.155
        ev = compute_expected_value(0.55, 2.10)
        assert ev == pytest.approx(0.155, rel=1e-3)

    def test_negative_ev(self):
        ev = compute_expected_value(0.45, 2.00)
        assert ev == pytest.approx(-0.10, rel=1e-3)

    def test_breakeven(self):
        ev = compute_expected_value(0.50, 2.00)
        assert ev == pytest.approx(0.0, abs=1e-10)

    def test_invalid_input_returns_zero(self):
        assert compute_expected_value(0.0, 2.0) == 0.0
        assert compute_expected_value(0.5, 1.0) == 0.0
        assert compute_expected_value(0.5, 0.5) == 0.0


class TestEVConfidenceInterval:
    def test_ci_contains_ev(self):
        lo, hi = ev_confidence_interval(0.155, 0.55, 2.10, sample_size=100)
        assert lo <= 0.155 <= hi

    def test_larger_sample_narrows_ci(self):
        lo_small, hi_small = ev_confidence_interval(0.10, 0.55, 2.00, 50)
        lo_large, hi_large = ev_confidence_interval(0.10, 0.55, 2.00, 1000)
        assert (hi_large - lo_large) < (hi_small - lo_small)

    def test_degenerate(self):
        lo, hi = ev_confidence_interval(0.0, 0.5, 2.0, 0)
        assert lo == 0.0
        assert hi == 0.0


class TestStatisticalSignificance:
    def test_strong_edge_is_significant(self):
        # EV=0.155, P=0.55, odd=2.10, n=500
        sig = is_statistically_significant(0.155, 0.55, 2.10, 500)
        assert sig is True

    def test_small_edge_not_significant(self):
        sig = is_statistically_significant(0.02, 0.51, 2.00, 30)
        assert sig is False

    def test_different_alphas(self):
        sig_90 = is_statistically_significant(0.08, 0.54, 2.00, 100, alpha=0.10)
        sig_99 = is_statistically_significant(0.08, 0.54, 2.00, 100, alpha=0.01)
        # Smaller alpha (stricter) should be harder to pass
        assert sig_90 or not sig_99  # at least 90% should pass if 1% doesn't


class TestClassifyValueGrade:
    def test_elite(self):
        assert classify_value_grade(0.12, 0.95, True) == ValueGrade.ELITE

    def test_strong(self):
        assert classify_value_grade(0.07, 0.85, False) == ValueGrade.STRONG

    def test_solid(self):
        assert classify_value_grade(0.04, 0.72, True) == ValueGrade.SOLID

    def test_speculative(self):
        assert classify_value_grade(0.02, 0.50, False) == ValueGrade.SPECULATIVE

    def test_noise(self):
        assert classify_value_grade(0.005, 0.20, False) == ValueGrade.NOISE


class TestEdgePct:
    def test_conversion(self):
        assert edge_pct(0.155) == 15.5
        assert edge_pct(-0.05) == -5.0
        assert edge_pct(0.0) == 0.0
