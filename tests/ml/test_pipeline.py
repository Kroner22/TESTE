"""Tests for pipeline: feature pipeline, trainer, validator, config."""

import pandas as pd
import numpy as np
import pytest

from backend.domains.ml.pipeline.feature_pipeline import FeaturePipeline, prepare_target
from backend.domains.ml.pipeline.validator import TimeSeriesCV, PurgedCV
from backend.domains.ml.models import FeatureConfig, TargetType


def _make_test_df(n=20):
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
            "match_id": f"M{i:03d}", "date": dates[i],
            "home_team": home, "away_team": away,
            "home_goals": np.random.randint(0, 4), "away_goals": np.random.randint(0, 4),
            "home_odd": round(np.random.uniform(1.5, 5.0), 2),
            "away_odd": round(np.random.uniform(1.5, 5.0), 2),
            "draw_odd": round(np.random.uniform(2.5, 4.0), 2),
        })
    return pd.DataFrame(data)


class TestFeaturePipeline:
    def test_fit_transform_returns_dataframe(self):
        df = _make_test_df(30)
        fp = FeaturePipeline()
        result = fp.fit_transform(df)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 30

    def test_get_feature_names(self):
        df = _make_test_df(20)
        fp = FeaturePipeline(config=FeatureConfig(elaborated_features=False))
        fp.fit(df)
        names = fp.get_feature_names()
        assert len(names) > 5
        assert "home_h2h_advantage" in names

    def test_configurable_windows(self):
        config = FeatureConfig(historical_windows=[3, 7])
        fp = FeaturePipeline(config=config)
        df = _make_test_df(20)
        fp.fit(df)
        names = fp.get_feature_names()
        windows_3 = [n for n in names if "rolling_3" in n]
        assert len(windows_3) > 0


class TestPrepareTarget:
    def test_home_win(self):
        df = pd.DataFrame({"home_goals": [3, 1, 0], "away_goals": [1, 1, 2]})
        target = prepare_target(df, "home_win")
        assert target.tolist() == [1, 0, 0]

    def test_away_win(self):
        df = pd.DataFrame({"home_goals": [1, 0, 2], "away_goals": [2, 3, 2]})
        target = prepare_target(df, "away_win")
        assert target.tolist() == [1, 1, 0]

    def test_over_under(self):
        df = pd.DataFrame({"home_goals": [3, 0, 2], "away_goals": [2, 0, 0], "total_line": [2.5, 2.5, 2.5]})
        target_over = prepare_target(df, "over")
        target_under = prepare_target(df, "under")
        assert target_over.tolist() == [1, 0, 0]
        assert target_under.tolist() == [0, 1, 1]


class TestTimeSeriesCV:
    def test_split_returns_correct_number_of_folds(self):
        X = pd.DataFrame({"f1": range(100)})
        y = pd.Series(range(100))
        cv = TimeSeriesCV(n_folds=3)
        folds = list(cv.split(X, y))
        assert len(folds) == 3

    def test_no_leakage(self):
        X = pd.DataFrame({"f1": range(50)})
        y = pd.Series(range(50))
        cv = TimeSeriesCV(n_folds=5, embargo=0)
        for train_idx, test_idx in cv.split(X, y):
            assert max(train_idx) < min(test_idx)

    def test_purging(self):
        X = pd.DataFrame({"f1": range(50)})
        y = pd.Series(range(50))
        cv = TimeSeriesCV(n_folds=3, purge_window=2, embargo=0)
        for train_idx, test_idx in cv.split(X, y):
            assert max(train_idx, default=0) < min(test_idx)
