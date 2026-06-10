"""Tests for risk module."""

import pytest
from backend.domains.value.risk import (
    edge_volatility_risk,
    time_pressure_risk,
    regime_risk,
    market_depth_risk,
    compute_risk_score,
    classify_risk,
)
from backend.domains.value.models import RiskLevel


class TestEdgeVolatilityRisk:
    def test_stable_edge_low_risk(self):
        risk = edge_volatility_risk([0.12, 0.11, 0.13, 0.12, 0.115])
        assert risk < 0.30

    def test_unstable_edge_high_risk(self):
        risk = edge_volatility_risk([0.50, -0.20, 0.80, -0.40, 0.60])
        assert risk > 0.60

    def test_unknown_cv_returns_default(self):
        assert edge_volatility_risk() == 0.5


class TestTimePressureRisk:
    def test_one_day_out(self):
        risk = time_pressure_risk(24)
        assert risk == pytest.approx(0.5, rel=1e-2)

    def test_in_play(self):
        assert time_pressure_risk(0) == 1.0

    def test_one_week_out(self):
        risk = time_pressure_risk(168)
        assert risk < 0.15

    def test_unknown_returns_default(self):
        assert time_pressure_risk() == 0.5


class TestRegimeRisk:
    def test_stable(self):
        assert regime_risk("STABLE") == 0.1

    def test_chaotic(self):
        assert regime_risk("CHAOTIC") == 0.8

    def test_unknown(self):
        assert regime_risk() == 0.5


class TestMarketDepthRisk:
    def test_single_bookmaker(self):
        risk = market_depth_risk(1)
        assert risk == pytest.approx(0.8333, rel=1e-2)

    def test_many_bookmakers(self):
        assert market_depth_risk(20) <= 0.20

    def test_no_bookmakers(self):
        assert market_depth_risk(0) == 1.0


class TestClassifyRisk:
    def test_low(self):
        assert classify_risk(0.10) == RiskLevel.LOW

    def test_medium(self):
        assert classify_risk(0.35) == RiskLevel.MEDIUM

    def test_high(self):
        assert classify_risk(0.60) == RiskLevel.HIGH

    def test_extreme(self):
        assert classify_risk(0.85) == RiskLevel.EXTREME


class TestComputeRiskScore:
    def test_low_risk_scenario(self):
        score, level = compute_risk_score(
            edge_estimates=[0.12, 0.11, 0.13, 0.12],
            hours_to_event=120,
            regime="STABLE",
            n_bookmakers=10,
        )
        assert level == RiskLevel.LOW
        assert score < 0.25

    def test_high_risk_scenario(self):
        score, level = compute_risk_score(
            edge_estimates=[0.5, -0.3, 0.8, -0.5],
            hours_to_event=1,
            regime="CHAOTIC",
            n_bookmakers=1,
        )
        assert level in (RiskLevel.HIGH, RiskLevel.EXTREME)
        assert score > 0.50

    def test_bounded_between_zero_and_one(self):
        for _ in range(10):
            score, _ = compute_risk_score()
            assert 0.0 <= score <= 1.0

    def test_custom_weights(self):
        w = {"volatility": 1.0, "time": 0.0, "regime": 0.0, "depth": 0.0}
        score, level = compute_risk_score(
            edge_estimates=[0.12, 0.11, 0.13], weights=w
        )
        assert 0.0 <= score <= 1.0
