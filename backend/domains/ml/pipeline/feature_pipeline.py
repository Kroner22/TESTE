"""Feature orchestration pipeline — builds feature matrix from raw data."""

from typing import Optional
import pandas as pd
import numpy as np

from backend.domains.ml.features.base import FeatureTransformer
from backend.domains.ml.features.historical import RollingAverages, StreakFeatures
from backend.domains.ml.features.market import MarketFeatures, OddsDistortionDetector
from backend.domains.ml.features.team import TeamFeatures, VenueFeatures
from backend.domains.ml.features.temporal import TemporalFeatures, CyclingFeatures
from backend.domains.ml.models import FeatureConfig


class FeaturePipeline:
    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
        self.transformers: list[FeatureTransformer] = []
        self._build_transformers()

    def _build_transformers(self):
        self.transformers = [
            RollingAverages(windows=self.config.historical_windows,
                            decay=self.config.decay_factor),
            StreakFeatures(),
            MarketFeatures(),
            OddsDistortionDetector(),
            TeamFeatures(),
            VenueFeatures(),
            TemporalFeatures(),
            CyclingFeatures(),
        ]
        if self.config.elaborated_features:
            pass

    def fit(self, matches: pd.DataFrame) -> "FeaturePipeline":
        for t in self.transformers:
            t.fit(matches)
        return self

    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        frames = [matches.reset_index(drop=True)]
        for t in self.transformers:
            frames.append(t.transform(matches).reset_index(drop=True))
        combined = pd.concat(frames, axis=1)
        combined = combined.loc[:, ~combined.columns.duplicated()]
        return combined

    def fit_transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        return self.fit(matches).transform(matches)

    def get_feature_names(self) -> list[str]:
        names = []
        for t in self.transformers:
            names.extend(t.get_feature_names())
        return names

    def select_features(self, df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
        available = [c for c in feature_cols if c in df.columns]
        return df[available]


def prepare_target(df: pd.DataFrame, target_type: str = "home_win") -> pd.Series:
    if target_type == "home_win":
        return (df["home_goals"] > df["away_goals"]).astype(int)
    elif target_type == "away_win":
        return (df["away_goals"] > df["home_goals"]).astype(int)
    elif target_type == "over":
        total = df["home_goals"] + df["away_goals"]
        over_line = df.get("total_line", 2.5)
        return (total > over_line).astype(int)
    elif target_type == "under":
        total = df["home_goals"] + df["away_goals"]
        over_line = df.get("total_line", 2.5)
        return (total <= over_line).astype(int)
    return (df["home_goals"] > df["away_goals"]).astype(int)
