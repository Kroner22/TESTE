"""ML Model loading — singleton pattern for FastAPI integration."""
import os, pickle, json, numpy as np

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

_models = None
_features = None
_metrics = None


def load_models(force: bool = False):
    """Load all trained models (cached)."""
    global _models, _features, _metrics
    if _models is not None and not force:
        return _models, _features, _metrics

    xgb_path = os.path.join(MODEL_DIR, "xgb_model.pkl")
    lgb_path = os.path.join(MODEL_DIR, "lgb_model.pkl")
    ensemble_path = os.path.join(MODEL_DIR, "ensemble.pkl")
    features_path = os.path.join(MODEL_DIR, "features.json")
    metrics_path = os.path.join(MODEL_DIR, "metrics.json")

    if not all(os.path.exists(p) for p in [xgb_path, lgb_path, ensemble_path, features_path]):
        return None, None, None

    with open(xgb_path, "rb") as f:
        xgb = pickle.load(f)
    with open(lgb_path, "rb") as f:
        lgb = pickle.load(f)
    with open(ensemble_path, "rb") as f:
        ensemble = pickle.load(f)
    with open(features_path) as f:
        _features = json.load(f)["features"]
    with open(metrics_path) as f:
        _metrics = json.load(f)

    _models = {"xgboost": xgb, "lightgbm": lgb, "ensemble": ensemble}
    return _models, _features, _metrics


def predict_match(home_team: str, away_team: str, sport: str = "soccer",
                  home_odds: float | None = None, away_odds: float | None = None) -> dict:
    """Predict match outcome using trained ensemble model."""
    models, features, metrics = load_models()
    if models is None:
        raise RuntimeError("Models not trained yet. Run backend/ml/train_models.py first.")

    from backend.app.database import SessionLocal, Event, OddsRecord
    db = SessionLocal()

    # Build feature vector
    evt = db.query(Event).filter(
        Event.home_team == home_team, Event.away_team == away_team
    ).first()
    db.close()

    implied_home = 1.0 / home_odds if home_odds else 0.5
    implied_away = 1.0 / away_odds if away_odds else 0.5

    import numpy as np
    feature_dict = {
        "best_home_odd": home_odds or 2.0,
        "best_away_odd": away_odds or 2.0,
        "best_draw_odd": 3.5,
        "n_bookmakers": 3,
        "n_outcomes": 2,
        "best_ev": 0.05,
        "best_confidence": 0.5,
        "best_grade_num": 1,
        "overround": round(implied_home + implied_away - 1.0, 4),
        "home_implied": round(implied_home, 4),
        "away_implied": round(implied_away, 4),
        "odds_volatility": 0.1,
        "has_opportunity": 1,
        "n_opportunities": 1,
    }

    X = np.array([[feature_dict.get(f, 0) for f in features]])

    # Ensemble prediction (blending)
    xgb_proba = models["xgboost"].predict_proba(X)[0, 1]
    lgb_proba = models["lightgbm"].predict_proba(X)[0, 1]
    rf_proba = models["ensemble"]["rf"].predict_proba(X)[0, 1]
    meta_X = np.array([[xgb_proba, lgb_proba, rf_proba]])
    final_proba = models["ensemble"]["meta"].predict_proba(meta_X)[0, 1]

    return {
        "home_win_prob": round(final_proba, 4),
        "away_win_prob": round(1 - final_proba, 4),
        "model_used": "ensemble (XGBoost + LightGBM + RF)",
        "model_metrics": metrics,
        "features_used": features,
    }
