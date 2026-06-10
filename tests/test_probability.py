"""Tests for probability module — overround removal methods."""

from decimal import Decimal
import pytest
from backend.domains.value.probability import (
    implied_probability,
    market_overround,
    compute_fair_probabilities,
    best_odds_across_bookmakers,
    decimal_from_implied,
)
from backend.domains.value.models import OverroundMethod


# ---- Implied probability ----

class TestImpliedProbability:
    def test_valid_odd(self):
        assert implied_probability(2.0) == 0.5

    def test_three_way(self):
        assert implied_probability(3.40) == pytest.approx(0.2941, rel=1e-3)

    def test_even_money(self):
        assert implied_probability(1.0) == 0.0

    def test_sub_unit_odd(self):
        assert implied_probability(0.5) == 0.0


# ---- Market overround ----

class TestMarketOverround:
    def test_typical_soccer_market(self):
        # Man Utd 2.10, Liverpool 3.40, Draw 3.25
        odds = [2.10, 3.40, 3.25]
        M = market_overround(odds)
        assert M == pytest.approx(0.0780, rel=1e-3)  # ~7.80%

    def test_juiced_basketball(self):
        odds = [1.91, 1.91]  # -110 each side
        M = market_overround(odds)
        assert M == pytest.approx(0.0471, rel=1e-3)  # ~4.71%

    def test_invalid_odds_return_zero(self):
        assert market_overround([1.0, 2.0]) == 0.0
        assert market_overround([]) == 0.0


# ---- Basic method ----

class TestBasicOverround:
    def test_two_outcome(self):
        odds = {"home": 1.91, "away": 1.91}
        result = compute_fair_probabilities(odds, OverroundMethod.BASIC)
        assert result.outcomes["home"] == pytest.approx(0.5, rel=1e-3)
        assert result.outcomes["away"] == pytest.approx(0.5, rel=1e-3)
        assert result.overround == pytest.approx(0.0471, rel=1e-3)

    def test_sums_to_one(self):
        odds = {"home": 2.10, "away": 3.40, "draw": 3.25}
        result = compute_fair_probabilities(odds, OverroundMethod.BASIC)
        assert sum(result.outcomes.values()) == pytest.approx(1.0, rel=1e-6)

    def test_invalid_odds_returns_zeros(self):
        result = compute_fair_probabilities({"home": 0.5, "away": 2.0})
        assert result.outcomes["home"] == 0.0
        assert result.outcomes["away"] == 0.0


# ---- Power method ----

class TestPowerOverround:
    def test_sums_to_one(self):
        odds = {"home": 2.10, "away": 3.40, "draw": 3.25}
        result = compute_fair_probabilities(odds, OverroundMethod.POWER)
        assert sum(result.outcomes.values()) == pytest.approx(1.0, rel=1e-6)

    def test_k_value_provided(self):
        odds = {"home": 2.10, "away": 3.40, "draw": 3.25}
        result = compute_fair_probabilities(odds, OverroundMethod.POWER, power_k=0.9)
        assert sum(result.outcomes.values()) == pytest.approx(1.0, rel=1e-6)

    def test_power_gives_different_results_than_basic(self):
        odds = {"a": 1.20, "b": 5.00}
        basic = compute_fair_probabilities(odds, OverroundMethod.BASIC)
        power = compute_fair_probabilities(odds, OverroundMethod.POWER)
        # Power inflates favorites vs basic (k > 1 makes extremes more extreme)
        assert power.outcomes["a"] > basic.outcomes["a"]


# ---- Shin method ----

class TestShinOverround:
    def test_sums_to_one(self):
        odds = {"home": 2.10, "away": 3.40, "draw": 3.25}
        result = compute_fair_probabilities(odds, OverroundMethod.SHIN)
        assert sum(result.outcomes.values()) == pytest.approx(1.0, rel=1e-4)

    def test_shin_adjusts_favorites(self):
        odds = {"a": 1.20, "b": 5.00}
        basic = compute_fair_probabilities(odds, OverroundMethod.BASIC)
        shin = compute_fair_probabilities(odds, OverroundMethod.SHIN)
        # Shin accounts for insider trading: penalizes longshots (potential insider targets)
        assert shin.outcomes["b"] < basic.outcomes["b"]
        assert shin.outcomes["a"] > basic.outcomes["a"]

    def test_shin_z_between_zero_and_one(self):
        odds = {"a": 1.5, "b": 3.0}
        result = compute_fair_probabilities(odds, OverroundMethod.SHIN)
        assert 0 <= sum(result.outcomes.values()) <= 1.0 + 1e-4


# ---- best_odds_across_bookmakers ----

class TestBestOdds:
    def test_picks_highest_per_outcome(self):
        books = {
            "pinny": {"home": 2.10, "away": 3.40},
            "bet365": {"home": 2.05, "away": 3.50},
        }
        best = best_odds_across_bookmakers(books)
        assert best == {"home": 2.10, "away": 3.50}

    def test_single_bookmaker(self):
        books = {"pinny": {"home": 1.91, "away": 1.91}}
        best = best_odds_across_bookmakers(books)
        assert best == {"home": 1.91, "away": 1.91}

    def test_empty(self):
        assert best_odds_across_bookmakers({}) == {}


# ---- decimal_from_implied ----

class TestDecimalFromImplied:
    def test_round_trip(self):
        assert decimal_from_implied(0.5) == 2.00

    def test_invalid(self):
        assert decimal_from_implied(0.0) == 0.0
        assert decimal_from_implied(1.0) == 0.0
