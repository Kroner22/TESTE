from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.backtesting.simulator import (
    BetSimulator, prepare_backtest_data, generate_synthetic_bets,
)
from backend.backtesting.metrics import (
    compute_metrics, _compute_drawdown, _compute_sharpe,
)
from backend.backtesting.validator import validate_backtest
from backend.backtesting.analyzer import BacktestAnalyzer
from backend.backtesting.report import generate_report
from backend.backtesting.models import (
    HistoricalBet, BetResult, BacktestConfig, BacktestResult,
    PerformanceMetrics, ValidationResult,
)


# ─── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def sample_bets(now) -> list[HistoricalBet]:
    return [
        HistoricalBet(
            bet_id=f"b{i}", event_id=f"e{i}", sport="soccer",
            market="h2h", bookmaker="Bet365", outcome="home",
            odd=Decimal("2.0"), stake=Decimal("100"),
            result=BetResult.WIN, actual_return=Decimal("2.0"),
            profit=Decimal("100"), predicted_ev=Decimal("5.0"),
            predicted_prob=Decimal("0.55"), implied_prob=Decimal("0.50"),
            confidence_score=0.8, risk_level="MEDIUM", value_grade="STRONG",
            kelly_fraction=0.25, event_date=now, placed_at=now,
        )
        for i in range(20)
    ] + [
        HistoricalBet(
            bet_id=f"b{i}", event_id=f"e{i}", sport="basketball",
            market="h2h", bookmaker="Pinnacle", outcome="away",
            odd=Decimal("3.0"), stake=Decimal("50"),
            result=BetResult.LOSS, actual_return=Decimal("0"),
            profit=Decimal("-50"), predicted_ev=Decimal("-2.0"),
            predicted_prob=Decimal("0.30"), implied_prob=Decimal("0.33"),
            confidence_score=0.3, risk_level="HIGH", value_grade="NOISE",
            kelly_fraction=0.05, event_date=now, placed_at=now,
        )
        for i in range(20, 40)
    ]


@pytest.fixture
def config() -> BacktestConfig:
    return BacktestConfig(
        min_ev=-999,
        min_confidence=0.0,
        max_risk_level="EXTREME",
        min_value_grade="NOISE",
        use_grade_filter=False,
        use_risk_filter=False,
        use_confidence_filter=False,
    )


@pytest.fixture
def result(sample_bets, config) -> BacktestResult:
    sim = BetSimulator(initial_bankroll=1000.0)
    return sim.run(sample_bets, config)


# ─── Models ──────────────────────────────────────────────────────

class TestModels:
    def test_historical_bet_defaults(self, now):
        bet = HistoricalBet(
            bet_id="b1", event_id="e1", sport="soccer",
            market="h2h", bookmaker="Bet365", outcome="home",
            odd=Decimal("2.0"), stake=Decimal("100"), profit=Decimal("0"),
            event_date=now, placed_at=now,
            result=BetResult.PENDING, actual_return=Decimal("0"),
            predicted_ev=Decimal("0"), predicted_prob=Decimal("0.5"),
            implied_prob=Decimal("0.5"), confidence_score=0.0,
            risk_level="LOW", value_grade="NOISE", kelly_fraction=0.0,
        )
        assert bet.result == BetResult.PENDING
        assert bet.actual_return == Decimal("0")
        assert bet.predicted_ev == Decimal("0")

    def _make_minimal_bet(self, now, **kw):
        defaults = dict(
            bet_id="b1", event_id="e1", sport="soccer",
            market="h2h", bookmaker="Bet365", outcome="home",
            odd=Decimal("2.0"), stake=Decimal("100"),
            result=BetResult.WIN, actual_return=Decimal("0"),
            profit=Decimal("100"), predicted_ev=Decimal("0"),
            predicted_prob=Decimal("0.5"), implied_prob=Decimal("0.5"),
            confidence_score=0.0, risk_level="LOW", value_grade="NOISE",
            kelly_fraction=0.0, event_date=now, placed_at=now,
        )
        defaults.update(kw)
        return HistoricalBet(**defaults)

    def test_bet_is_winner(self, now):
        bet = self._make_minimal_bet(now, result=BetResult.WIN)
        assert bet.is_winner

    def test_bet_is_not_winner_on_loss(self, now):
        bet = self._make_minimal_bet(now, result=BetResult.LOSS, profit=Decimal("-100"))
        assert not bet.is_winner

    def test_bet_is_valid(self, now):
        bet = self._make_minimal_bet(now, result=BetResult.WIN)
        assert bet.is_valid

    def test_bet_invalid_pending(self, now):
        bet = self._make_minimal_bet(now, result=BetResult.PENDING, profit=Decimal("0"))
        assert not bet.is_valid

    def test_bet_roi(self, now):
        bet = self._make_minimal_bet(now, result=BetResult.WIN,
                                     actual_return=Decimal("2.0"))
        assert bet.roi == 100.0

    def test_backtest_config_label(self):
        c = BacktestConfig(min_ev=0.0)
        assert "ev_threshold" in c.label

    def test_backtest_result_defaults(self):
        r = BacktestResult(config=BacktestConfig())
        assert r.total_bets == 0
        assert r.total_profit == Decimal("0")
        assert r.bets == []

    def test_performance_metrics_defaults(self):
        m = PerformanceMetrics(config_label="test")
        assert m.sharpe_ratio == 0.0
        assert m.hit_rate == 0.0

    def test_validation_result_minimal(self):
        v = ValidationResult(passed=True)
        assert v.passed


# ─── Simulator ───────────────────────────────────────────────────

class TestBetSimulator:
    def test_run_empty_bets(self, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        result = sim.run([], config)
        assert result.total_bets == 0
        assert result.final_bankroll == 1000.0

    def test_run_all_wins(self, config, now):
        bets = [
            HistoricalBet(
                bet_id=f"b{i}", event_id=f"e{i}", sport="soccer",
                market="h2h", bookmaker="Bet365", outcome="home",
                odd=Decimal("2.0"), stake=Decimal("100"),
                result=BetResult.WIN, actual_return=Decimal("2.0"),
                profit=Decimal("100"), predicted_ev=Decimal("5.0"),
                predicted_prob=Decimal("0.55"), implied_prob=Decimal("0.50"),
                confidence_score=0.8, risk_level="MEDIUM", value_grade="STRONG",
                kelly_fraction=0.25, event_date=now, placed_at=now,
            )
            for i in range(5)
        ]
        sim = BetSimulator(initial_bankroll=1000.0)
        result = sim.run(bets, config)
        assert result.total_bets == 5
        assert result.winning_bets == 5
        assert result.total_profit > 0
        assert result.final_bankroll > 1000.0

    def test_run_all_losses(self, config, now):
        bets = [
            HistoricalBet(
                bet_id=f"b{i}", event_id=f"e{i}", sport="soccer",
                market="h2h", bookmaker="Bet365", outcome="home",
                odd=Decimal("2.0"), stake=Decimal("100"),
                result=BetResult.LOSS, actual_return=Decimal("0"),
                profit=Decimal("-100"), predicted_ev=Decimal("-5.0"),
                predicted_prob=Decimal("0.45"), implied_prob=Decimal("0.50"),
                confidence_score=0.2, risk_level="HIGH", value_grade="NOISE",
                kelly_fraction=0.05, event_date=now, placed_at=now,
            )
            for i in range(5)
        ]
        sim = BetSimulator(initial_bankroll=1000.0)
        result = sim.run(bets, config)
        assert result.total_bets == 5
        assert result.losing_bets == 5
        assert result.total_profit < 0
        assert result.final_bankroll < 1000.0

    def test_run_with_commission(self, config, now):
        bets = [
            HistoricalBet(
                bet_id="b1", event_id="e1", sport="soccer",
                market="h2h", bookmaker="Bet365", outcome="home",
                odd=Decimal("2.0"), stake=Decimal("100"),
                result=BetResult.WIN, actual_return=Decimal("2.0"),
                profit=Decimal("100"), predicted_ev=Decimal("5.0"),
                predicted_prob=Decimal("0.55"), implied_prob=Decimal("0.50"),
                confidence_score=0.8, risk_level="MEDIUM", value_grade="STRONG",
                kelly_fraction=0.25, event_date=now, placed_at=now,
            )
        ]
        sim = BetSimulator(initial_bankroll=1000.0, commission_rate=0.05)
        result = sim.run(bets, config)
        assert result.total_bets == 1
        assert result.total_profit < Decimal("100")

    def test_run_filters_by_config(self, now):
        bets = [
            HistoricalBet(
                bet_id="b1", event_id="e1", sport="soccer",
                market="h2h", bookmaker="Bet365", outcome="home",
                odd=Decimal("2.0"), stake=Decimal("100"),
                result=BetResult.WIN, actual_return=Decimal("2.0"),
                profit=Decimal("100"), predicted_ev=Decimal("5.0"),
                predicted_prob=Decimal("0.55"), implied_prob=Decimal("0.50"),
                confidence_score=0.9, risk_level="LOW", value_grade="ELITE",
                kelly_fraction=0.25, event_date=now, placed_at=now,
            ),
            HistoricalBet(
                bet_id="b2", event_id="e2", sport="soccer",
                market="h2h", bookmaker="Bet365", outcome="away",
                odd=Decimal("3.0"), stake=Decimal("50"),
                result=BetResult.LOSS, actual_return=Decimal("0"),
                profit=Decimal("-50"), predicted_ev=Decimal("-10.0"),
                predicted_prob=Decimal("0.25"), implied_prob=Decimal("0.33"),
                confidence_score=0.1, risk_level="EXTREME", value_grade="NOISE",
                kelly_fraction=0.0, event_date=now, placed_at=now,
            ),
        ]
        strict_config = BacktestConfig(
            min_ev=0.0,
            min_confidence=0.5,
            max_risk_level="HIGH",
            min_value_grade="SOLID",
        )
        sim = BetSimulator(initial_bankroll=1000.0)
        result = sim.run(bets, strict_config)
        assert result.total_bets == 1
        assert result.winning_bets == 1

    def test_prepare_backtest_data(self):
        now = datetime.now(timezone.utc)
        opportunities = [
            {
                "event_id": "e1", "sport": "soccer", "market": "h2h",
                "bookmaker": "Bet365", "outcome": "home", "odd": 2.0,
                "stake_x": 100, "predicted_ev": 5.0, "predicted_prob": 0.55,
                "implied_prob": 0.50, "confidence_score": 0.8,
                "risk_level": "MEDIUM", "value_grade": "STRONG",
                "kelly_fraction": 0.25, "detected_at": now,
            },
            {
                "event_id": "e2", "sport": "basketball", "market": "spread",
                "bookmaker": "Pinnacle", "outcome": "away", "odd": 3.0,
                "stake_x": 50, "predicted_ev": 10.0, "predicted_prob": 0.35,
                "implied_prob": 0.33, "confidence_score": 0.6,
                "risk_level": "HIGH", "value_grade": "SOLID",
                "kelly_fraction": 0.10, "detected_at": now,
            },
        ]
        outcomes = {"e1": "home", "e2": "home"}
        bets = prepare_backtest_data(opportunities, outcomes)
        assert len(bets) == 2
        assert bets[0].result == BetResult.WIN
        assert bets[1].result == BetResult.LOSS

    def test_generate_synthetic_bets(self):
        bets = generate_synthetic_bets(n_bets=100, edge_pct=3.0, seed=42)
        assert len(bets) == 100
        assert all(isinstance(b, HistoricalBet) for b in bets)

    def test_synthetic_bets_reproducible(self):
        b1 = generate_synthetic_bets(50, 5.0, seed=123)
        b2 = generate_synthetic_bets(50, 5.0, seed=123)
        assert [b.bet_id for b in b1] == [b.bet_id for b in b2]

    def test_run_sorts_by_time(self, config):
        now = datetime.now(timezone.utc)
        bets = [
            HistoricalBet(
                bet_id=f"b{i}", event_id=f"e{i}", sport="soccer",
                market="h2h", bookmaker="Bet365", outcome="home",
                odd=Decimal("1.5"), stake=Decimal("10"),
                result=BetResult.WIN, actual_return=Decimal("1.5"),
                profit=Decimal("5"), predicted_ev=Decimal("2.0"),
                predicted_prob=Decimal("0.6"), implied_prob=Decimal("0.5"),
                confidence_score=0.6, risk_level="LOW", value_grade="SOLID",
                kelly_fraction=0.1, event_date=now, placed_at=now,
            )
            for i in range(5, -1, -1)
        ]
        sim = BetSimulator(initial_bankroll=1000.0)
        result = sim.run(bets, config, sort_by_time=True)
        assert result.total_bets == 6
        assert result.bets[0].placed_at <= result.bets[-1].placed_at


# ─── Metrics ─────────────────────────────────────────────────────

class TestMetrics:
    def test_compute_metrics_empty(self):
        r = BacktestResult(config=BacktestConfig())
        m = compute_metrics(r)
        assert m.total_bets == 0
        assert m.sharpe_ratio == 0.0

    def test_compute_metrics_with_bets(self, result):
        m = compute_metrics(result)
        assert m.total_bets == 40
        assert m.winning_bets == 20
        assert m.losing_bets == 20
        assert m.hit_rate == 0.5

    def test_compute_metrics_with_losses(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        m = compute_metrics(r)
        assert m.total_bets == 40
        assert m.winning_bets == 20
        assert m.losing_bets == 20
        assert m.hit_rate == 0.5

    def test_drawdown_no_decline(self):
        bankrolls = [1000, 1100, 1200, 1300]
        max_dd, dur, avg_dd, ulcer = _compute_drawdown(bankrolls)
        assert max_dd == 0.0
        assert dur == 0
        assert avg_dd == 0.0
        assert ulcer == 0.0

    def test_drawdown_with_decline(self):
        bankrolls = [1000, 900, 800, 950, 850, 1100]
        max_dd, dur, avg_dd, ulcer = _compute_drawdown(bankrolls)
        assert max_dd > 0
        assert dur > 0

    def test_sharpe_ratio(self):
        returns = [0.01, 0.02, -0.01, 0.015, 0.005, -0.005]
        s = _compute_sharpe(returns)
        assert isinstance(s, float)

    def test_sharpe_zero_std(self):
        returns = [0.01, 0.01, 0.01]
        s = _compute_sharpe(returns)
        assert s == 0.0

    def test_sharpe_single_return(self):
        s = _compute_sharpe([0.01])
        assert s == 0.0

    def test_roi_std_calculated(self, result):
        m = compute_metrics(result)
        assert m.roi_std >= 0

    def test_median_profit(self, result):
        m = compute_metrics(result)
        assert isinstance(m.median_profit_per_bet, float)

    def test_best_and_worst_month(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        m = compute_metrics(r)
        assert m.backtest_days >= 0
        assert isinstance(m.best_month_pct, float)
        assert isinstance(m.worst_month_pct, float)

    def test_bankroll_multiple(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        m = compute_metrics(r)
        assert isinstance(m.bankroll_multiple, float)

    def test_ulcer_index(self, result):
        m = compute_metrics(result)
        assert m.ulcer_index >= 0

    def test_predicted_vs_realized_r2_few_bets(self):
        r = BacktestResult(config=BacktestConfig())
        m = compute_metrics(r)
        assert m.predicted_vs_realized_r2 == 0.0

    def test_information_coefficient_few_bets(self):
        r = BacktestResult(config=BacktestConfig())
        m = compute_metrics(r)
        assert m.information_coefficient == 0.0


# ─── Validator ───────────────────────────────────────────────────

class TestValidator:
    def test_validate_empty_result(self):
        r = BacktestResult(config=BacktestConfig())
        v = validate_backtest(r)
        assert not v.passed

    def test_validate_with_edge(self, result):
        v = validate_backtest(result)
        assert isinstance(v.passed, bool)
        assert isinstance(v.t_statistic, float)
        assert isinstance(v.p_value, float)
        assert isinstance(v.bootstrap_sharpe_mean, float)

    def test_validate_with_losses(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        v = validate_backtest(r)
        assert v.num_trials == 1000
        assert isinstance(v.bootstrap_sharpe_mean, float)
        assert isinstance(v.bootstrap_sharpe_ci_lower, float)
        assert isinstance(v.bootstrap_sharpe_ci_upper, float)

    def test_validate_passed_min_bets(self, config, now):
        bets = [
            HistoricalBet(
                bet_id=f"b{i}", event_id=f"e{i}", sport="soccer",
                market="h2h", bookmaker="Bet365", outcome="home",
                odd=Decimal("2.0"), stake=Decimal("100"),
                result=BetResult.WIN, actual_return=Decimal("2.0"),
                profit=Decimal("100"), predicted_ev=Decimal("5.0"),
                predicted_prob=Decimal("0.55"), implied_prob=Decimal("0.50"),
                confidence_score=0.8, risk_level="MEDIUM",
                value_grade="STRONG", kelly_fraction=0.25,
                event_date=now, placed_at=now,
            )
            for i in range(5)
        ]
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(bets, config)
        v = validate_backtest(r)
        assert not v.passed_min_bets

    def test_dsr_zero_for_small_sample(self, config, now):
        bets = [
            HistoricalBet(
                bet_id=f"b{i}", event_id=f"e{i}", sport="soccer",
                market="h2h", bookmaker="Bet365", outcome="home",
                odd=Decimal("2.0"), stake=Decimal("100"),
                result=BetResult.WIN, actual_return=Decimal("2.0"),
                profit=Decimal("100"), predicted_ev=Decimal("5.0"),
                predicted_prob=Decimal("0.55"), implied_prob=Decimal("0.50"),
                confidence_score=0.8, risk_level="MEDIUM",
                value_grade="STRONG", kelly_fraction=0.25,
                event_date=now, placed_at=now,
            )
            for i in range(3)
        ]
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(bets, config)
        m = compute_metrics(r)
        assert m.deflated_sharpe_ratio == 0.0


# ─── Analyzer ────────────────────────────────────────────────────

class TestBacktestAnalyzer:
    def test_by_sport(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        sports = a.by_sport()
        assert "soccer" in sports
        assert "basketball" in sports

    def test_by_market(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        markets = a.by_market()
        assert "h2h" in markets

    def test_by_bookmaker(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        bms = a.by_bookmaker()
        assert "Bet365" in bms
        assert "Pinnacle" in bms

    def test_by_grade(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        grades = a.by_grade()
        assert "STRONG" in grades
        assert "NOISE" in grades

    def test_by_risk_level(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        risks = a.by_risk_level()
        assert "MEDIUM" in risks
        assert "HIGH" in risks

    def test_by_ev_bucket(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        evs = a.by_ev_bucket()
        assert len(evs) > 0

    def test_by_confidence(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        confs = a.by_confidence()
        assert "80-100%" in confs
        assert "0-40%" in confs

    def test_by_month(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        months = a.by_month()
        assert len(months) > 0

    def test_by_hour(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        hours = a.by_hour()
        assert len(hours) > 0

    def test_summary(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        a = BacktestAnalyzer(r)
        s = a.summary()
        assert "total" in s
        assert "by_sport" in s
        assert "by_market" in s
        assert "by_bookmaker" in s

    def test_slice_few_bets_skipped(self, config):
        r = BacktestResult(config=config)
        a = BacktestAnalyzer(r)
        assert a.by_sport() == {}


# ─── Report ──────────────────────────────────────────────────────

class TestReport:
    def test_generate_report(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        report = generate_report(r)
        assert "report_metadata" in report
        assert "summary" in report
        assert "risk_metrics" in report
        assert "statistical_validation" in report
        assert "predictive_power" in report
        assert "segmented_analysis" in report
        assert "validation_detail" in report

    def test_report_metadata(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        report = generate_report(r)
        meta = report["report_metadata"]
        assert "config_label" in meta
        assert "min_ev" in meta["config"]

    def test_report_summary_values(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        report = generate_report(r)
        s = report["summary"]
        assert s["total_bets"] == 40
        assert s["winning_bets"] == 20
        assert s["losing_bets"] == 20

    def test_report_statistical_validation(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        report = generate_report(r)
        v = report["statistical_validation"]
        assert "t_statistic" in v
        assert "p_value" in v
        assert "deflated_sharpe_ratio" in v

    def test_report_validation_detail(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        report = generate_report(r)
        vd = report["validation_detail"]
        assert "passed_min_bets" in vd
        assert "passed_min_sharpe" in vd

    def test_report_empty_result(self):
        r = BacktestResult(config=BacktestConfig())
        report = generate_report(r)
        assert report["summary"]["total_bets"] == 0

    def test_report_generated_at_is_utc(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)
        report = generate_report(r)
        assert report["report_metadata"]["generated_at"].endswith("+00:00") or "Z" in report["report_metadata"]["generated_at"]


# ─── Integration ─────────────────────────────────────────────────

class TestIntegration:
    def test_simulate_metrics_validate(self, sample_bets, config):
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(sample_bets, config)

        m = compute_metrics(r)
        assert m.total_bets == 40

        v = validate_backtest(r)
        assert not v.passed

        report = generate_report(r)
        assert report["summary"]["total_bets"] == 40
        assert not report["summary"]["passed_validation"]

    def test_synthetic_edge_detected(self, config):
        bets = generate_synthetic_bets(n_bets=200, edge_pct=5.0, seed=42)
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(bets, config)
        v = validate_backtest(r)
        assert v.passed_min_bets
        assert v.num_trials == 1000

    def test_synthetic_no_edge(self, config):
        bets = generate_synthetic_bets(n_bets=200, edge_pct=-2.0, seed=42)
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(bets, config)
        v = validate_backtest(r)
        assert not v.passed

    def test_segmented_analysis_synthetic(self, config):
        bets = generate_synthetic_bets(n_bets=100, edge_pct=3.0, seed=42)
        sim = BetSimulator(initial_bankroll=1000.0)
        r = sim.run(bets, config)
        a = BacktestAnalyzer(r)
        summary = a.summary()
        assert "total" in summary
        assert summary["total"].total_bets > 0
