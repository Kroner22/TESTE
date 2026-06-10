from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from backend.domains.market_reality.models import (
    OddsTick, OddsTimeSeries, SteamMove, SteamStrength,
    DriftAnalysis, DriftType, VolatilityMetrics, VolatilityRegime,
    LiquidityEstimate, LiquidityClass, MarketPressure, MoveDirection,
    OddsMomentum, MarketSensitivity, BookmakerProfile, BookmakerStyle,
    MarketDistortion, DistortionType, MarketRealitySnapshot,
)
from backend.domains.market_reality.tracker import OddsTracker
from backend.domains.market_reality.drift import (
    analyze_drift, calculate_closing_line_value, detect_market_direction,
)
from backend.domains.market_reality.steam import (
    detect_steam_moves, detect_steam_across_bookmakers,
)
from backend.domains.market_reality.volatility import (
    compute_volatility, cross_series_volatility,
)
from backend.domains.market_reality.liquidity import (
    estimate_liquidity, aggregate_liquidity,
)
from backend.domains.market_reality.pressure import (
    analyze_pressure, detect_steam_pressure,
)
from backend.domains.market_reality.momentum import (
    compute_momentum, momentum_divergence,
)
from backend.domains.market_reality.sensitivity import (
    analyze_sensitivity,
)
from backend.domains.market_reality.bookmaker import (
    analyze_bookmaker, compare_bookmaker_pairs,
)
from backend.domains.market_reality.engine import (
    MarketRealityEngine, MarketRealityConfig,
)


# ─── Helpers ─────────────────────────────────────────────────────

def make_tick(event="e1", market="h2h", outcome="home", bk="Pinnacle",
              odd=Decimal("2.0"), ts=None, opening=False, closing=False):
    return OddsTick(
        event_id=event, market=market, outcome=outcome,
        bookmaker=bk, odd=odd,
        timestamp=ts or datetime.now(timezone.utc),
        is_opening=opening, is_closing=closing,
    )


def make_series(event="e1", market="h2h", outcome="home", bk="Pinnacle",
                odds=None, base_ts=None, interval_hours=1):
    if odds is None:
        odds = [Decimal("2.0"), Decimal("2.1"), Decimal("1.95")]
    base = base_ts or datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    ticks = []
    for i, odd in enumerate(odds):
        ticks.append(OddsTick(
            event_id=event, market=market, outcome=outcome,
            bookmaker=bk, odd=odd,
            timestamp=base + timedelta(hours=i * interval_hours),
            is_opening=(i == 0),
            is_closing=(i == len(odds) - 1),
        ))
    return OddsTimeSeries(event, market, outcome, bk, ticks)


def make_rapid_series(event="e1", market="h2h", outcome="home", bk="Pinnacle",
                      odds=None, interval_seconds=300):
    if odds is None:
        odds = [Decimal("2.0"), Decimal("2.1"), Decimal("2.2")]
    base = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    ticks = []
    for i, odd in enumerate(odds):
        ticks.append(OddsTick(
            event_id=event, market=market, outcome=outcome,
            bookmaker=bk, odd=odd,
            timestamp=base + timedelta(seconds=i * interval_seconds),
            is_opening=(i == 0),
            is_closing=(i == len(odds) - 1),
        ))
    return OddsTimeSeries(event, market, outcome, bk, ticks)


# ─── Models ──────────────────────────────────────────────────────

class TestModels:
    def test_odds_tick_implied_prob(self):
        t = make_tick(odd=Decimal("2.0"))
        assert t.implied_prob == 0.5

    def test_odds_tick_implied_prob_below_one(self):
        t = make_tick(odd=Decimal("0.5"))
        assert t.implied_prob == 0.0

    def test_odds_tick_change_from(self):
        t1 = make_tick(odd=Decimal("2.0"))
        t2 = make_tick(odd=Decimal("2.2"))
        change = t2.change_from(t1)
        assert change == pytest.approx(10.0, rel=0.1)

    def test_time_series_opening_odd(self):
        s = make_series(odds=[Decimal("1.5"), Decimal("1.6"), Decimal("1.7")])
        assert s.opening_odd == Decimal("1.5")

    def test_time_series_closing_odd(self):
        s = make_series(odds=[Decimal("1.5"), Decimal("1.6"), Decimal("1.7")])
        assert s.closing_odd == Decimal("1.7")

    def test_time_series_no_opening(self):
        base = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        ticks = [OddsTick("e1","h2h","home","Pinnacle",Decimal("2.0"),base+timedelta(hours=i)) for i in range(3)]
        s = OddsTimeSeries("e1","h2h","home","Pinnacle",ticks)
        assert s.opening_odd is None

    def test_time_series_duration(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.1"), Decimal("1.95")])
        assert s.duration_hours == pytest.approx(2.0, rel=0.1)

    def test_time_series_closing_line_value(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.1"), Decimal("2.2")])
        clv = s.closing_line_value()
        assert clv is not None and clv > 0

    def test_steam_move_magnitude(self):
        sm = SteamMove("e1","h2h","home","Pinnacle",Decimal("2.0"),Decimal("2.5"),
                       datetime.now(timezone.utc),datetime.now(timezone.utc),10,25.0,
                       SteamStrength.STRONG,5.0,True)
        assert sm.magnitude == 25.0

    def test_drift_direction_up(self):
        d = DriftAnalysis("e1","h2h","home",Decimal("2.0"),Decimal("2.2"),10.0,
                          DriftType.SUSTAINED,10.0,0.5,0.3,False,0)
        assert d.direction == MoveDirection.UP

    def test_drift_direction_flat(self):
        d = DriftAnalysis("e1","h2h","home",Decimal("2.0"),Decimal("2.0"),0.05,
                          DriftType.NONE,0.05,0.1,0.1,False,0)
        assert d.direction == MoveDirection.FLAT

    def test_volatility_metrics_calm(self):
        v = VolatilityMetrics("e1","h2h",1.0,0.5,2.0,0.5,VolatilityRegime.CALM,5.0,10,2,2.0)
        assert v.is_calm
        assert not v.is_chaotic

    def test_liquidity_estimate_deep(self):
        l = LiquidityEstimate("e1","h2h","home",LiquidityClass.DEEP,80,0.1,0.5,50,1.0,0.9)
        assert l.is_deep
        assert not l.is_fragile

    def test_market_pressure_bias_label(self):
        p = MarketPressure("e1","h2h",0.5,0.8,0.7,12.5,MoveDirection.UP,True,["Pinnacle"])
        assert p.bias_label == "chasing"

    def test_market_pressure_bias_negative(self):
        p = MarketPressure("e1","h2h",0.5,-0.8,0.7,-12.5,MoveDirection.DOWN,True,["Pinnacle"])
        assert p.bias_label == "fading"

    def test_market_sensitivity_elastic(self):
        ms = MarketSensitivity("e1","h2h",{},0.5,0.8,0.3,False,60)
        assert ms.is_elastic

    def test_snapshot_has_steam(self):
        snap = MarketRealitySnapshot("e1","h2h",datetime.now(timezone.utc))
        snap.steam_moves.append(
            SteamMove("e1","h2h","home","Pinnacle",Decimal("2.0"),Decimal("2.5"),
                     datetime.now(timezone.utc),datetime.now(timezone.utc),10,25.0,
                     SteamStrength.EXTREME,5.0,True)
        )
        assert snap.has_steam

    def test_snapshot_has_distortion(self):
        snap = MarketRealitySnapshot("e1","h2h",datetime.now(timezone.utc))
        snap.distortions.append(
            MarketDistortion("e1","h2h",DistortionType.OVERREACTION,0.7,"test",
                           datetime.now(timezone.utc),0.9,["Pinnacle"])
        )
        assert snap.has_distortion


# ─── Tracker ─────────────────────────────────────────────────────

class TestOddsTracker:
    def test_record_tick(self):
        tr = OddsTracker()
        t = tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        assert t.event_id == "e1"
        assert tr.series_count == 1

    def test_get_series(self):
        tr = OddsTracker()
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        s = tr.get_series("e1","h2h","home","Pinnacle")
        assert s is not None
        assert len(s.ticks) == 1

    def test_get_series_missing(self):
        tr = OddsTracker()
        assert tr.get_series("e1","h2h","home","Pinnacle") is None

    def test_get_series_for_event(self):
        tr = OddsTracker()
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        tr.record_tick("e1","spreads","home","Bet365",Decimal("1.8"))
        tr.record_tick("e2","h2h","away","DraftKings",Decimal("3.0"))
        series = tr.get_series_for_event("e1")
        assert len(series) == 2

    def test_get_series_for_market(self):
        tr = OddsTracker()
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        tr.record_tick("e1","h2h","away","Bet365",Decimal("3.0"))
        tr.record_tick("e1","spreads","home","Pinnacle",Decimal("1.8"))
        series = tr.get_series_for_market("e1","h2h")
        assert len(series) == 2

    def test_latest_tick(self):
        tr = OddsTracker()
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.2"))
        t = tr.latest_tick("e1","h2h","home","Pinnacle")
        assert t is not None and t.odd == Decimal("2.2")

    def test_remove_series(self):
        tr = OddsTracker()
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        tr.record_tick("e2","h2h","away","Bet365",Decimal("3.0"))
        removed = tr.remove_series("e1")
        assert removed == 1
        assert tr.series_count == 1

    def test_clear(self):
        tr = OddsTracker()
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        tr.clear()
        assert tr.series_count == 0

    def test_ticks_since(self):
        tr = OddsTracker()
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        later = datetime.now(timezone.utc) + timedelta(hours=1)
        tr.record_tick("e1","h2h","home","Pinnacle",Decimal("2.2"),timestamp=later)
        since = datetime.now(timezone.utc) + timedelta(minutes=30)
        ticks = tr.ticks_since("e1","h2h",since)
        assert len(ticks) == 1

    def test_build_synthetic_series(self):
        tr = OddsTracker()
        s = tr.build_synthetic_series("e1","h2h","home","Pinnacle",
                                       Decimal("2.0"), Decimal("2.5"), num_ticks=10)
        assert len(s.ticks) == 10
        assert s.opening_odd == Decimal("2.0")
        assert s.closing_odd == Decimal("2.5")


# ─── Drift ───────────────────────────────────────────────────────

class TestDrift:
    def test_analyze_drift_basic(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.5")])
        d = analyze_drift(s)
        assert d is not None
        assert d.drift_pct > 0
        assert d.closing_line_value_pct is not None

    def test_analyze_drift_down(self):
        s = make_series(odds=[Decimal("3.0"), Decimal("2.8"), Decimal("2.5")])
        d = analyze_drift(s)
        assert d is not None and d.drift_pct < 0

    def test_analyze_drift_insufficient_ticks(self):
        s = make_series(odds=[Decimal("2.0")])
        d = analyze_drift(s)
        assert d is None

    def test_analyze_drift_no_opening(self):
        base = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        ticks = [OddsTick("e1","h2h","home","Pinnacle",Decimal("2.0"),base+timedelta(hours=i)) for i in range(3)]
        s = OddsTimeSeries("e1","h2h","home","Pinnacle",ticks)
        d = analyze_drift(s)
        assert d is None

    def test_closing_line_value(self):
        clv = calculate_closing_line_value(Decimal("2.0"), Decimal("2.5"))
        assert clv == pytest.approx(25.0, rel=0.1)

    def test_closing_line_value_zero_odd(self):
        assert calculate_closing_line_value(Decimal("0"), Decimal("2.0")) is None

    def test_detect_market_direction(self):
        s1 = make_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.5")])
        s2 = make_series(event="e1", outcome="away", odds=[Decimal("3.0"), Decimal("2.8"), Decimal("2.6")])
        dirs = detect_market_direction([s1, s2])
        assert dirs["home"] == MoveDirection.UP
        assert dirs["away"] == MoveDirection.DOWN

    def test_drift_reversal_detected(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.3"), Decimal("2.5"),
                               Decimal("2.2"), Decimal("2.1"), Decimal("2.4")])
        d = analyze_drift(s)
        assert d is not None and d.num_reversals > 0


# ─── Steam ───────────────────────────────────────────────────────

class TestSteam:
    def test_detect_steam(self):
        s = make_rapid_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.6"),
                                     Decimal("3.2"), Decimal("4.0")],
                              interval_seconds=60)
        moves = detect_steam_moves(s, min_change_pct=0.5, min_velocity=0.1)
        assert len(moves) > 0

    def test_steam_strength_strong(self):
        s = make_rapid_series(odds=[Decimal("2.0"), Decimal("2.3"), Decimal("2.8"),
                                     Decimal("3.5"), Decimal("4.5")],
                              interval_seconds=30)
        moves = detect_steam_moves(s, min_change_pct=1.0, min_velocity=0.5)
        strong = [m for m in moves if m.strength == SteamStrength.MODERATE]
        assert len(moves) > 0

    def test_steam_across_bookmakers(self):
        s1 = make_rapid_series(odds=[Decimal("2.0"), Decimal("2.3"), Decimal("2.8")],
                               interval_seconds=60)
        s2 = make_rapid_series(bk="Bet365", odds=[Decimal("2.0"), Decimal("2.3"), Decimal("2.8")],
                               interval_seconds=60)
        moves = detect_steam_across_bookmakers([s1, s2])
        assert len(moves) >= 2


# ─── Volatility ──────────────────────────────────────────────────

class TestVolatility:
    def test_compute_volatility_basic(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("1.8"),
                               Decimal("2.5"), Decimal("2.0")])
        v = compute_volatility(s)
        assert v.num_moves > 0
        assert v.overall_std > 0

    def test_compute_volatility_calm(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.01"), Decimal("2.0"),
                               Decimal("2.01")])
        v = compute_volatility(s)
        assert v.regime in (VolatilityRegime.CALM, VolatilityRegime.NORMAL)

    def test_compute_volatility_few_ticks(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.1")])
        v = compute_volatility(s)
        assert v.regime == VolatilityRegime.CALM

    def test_compute_volatility_large_moves_counted(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.5"), Decimal("3.0"),
                               Decimal("2.0"), Decimal("1.5")])
        v = compute_volatility(s, large_move_threshold_pct=1.0)
        assert v.large_moves_count > 0

    def test_cross_series_volatility(self):
        s1 = make_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.4")])
        s2 = make_series(outcome="away", odds=[Decimal("3.0"), Decimal("2.8"), Decimal("2.6")])
        vols = cross_series_volatility([s1, s2])
        assert "home" in vols
        assert "away" in vols


# ─── Liquidity ──────────────────────────────────────────────────

class TestLiquidity:
    def test_estimate_liquidity_basic(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.01"), Decimal("2.0"),
                               Decimal("2.01"), Decimal("2.0")])
        l = estimate_liquidity(s)
        assert l.avg_tick_size > 0
        assert l.liquidity_class in LiquidityClass.__members__.values()

    def test_estimate_liquidity_fragile_few_ticks(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.1")])
        l = estimate_liquidity(s, min_ticks=5)
        assert l.liquidity_class == LiquidityClass.FRAGILE

    def test_estimate_liquidity_deep_small_moves(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.005"), Decimal("2.01"),
                               Decimal("2.005"), Decimal("2.0"), Decimal("2.005"),
                               Decimal("2.01"), Decimal("2.005"), Decimal("2.0")])
        l = estimate_liquidity(s)
        assert l.depth_score > 30

    def test_aggregate_liquidity(self):
        l1 = LiquidityEstimate("e1","h2h","home",LiquidityClass.DEEP,80,0.1,0.5,50,1.0,0.9)
        l2 = LiquidityEstimate("e1","h2h","away",LiquidityClass.MODERATE,50,0.3,1.0,20,0.5,0.7)
        agg = aggregate_liquidity([l1, l2])
        assert "deep" in agg
        assert "moderate" in agg


# ─── Pressure ────────────────────────────────────────────────────

class TestPressure:
    def test_analyze_pressure_basic(self):
        s1 = make_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.5"),
                                Decimal("2.8"), Decimal("3.0")])
        s2 = make_series(outcome="away", odds=[Decimal("3.0"), Decimal("2.7"), Decimal("2.5"),
                                                Decimal("2.3"), Decimal("2.0")])
        p = analyze_pressure([s1, s2])
        assert p is not None
        assert isinstance(p.pressure_score, float)

    def test_analyze_pressure_insufficient_data(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.1")])
        p = analyze_pressure([s], min_ticks_per_series=5)
        assert p is None

    def test_detect_steam_pressure(self):
        base = datetime.now(timezone.utc)
        ticks = [
            make_tick(odd=Decimal("2.0"), ts=base + timedelta(seconds=i*10))
            for i in range(10)
        ]
        result = detect_steam_pressure(ticks, window_minutes=5.0, acceleration_threshold=0.1)
        assert isinstance(result, bool)

    def test_detect_steam_pressure_few_ticks(self):
        ticks = [make_tick(odd=Decimal("2.0")), make_tick(odd=Decimal("2.1"))]
        assert not detect_steam_pressure(ticks)


# ─── Momentum ────────────────────────────────────────────────────

class TestMomentum:
    def test_compute_momentum_basic(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.4"),
                               Decimal("2.6"), Decimal("2.8"), Decimal("3.0"),
                               Decimal("3.2"), Decimal("3.5"), Decimal("3.8")])
        m = compute_momentum(s, short_window=3, long_window=8)
        assert m is not None
        assert m.is_rising
        assert m.momentum_value > 0

    def test_compute_momentum_insufficient_ticks(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.1")])
        m = compute_momentum(s)
        assert m is None

    def test_momentum_strength_label(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.5"), Decimal("3.0"),
                               Decimal("3.5"), Decimal("4.0"), Decimal("4.5"),
                               Decimal("5.0"), Decimal("5.5"), Decimal("6.0")])
        m = compute_momentum(s, short_window=3, long_window=8)
        assert m is not None
        assert m.strength in ("weak", "moderate", "strong", "extreme")

    def test_momentum_divergence(self):
        s1 = make_series(odds=[Decimal("2.0"), Decimal("2.5"), Decimal("3.0"),
                                Decimal("3.5"), Decimal("4.0")])
        s2 = make_series(outcome="away", odds=[Decimal("5.0"), Decimal("4.5"), Decimal("4.0"),
                                                Decimal("3.5"), Decimal("3.0")])
        divs = momentum_divergence([s1, s2])
        assert isinstance(divs, list)


# ─── Sensitivity ─────────────────────────────────────────────────

class TestSensitivity:
    def test_analyze_sensitivity_basic(self):
        s1 = make_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.4"),
                                Decimal("2.6"), Decimal("2.8")])
        s2 = make_series(outcome="away", odds=[Decimal("3.0"), Decimal("2.9"), Decimal("2.8"),
                                                Decimal("2.7"), Decimal("2.6")])
        ms = analyze_sensitivity([s1, s2])
        assert ms is not None
        assert ms.sensitivity_score > 0

    def test_analyze_sensitivity_insufficient_series(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.1"), Decimal("2.2")])
        ms = analyze_sensitivity([s], min_ticks=3)
        assert ms is None

    def test_analyze_sensitivity_cross_correlation(self):
        s1 = make_series(odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.4"),
                                Decimal("2.6"), Decimal("2.8")])
        s2 = make_series(outcome="away", odds=[Decimal("3.0"), Decimal("2.8"), Decimal("2.6"),
                                                Decimal("2.4"), Decimal("2.2")])
        ms = analyze_sensitivity([s1, s2])
        assert ms is not None
        assert len(ms.cross_correlation) > 0


# ─── Bookmaker ───────────────────────────────────────────────────

class TestBookmaker:
    def test_analyze_bookmaker_basic(self):
        s1 = make_series(odds=[Decimal("2.0"), Decimal("2.1"), Decimal("2.2"),
                                Decimal("2.3"), Decimal("2.4")])
        s2 = make_series(bk="Bet365", odds=[Decimal("2.0"), Decimal("2.15"), Decimal("2.25"),
                                              Decimal("2.35"), Decimal("2.45")])
        report = analyze_bookmaker([s1, s2])
        assert "Pinnacle" in report.profiles
        assert "Bet365" in report.profiles

    def test_analyze_bookmaker_style(self):
        fast = make_series(bk="FastBk", odds=[Decimal("2.0"), Decimal("2.2"), Decimal("2.4"),
                                               Decimal("2.6"), Decimal("2.8")])
        report = analyze_bookmaker([fast])
        profile = report.profiles.get("FastBk")
        assert profile is not None
        assert isinstance(profile.style, BookmakerStyle)

    def test_compare_bookmaker_pairs(self):
        p1 = BookmakerProfile("Pinnacle", BookmakerStyle.AGGRESSIVE, 10, 2.0, 0.03, 0.8, 0.6, 0.7, 5)
        p2 = BookmakerProfile("Bet365", BookmakerStyle.CONSERVATIVE, 60, 0.5, 0.05, 0.2, 0.1, 0.9, 5)
        comps = compare_bookmaker_pairs({"Pinnacle": p1, "Bet365": p2})
        assert len(comps) == 1
        assert comps[0]["faster"] == "Pinnacle"

    def test_bookmaker_report_structure(self):
        s = make_series(odds=[Decimal("2.0"), Decimal("2.1"), Decimal("2.2"),
                               Decimal("2.3"), Decimal("2.4")])
        report = analyze_bookmaker([s])
        assert report.avg_reaction_time > 0
        assert report.most_aggressive is not None or report.most_conservative is not None


# ─── Engine ──────────────────────────────────────────────────────

class TestMarketRealityEngine:
    def test_record_tick(self):
        eng = MarketRealityEngine()
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        assert "e1" in eng.tracked_events

    def test_snapshot_basic(self):
        eng = MarketRealityEngine()
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"),is_opening=True)
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.2"))
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.5"),is_closing=True)
        snap = eng.snapshot("e1","h2h")
        assert snap is not None
        assert snap.drift is not None
        assert snap.volatility is not None

    def test_snapshot_no_data(self):
        eng = MarketRealityEngine()
        assert eng.snapshot("e1","h2h") is None

    def test_full_report(self):
        eng = MarketRealityEngine()
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"),is_opening=True)
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.2"))
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.5"),is_closing=True)
        eng.record_tick("e1","h2h","away","Pinnacle",Decimal("3.0"),is_opening=True)
        eng.record_tick("e1","h2h","away","Pinnacle",Decimal("2.7"))
        eng.record_tick("e1","h2h","away","Pinnacle",Decimal("2.5"),is_closing=True)
        report = eng.full_report("e1","h2h")
        assert report is not None
        assert "snapshot" in report
        assert "bookmakers" in report
        assert "aggregates" in report

    def test_full_report_no_data(self):
        eng = MarketRealityEngine()
        assert eng.full_report("e1","h2h") is None

    def test_clear_event(self):
        eng = MarketRealityEngine()
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        eng.record_tick("e2","h2h","away","Bet365",Decimal("3.0"))
        eng.clear_event("e1")
        assert "e1" not in eng.tracked_events
        assert "e2" in eng.tracked_events

    def test_clear_all(self):
        eng = MarketRealityEngine()
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"))
        eng.clear_all()
        assert eng.tracked_events == []

    def test_snapshot_with_distortions(self):
        eng = MarketRealityEngine(config=MarketRealityConfig(steam_min_change_pct=0.01, steam_min_velocity=0.01))
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("2.0"),is_opening=True)
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("3.5"))
        eng.record_tick("e1","h2h","home","Pinnacle",Decimal("5.0"),is_closing=True)
        snap = eng.snapshot("e1","h2h")
        assert snap is not None
        assert len(snap.distortions) > 0

    def test_config_custom(self):
        cfg = MarketRealityConfig(min_ticks_for_analysis=100, steam_min_change_pct=5.0)
        assert cfg.min_ticks_for_analysis == 100
        assert cfg.steam_min_change_pct == 5.0


# ─── Integration ─────────────────────────────────────────────────

class TestIntegration:
    def test_track_to_snapshot_to_report(self):
        eng = MarketRealityEngine()
        base = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
        odds_home = [Decimal("2.0"), Decimal("2.1"), Decimal("2.3"),
                     Decimal("2.5"), Decimal("2.8")]
        odds_away = [Decimal("3.0"), Decimal("2.8"), Decimal("2.6"),
                     Decimal("2.4"), Decimal("2.2")]
        for i in range(5):
            eng.record_tick("e1","h2h","home","Pinnacle",odds_home[i],
                           timestamp=base+timedelta(hours=i),
                           is_opening=(i==0), is_closing=(i==4))
            eng.record_tick("e1","h2h","away","Pinnacle",odds_away[i],
                           timestamp=base+timedelta(hours=i),
                           is_opening=(i==0), is_closing=(i==4))

        snap = eng.snapshot("e1","h2h")
        assert snap is not None
        assert snap.drift is not None
        assert snap.volatility is not None
        assert snap.liquidity is not None

        report = eng.full_report("e1","h2h")
        assert report is not None
        assert report["snapshot"]["drift"] is not None
        assert len(report["bookmakers"]["report"].profiles) == 1

    def test_synthetic_data_roundtrip(self):
        eng = MarketRealityEngine()
        s = eng.tracker.build_synthetic_series(
            "e1","h2h","home","Pinnacle",
            Decimal("2.0"), Decimal("3.0"), num_ticks=20
        )
        assert len(s.ticks) == 20
        snap = eng.snapshot("e1","h2h")
        assert snap is not None
        assert snap.drift is not None

    def test_all_components_non_null(self):
        eng = MarketRealityEngine()
        base = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
        for i in range(10):
            odd = Decimal(str(round(2.0 + i * 0.2, 2)))
            eng.record_tick("e1","h2h","home","Pinnacle",odd,
                           timestamp=base+timedelta(hours=i),
                           is_opening=(i==0), is_closing=(i==9))
            away_odd = Decimal(str(round(3.0 - i * 0.15, 2)))
            eng.record_tick("e1","h2h","away","Pinnacle",away_odd,
                           timestamp=base+timedelta(hours=i),
                           is_opening=(i==0), is_closing=(i==9))
        snap = eng.snapshot("e1","h2h")
        assert snap is not None
        assert snap.drift is not None
        assert snap.volatility is not None
        assert snap.liquidity is not None
        assert snap.pressure is not None
        assert snap.momentum is not None
        assert snap.sensitivity is not None

    def test_multiple_events_independent(self):
        eng = MarketRealityEngine()
        for eid in ("e1", "e2"):
            eng.record_tick(eid,"h2h","home","Pinnacle",Decimal("2.0"),is_opening=True)
            eng.record_tick(eid,"h2h","home","Pinnacle",Decimal("2.2"))
            eng.record_tick(eid,"h2h","home","Pinnacle",Decimal("2.5"),is_closing=True)
        assert len(eng.tracked_events) == 2
        s1 = eng.snapshot("e1","h2h")
        s2 = eng.snapshot("e2","h2h")
        assert s1 is not None and s2 is not None
