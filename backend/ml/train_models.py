"""ML Model Training — XGBoost, LightGBM, and Ensemble for match outcome prediction."""
import os, sys, json, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['RUNTIME_MODE'] = 'SIMULATION'

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.app.database import SessionLocal, Event, OddsRecord, OpportunityRecord


MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)


def build_training_data() -> pd.DataFrame:
    """Build a feature matrix from the database for training."""
    db = SessionLocal()

    events = db.query(Event).all()
    odds = db.query(OddsRecord).all()
    opps = db.query(OpportunityRecord).all()

    odds_by_event = {}
    for o in odds:
        odds_by_event.setdefault(o.event_id, []).append(o)

    opps_by_event = {}
    for o in opps:
        opps_by_event.setdefault(o.event_id, []).append(o)

    rows = []
    for evt in events:
        ev_odds = odds_by_event.get(evt.event_id, [])
        ev_opps = opps_by_event.get(evt.event_id, [])

        home_odds = [float(o.odd) for o in ev_odds if o.outcome == "home"]
        away_odds = [float(o.odd) for o in ev_odds if o.outcome == "away"]
        draw_odds = [float(o.odd) for o in ev_odds if o.outcome == "draw"]

        best_home = max(home_odds) if home_odds else None
        best_away = max(away_odds) if away_odds else None
        best_draw = max(draw_odds) if draw_odds else None

        n_bookmakers = len(set(o.bookmaker for o in ev_odds)) if ev_odds else 0
        n_outcomes = len(set(o.outcome for o in ev_odds)) if ev_odds else 0

        best_ev = max((float(o.ev or 0) for o in ev_opps), default=0)
        best_conf = max((float(o.confidence_score or 0) for o in ev_opps), default=0)
        best_grade = max((o.value_grade for o in ev_opps), default="NOISE")

        grade_map = {"ELITE": 4, "STRONG": 3, "SOLID": 2, "SPECULATIVE": 1, "NOISE": 0}
        grade_num = grade_map.get(best_grade, 0)

        row = {
            "event_id": evt.event_id,
            "sport": evt.sport,
            "home_team": evt.home_team,
            "away_team": evt.away_team,
            "best_home_odd": best_home,
            "best_away_odd": best_away,
            "best_draw_odd": best_draw,
            "n_bookmakers": n_bookmakers,
            "n_outcomes": n_outcomes,
            "best_ev": best_ev,
            "best_confidence": best_conf,
            "best_grade_num": grade_num,
        }

        if best_home and best_away:
            implied_home = 1.0 / best_home
            implied_away = 1.0 / best_away
            total_implied = implied_home + implied_away + (1.0 / best_draw if best_draw else 0)
            row["overround"] = round(total_implied - 1.0, 4)
            row["home_implied"] = round(implied_home, 4)
            row["away_implied"] = round(implied_away, 4)
        else:
            row["overround"] = 0
            row["home_implied"] = 0.5
            row["away_implied"] = 0.5

        row["odds_volatility"] = round(
            np.std([float(o.odd) for o in ev_odds]) if len(ev_odds) > 1 else 0, 4
        )

        if ev_opps:
            row["has_opportunity"] = 1
            row["n_opportunities"] = len(ev_opps)
        else:
            row["has_opportunity"] = 0
            row["n_opportunities"] = 0

        # Target: 1 if best_ev > 0.03 (strong value), else 0
        row["target"] = 1 if best_ev > 0.03 else 0

        rows.append(row)

    db.close()
    df = pd.DataFrame(rows)
    print(f"  -> {len(df)} samples, {len(df.columns)} features")
    print(f"  -> Target distribution: {df['target'].value_counts().to_dict()}")
    return df


def train_xgboost(df: pd.DataFrame) -> tuple:
    """Train an XGBoost classifier."""
    from xgboost import XGBClassifier
    features = _get_feature_cols(df)
    X = df[features].fillna(0)
    y = df["target"]

    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", early_stopping_rounds=20,
        random_state=42, verbosity=0,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    from sklearn.metrics import accuracy_score, roc_auc_score
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    metrics = {
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "auc_roc": round(roc_auc_score(y_test, y_proba), 4),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
    }

    print(f"  -> XGBoost: accuracy={metrics['accuracy']}, AUC={metrics['auc_roc']}")
    return model, metrics, features


def train_lightgbm(df: pd.DataFrame) -> tuple:
    """Train a LightGBM classifier."""
    from lightgbm import LGBMClassifier
    features = _get_feature_cols(df)
    X = df[features].fillna(0)
    y = df["target"]

    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbosity=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)])

    from sklearn.metrics import accuracy_score, roc_auc_score
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    metrics = {
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "auc_roc": round(roc_auc_score(y_test, y_proba), 4),
    }
    print(f"  -> LightGBM: accuracy={metrics['accuracy']}, AUC={metrics['auc_roc']}")
    return model, metrics, features


def train_ensemble(xgb_model, lgb_model, df: pd.DataFrame) -> tuple:
    """Create a blending ensemble of XGBoost and LightGBM."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    features = _get_feature_cols(df)
    X = df[features].fillna(0)
    y = df["target"]

    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Blending: use base models + RF + LR as meta-features
    xgb_proba = xgb_model.predict_proba(X_train)[:, 1].reshape(-1, 1)
    lgb_proba = lgb_model.predict_proba(X_train)[:, 1].reshape(-1, 1)

    rf = RandomForestClassifier(n_estimators=100, max_depth=3, random_state=42)
    rf.fit(X_train, y_train)
    rf_proba = rf.predict_proba(X_train)[:, 1].reshape(-1, 1)

    meta_X = np.hstack([xgb_proba, lgb_proba, rf_proba])
    meta_model = LogisticRegression(C=1.0)
    meta_model.fit(meta_X, y_train)

    # Evaluate
    xgb_proba_test = xgb_model.predict_proba(X_test)[:, 1].reshape(-1, 1)
    lgb_proba_test = lgb_model.predict_proba(X_test)[:, 1].reshape(-1, 1)
    rf_proba_test = rf.predict_proba(X_test)[:, 1].reshape(-1, 1)
    meta_X_test = np.hstack([xgb_proba_test, lgb_proba_test, rf_proba_test])
    y_pred = meta_model.predict(meta_X_test)
    y_proba = meta_model.predict_proba(meta_X_test)[:, 1]

    from sklearn.metrics import accuracy_score, roc_auc_score
    metrics = {
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "auc_roc": round(roc_auc_score(y_test, y_proba), 4),
    }
    print(f"  -> Ensemble: accuracy={metrics['accuracy']}, AUC={metrics['auc_roc']}")
    return {"meta": meta_model, "rf": rf}, metrics, features


def _get_feature_cols(df: pd.DataFrame) -> list:
    exclude = {"event_id", "sport", "home_team", "away_team", "target"}
    return [c for c in df.columns if c not in exclude]


def save_models(xgb, lgb, ensemble, metrics: dict, features: list):
    """Save trained models and metadata."""
    with open(os.path.join(MODEL_DIR, "xgb_model.pkl"), "wb") as f:
        pickle.dump(xgb, f)
    with open(os.path.join(MODEL_DIR, "lgb_model.pkl"), "wb") as f:
        pickle.dump(lgb, f)
    with open(os.path.join(MODEL_DIR, "ensemble.pkl"), "wb") as f:
        pickle.dump(ensemble, f)
    with open(os.path.join(MODEL_DIR, "features.json"), "w") as f:
        json.dump({"features": features}, f)
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"  -> Modelos salvos em {MODEL_DIR}")


def main():
    print("[ML] Construindo dados de treinamento...")
    df = build_training_data()

    if len(df) < 10:
        print("[!] Dados insuficientes para treinamento (< 10 amostras). Pulando.")
        return

    print("[ML] Treinando XGBoost...")
    xgb, xgb_metrics, features = train_xgboost(df)

    print("[ML] Treinando LightGBM...")
    lgb, lgb_metrics, _ = train_lightgbm(df)

    print("[ML] Criando Ensemble...")
    ensemble, ensemble_metrics, _ = train_ensemble(xgb, lgb, df)

    all_metrics = {
        "xgboost": xgb_metrics,
        "lightgbm": lgb_metrics,
        "ensemble": ensemble_metrics,
        "n_samples": len(df),
        "n_features": len(features),
        "feature_names": features,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    save_models(xgb, lgb, ensemble, all_metrics, features)
    print(f"\n[ML] TREINAMENTO CONCLUIDO")
    print(f"     Amostras: {len(df)}")
    print(f"     Features: {len(features)}")
    print(f"     XGBoost AUC: {xgb_metrics['auc_roc']}")
    print(f"     LightGBM AUC: {lgb_metrics['auc_roc']}")
    print(f"     Ensemble AUC: {ensemble_metrics['auc_roc']}")


if __name__ == "__main__":
    main()
