from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domains.clv.models import (
    ClvGrade, TimingEfficiency, ClvRecord, ClvSnapshot,
)
from backend.domains.clv.calculator import (
    compute_clv, classify_clv, classify_timing, build_clv_record,
    compute_clv_from_snapshots, detect_leak, compute_implied_prob,
    compute_odds_movement, compute_hours_between,
)
from backend.domains.clv.analyzer import (
    compute_distribution, compute_by_bookmaker, compute_correlation,
    compute_timing_analysis, compute_t_test,
)
from backend.domains.clv.report import generate_clv_report, format_report_text


def _ts(hours_ago: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _make_record(
    captured=Decimal("2.10"), closing=Decimal("2.00"),
    opening=Decimal("2.20"), ev=0.05, outcome="home",
    bookmaker="Pinnacle", captured_at=None, closed_at=None, opening_at=None,
    event_id="evt_1",
) -> ClvRecord:
    cap_t = captured_at or _ts(12)
    clo_t = closed_at or _ts(0)
    ope_t = opening_at or _ts(24)
    return build_clv_record(
        event_id=event_id, market="h2h", outcome=outcome,
        bookmaker=bookmaker,
        captured_odd=captured, captured_at=cap_t,
        closing_odd=closing, closed_at=clo_t,
        opening_odd=opening, opening_at=ope_t,
        simulated_ev=ev,
    )


class TestClvCalculator:
    def test_positive_clv(self):
        clv_odds, clv_prob = compute_clv(Decimal("2.10"), Decimal("2.00"))
        assert clv_odds > 0
        assert clv_prob > 0

    def test_negative_clv(self):
        clv_odds, clv_prob = compute_clv(Decimal("1.90"), Decimal("2.00"))
        assert clv_odds < 0
        assert clv_prob < 0

    def test_zero_clv(self):
        clv_odds, clv_prob = compute_clv(Decimal("2.00"), Decimal("2.00"))
        assert clv_odds == 0
        assert clv_prob == 0

    def test_clv_formula_accuracy(self):
        # 2.10 vs 2.00 → (2.10 - 2.00) / 2.00 = 0.05 = 5%
        clv_odds, _ = compute_clv(Decimal("2.10"), Decimal("2.00"))
        assert abs(clv_odds - 0.05) < 0.001

    def test_clv_prob_space(self):
        # captured=2.00 (50%), closing=2.50 (40%) → CLV prob = -10%
        _, clv_prob = compute_clv(Decimal("2.00"), Decimal("2.50"))
        assert abs(clv_prob - (-0.10)) < 0.001

    def test_clv_with_explicit_probs(self):
        _, clv_prob = compute_clv(
            Decimal("2.00"), Decimal("2.00"),
            captured_prob=0.48, closing_prob=0.52,
        )
        assert abs(clv_prob - 0.04) < 0.001


class TestClassifyClv:
    def test_elite(self):
        assert classify_clv(4.0) == ClvGrade.ELITE
        assert classify_clv(3.1) == ClvGrade.ELITE

    def test_strong(self):
        assert classify_clv(2.0) == ClvGrade.STRONG
        assert classify_clv(1.6) == ClvGrade.STRONG

    def test_positive(self):
        assert classify_clv(0.8) == ClvGrade.POSITIVE
        assert classify_clv(0.6) == ClvGrade.POSITIVE

    def test_neutral(self):
        assert classify_clv(0.0) == ClvGrade.NEUTRAL
        assert classify_clv(0.3) == ClvGrade.NEUTRAL

    def test_negative(self):
        assert classify_clv(-0.8) == ClvGrade.NEGATIVE
        assert classify_clv(-1.2) == ClvGrade.NEGATIVE

    def test_bad(self):
        assert classify_clv(-2.0) == ClvGrade.BAD
        assert classify_clv(-2.5) == ClvGrade.BAD

    def test_catastrophic(self):
        assert classify_clv(-3.5) == ClvGrade.CATASTROPHIC
        assert classify_clv(-10.0) == ClvGrade.CATASTROPHIC


class TestClassifyTiming:
    def test_early(self):
        opening = _ts(24)
        captured = _ts(22)
        closing = _ts(0)
        assert classify_timing(captured, closing, opening, 5.0) == TimingEfficiency.EARLY

    def test_optimal(self):
        opening = _ts(24)
        captured = _ts(10)
        closing = _ts(0)
        assert classify_timing(captured, closing, opening, 5.0) == TimingEfficiency.OPTIMAL

    def test_late(self):
        opening = _ts(24)
        captured = _ts(2)
        closing = _ts(0)
        assert classify_timing(captured, closing, opening, 5.0) == TimingEfficiency.LATE

    def test_dead(self):
        opening = _ts(24)
        captured = _ts(0.1)
        closing = _ts(0)
        assert classify_timing(captured, closing, opening, 5.0) == TimingEfficiency.DEAD

    def test_zero_window(self):
        now = _ts(0)
        assert classify_timing(now, now, now, 0.0) == TimingEfficiency.OPTIMAL


class TestBuildClvRecord:
    def test_basic_record(self):
        r = _make_record()
        assert r.clv > 0
        assert r.clv_pct > 0
        assert r.grade in ClvGrade
        assert r.timing_efficiency in TimingEfficiency
        assert r.event_id == "evt_1"

    def test_negative_clv_record(self):
        r = _make_record(captured=Decimal("1.80"), closing=Decimal("2.00"))
        assert r.clv < 0
        assert r.grade in (ClvGrade.NEGATIVE, ClvGrade.BAD, ClvGrade.CATASTROPHIC)

    def test_hours_to_close(self):
        cap = _ts(12)
        clo = _ts(0)
        r = _make_record(captured_at=cap, closed_at=clo)
        assert abs(r.hours_to_close - 12.0) < 0.01


class TestClvFromSnapshots:
    def test_from_snapshots(self):
        cap = ClvSnapshot(
            event_id="e1", market="h2h", outcome="home",
            bookmaker="P1", odd=Decimal("2.10"), prob=0.476,
            timestamp=_ts(12),
        )
        clo = ClvSnapshot(
            event_id="e1", market="h2h", outcome="home",
            bookmaker="P1", odd=Decimal("2.00"), prob=0.50,
            timestamp=_ts(0), is_closing=True,
        )
        ope = ClvSnapshot(
            event_id="e1", market="h2h", outcome="home",
            bookmaker="P1", odd=Decimal("2.20"), prob=0.455,
            timestamp=_ts(24), is_opening=True,
        )
        record = compute_clv_from_snapshots(cap, clo, ope)
        assert record.clv > 0
        assert record.captured_odd == Decimal("2.10")
        assert record.closing_odd == Decimal("2.00")

    def test_from_snapshots_no_opening(self):
        cap = ClvSnapshot("e1", "h2h", "home", "P1", Decimal("2.10"), 0.476, _ts(12))
        clo = ClvSnapshot("e1", "h2h", "home", "P1", Decimal("2.00"), 0.50, _ts(0), is_closing=True)
        record = compute_clv_from_snapshots(cap, clo)
        assert record.opening_odd == Decimal("2.10")


class TestDetectLeak:
    def test_late_entry_leak(self):
        # Opening 2.00 → captured 1.80 (worse) → closing 1.60 (worse still)
        # The odds moved against us from the start
        records = [
            _make_record(
                opening=Decimal("2.00"), captured=Decimal("1.80"), closing=Decimal("1.60"),
                ev=0.08,
            ),
        ]
        leaks = detect_leak(records)
        assert len(leaks) >= 1
        assert any(l["type"] == "late_entry" for l in leaks)

    def test_false_positive_ev_leak(self):
        records = [
            _make_record(
                captured=Decimal("1.80"), closing=Decimal("2.10"),
                ev=0.10,  # high EV but CLV is very negative
            ),
        ]
        leaks = detect_leak(records, threshold_pct=1.0)
        assert len(leaks) >= 1
        assert any(l["type"] == "false_positive_ev" for l in leaks)

    def test_no_leak_clean_record(self):
        records = [
            _make_record(
                opening=Decimal("2.20"), captured=Decimal("2.10"), closing=Decimal("2.00"),
                ev=0.05,
            ),
        ]
        leaks = detect_leak(records)
        assert len(leaks) == 0


class TestComputeImpliedProb:
    def test_basic(self):
        assert abs(compute_implied_prob(Decimal("2.00")) - 0.50) < 0.001

    def test_negative_odd(self):
        assert compute_implied_prob(Decimal("-1.0")) == 0.0

    def test_odd_one(self):
        assert compute_implied_prob(Decimal("1.0")) == 0.0


class TestComputeOddsMovement:
    def test_positive_movement(self):
        assert compute_odds_movement(Decimal("2.00"), Decimal("2.20")) > 0

    def test_negative_movement(self):
        assert compute_odds_movement(Decimal("2.00"), Decimal("1.80")) < 0

    def test_no_movement(self):
        assert compute_odds_movement(Decimal("2.00"), Decimal("2.00")) == 0


class TestDistribution:
    def test_empty(self):
        dist = compute_distribution([])
        assert dist.total_records == 0

    def test_basic_distribution(self):
        records = [
            _make_record(captured=Decimal("2.10"), closing=Decimal("2.00")),
            _make_record(captured=Decimal("2.00"), closing=Decimal("2.00")),
            _make_record(captured=Decimal("1.90"), closing=Decimal("2.00")),
        ]
        dist = compute_distribution(records)
        assert dist.total_records == 3
        assert dist.positive_count >= 1
        assert dist.negative_count >= 1

    def test_positive_rate(self):
        records = [_make_record(captured=Decimal(f"2.{i}0"), closing=Decimal("2.00")) for i in range(10)]
        dist = compute_distribution(records)
        assert dist.positive_pct >= 0

    def test_grade_distribution(self):
        records = [
            _make_record(captured=Decimal("2.50"), closing=Decimal("2.00")),
            _make_record(captured=Decimal("2.00"), closing=Decimal("2.00")),
            _make_record(captured=Decimal("3.50"), closing=Decimal("2.00")),
            _make_record(captured=Decimal("1.70"), closing=Decimal("2.00")),
        ]
        dist = compute_distribution(records)
        assert sum(dist.grade_distribution.values()) == 4


class TestByBookmaker:
    def test_single_bookmaker(self):
        records = [_make_record(bookmaker="Pinnacle") for _ in range(5)]
        stats = compute_by_bookmaker(records)
        assert len(stats) == 1
        assert stats[0].bookmaker == "Pinnacle"
        assert stats[0].n_bets == 5

    def test_multiple_bookmakers(self):
        records = [
            _make_record(bookmaker="Pinnacle"),
            _make_record(bookmaker="Bet365"),
            _make_record(bookmaker="DraftKings"),
        ]
        stats = compute_by_bookmaker(records)
        assert len(stats) == 3

    def test_empty(self):
        assert compute_by_bookmaker([]) == []


class TestCorrelation:
    def test_insufficient_data(self):
        corr = compute_correlation([])
        assert corr.interpretation == "insufficient_data"
        corr = compute_correlation([_make_record()])
        assert corr.interpretation == "insufficient_data"

    def test_positive_correlation(self):
        records = [
            _make_record(captured=Decimal(f"2.{i}0"), closing=Decimal("2.00"), ev=0.01 * i)
            for i in range(10, 30)
        ]
        corr = compute_correlation(records)
        assert corr.pearson_r != 0 or corr.spearman_rho != 0


class TestTimingAnalysis:
    def test_basic_timing(self):
        records = [
            _make_record(captured_at=_ts(20), closed_at=_ts(0), opening_at=_ts(24)),
            _make_record(captured_at=_ts(8), closed_at=_ts(0), opening_at=_ts(24)),
            _make_record(captured_at=_ts(1), closed_at=_ts(0), opening_at=_ts(24)),
        ]
        timing = compute_timing_analysis(records)
        assert timing.avg_hours_to_close > 0
        assert timing.early_pct + timing.optimal_pct + timing.late_pct + timing.dead_pct == pytest.approx(100.0)

    def test_empty(self):
        timing = compute_timing_analysis([])
        assert timing.avg_hours_to_close == 0


class TestTTest:
    def test_insufficient_data(self):
        result = compute_t_test([])
        assert result["interpretation"] == "insufficient_data"

    def test_positive_clv_significant(self):
        records = [_make_record(captured=Decimal(f"2.{i}0"), closing=Decimal("2.00")) for i in range(5, 25)]
        result = compute_t_test(records)
        # Should not crash
        assert "t_statistic" in result
        assert "p_value" in result


class TestReport:
    def test_empty_report(self):
        report = generate_clv_report([], "Empty Test")
        assert report.verdict == "no_data"
        assert len(report.recommendations) == 1

    def test_report_with_data(self):
        records = [_make_record() for _ in range(20)]
        report = generate_clv_report(records, "Test Report")
        assert report.n_records == 20
        assert report.n_events >= 1
        assert report.n_bookmakers >= 1
        assert report.overall_clv_pct != 0
        assert report.distribution is not None
        assert report.correlation is not None
        assert report.timing is not None
        assert len(report.recommendations) >= 1

    def test_report_multiple_events(self):
        records = [
            _make_record(event_id="evt_1", outcome="home"),
            _make_record(event_id="evt_1", outcome="away"),
            _make_record(event_id="evt_2", outcome="home"),
        ]
        report = generate_clv_report(records)
        assert report.n_events == 2

    def test_report_multiple_bookmakers(self):
        records = [
            _make_record(bookmaker="Pinnacle"),
            _make_record(bookmaker="Bet365"),
            _make_record(bookmaker="DraftKings"),
        ]
        report = generate_clv_report(records)
        assert report.n_bookmakers == 3

    def test_format_report_text(self):
        records = [_make_record() for _ in range(10)]
        report = generate_clv_report(records)
        text = format_report_text(report)
        assert "CLV ANALYSIS REPORT" in text
        assert "Recommendations" in text
        assert "Verdict" in text


class TestIntegration:
    def test_full_pipeline(self):
        now = datetime.now(timezone.utc)
        records = []
        for i in range(50):
            captured = Decimal(str(round(2.0 + (i % 10) * 0.05, 2)))
            closing = Decimal(str(round(2.0 + ((i + 3) % 10) * 0.03, 2)))
            opening = Decimal(str(round(2.0 + ((i + 5) % 10) * 0.08, 2)))
            ev = 0.02 + (i % 5) * 0.01
            records.append(build_clv_record(
                event_id=f"evt_{i % 8}",
                market="h2h",
                outcome=["home", "away", "draw"][i % 3],
                bookmaker=["Pinnacle", "Bet365", "DraftKings"][i % 3],
                captured_odd=captured,
                captured_at=now - timedelta(hours=10 + (i % 12)),
                closing_odd=closing,
                closed_at=now - timedelta(hours=i % 3),
                opening_odd=opening,
                opening_at=now - timedelta(hours=24 + (i % 6)),
                simulated_ev=ev,
                simulated_kelly=0.02 + (i % 5) * 0.005,
                model_edge=ev + 0.01,
            ))

        report = generate_clv_report(records, "Integration Test")
        assert report.n_records == 50
        assert report.n_events <= 8
        assert report.n_bookmakers == 3
        assert report.overall_clv_pct != 0
        assert report.distribution is not None
        assert report.distribution.total_records == 50
        assert report.correlation is not None
        assert report.timing is not None
        assert len(report.by_bookmaker) == 3

        text = format_report_text(report)
        assert "Integration Test" in text or "CLV ANALYSIS REPORT" in text
