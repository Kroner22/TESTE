"""Tests for Kelly Criterion module."""

import pytest
from backend.domains.value.kelly import (
    full_kelly,
    half_kelly,
    quarter_kelly,
    fractional_kelly,
    compute_kelly,
    expected_growth,
)


class TestFullKelly:
    def test_typical_value_bet(self):
        # P=0.55, odd=2.10 → f* = (0.55*2.10 - 1) / (2.10 - 1) = 0.141
        f = full_kelly(0.55, 2.10)
        assert f == pytest.approx(0.141, rel=1e-2)

    def test_no_edge_returns_zero(self):
        assert full_kelly(0.50, 2.00) == 0.0

    def test_negative_edge_returns_zero(self):
        assert full_kelly(0.40, 2.00) == 0.0

    def test_pure_arbitrage(self):
        # P=0.60, odd=2.00 → EV=0.20 → f = 0.20 / 1.0 = 0.20
        f = full_kelly(0.60, 2.00)
        assert f == pytest.approx(0.20, rel=1e-2)

    def test_invalid_inputs(self):
        assert full_kelly(0.0, 2.0) == 0.0
        assert full_kelly(1.0, 2.0) == 0.0
        assert full_kelly(0.5, 1.0) == 0.0


class TestFractionalKelly:
    def test_half_kelly(self):
        f = half_kelly(0.55, 2.10)
        full = full_kelly(0.55, 2.10)
        assert f == pytest.approx(full * 0.5, rel=1e-4)

    def test_quarter_kelly(self):
        f = quarter_kelly(0.55, 2.10)
        full = full_kelly(0.55, 2.10)
        assert f == pytest.approx(full * 0.25, rel=1e-4)

    def test_custom_fraction(self):
        f = fractional_kelly(0.55, 2.10, 0.333)
        full = full_kelly(0.55, 2.10)
        assert f == pytest.approx(full * 0.333, rel=1e-4)


class TestExpectedGrowth:
    def test_positive_growth(self):
        # P=0.55, odd=2.10, f=0.10 → positive growth rate
        g = expected_growth(0.55, 2.10, 0.10)
        assert g > 0

    def test_zero_stake_zero_growth(self):
        assert expected_growth(0.55, 2.10, 0.0) == 0.0

    def test_overbet_negative_growth(self):
        # Betting too aggressively can reduce growth
        g = expected_growth(0.55, 2.10, 0.50)
        assert g < expected_growth(0.55, 2.10, 0.141)


class TestComputeKelly:
    def test_full_result_structure(self):
        result = compute_kelly(0.55, 2.10)
        assert result.full_kelly == pytest.approx(0.141, rel=1e-2)
        assert result.half_kelly == pytest.approx(0.0705, rel=1e-2)
        assert result.quarter_kelly == pytest.approx(0.0352, rel=1e-2)
        assert result.is_viable is True

    def test_non_viable_when_no_edge(self):
        result = compute_kelly(0.50, 2.00)
        assert result.is_viable is False
        assert result.recommended_stake == 0.0

    def test_bankroll_clamp(self):
        # Very high edge would suggest > 25% — clamp
        result = compute_kelly(0.80, 1.50, bankroll_pct_limit=0.25)
        assert result.recommended_stake <= 0.25

    def test_below_min_stake_not_viable(self):
        result = compute_kelly(0.51, 2.00, min_stake_pct=0.10)
        assert result.is_viable is False

    def test_custom_kelly_fraction(self):
        result = compute_kelly(0.55, 2.10, kelly_fraction=0.25)
        assert result.fractional_kelly == pytest.approx(result.full_kelly * 0.25, abs=5e-4)
