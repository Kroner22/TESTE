import pytest
from decimal import Decimal

from backend.domains.arbitrage.models import (
    BookmakerOdds, ArbType, ArbGrade, ArbFilter,
)
from backend.domains.arbitrage.core import (
    implied_probability, total_implied, eff_odd,
    arb_profit_pct, has_arb,
    best_odds_across_bookmakers, grade_arbitrage,
    detect_2way_arb, detect_3way_arb,
    distribute_equal_profit, scan_for_arbitrage,
)


class TestImpliedProbability:
    def test_valid_odd(self):
        assert implied_probability(Decimal("2")) == Decimal("0.5")

    def test_decimal_odd(self):
        assert implied_probability(Decimal("3.33")) == Decimal("1") / Decimal("3.33")

    def test_odd_of_one(self):
        assert implied_probability(Decimal("1")) == Decimal("0")

    def test_odd_below_one(self):
        assert implied_probability(Decimal("0.5")) == Decimal("0")


class TestTotalImplied:
    def test_sum_below_one(self):
        t = total_implied([Decimal("2"), Decimal("2.5")])
        assert t == Decimal("1") / Decimal("2") + Decimal("1") / Decimal("2.5")

    def test_sum_above_one(self):
        t = total_implied([Decimal("1.5"), Decimal("1.8")])
        assert t > Decimal("1")

    def test_empty(self):
        assert total_implied([]) == Decimal("0")


class TestEffOdd:
    def test_no_commission(self):
        assert eff_odd(Decimal("2"), Decimal("0")) == Decimal("2")

    def test_with_commission(self):
        assert eff_odd(Decimal("2"), Decimal("0.05")) == Decimal("2") / Decimal("1.05")


class TestArbProfitPct:
    def test_no_arb(self):
        pct = arb_profit_pct([Decimal("1.5"), Decimal("1.8")])
        assert pct < Decimal("0")

    def test_2way_arb(self):
        odds = [Decimal("2.1"), Decimal("2.2")]
        pct = arb_profit_pct(odds)
        assert pct > Decimal("0")

    def test_3way_arb(self):
        odds = [Decimal("3.5"), Decimal("3.8"), Decimal("4.0")]
        pct = arb_profit_pct(odds)
        assert pct > Decimal("0")

    def test_with_commissions(self):
        odds = [Decimal("2.15"), Decimal("2.25")]
        pct = arb_profit_pct(odds, [Decimal("0.02"), Decimal("0.02")])
        assert pct < arb_profit_pct(odds)


class TestHasArb:
    def test_arb_exists(self):
        assert has_arb([Decimal("2.1"), Decimal("2.2")]) is True

    def test_no_arb(self):
        assert has_arb([Decimal("1.5"), Decimal("1.8")]) is False

    def test_marginal_arb(self):
        assert has_arb([Decimal("2.0"), Decimal("2.02")]) is True


class TestBestOddsAcrossBookmakers:
    def test_picks_best(self):
        odds_by_outcome = {
            "home": [
                BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("1.8")),
                BookmakerOdds(bookmaker="B", outcome="home", odd=Decimal("1.9")),
            ],
            "away": [
                BookmakerOdds(bookmaker="A", outcome="away", odd=Decimal("2.1")),
                BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.0")),
            ],
        }
        best = best_odds_across_bookmakers(odds_by_outcome)
        assert best["home"].bookmaker == "B"
        assert best["home"].odd == Decimal("1.9")
        assert best["away"].bookmaker == "A"
        assert best["away"].odd == Decimal("2.1")

    def test_with_commission(self):
        odds_by_outcome = {
            "home": [
                BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.0"), commission=Decimal("0")),
                BookmakerOdds(bookmaker="B", outcome="home", odd=Decimal("2.1"), commission=Decimal("0.10")),
            ],
            "away": [
                BookmakerOdds(bookmaker="A", outcome="away", odd=Decimal("2.2"), commission=Decimal("0")),
                BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.3"), commission=Decimal("0.05")),
            ],
        }
        best = best_odds_across_bookmakers(odds_by_outcome)
        assert best["home"].bookmaker == "A"

    def test_empty_outcome(self):
        assert best_odds_across_bookmakers({}) == {}


class TestGradeArbitrage:
    def test_elite(self):         assert grade_arbitrage(Decimal("0.07")) == ArbGrade.ELITE
    def test_strong(self):        assert grade_arbitrage(Decimal("0.04")) == ArbGrade.STRONG
    def test_solid(self):         assert grade_arbitrage(Decimal("0.02")) == ArbGrade.SOLID
    def test_marginal(self):      assert grade_arbitrage(Decimal("0.008")) == ArbGrade.MARGINAL
    def test_noise(self):         assert grade_arbitrage(Decimal("0.003")) == ArbGrade.NOISE

    def test_boundaries(self):
        assert grade_arbitrage(Decimal("0.05")) == ArbGrade.ELITE
        assert grade_arbitrage(Decimal("0.03")) == ArbGrade.STRONG
        assert grade_arbitrage(Decimal("0.015")) == ArbGrade.SOLID
        assert grade_arbitrage(Decimal("0.005")) == ArbGrade.MARGINAL


class TestDistributeEqualProfit:
    def test_two_outcomes(self):
        stakes = distribute_equal_profit(
            [Decimal("2.0"), Decimal("3.0")],
            total_stake=Decimal("100"),
        )
        assert len(stakes) == 2
        assert sum(stakes) == Decimal("100")
        ret0 = stakes[0] * Decimal("2.0")
        ret1 = stakes[1] * Decimal("3.0")
        assert abs(ret0 - ret1) <= Decimal("0.01")

    def test_with_commissions(self):
        stakes = distribute_equal_profit(
            [Decimal("2.0"), Decimal("3.0")],
            commissions=[Decimal("0.02"), Decimal("0.01")],
            total_stake=Decimal("100"),
        )
        assert sum(stakes) == Decimal("100")

    def test_single_outcome(self):
        stakes = distribute_equal_profit([Decimal("2.0")])
        assert stakes == [Decimal("100.00")]


class TestDetect2WayArb:
    def test_detects_arb(self):
        odds_by_outcome = {
            "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.1"))],
            "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.2"))],
        }
        arb = detect_2way_arb(
            event_id="evt1", sport="tennis",
            home_team="Player A", away_team="Player B",
            market="h2h", odds_by_outcome=odds_by_outcome,
        )
        assert arb is not None
        assert arb.arb_type == ArbType.TWO_WAY
        assert arb.profit_pct > Decimal("0")
        assert len(arb.legs) == 2

    def test_no_arb(self):
        odds_by_outcome = {
            "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("1.3"))],
            "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("3.5"))],
        }
        arb = detect_2way_arb("evt1", "tennis", "A", "B", "h2h", odds_by_outcome)
        assert arb is None

    def test_filtered_by_min_profit(self):
        odds_by_outcome = {
            "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.01"))],
            "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.02"))],
        }
        filter_config = ArbFilter(min_profit_pct=Decimal("0.05"))
        arb = detect_2way_arb(
            "evt1", "tennis", "A", "B", "h2h",
            odds_by_outcome, filter_config=filter_config,
        )
        assert arb is None

    def test_custom_stake(self):
        odds_by_outcome = {
            "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.1"))],
            "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.2"))],
        }
        arb = detect_2way_arb(
            "evt1", "tennis", "A", "B", "h2h",
            odds_by_outcome, total_stake=Decimal("500"),
        )
        assert arb is not None
        assert arb.total_stake == Decimal("500")

    def test_single_outcome_returns_none(self):
        odds_by_outcome = {
            "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.1"))],
        }
        arb = detect_2way_arb("evt1", "tennis", "A", "B", "h2h", odds_by_outcome)
        assert arb is None

    def test_actionable_flag(self):
        odds_by_outcome = {
            "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.1"), max_stake=Decimal("10"))],
            "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.2"), max_stake=Decimal("1000"))],
        }
        arb = detect_2way_arb(
            "evt1", "tennis", "A", "B", "h2h",
            odds_by_outcome, total_stake=Decimal("500"),
        )
        assert arb is not None
        assert arb.is_actionable is False


class TestDetect3WayArb:
    def test_detects_arb(self):
        odds_by_outcome = {
            "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("3.5"))],
            "draw": [BookmakerOdds(bookmaker="B", outcome="draw", odd=Decimal("3.8"))],
            "away": [BookmakerOdds(bookmaker="C", outcome="away", odd=Decimal("4.0"))],
        }
        arb = detect_3way_arb(
            event_id="evt1", sport="soccer",
            home_team="Team A", away_team="Team B",
            market="1x2", odds_by_outcome=odds_by_outcome,
        )
        assert arb is not None
        assert arb.arb_type == ArbType.THREE_WAY
        assert len(arb.legs) == 3
        assert arb.profit_pct > Decimal("0")

    def test_two_outcomes_fallsback_to_2way(self):
        odds_by_outcome = {
            "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.1"))],
            "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.2"))],
        }
        arb = detect_3way_arb("evt1", "soccer", "A", "B", "1x2", odds_by_outcome)
        assert arb is not None
        assert arb.arb_type == ArbType.TWO_WAY


class TestScanForArbitrage:
    def test_scan_multiple_markets(self):
        markets = {
            "evt1:tennis:PlayerA:PlayerB:h2h": {
                "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.1"))],
                "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.2"))],
            },
            "evt2:tennis:PlayerC:PlayerD:h2h": {
                "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("1.3"))],
                "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("3.5"))],
            },
        }
        results = scan_for_arbitrage(markets)
        assert len(results) == 1
        assert results[0].event_id == "evt1"

    def test_empty_markets(self):
        assert scan_for_arbitrage({}) == []

    def test_scan_with_filter(self):
        markets = {
            "evt1:tennis:A:B:h2h": {
                "home": [BookmakerOdds(bookmaker="A", outcome="home", odd=Decimal("2.01"))],
                "away": [BookmakerOdds(bookmaker="B", outcome="away", odd=Decimal("2.02"))],
            },
        }
        filter_config = ArbFilter(min_profit_pct=Decimal("0.05"))
        results = scan_for_arbitrage(markets, filter_config=filter_config)
        assert len(results) == 0
