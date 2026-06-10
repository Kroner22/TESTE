"""Tests for ValueDetector — end-to-end orchestration."""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest
from backend.domains.value.detector import ValueDetector
from backend.domains.value.models import (
    MarketOdds, OverroundMethod, ValueGrade, RiskLevel,
)


@pytest.fixture
def sample_market():
    return MarketOdds(
        event_id="evt_001", sport="soccer",
        home_team="Manchester United", away_team="Liverpool",
        market="h2h",
        outcomes={"home": Decimal("2.10"), "away": Decimal("3.40"),
                  "draw": Decimal("3.25")},
    )


@pytest.fixture
def model_probs():
    """Model sees home at 50% → EV_home = 0.50*2.10-1 = +0.05"""
    return {"evt_001:home": 0.50, "evt_001:away": 0.28, "evt_001:draw": 0.22}


@pytest.fixture
def arb_market():
    """Negative-margin (arb) market → value from fair odds alone."""
    return MarketOdds(
        event_id="evt_002", sport="tennis",
        home_team="Player A", away_team="Player B",
        market="h2h",
        outcomes={"home": Decimal("2.50"), "away": Decimal("1.70")},
    )


class TestValueDetector:
    def test_scan_returns_value_opportunities(self, sample_market, model_probs):
        detector = ValueDetector()
        results = detector.scan([sample_market], model_probabilities=model_probs)
        assert len(results) > 0
        for o in results:
            assert o.event_id == "evt_001"
            assert o.sport == "soccer"
            assert 0 < o.confidence <= 1.0
            assert 0 <= o.risk_score <= 1.0
            assert o.grade in list(ValueGrade)
            assert o.risk_level in list(RiskLevel)

    def test_scan_sorted_by_ev_descending(self, sample_market, arb_market):
        detector = ValueDetector()
        # Edge data creates positive EV for both markets
        edge_hist = {
            "evt_001:home": [0.15, 0.14, 0.16],
            "evt_002:home": [0.10, 0.11, 0.12],
            "evt_002:away": [0.08, 0.07, 0.09],
        }
        results = detector.scan([sample_market, arb_market],
                                edge_history=edge_hist)
        for i in range(len(results) - 1):
            assert results[i].expected_value >= results[i + 1].expected_value

    def test_min_ev_filter(self, sample_market, model_probs):
        detector = ValueDetector(min_ev=100.0)
        results = detector.scan([sample_market], model_probabilities=model_probs)
        assert len(results) == 0

    def test_min_confidence_filter(self, sample_market, model_probs):
        detector = ValueDetector(min_confidence=0.99)
        results = detector.scan([sample_market], model_probabilities=model_probs)
        assert len(results) == 0

    def test_fair_prob_fallback_for_arb_market(self, arb_market):
        """Arbitrage (negative margin) markets produce value without model."""
        detector = ValueDetector()
        results = detector.scan([arb_market])
        assert len(results) > 0
        for o in results:
            assert o.expected_value > 0

    def test_with_model_probabilities(self, sample_market, model_probs):
        detector = ValueDetector()
        results = detector.scan([sample_market],
                                model_probabilities=model_probs)
        for o in results:
            if o.outcome == "home":
                assert o.model_probability == 0.50
                assert o.expected_value == pytest.approx(0.05, rel=1e-3)

    def test_with_edge_history(self, sample_market, model_probs):
        detector = ValueDetector()
        edge_history = {
            "evt_001:home": [0.15, 0.14, 0.16, 0.145, 0.155],
        }
        results = detector.scan([sample_market],
                                model_probabilities=model_probs,
                                edge_history=edge_history)
        for o in results:
            if o.outcome == "home":
                assert o.sample_size == 5
                assert o.confidence > 0.35

    def test_with_risk_factors(self, sample_market, model_probs):
        detector = ValueDetector()
        results = detector.scan(
            [sample_market],
            model_probabilities=model_probs,
            hours_to_event=1,
            regime="CHAOTIC",
            n_bookmakers=1,
        )
        assert all(o.risk_score > 0.3 for o in results)

    def test_different_overround_methods(self, arb_market):
        """Arb markets work with all overround methods."""
        basic = ValueDetector(overround_method=OverroundMethod.BASIC)
        shin = ValueDetector(overround_method=OverroundMethod.SHIN)
        power = ValueDetector(overround_method=OverroundMethod.POWER)

        assert len(basic.scan([arb_market])) > 0
        assert len(shin.scan([arb_market])) > 0
        assert len(power.scan([arb_market])) > 0

    def test_empty_market_returns_empty(self):
        detector = ValueDetector()
        empty = MarketOdds(
            event_id="empty", sport="soccer", home_team="", away_team="",
            market="h2h", outcomes={},
        )
        assert detector.scan([empty]) == []

    def test_kelly_stake_in_results(self, sample_market, model_probs):
        detector = ValueDetector(kelly_fraction=0.5)
        results = detector.scan([sample_market],
                                model_probabilities=model_probs)
        for o in results:
            assert o.kelly_stake >= 0.0
            assert o.kelly_stake <= 0.25

    def test_expiry_set_correctly(self, sample_market, model_probs):
        detector = ValueDetector()
        now = datetime.now(timezone.utc)
        results = detector.scan([sample_market],
                                model_probabilities=model_probs,
                                hours_to_event=2)
        for o in results:
            expected = now + timedelta(hours=2)
            assert abs((o.expires_at - expected).total_seconds()) < 5

    def test_default_expiry_six_hours(self, sample_market, model_probs):
        detector = ValueDetector()
        now = datetime.now(timezone.utc)
        results = detector.scan([sample_market],
                                model_probabilities=model_probs)
        for o in results:
            expected = now + timedelta(hours=6)
            assert abs((o.expires_at - expected).total_seconds()) < 5
