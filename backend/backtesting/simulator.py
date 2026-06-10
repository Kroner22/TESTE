from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from backend.app.log_config import get_logger
from .models import (
    HistoricalBet, BetResult, BacktestConfig, BacktestResult,
)
from .strategies import Strategy

logger = get_logger(__name__)


class BetSimulator:
    """
    Simulates historical betting given odds and actual outcomes.

    Takes a list of HistoricalBets (pre-settled with actual results),
    applies a strategy, and produces a BacktestResult with full
    equity curve.
    """

    def __init__(
        self,
        initial_bankroll: float = 1000.0,
        commission_rate: float = 0.0,
    ):
        self.initial_bankroll = Decimal(str(initial_bankroll))
        self.commission_rate = Decimal(str(commission_rate))

    def run(
        self,
        bets: list[HistoricalBet],
        config: BacktestConfig,
        sort_by_time: bool = True,
    ) -> BacktestResult:
        strategy = Strategy(config)
        result = BacktestResult(
            config=config,
            initial_bankroll=float(self.initial_bankroll),
            final_bankroll=float(self.initial_bankroll),
        )

        bankroll = self.initial_bankroll
        peak_bankroll = bankroll
        equity_curve: list[tuple[datetime, float]] = []
        cumulative_returns: list[float] = []
        running_bankroll: list[float] = []

        if sort_by_time:
            bets = sorted(bets, key=lambda b: b.placed_at)

        min_date = None
        max_date = None

        for bet in bets:
            if not bet.is_valid:
                continue

            if not strategy.should_accept(bet):
                continue

            stake = strategy.compute_stake(bet, bankroll)
            if stake <= Decimal("0"):
                continue

            stake = min(stake, bankroll * Decimal("0.95"))
            if stake <= Decimal("0"):
                continue

            commission = stake * self.commission_rate
            effective_stake = stake + commission

            if effective_stake > bankroll:
                continue

            bankroll -= effective_stake

            if bet.result == BetResult.WIN:
                payout = stake * bet.odd
                profit = payout - effective_stake
                result.winning_bets += 1
                result.gross_profit += profit
            else:
                payout = Decimal("0")
                profit = -effective_stake
                result.losing_bets += 1
                result.gross_loss += abs(effective_stake)

            bankroll += payout

            if bankroll > peak_bankroll:
                peak_bankroll = bankroll

            if min_date is None or bet.placed_at < min_date:
                min_date = bet.placed_at
            if max_date is None or bet.placed_at > max_date:
                max_date = bet.placed_at

            result.total_bets += 1
            result.total_staked += effective_stake
            result.total_profit += profit

            bet.stake = stake
            bet.profit = profit
            result.bets.append(bet)

            cumulative_returns.append(float(profit))
            running_bankroll.append(float(bankroll))
            equity_curve.append((bet.placed_at, float(bankroll)))

        result.start_date = min_date
        result.end_date = max_date
        result.final_bankroll = float(bankroll)
        result.cumulative_returns = cumulative_returns
        result.running_bankroll = running_bankroll
        result.equity_curve = equity_curve

        return result


def prepare_backtest_data(
    value_opportunities: list[dict],
    actual_outcomes: dict[str, str],
) -> list[HistoricalBet]:
    """
    Convert raw value opportunity data + actual outcomes into HistoricalBet list.

    Args:
        value_opportunities: List of dicts with keys:
            event_id, sport, market, bookmaker, outcome, odd, stake_x,
            predicted_ev, predicted_prob, implied_prob, confidence_score,
            risk_level, value_grade, kelly_fraction, detected_at
        actual_outcomes: {event_id: winning_outcome}

    Returns:
        List of HistoricalBet with results set.
    """
    bets = []
    bet_id = 0

    for opp in value_opportunities:
        event_id = opp.get("event_id", "")
        outcome = opp.get("outcome", "")

        actual_outcome = actual_outcomes.get(event_id, "")
        if not actual_outcome:
            continue

        won = outcome == actual_outcome
        odd = Decimal(str(opp.get("odd", 0)))
        stake = Decimal(str(opp.get("stake_x", opp.get("stake", 0))))

        if won:
            result = BetResult.WIN
            actual_return = odd
            profit = odd * stake - stake
        else:
            result = BetResult.LOSS
            actual_return = Decimal("0")
            profit = -stake

        bet_id += 1
        bet = HistoricalBet(
            bet_id=f"bt_{bet_id}",
            event_id=event_id,
            sport=opp.get("sport", ""),
            market=opp.get("market", "h2h"),
            bookmaker=opp.get("bookmaker", ""),
            outcome=outcome,
            odd=odd,
            stake=stake,
            result=result,
            actual_return=actual_return,
            profit=profit,
            predicted_ev=Decimal(str(opp.get("predicted_ev", 0))),
            predicted_prob=Decimal(str(opp.get("predicted_prob", opp.get("fair_prob", 0)))),
            implied_prob=Decimal(str(opp.get("implied_prob", 0))),
            confidence_score=float(opp.get("confidence_score", 0)),
            risk_level=opp.get("risk_level", "MEDIUM"),
            value_grade=opp.get("value_grade", "NOISE"),
            kelly_fraction=float(opp.get("kelly_fraction", 0)),
            event_date=opp.get("event_date", opp.get("detected_at", datetime.now(timezone.utc))),
            placed_at=opp.get("detected_at", datetime.now(timezone.utc)),
            settled_at=opp.get("settled_at", datetime.now(timezone.utc)),
        )
        bets.append(bet)

    return bets


def run_multiple_strategies(
    bets: list[HistoricalBet],
    configs: list[BacktestConfig],
    initial_bankroll: float = 1000.0,
) -> list[tuple[BacktestConfig, BacktestResult]]:
    """Run backtest for multiple strategy configurations."""
    simulator = BetSimulator(initial_bankroll=initial_bankroll)
    results = []
    for config in configs:
        result = simulator.run(bets, config)
        results.append((config, result))
    return results


def generate_synthetic_bets(
    n_bets: int = 1000,
    edge_pct: float = 3.0,
    seed: int = 42,
) -> list[HistoricalBet]:
    """Generate synthetic HistoricalBets for testing."""
    import random
    import math
    rng = random.Random(seed)

    bets = []
    sports = ["soccer", "basketball", "tennis", "american_football"]
    markets = ["h2h", "spread", "totals"]
    bookmakers = ["Bet365", "Pinnacle", "DraftKings", "FanDuel"]
    grades = ["ELITE", "STRONG", "SOLID", "SPECULATIVE", "NOISE"]
    risk_levels = ["LOW", "MEDIUM", "HIGH", "EXTREME"]
    outcomes_pool = ["home", "away", "draw"]
    base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    for i in range(n_bets):
        has_edge = rng.random() < 0.55  # 55% of bets have real edge
        actual_edge = edge_pct / 100.0 if has_edge else -edge_pct / 100.0
        noise = rng.gauss(0, 0.02)
        real_prob = 0.5 + actual_edge + noise
        real_prob = max(0.05, min(0.95, real_prob))

        outcome = rng.choice(outcomes_pool)
        odd = Decimal(str(round(1.0 / max(real_prob, 0.05), 2)))
        predicted_ev = Decimal(str(round((rng.gauss(edge_pct, 2.0)) if has_edge else rng.gauss(-1.0, 2.0), 2)))
        win = rng.random() < real_prob

        bets.append(HistoricalBet(
            bet_id=f"syn_{i}",
            event_id=f"evt_{i}",
            sport=rng.choice(sports),
            market=rng.choice(markets),
            bookmaker=rng.choice(bookmakers),
            outcome=outcome,
            odd=odd,
            stake=Decimal(str(round(rng.uniform(10, 100), 2))),
            result=BetResult.WIN if win else BetResult.LOSS,
            actual_return=odd if win else Decimal("0"),
            profit=(odd - Decimal("1")) * Decimal("100") if win else -Decimal("100"),
            predicted_ev=predicted_ev,
            predicted_prob=Decimal(str(round(real_prob, 4))),
            implied_prob=Decimal(str(round(1.0 / float(odd), 4))),
            confidence_score=round(rng.uniform(0.3, 0.95), 2),
            risk_level=rng.choice(risk_levels),
            value_grade=rng.choice(grades),
            kelly_fraction=round(rng.uniform(0.05, 0.5), 2),
            event_date=base_date,
            placed_at=base_date,
            settled_at=base_date,
        ))

    return bets
