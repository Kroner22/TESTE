"""Team-specific features: squad value, rest days, venue, travel."""

import pandas as pd
import numpy as np
from .base import FeatureTransformer


class TeamFeatures(FeatureTransformer):
    def __init__(self):
        super().__init__("team")

    def fit(self, matches: pd.DataFrame) -> "TeamFeatures":
        self._fitted = True
        self._feature_names = [
            "home_rest_days", "away_rest_days", "rest_advantage",
            "home_squad_value", "away_squad_value", "squad_value_ratio",
            "home_travel_distance", "away_travel_distance",
            "home_is_top5", "away_is_top5",
            "home_avg_age", "away_avg_age",
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

        if "home_team" in df.columns and "away_team" in df.columns:
            all_teams = pd.unique(df[["home_team", "away_team"]].values.ravel())
        else:
            result["home_rest_days"] = 7.0
            result["away_rest_days"] = 7.0
            result["rest_advantage"] = 0.0
            for c in self._feature_names[3:]:
                result[c] = 0.0
            return result

        team_last_match: dict[str, pd.Timestamp] = {}
        home_rest = []
        away_rest = []

        for i, row in df.iterrows():
            h, a = row["home_team"], row["away_team"]
            d = pd.to_datetime(row["date"]) if "date" in row else pd.Timestamp.now()

            home_rest.append((d - team_last_match.get(h, d - pd.Timedelta(days=7))).days
                             if h in team_last_match else 7.0)
            away_rest.append((d - team_last_match.get(a, d - pd.Timedelta(days=7))).days
                             if a in team_last_match else 7.0)

            team_last_match[h] = d
            team_last_match[a] = d

        result["home_rest_days"] = np.clip(home_rest, 1, 30)
        result["away_rest_days"] = np.clip(away_rest, 1, 30)
        result["rest_advantage"] = (np.array(home_rest) - np.array(away_rest)) / 7.0

        result["home_squad_value"] = df.get("home_squad_value", 0)
        result["away_squad_value"] = df.get("away_squad_value", 0)

        hv = result["home_squad_value"].values
        av = result["away_squad_value"].values
        av_safe = np.where(av > 0, av, 1)
        svr = np.where(av > 0, hv / av_safe, 0)
        result["squad_value_ratio"] = np.log1p(np.abs(svr)) * np.sign(svr)

        result["home_travel_distance"] = df.get("home_travel_distance", 0)
        result["away_travel_distance"] = df.get("away_travel_distance", df.get("home_travel_distance", 0))
        result["home_is_top5"] = df.get("home_is_top5", 0)
        result["away_is_top5"] = df.get("away_is_top5", 0)
        result["home_avg_age"] = df.get("home_avg_age", 26.0)
        result["away_avg_age"] = df.get("away_avg_age", 26.0)

        return result.fillna(0)


class VenueFeatures(FeatureTransformer):
    def __init__(self):
        super().__init__("venue")

    def fit(self, matches: pd.DataFrame) -> "VenueFeatures":
        self._fitted = True
        self._feature_names = [
            "home_advantage_index", "home_attendance_ratio",
            "is_derby", "neutral_venue",
        ]
        return self

    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("fit must be called before transform")
        df = matches.copy()
        result = pd.DataFrame(index=df.index)

        ha = df.get("home_advantage")
        if ha is None:
            result["home_advantage_index"] = 0.5
        else:
            result["home_advantage_index"] = ha.clip(0, 1) if hasattr(ha, "clip") else float(ha)

        att = df.get("attendance", 0)
        cap = df.get("stadium_capacity", 1)
        if hasattr(cap, "clip"):
            cap = cap.clip(lower=1)
        else:
            cap = max(float(cap), 1)
        result["home_attendance_ratio"] = att / cap

        result["is_derby"] = df.get("is_derby", 0)
        result["neutral_venue"] = df.get("neutral_venue", 0)

        return result.fillna(0)
