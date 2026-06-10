from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from backend.domains.clv.models import ClvRecord, ClvGrade, TimingEfficiency
from backend.domains.clv.calculator import build_clv_record
from backend.backtesting.clv.models import (
    BetOutcome, EdgeSignal, ClvValidationBet, ClvValidationMetrics,
    ClvValidationReport, SegmentAnalysis, SystemEdgeClass, Recommendation,
)
from backend.backtesting.clv.engine import (
    run_clv_backtest, _classify_edge_signal, _simulate_bet_outcome,
    _odds_range, _compute_metrics, _compute_drawdown,
    _segment_by, _segment_by_month, format_clv_backtest_report,
    _classify_system, _recommend, _compute_edge_decay_slope,
)


def _ts(hours_ago: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _make_record(
    event_id="evt_1", sport="soccer", bookmaker="Pinnacle",
    captured_odd=Decimal("2.10"), closing_odd=Decimal("2.00"),
    opening_odd=Decimal("2.20"), ev=0.05,
    captured_at=None, closed_at=None, opening_at=None,
    outcome="home",
) -> ClvRecord:
    cap_t = captured_at or _ts(12)
    clo_t = closed_at or _ts(0)
    ope_t = opening_at or _ts(24)
    return build_clv_record(
        event_id=event_id, market="h2h", outcome=outcome,
        bookmaker=bookmaker,
        captured_odd=captured_odd, captured_at=cap_t,
        closing_odd=closing_odd, closed_at=clo_t,
        opening_odd=opening_odd, opening_at=ope_t,
        simulated_ev=ev,
    )


# ─── Edge Signal Classification ───────────────────────────────────

class TestEdgeSignalClassification:
    def test_true_edge_ev_positive_clv_positive(self):
        assert _classify_edge_signal(0.05, 2.5) == EdgeSignal.TRUE_EDGE

    def test_false_positive_ev_positive_clv_negative(self):
        assert _classify_edge_signal(0.05, -1.0) == EdgeSignal.FALSE_POSITIVE

    def test_false_positive_ev_positive_clv_zero(self):
        assert _classify_edge_signal(0.05, 0.0) == EdgeSignal.FALSE_POSITIVE

    def test_correctly_avoided_ev_negative_clv_negative(self):
        assert _classify_edge_signal(-0.02, -0.5) == EdgeSignal.CORRECTLY_AVOIDED

    def test_correctly_avoided_ev_zero_clv_negative(self):
        assert _classify_edge_signal(0.0, -1.0) == EdgeSignal.CORRECTLY_AVOIDED

    def test_blind_spot_ev_negative_clv_positive(self):
        assert _classify_edge_signal(-0.02, 1.5) == EdgeSignal.MODEL_BLIND_SPOT

    def test_blind_spot_ev_zero_clv_positive(self):
        assert _classify_edge_signal(0.0, 2.0) == EdgeSignal.MODEL_BLIND_SPOT


# ─── Odds Range ──────────────────────────────────────────────────

class TestOddsRange:
    def test_range_below_2(self):
        assert _odds_range(Decimal("1.50")) == "1.0-2.0"

    def test_range_2_to_3(self):
        assert _odds_range(Decimal("2.50")) == "2.0-3.0"

    def test_range_3_to_5(self):
        assert _odds_range(Decimal("4.00")) == "3.0-5.0"

    def test_range_5_plus(self):
        assert _odds_range(Decimal("6.00")) == "5.0+"

    def test_range_exact_boundary_2(self):
        assert _odds_range(Decimal("2.00")) == "2.0-3.0"

    def test_range_exact_boundary_3(self):
        assert _odds_range(Decimal("3.00")) == "3.0-5.0"

    def test_range_exact_boundary_5(self):
        assert _odds_range(Decimal("5.00")) == "5.0+"


# ─── Bet Outcome Simulation ──────────────────────────────────────

class TestBetOutcomeSimulation:
    def test_outcome_is_win_or_loss(self):
        for _ in range(100):
            result = _simulate_bet_outcome(Decimal("2.00"))
            assert result in (BetOutcome.WIN, BetOutcome.LOSS)

    def test_high_prob_favors_wins(self):
        random.seed(42)
        wins = sum(1 for _ in range(1000) if _simulate_bet_outcome(Decimal("1.10")) == BetOutcome.WIN)
        assert wins > 800

    def test_low_prob_favors_losses(self):
        random.seed(42)
        wins = sum(1 for _ in range(1000) if _simulate_bet_outcome(Decimal("10.00")) == BetOutcome.WIN)
        assert wins < 300


# ─── Drawdown ────────────────────────────────────────────────────

class TestDrawdown:
    def test_no_drawdown_all_profits(self):
        class FakeBet:
            def __init__(self, profit):
                self.profit = profit
        bets = [FakeBet(10) for _ in range(10)]
        dd, dur = _compute_drawdown(bets)
        assert dd == 0.0
        assert dur == 0

    def test_drawdown_with_decline(self):
        class FakeBet:
            def __init__(self, profit):
                self.profit = profit
        bets = [FakeBet(10), FakeBet(10), FakeBet(-30), FakeBet(-20), FakeBet(5)]
        dd, dur = _compute_drawdown(bets)
        assert dd > 0
        assert dur >= 0

    def test_drawdown_empty(self):
        dd, dur = _compute_drawdown([])
        assert dd == 0.0
        assert dur == 0

    def test_drawdown_peak_to_trough(self):
        class FakeBet:
            def __init__(self, profit):
                self.profit = profit
        bets = [FakeBet(100), FakeBet(-50), FakeBet(-30), FakeBet(10)]
        dd, dur = _compute_drawdown(bets)
        assert dd > 20.0


# ─── Full Backtest ───────────────────────────────────────────────

class TestFullBacktest:
    def test_empty_records(self):
        report = run_clv_backtest([], seed=42)
        assert report.metrics.n_bets == 0
        assert report.verdict == "No records to backtest"

    def test_basic_backtest(self):
        records = [_make_record(event_id=f"e{i}", ev=0.03 + (i % 5) * 0.01) for i in range(50)]
        report = run_clv_backtest(records, seed=42)
        assert report.metrics.n_bets == 50
        assert report.metrics.total_staked > 0
        assert len(report.bets) == 50
        assert len(report.equity_curve) == 50

    def test_backtest_with_strong_positive_clv(self):
        records = [
            _make_record(
                event_id=f"e{i}",
                captured_odd=Decimal("2.50"),
                closing_odd=Decimal("2.00"),
                ev=0.10,
            )
            for i in range(100)
        ]
        report = run_clv_backtest(records, seed=42)
        assert report.metrics.avg_clv_pct > 0
        assert report.metrics.true_edge_pct > 50

    def test_backtest_with_negative_clv(self):
        records = [
            _make_record(
                event_id=f"e{i}",
                captured_odd=Decimal("1.80"),
                closing_odd=Decimal("2.20"),
                ev=0.08,
            )
            for i in range(100)
        ]
        report = run_clv_backtest(records, seed=42)
        assert report.metrics.avg_clv_pct < 0
        assert report.metrics.false_positive_pct > 50

    def test_backtest_with_mixed_records(self):
        records = []
        for i in range(100):
            ev = 0.02 if i < 50 else 0.08
            captured = Decimal("2.00") if i < 50 else Decimal("2.20")
            closing = Decimal("2.20") if i < 50 else Decimal("2.00")
            records.append(_make_record(
                event_id=f"e{i}", captured_odd=captured, closing_odd=closing, ev=ev,
            ))
        report = run_clv_backtest(records, seed=42)
        assert report.metrics.n_bets == 100
        assert 0 < report.metrics.true_edge_pct < 100

    def test_backtest_by_sport(self):
        records = [
            _make_record(event_id=f"e{i}", ev=0.05)
            for i in range(30)
        ] + [
            _make_record(event_id=f"e{i+30}", ev=0.04)
            for i in range(20)
        ]
        for r in records[:30]:
            r.sport = "soccer"
        for r in records[30:]:
            r.sport = "basketball"
        report = run_clv_backtest(records, seed=42)
        assert len(report.by_sport) >= 2

    def test_backtest_by_bookmaker(self):
        records = [
            _make_record(event_id=f"e{i}", bookmaker="Pinnacle", ev=0.05)
            for i in range(20)
        ] + [
            _make_record(event_id=f"e{i+20}", bookmaker="Bet365", ev=0.04)
            for i in range(20)
        ]
        report = run_clv_backtest(records, seed=42)
        assert len(report.by_bookmaker) >= 2

    def test_backtest_by_odds_range(self):
        records = [
            _make_record(event_id=f"e{i}", captured_odd=Decimal("1.50"), ev=0.05)
            for i in range(20)
        ] + [
            _make_record(event_id=f"e{i+20}", captured_odd=Decimal("3.50"), ev=0.05)
            for i in range(20)
        ]
        report = run_clv_backtest(records, seed=42)
        assert len(report.by_odds_range) >= 2

    def test_backtest_outputs_charts(self):
        records = [_make_record(event_id=f"e{i}", ev=0.03) for i in range(30)]
        report = run_clv_backtest(records, seed=42)
        assert len(report.charts_ev_vs_clv) == 30
        assert len(report.charts_equity) == 30
        assert len(report.charts_distribution) == 8


# ─── Segmentation ────────────────────────────────────────────────

class TestSegmentation:
    def test_segment_by_sport(self):
        class FakeBet:
            def __init__(self, sport, profit=10, stake=100, is_winner=True, ev=0.05, clv=1.0):
                self.sport = sport
                self.profit = profit
                self.stake = stake
                self._is_winner = is_winner
                self.simulated_ev = ev
                self.clv_pct = clv
                self.edge_signal = "TRUE_EDGE"
            @property
            def is_winner(self):
                return self._is_winner
            @property
            def ev_aligned_with_clv(self):
                return (self.simulated_ev > 0) == (self.clv_pct > 0)

        bets = [FakeBet("soccer") for _ in range(10)] + [FakeBet("basketball") for _ in range(5)]
        segments = _segment_by(bets, "sport")
        assert len(segments) == 2

    def test_segment_by_month(self):
        now = datetime.now(timezone.utc)
        class FakeBet:
            captured_at = now
            profit = 10
            stake = 100
            simulated_ev = 0.05
            clv_pct = 1.0
            edge_signal = "TRUE_EDGE"
            @property
            def is_winner(self):
                return True
            @property
            def ev_aligned_with_clv(self):
                return True

        bets = [FakeBet() for _ in range(10)]
        segments = _segment_by_month(bets)
        assert len(segments) >= 1


# ─── Metrics ─────────────────────────────────────────────────────

class TestMetrics:
    def test_metrics_empty(self):
        m = _compute_metrics([], True)
        assert m.n_bets == 0

    def test_metrics_all_wins(self):
        class FakeBet:
            def __init__(self):
                self.profit = 10.0
                self.stake = 100.0
                self.clv_pct = 2.0
                self.simulated_ev = 0.05
                self.edge_signal = EdgeSignal.TRUE_EDGE
            @property
            def is_winner(self):
                return True
            @property
            def ev_aligned_with_clv(self):
                return True

        m = _compute_metrics([FakeBet() for _ in range(50)], True)
        assert m.n_bets == 50
        assert m.n_wins == 50
        assert m.hit_rate == 100.0
        assert m.roi_pct > 0

    def test_metrics_all_losses(self):
        class FakeBet:
            def __init__(self):
                self.profit = -10.0
                self.stake = 100.0
                self.clv_pct = -2.0
                self.simulated_ev = 0.05
                self.edge_signal = EdgeSignal.FALSE_POSITIVE
            @property
            def is_winner(self):
                return False
            @property
            def ev_aligned_with_clv(self):
                return False

        m = _compute_metrics([FakeBet() for _ in range(30)], False)
        assert m.n_wins == 0
        assert m.roi_pct < 0
        assert m.hit_rate == 0.0

    def test_efficiency_score_all_aligned(self):
        class FakeBet:
            def __init__(self, ev=0.05, clv=1.0):
                self.profit = 5.0
                self.stake = 100.0
                self.clv_pct = clv
                self.simulated_ev = ev
                self.edge_signal = EdgeSignal.TRUE_EDGE
            @property
            def is_winner(self):
                return True
            @property
            def ev_aligned_with_clv(self):
                return (self.simulated_ev > 0) == (self.clv_pct > 0)

        m = _compute_metrics([FakeBet() for _ in range(20)], True)
        assert m.efficiency_score == 100.0

    def test_efficiency_score_mixed(self):
        class FakeBet:
            def __init__(self, aligned=True):
                self.profit = 0.0
                self.stake = 100.0
                self.clv_pct = 1.0 if aligned else -1.0
                self.simulated_ev = 0.05
                self.edge_signal = EdgeSignal.TRUE_EDGE if aligned else EdgeSignal.FALSE_POSITIVE
            @property
            def is_winner(self):
                return True if self.clv_pct > 0 else False
            @property
            def ev_aligned_with_clv(self):
                return (self.simulated_ev > 0) == (self.clv_pct > 0)

        bets = [FakeBet(aligned=True) for _ in range(15)] + [FakeBet(aligned=False) for _ in range(5)]
        m = _compute_metrics(bets, True)
        assert m.efficiency_score == 75.0

    def test_edge_quality_score(self):
        class FakeBet:
            def __init__(self, ev=0.05, clv=1.0):
                self.profit = 5.0
                self.stake = 100.0
                self.clv_pct = clv
                self.simulated_ev = ev
                self.edge_signal = EdgeSignal.TRUE_EDGE if clv > 0 else EdgeSignal.FALSE_POSITIVE
            @property
            def is_winner(self):
                return self.clv_pct > 0
            @property
            def ev_aligned_with_clv(self):
                return (self.simulated_ev > 0) == (self.clv_pct > 0)

        bets = [FakeBet(ev=0.05, clv=2.0) for _ in range(20)] + [FakeBet(ev=0.05, clv=-1.0) for _ in range(5)]
        m = _compute_metrics(bets, True)
        assert m.edge_quality_score == 80.0
        assert m.true_edge_pct == 80.0
        assert m.false_positive_pct == 20.0


# ─── System Classification ───────────────────────────────────────

class TestSystemClassification:
    def test_strong_edge(self):
        assert _classify_system(roi=5.0, avg_clv=2.0, p_value=0.01, efficiency=70, edge_quality=80) == SystemEdgeClass.STRONG_EDGE

    def test_no_edge_negative_clv(self):
        assert _classify_system(roi=-2.0, avg_clv=-1.5, p_value=0.50, efficiency=30, edge_quality=20) == SystemEdgeClass.NO_EDGE

    def test_strong_edge_high_efficiency(self):
        assert _classify_system(roi=1.0, avg_clv=0.3, p_value=0.50, efficiency=60, edge_quality=60) == SystemEdgeClass.STRONG_EDGE

    def test_weak_edge(self):
        assert _classify_system(roi=2.0, avg_clv=0.2, p_value=0.50, efficiency=45, edge_quality=35) == SystemEdgeClass.WEAK_EDGE

    def test_inconclusive(self):
        assert _classify_system(roi=0.0, avg_clv=0.0, p_value=0.50, efficiency=50, edge_quality=25) == SystemEdgeClass.INCONCLUSIVE


# ─── Recommendation ──────────────────────────────────────────────

class TestRecommendation:
    def test_scale_for_strong_edge(self):
        assert _recommend(SystemEdgeClass.STRONG_EDGE) == Recommendation.SCALE

    def test_kill_for_no_edge(self):
        assert _recommend(SystemEdgeClass.NO_EDGE) == Recommendation.KILL

    def test_fix_for_weak_edge(self):
        assert _recommend(SystemEdgeClass.WEAK_EDGE) == Recommendation.FIX

    def test_fix_for_inconclusive(self):
        assert _recommend(SystemEdgeClass.INCONCLUSIVE) == Recommendation.FIX


# ─── Edge Decay ──────────────────────────────────────────────────

class TestEdgeDecay:
    def test_insufficient_data(self):
        bets = []
        slope, interp = _compute_edge_decay_slope(bets)
        assert interp == "insufficient_data"

    def test_few_bets(self):
        class FakeBet:
            def __init__(self, clv):
                self.clv_pct = clv
        bets = [FakeBet(1.0) for _ in range(5)]
        slope, interp = _compute_edge_decay_slope(bets)
        assert interp == "insufficient_data"

    def test_stable_edge(self):
        class FakeBet:
            def __init__(self, clv):
                self.clv_pct = clv
        bets = [FakeBet(1.0) for _ in range(50)]
        slope, interp = _compute_edge_decay_slope(bets)
        assert interp == "stable_edge"

    def test_degrading_edge(self):
        class FakeBet:
            def __init__(self, clv):
                self.clv_pct = clv
        bets = [FakeBet(5.0 - i * 0.2) for i in range(50)]
        slope, interp = _compute_edge_decay_slope(bets)
        assert interp == "degrading_edge"

    def test_improving_edge(self):
        class FakeBet:
            def __init__(self, clv):
                self.clv_pct = clv
        bets = [FakeBet(-2.0 + i * 0.2) for i in range(50)]
        slope, interp = _compute_edge_decay_slope(bets)
        assert interp == "improving_edge"


# ─── Report ──────────────────────────────────────────────────────

class TestReport:
    def test_format_report_empty(self):
        report = run_clv_backtest([], seed=42)
        text = format_clv_backtest_report(report)
        assert "Bets: 0" in text

    def test_format_report_with_data(self):
        records = [_make_record(event_id=f"e{i}", ev=0.05) for i in range(20)]
        report = run_clv_backtest(records, seed=42)
        text = format_clv_backtest_report(report)
        assert "CLV VALIDATION BACKTEST REPORT" in text
        assert "Bets:" in text
        assert "ROI:" in text
        assert "Efficiency Score:" in text

    def test_format_report_classification(self):
        records = [
            _make_record(
                event_id=f"e{i}",
                captured_odd=Decimal("2.50"), closing_odd=Decimal("2.00"),
                ev=0.10,
            )
            for i in range(100)
        ]
        report = run_clv_backtest(records, seed=42)
        text = format_clv_backtest_report(report)
        assert report.metrics.system_edge_class == SystemEdgeClass.STRONG_EDGE


# ─── Edge Cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_record(self):
        records = [_make_record(event_id="e1")]
        report = run_clv_backtest(records, seed=42)
        assert report.metrics.n_bets == 1
        assert report.metrics.n_wins + report.metrics.n_losses == 1

    def test_ten_records(self):
        records = [_make_record(event_id=f"e{i}") for i in range(10)]
        report = run_clv_backtest(records, seed=42)
        assert report.metrics.n_bets == 10

    def test_backtest_stake_pct(self):
        records = [_make_record(event_id=f"e{i}", ev=0.05) for i in range(10)]
        report_high = run_clv_backtest(records, stake_pct=0.1, seed=42)
        report_low = run_clv_backtest(records, stake_pct=0.01, seed=42)
        assert report_high.metrics.total_staked > report_low.metrics.total_staked

    def test_backtest_initial_bankroll(self):
        records = [_make_record(event_id=f"e{i}", ev=0.05) for i in range(10)]
        report = run_clv_backtest(records, initial_bankroll=10000, seed=42)
        assert report.metrics.total_staked < 10000

    def test_deterministic_seed(self):
        records = [_make_record(event_id=f"e{i}", ev=0.05) for i in range(20)]
        r1 = run_clv_backtest(records, seed=42)
        r2 = run_clv_backtest(records, seed=42)
        assert r1.metrics.roi_pct == r2.metrics.roi_pct
        assert [b.bet_result for b in r1.bets] == [b.bet_result for b in r2.bets]

    def test_mixed_edge_signals_in_metrics(self):
        class FakeBet:
            def __init__(self, ev, clv):
                self.profit = 5.0 if clv > 0 else -5.0
                self.stake = 100.0
                self.clv_pct = clv
                self.simulated_ev = ev
                self.edge_signal = EdgeSignal.TRUE_EDGE if clv > 0 and ev > 0 else EdgeSignal.FALSE_POSITIVE
            @property
            def is_winner(self):
                return self.clv_pct > 0
            @property
            def ev_aligned_with_clv(self):
                return (self.simulated_ev > 0) == (self.clv_pct > 0)

        bets = [FakeBet(0.05, 2.0) for _ in range(30)] + [FakeBet(0.05, -1.0) for _ in range(10)]
        m = _compute_metrics(bets, True)
        assert m.n_wins == 30
        assert m.n_losses == 10
        assert m.true_edge_pct == 75.0
        assert m.false_positive_pct == 25.0


# ─── Integration ─────────────────────────────────────────────────

class TestIntegration:
    def test_clv_backtest_pipeline(self):
        records = []
        for i in range(200):
            ev = 0.08 if i < 100 else 0.03
            captured = Decimal("2.20") if i < 100 else Decimal("2.00")
            closing = Decimal("2.00") if i < 100 else Decimal("2.10")
            records.append(_make_record(
                event_id=f"e{i}", captured_odd=captured,
                closing_odd=closing, ev=ev,
            ))

        report = run_clv_backtest(records, seed=42)

        assert report.metrics.n_bets == 200
        assert report.verdict in ("SCALE", "FIX", "KILL")
        assert report.metrics.efficiency_score > 0
        assert report.metrics.true_edge_pct > 0
        assert report.metrics.false_positive_pct > 0
        assert len(report.charts_ev_vs_clv) == 200
        assert len(report.charts_equity) == 200
        assert len(report.charts_distribution) == 8

    def test_synthetic_no_edge(self):
        records = [
            _make_record(
                event_id=f"e{i}",
                captured_odd=Decimal("1.80"), closing_odd=Decimal("2.20"),
                ev=0.08,
            )
            for i in range(150)
        ]
        report = run_clv_backtest(records, seed=42)
        assert report.metrics.avg_clv_pct < 0
        assert report.metrics.false_positive_pct > 50
