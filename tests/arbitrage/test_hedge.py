import pytest
from decimal import Decimal

from backend.domains.arbitrage.models import HedgePosition
from backend.domains.arbitrage.hedge import (
    hedge_stake, locked_profit, locked_profit_pct,
    cash_out_value, partial_hedge, evaluate_hedge,
)


class TestHedgeStake:
    def test_basic(self):
        hs = hedge_stake(
            original_stake=Decimal("100"),
            original_odd=Decimal("2.5"),
            hedge_odd=Decimal("1.6"),
        )
        assert hs == Decimal("156.25")

    def test_zero_original_odd(self):
        assert hedge_stake(Decimal("100"), Decimal("0"), Decimal("2")) == Decimal("0")

    def test_hedge_odd_below_one(self):
        assert hedge_stake(Decimal("100"), Decimal("2"), Decimal("0.5")) == Decimal("0")


class TestLockedProfit:
    def test_even_hedge(self):
        hs = hedge_stake(Decimal("100"), Decimal("2.5"), Decimal("1.6"))
        profit = locked_profit(Decimal("100"), Decimal("2.5"), hs, Decimal("1.6"))
        assert profit == Decimal("-6.25")

    def test_with_commission(self):
        profit = locked_profit(Decimal("100"), Decimal("2.5"), Decimal("150"), Decimal("1.6"), hedge_commission=Decimal("0.02"))
        profit_no_comm = locked_profit(Decimal("100"), Decimal("2.5"), Decimal("150"), Decimal("1.6"))
        assert profit < profit_no_comm


class TestLockedProfitPct:
    def test_basic(self):
        pct = locked_profit_pct(
            Decimal("100"), Decimal("2.5"), Decimal("1.6"),
        )
        assert pct == Decimal("-2.44")

    def test_no_profit(self):
        pct = locked_profit_pct(Decimal("100"), Decimal("1.5"), Decimal("1.8"))
        assert pct < Decimal("0")


class TestCashOutValue:
    def test_odds_moved_against(self):
        value = cash_out_value(Decimal("100"), Decimal("2.0"), Decimal("3.0"))
        assert value == Decimal("66.67")

    def test_odds_moved_favorably(self):
        value = cash_out_value(Decimal("100"), Decimal("3.0"), Decimal("1.5"))
        assert value == Decimal("200.00")

    def test_with_commission(self):
        value = cash_out_value(Decimal("100"), Decimal("2.0"), Decimal("3.0"), Decimal("0.05"))
        assert value < Decimal("66.67")

    def test_invalid_odd(self):
        assert cash_out_value(Decimal("100"), Decimal("2.0"), Decimal("0")) == Decimal("0")


class TestPartialHedge:
    def test_basic(self):
        hs, profit = partial_hedge(
            original_stake=Decimal("100"),
            original_odd=Decimal("2.0"),
            hedge_odd=Decimal("2.2"),
            desired_profit_pct=Decimal("5"),
        )
        assert hs > Decimal("0")
        assert profit > Decimal("0")

    def test_zero_desired(self):
        hs, profit = partial_hedge(
            original_stake=Decimal("100"),
            original_odd=Decimal("2.0"),
            hedge_odd=Decimal("2.2"),
            desired_profit_pct=Decimal("0"),
        )
        assert hs > Decimal("0")
        assert profit == Decimal("0.00")


class TestEvaluateHedge:
    def test_basic(self):
        position = HedgePosition(
            event_id="evt1", original_outcome="home",
            original_odd=Decimal("2.0"), original_stake=Decimal("100"),
            current_hedge_odd=Decimal("2.2"), hedge_bookmaker="Bookmaker B",
        )
        result = evaluate_hedge(position)
        assert result.hedge_stake > Decimal("0")
        assert result.is_locked is True

    def test_no_hedge_possible(self):
        position = HedgePosition(
            event_id="evt1", original_outcome="home",
            original_odd=Decimal("1.1"), original_stake=Decimal("100"),
            current_hedge_odd=Decimal("1.05"), hedge_bookmaker="Bookmaker B",
        )
        result = evaluate_hedge(position)
        assert result.is_locked is False
