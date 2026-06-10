from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ModelType(str, Enum):
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    LOGISTIC = "logistic"


class TargetType(str, Enum):
    HOME_WIN = "home_win"
    AWAY_WIN = "away_win"
    OVER = "over"
    UNDER = "under"
    BINARY = "binary"


class FeatureCategory(str, Enum):
    HISTORICAL = "historical"
    MARKET = "market"
    TEAM = "team"
    TEMPORAL = "temporal"
    ELABORATED = "elaborated"


class DriftSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    SEVERE = "severe"


class CalibrationMethod(str, Enum):
    PLATT = "platt"
    ISOTONIC = "isotonic"
    BETA = "beta"
    NONE = "none"


@dataclass
class MatchFeatures:
    features: dict[str, float]
    target: Optional[float] = None
    match_id: Optional[str] = None
    event_date: Optional[datetime] = None
    sport: Optional[str] = None
    league: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None


@dataclass
class FeatureConfig:
    historical_windows: list[int] = field(default_factory=lambda: [5, 10, 20, 38])
    market_features: bool = True
    team_features: bool = True
    temporal_features: bool = True
    elaborated_features: bool = False
    min_samples_for_rolling: int = 3
    decay_factor: float = 0.95
    home_advantage_decay: bool = True


@dataclass
class PredictionResult:
    match_id: str
    home_win_prob: float
    away_win_prob: float
    draw_prob: Optional[float] = None
    implied_home: Optional[float] = None
    implied_away: Optional[float] = None
    implied_draw: Optional[float] = None
    expected_value: Optional[float] = None
    model_confidence: float = 0.0
    prediction_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model_version: Optional[str] = None
    features_used: int = 0


@dataclass
class EnsembleConfig:
    weights: Optional[dict[str, float]] = None
    meta_learner: str = "logistic"
    stacking: bool = True
    calibration_method: CalibrationMethod = CalibrationMethod.PLATT
    threshold_optimization_metric: str = "profit"
    n_folds_meta: int = 5


@dataclass
class TrainConfig:
    model_type: ModelType = ModelType.XGBOOST
    target_type: TargetType = TargetType.HOME_WIN
    test_size: float = 0.15
    validation_size: float = 0.10
    n_folds: int = 5
    early_stopping_rounds: int = 50
    n_trials_hyperopt: int = 30
    random_state: int = 42
    calibrate: bool = True
    calibration_method: CalibrationMethod = CalibrationMethod.PLATT
    save_artifacts: bool = True
    artifact_path: Optional[str] = None


@dataclass
class TrainMetrics:
    brier: float = 0.0
    log_loss: float = 0.0
    auc_roc: float = 0.0
    auc_pr: float = 0.0
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    calibration_slope: float = 1.0
    calibration_intercept: float = 0.0
    ece: float = 0.0
    mse: float = 0.0
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    roi: Optional[float] = None
    n_matches: int = 0


@dataclass
class BacktestResult:
    window_metrics: list[TrainMetrics] = field(default_factory=list)
    aggregate: Optional[TrainMetrics] = None
    n_windows: int = 0
    stability_score: float = 0.0
    degradation_rate: float = 0.0


@dataclass
class DriftReport:
    psi: float = 0.0
    ks_statistic: float = 0.0
    ks_p_value: float = 1.0
    feature_drift_scores: dict[str, float] = field(default_factory=dict)
    drifted_features: list[str] = field(default_factory=list)
    severity: DriftSeverity = DriftSeverity.NONE
    model_confidence_drop: float = 0.0
    recommendation: str = ""


__all__ = [
    "ModelType", "TargetType", "FeatureCategory", "DriftSeverity", "CalibrationMethod",
    "MatchFeatures", "FeatureConfig", "PredictionResult", "EnsembleConfig",
    "TrainConfig", "TrainMetrics", "BacktestResult", "DriftReport",
]
