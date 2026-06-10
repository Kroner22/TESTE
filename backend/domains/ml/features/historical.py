"""Historical performance features: rolling averages, form, streaks, H2H."""

from typing import Optional
import pandas as pd
import numpy as np
from .base import FeatureTransformer


class RollingAverages(FeatureTransformer):
    def __init__(self, windows: list[int] | None = None, decay: float = 0.95):
        super().__init__("rolling_averages")
        self.windows = windows or [5, 10, 20, 38]
        self.decay = decay

    def fit(self, matches: pd.DataFrame) -> "RollingAverages":
        self._fitted = True
        cols = []
        for team_col in ["home_team", "away_team"]:
            for stat in ["goals_scored", "goals_conceded", "shots", "shots_target"]:
                for w in self.windows:
                    cols.append(f"{team_col}_{stat}_rolling_{w}")
                cols.append(f"{team_col}_{stat}_weighted")
            for w in self.windows:
                cols.append(f"{team_col}_points_rolling_{w}")
                cols.append(f"{team_col}_winrate_rolling_{w}")
            cols.append(f"{team_col}_points_weighted")
            cols.append(f"{team_col}_winrate_weighted")
            cols.append(f"{team_col}_form_rating")
        self._feature_names = cols
        return self

    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("fit must be called before transform")
        df = matches.copy()
        if "date" not in df.columns:
            df["date"] = pd.Timestamp.now()
        df = df.sort_values("date")

        for team_col, stat_col in [("home_team", "home_goals"), ("away_team", "away_goals")]:
            opp_col = "away_team" if team_col == "home_team" else "home_team"
            opp_goals = "away_goals" if team_col == "home_team" else "home_goals"
            df[f"{team_col}_goals_scored"] = df[stat_col]
            df[f"{team_col}_goals_conceded"] = df[opp_goals]
            df[f"{team_col}_points"] = np.where(
                df[stat_col] > df[opp_goals], 3,
                np.where(df[stat_col] == df[opp_goals], 1, 0),
            )
            df[f"{team_col}_win"] = (df[stat_col] > df[opp_goals]).astype(float)

        all_teams = pd.unique(df[["home_team", "away_team"]].values.ravel())
        team_stats = {t: [] for t in all_teams}

        result = pd.DataFrame(index=df.index)
        for team_col in ["home_team", "away_team"]:
            for w in self.windows:
                gp_col = f"{team_col}_games_{w}"
                result[gp_col] = 0
            for stat in ["goals_scored", "goals_conceded", "points", "win"]:
                stat_col = f"{team_col}_{stat}"
                for w in self.windows:
                    result[f"{team_col}_{stat}_rolling_{w}"] = 0.0

            decay_sum = f"{team_col}_decay_sum"
            result[decay_sum] = 0.0
            result[f"{team_col}_form_rating"] = 0.0

        for i, row in df.iterrows():
            for team_col in ["home_team", "away_team"]:
                team = row[team_col]
                team_data = team_stats.setdefault(team, [])
                team_data.append((row["date"], row[f"{team_col}_goals_scored"],
                                  row[f"{team_col}_goals_conceded"],
                                  row[f"{team_col}_points"], row[f"{team_col}_win"]))

        for team_col in ["home_team", "away_team"]:
            for i, row in df.iterrows():
                team = row[team_col]
                history = team_stats[team][:-1]
                n_history = len(history)
                for w in self.windows:
                    recent = history[-w:] if w <= n_history else history
                    if not recent:
                        continue
                    gs = sum(r[1] for r in recent)
                    gc = sum(r[2] for r in recent)
                    pts = sum(r[3] for r in recent)
                    wins = sum(r[4] for r in recent)
                    result.at[i, f"{team_col}_goals_scored_rolling_{w}"] = gs / len(recent)
                    result.at[i, f"{team_col}_goals_conceded_rolling_{w}"] = gc / len(recent)
                    result.at[i, f"{team_col}_points_rolling_{w}"] = pts / len(recent)
                    result.at[i, f"{team_col}_winrate_rolling_{w}"] = wins / len(recent)

        return result


class StreakFeatures(FeatureTransformer):
    def __init__(self):
        super().__init__("streaks")

    def fit(self, matches: pd.DataFrame) -> "StreakFeatures":
        self._fitted = True
        self._feature_names = [
            "home_win_streak", "home_lose_streak", "home_unbeaten_streak",
            "away_win_streak", "away_lose_streak", "away_unbeaten_streak",
            "home_h2h_advantage", "home_h2h_winrate",
        ]
        return self

    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("fit must be called before transform")
        df = matches.copy()
        if "date" not in df.columns:
            df["date"] = pd.Timestamp.now()
        df = df.sort_values("date")

        df["home_win"] = (df["home_goals"] > df["away_goals"]).astype(float)
        df["away_win"] = (df["away_goals"] > df["home_goals"]).astype(float)
        df["draw"] = (df["home_goals"] == df["away_goals"]).astype(float)

        result = pd.DataFrame(index=df.index)
        result["home_win_streak"] = 0
        result["home_lose_streak"] = 0
        result["home_unbeaten_streak"] = 0
        result["away_win_streak"] = 0
        result["away_lose_streak"] = 0
        result["away_unbeaten_streak"] = 0
        result["home_h2h_advantage"] = 0.0
        result["home_h2h_winrate"] = 0.0

        team_streaks: dict[str, dict] = {}
        h2h: dict[tuple[str, str], list[float]] = {}

        for i, row in df.iterrows():
            home, away = row["home_team"], row["away_team"]
            home_won, away_won = row["home_win"], row["away_win"]

            for team, won, prefix in [(home, home_won, "home"), (away, away_won, "away")]:
                s = team_streaks.get(team, {"wins": 0, "losses": 0, "unbeaten": 0})
                result.at[i, f"{prefix}_win_streak"] = s["wins"]
                result.at[i, f"{prefix}_lose_streak"] = s["losses"]
                result.at[i, f"{prefix}_unbeaten_streak"] = s["unbeaten"]
                if won:
                    s["wins"] += 1
                    s["losses"] = 0
                    s["unbeaten"] += 1
                elif row["draw"]:
                    s["wins"] = 0
                    s["losses"] = 0
                    s["unbeaten"] += 1
                else:
                    s["wins"] = 0
                    s["losses"] += 1
                    s["unbeaten"] = 0
                team_streaks[team] = s

            key = (min(home, away), max(home, away))
            pair = h2h.get(key, [0, 0, 0])
            if pair[2] > 0:
                result.at[i, "home_h2h_advantage"] = pair[0] / pair[2]
                result.at[i, "home_h2h_winrate"] = (pair[0] + pair[1] * 0.5) / pair[2]
            if home_won:
                pair[0] += 1
            elif away_won:
                pair[1] += 1
            pair[2] += 1
            h2h[key] = pair

        return result
