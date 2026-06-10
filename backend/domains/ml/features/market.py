"""Market/odds features: movements, sharpness, overround, depth."""

import pandas as pd
import numpy as np
from .base import FeatureTransformer


class MarketFeatures(FeatureTransformer):
    def __init__(self):
        super().__init__("market")

    def fit(self, matches: pd.DataFrame) -> "MarketFeatures":
        self._fitted = True
        self._feature_names = [
            "market_overround", "market_sharpness", "odds_volatility",
            "home_odds_movement", "away_odds_movement",
            "implied_home_prob", "implied_away_prob", "implied_draw_prob",
            "home_implied_edge", "away_implied_edge",
            "n_bookmakers", "odds_divergence",
        ]
        return self

    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("fit must be called before transform")
        df = matches.copy()
        result = pd.DataFrame(index=df.index)

        home_odds = df.get("home_odd", np.nan)
        away_odds = df.get("away_odd", np.nan)
        draw_odds = df.get("draw_odd", np.nan)

        impl_h = 1.0 / home_odds
        impl_a = 1.0 / away_odds
        impl_d = 1.0 / draw_odds

        result["implied_home_prob"] = impl_h
        result["implied_away_prob"] = impl_a
        result["implied_draw_prob"] = impl_d
        result["home_implied_edge"] = impl_h / (impl_h + impl_a + impl_d)
        result["away_implied_edge"] = impl_a / (impl_h + impl_a + impl_d)

        overround = impl_h + impl_a + impl_d - 1.0
        result["market_overround"] = overround.fillna(0).clip(lower=0)

        result["market_sharpness"] = (1.0 / overround).replace([np.inf, -np.inf], 0).fillna(0)

        if "home_odd_open" in df.columns and "home_odd" in df.columns:
            result["home_odds_movement"] = (df["home_odd"] - df["home_odd_open"]) / df["home_odd_open"]
            result["away_odds_movement"] = (df["away_odd"] - df["away_odd_open"]) / df["away_odd_open"]
        else:
            result["home_odds_movement"] = 0.0
            result["away_odds_movement"] = 0.0

        if "n_bookmakers" in df.columns:
            result["n_bookmakers"] = df["n_bookmakers"]
            result["odds_divergence"] = overround / df["n_bookmakers"].clip(lower=1)
        else:
            result["n_bookmakers"] = 1
            result["odds_divergence"] = overround

        odds_cols = [c for c in df.columns if
                     c.startswith("bookmaker_") and "odd" in c.lower()]
        if len(odds_cols) >= 4:
            odds_matrix = df[odds_cols].values
            result["odds_volatility"] = np.nanstd(odds_matrix, axis=1)
        else:
            result["odds_volatility"] = 0.0

        return result.fillna(0)


class OddsDistortionDetector(FeatureTransformer):
    def __init__(self):
        super().__init__("odds_distortion")

    def fit(self, matches: pd.DataFrame) -> "OddsDistortionDetector":
        self._fitted = True
        self._feature_names = [
            "distortion_score", "market_mispricing", "arbitrage_flag",
            "value_index", "shin_z_estimate",
        ]
        return self

    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("fit must be called before transform")
        df = matches.copy()
        result = pd.DataFrame(index=df.index)

        home_odds = df.get("home_odd", np.nan).values
        away_odds = df.get("away_odd", np.nan).values
        if "draw_odd" in df.columns:
            draw_odds = df["draw_odd"].values
        else:
            draw_odds = np.full_like(home_odds, np.inf)

        impl_h = np.where(home_odds > 1, 1.0 / home_odds, 0)
        impl_a = np.where(away_odds > 1, 1.0 / away_odds, 0)
        impl_d = np.where(draw_odds > 1, 1.0 / draw_odds, 0)
        total_impl = impl_h + impl_a + impl_d

        result["arbitrage_flag"] = (total_impl < 0.99).astype(float)

        fair_h = np.divide(impl_h, total_impl, out=np.zeros_like(impl_h), where=total_impl > 0)
        fair_a = np.divide(impl_a, total_impl, out=np.zeros_like(impl_a), where=total_impl > 0)

        ev_h = fair_h * home_odds - 1
        ev_a = fair_a * away_odds - 1

        result["value_index"] = np.maximum(ev_h, ev_a)
        result["market_mispricing"] = np.abs(fair_h - impl_h)
        result["distortion_score"] = np.abs(fair_h - impl_h) / np.clip(total_impl, 0.01, None)

        overround = total_impl - 1
        clipped_or = np.clip(overround, 0, None)
        result["shin_z_estimate"] = clipped_or / np.clip(overround, 0.01, None).max() if overround.max() > 0 else 0

        return result.fillna(0)
