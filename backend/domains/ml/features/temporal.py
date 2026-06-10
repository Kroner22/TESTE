"""Temporal features: time-based and seasonality."""

import pandas as pd
import numpy as np
from .base import FeatureTransformer


class TemporalFeatures(FeatureTransformer):
    def __init__(self):
        super().__init__("temporal")

    def fit(self, matches: pd.DataFrame) -> "TemporalFeatures":
        self._fitted = True
        self._feature_names = [
            "hour", "day_of_week", "month", "season_progress",
            "days_since_season_start", "is_weekend", "is_midweek",
            "fixture_congestion", "days_since_last_match_home",
            "days_since_last_match_away",
        ]
        return self

    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("fit must be called before transform")
        df = matches.copy()
        result = pd.DataFrame(index=df.index)

        if "date" in df.columns:
            dates = pd.to_datetime(df["date"])
        else:
            dates = pd.Timestamp.now()
            dates = pd.Series([dates] * len(df), index=df.index)

        result["hour"] = dates.dt.hour
        result["day_of_week"] = dates.dt.dayofweek
        result["month"] = dates.dt.month
        result["season_progress"] = dates.dt.dayofyear / 365.0

        result["is_weekend"] = (dates.dt.dayofweek >= 5).astype(float)
        result["is_midweek"] = dates.dt.dayofweek.isin([1, 2, 3]).astype(float)

        if "season_start" in df.columns:
            season_start = pd.to_datetime(df["season_start"])
            result["days_since_season_start"] = (dates - season_start).dt.days.clip(0, 365)
        else:
            result["days_since_season_start"] = dates.dt.dayofyear

        if "fixture_congestion" in df.columns:
            result["fixture_congestion"] = df["fixture_congestion"]
        else:
            result["fixture_congestion"] = 0.0

        result["days_since_last_match_home"] = df.get("home_days_since_last", result["days_since_season_start"])
        result["days_since_last_match_away"] = df.get("away_days_since_last", result["days_since_season_start"])

        return result.fillna(0)


class CyclingFeatures(FeatureTransformer):
    """Cyclical encoding of temporal features (sin/cos)."""

    def __init__(self):
        super().__init__("cycling")

    def fit(self, matches: pd.DataFrame) -> "CyclingFeatures":
        self._fitted = True
        self._feature_names = [
            "hour_sin", "hour_cos", "dow_sin", "dow_cos",
            "month_sin", "month_cos",
        ]
        return self

    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("fit must be called before transform")
        df = matches.copy()
        result = pd.DataFrame(index=df.index)

        if "date" in df.columns:
            dates = pd.to_datetime(df["date"])
        else:
            dates = pd.Timestamp.now()
            dates = pd.Series([dates] * len(df), index=df.index)

        hour = dates.dt.hour
        dow = dates.dt.dayofweek
        month = dates.dt.month

        result["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        result["hour_cos"] = np.cos(2 * np.pi * hour / 24)
        result["dow_sin"] = np.sin(2 * np.pi * dow / 7)
        result["dow_cos"] = np.cos(2 * np.pi * dow / 7)
        result["month_sin"] = np.sin(2 * np.pi * month / 12)
        result["month_cos"] = np.cos(2 * np.pi * month / 12)

        return result.fillna(0)
