import pytest
from decimal import Decimal

from backend.domains.arbitrage.models import StakeMethod
from backend.domains.arbitrage.stake import (
    distribute_stakes, required_stake_for_return, max_profit_given_limits,
)


class TestDistributeStakes:
    def test_equal_profit_two_outcomes(self):
        stakes = distribute_stakes(
            [Decimal("2.0"), Decimal("3.0")],
            method=StakeMethod.EQUAL_PROFIT,
            total_stake=Decimal("100"),
        )
        assert len(stakes) == 2
        assert sum(stakes) == Decimal("100")
        ret0 = stakes[0] * Decimal("2.0")
        ret1 = stakes[1] * Decimal("3.0")
        assert abs(ret0 - ret1) <= Decimal("0.01")

    def test_equal_profit_three_outcomes(self):
        stakes = distribute_stakes(
            [Decimal("3.0"), Decimal("4.0"), Decimal("5.0")],
            total_stake=Decimal("100"),
        )
        assert len(stakes) == 3
        assert abs(sum(stakes) - Decimal("100")) <= Decimal("0.01")

    def test_weighted_same_as_equal(self):
        eq = distribute_stakes([Decimal("2.0"), Decimal("3.0")], method=StakeMethod.EQUAL_PROFIT)
        w = distribute_stakes([Decimal("2.0"), Decimal("3.0")], method=StakeMethod.WEIGHTED)
        assert eq == w

    def test_risk_parity_same_as_equal(self):
        eq = distribute_stakes([Decimal("2.0"), Decimal("3.0")], method=StakeMethod.EQUAL_PROFIT)
        rp = distribute_stakes([Decimal("2.0"), Decimal("3.0")], method=StakeMethod.RISK_PARITY)
        assert eq == rp

    def test_with_commissions(self):
        stakes = distribute_stakes(
            [Decimal("2.0"), Decimal("3.0")],
            total_stake=Decimal("100"),
            commissions=[Decimal("0.02"), Decimal("0.01")],
        )
        assert sum(stakes) == Decimal("100")

    def test_with_max_stakes_no_cap(self):
        stakes = distribute_stakes(
            [Decimal("2.0"), Decimal("3.0")],
            total_stake=Decimal("100"),
            max_stakes=[Decimal("1000"), Decimal("1000")],
        )
        assert abs(sum(stakes) - Decimal("100")) <= Decimal("0.01")

    def test_with_max_stakes_capped(self):
        stakes = distribute_stakes(
            [Decimal("2.0"), Decimal("3.0")],
            total_stake=Decimal("100"),
            max_stakes=[Decimal("10"), None],
        )
        assert stakes[0] <= Decimal("10")
        assert abs(sum(stakes) - Decimal("100")) <= Decimal("0.01")

    def test_single_outcome(self):
        stakes = distribute_stakes([Decimal("2.0")], total_stake=Decimal("100"))
        assert stakes == [Decimal("100.00")]

    def test_zero_odds(self):
        stakes = distribute_stakes([Decimal("0")], total_stake=Decimal("100"))
        assert all(s == Decimal("0") for s in stakes)


class TestRequiredStakeForReturn:
    def test_basic(self):
        stake = required_stake_for_return(Decimal("200"), Decimal("2.0"))
        assert stake == Decimal("100.00")

    def test_with_commission(self):
        stake = required_stake_for_return(Decimal("200"), Decimal("2.0"), Decimal("0.05"))
        assert stake > Decimal("100.00")

    def test_odd_below_one(self):
        assert required_stake_for_return(Decimal("100"), Decimal("0.5")) == Decimal("0")


class TestMaxProfitGivenLimits:
    def test_no_arb(self):
        profit, stakes = max_profit_given_limits([Decimal("1.5"), Decimal("1.8")], [None, None])
        assert profit == Decimal("0")

    def test_arb_with_limits(self):
        profit, stakes = max_profit_given_limits(
            [Decimal("2.1"), Decimal("2.2")], [Decimal("100"), Decimal("100")],
        )
        assert profit >= Decimal("0")
        assert len(stakes) == 2

    def test_arb_no_limits(self):
        profit, stakes = max_profit_given_limits([Decimal("2.1"), Decimal("2.2")], [None, None])
        assert profit >= Decimal("0")
