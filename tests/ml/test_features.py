"""Tests for feature transformers."""

import pandas as pd
import numpy as np
import pytest
from backend.domains.ml.features.historical import RollingAverages, StreakFeatures
from backend.domains.ml.features.market import MarketFeatures, OddsDistortionDetector
from backend.domains.ml.features.team import TeamFeatures, VenueFeatures
from backend.domains.ml.features.temporal import TemporalFeatures, CyclingFeatures


def _make_match_df(n=20):
    teams = [f"Team_{i}" for i in range(6)]
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="7D")
    data = []
    for i in range(n):
        home = teams[i % len(teams)]
        away = teams[(i + 2) % len(teams)]
        if home == away:
            away = teams[(i + 3) % len(teams)]
        data.append({
            "match_id": f"M{i:03d}",
            "date": dates[i],
            "home_team": home,
            "away_team": away,
            "home_goals": np.random.randint(0, 4),
            "away_goals": np.random.randint(0, 4),
            "home_odd": round(np.random.uniform(1.5, 5.0), 2),
            "away_odd": round(np.random.uniform(1.5, 5.0), 2),
            "draw_odd": round(np.random.uniform(2.5, 4.0), 2),
            "home_squad_value": np.random.uniform(10, 500),
            "away_squad_value": np.random.uniform(10, 500),
        })
    return pd.DataFrame(data)


class TestRollingAverages:
    def test_fit_creates_feature_names(self):
        df = _make_match_df()
        ra = RollingAverages(windows=[5, 10])
        ra.fit(df)
        names = ra.get_feature_names()
        assert len(names) > 0
        assert any("rolling" in n for n in names)

    def test_transform_returns_valid_shape(self):
        df = _make_match_df(30)
        ra = RollingAverages(windows=[5])
        result = ra.fit_transform(df)
        assert not result.empty
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        assert len(numeric_cols) > 0

    def test_not_fitted_raises(self):
        ra = RollingAverages()
        with pytest.raises(RuntimeError):
            ra.transform(pd.DataFrame())


class TestStreakFeatures:
    def test_streaks_initialized(self):
        df = _make_match_df(30)
        sf = StreakFeatures()
        result = sf.fit_transform(df)
        assert "home_win_streak" in result.columns
        assert "away_win_streak" in result.columns
        assert "home_h2h_advantage" in result.columns

    def test_streaks_non_negative(self):
        df = _make_match_df(30)
        sf = StreakFeatures()
        result = sf.fit_transform(df)
        for col in ["home_win_streak", "home_lose_streak"]:
            assert (result[col] >= 0).all()


class TestMarketFeatures:
    def test_implied_probabilities(self):
        df = pd.DataFrame({"home_odd": [2.0], "away_odd": [2.0], "draw_odd": [4.0]})
        mf = MarketFeatures()
        result = mf.fit_transform(df)
        assert result["implied_home_prob"].iloc[0] == 0.5

    def test_overround_non_negative(self):
        df = pd.DataFrame({
            "home_odd": [2.0, 1.5], "away_odd": [2.0, 3.0], "draw_odd": [4.0, 4.5],
        })
        mf = MarketFeatures()
        result = mf.fit_transform(df)
        assert (result["market_overround"] >= 0).all()


class TestOddsDistortionDetector:
    def test_no_arb_on_normal_market(self):
        df = pd.DataFrame({"home_odd": [2.0], "away_odd": [2.0], "draw_odd": [4.0]})
        odd = OddsDistortionDetector()
        result = odd.fit_transform(df)
        assert result["arbitrage_flag"].iloc[0] == 0.0

    def test_detects_arbitrage(self):
        df = pd.DataFrame({"home_odd": [2.50], "away_odd": [1.70]})
        odd = OddsDistortionDetector()
        result = odd.fit_transform(df)
        assert result["value_index"].iloc[0] > 0


class TestTeamFeatures:
    def test_rest_days_calculated(self):
        df = _make_match_df(10)
        tf = TeamFeatures()
        result = tf.fit_transform(df)
        assert "home_rest_days" in result.columns
        assert (result["home_rest_days"] >= 1).all()


class TestVenueFeatures:
    def test_basic_defaults(self):
        df = pd.DataFrame({"home_advantage": [0.6], "attendance": [50000], "stadium_capacity": [60000]})
        vf = VenueFeatures()
        result = vf.fit_transform(df)
        assert result["home_advantage_index"].iloc[0] == 0.6
        assert result["home_attendance_ratio"].iloc[0] == pytest.approx(0.8333, rel=1e-2)


class TestTemporalFeatures:
    def test_hour_and_dow(self):
        df = pd.DataFrame({"date": ["2024-03-15 20:00:00", "2024-03-16 15:00:00"]})
        tf = TemporalFeatures()
        result = tf.fit_transform(df)
        assert result["hour"].iloc[0] == 20
        assert result["day_of_week"].iloc[0] == 4
        assert result["is_weekend"].iloc[1] == 1.0


class TestCyclingFeatures:
    def test_sin_cos_output(self):
        df = pd.DataFrame({"date": ["2024-06-01 12:00:00"]})
        cf = CyclingFeatures()
        result = cf.fit_transform(df)
        assert "hour_sin" in result.columns
        assert "hour_cos" in result.columns
        assert "month_sin" in result.columns
        assert -1 <= result["hour_sin"].iloc[0] <= 1
