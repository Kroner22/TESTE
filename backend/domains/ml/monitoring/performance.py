"""Performance tracking and alert thresholds for production."""

from typing import Optional
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from backend.domains.ml.models import TrainMetrics


class PerformanceTracker:
    def __init__(self, window: int = 100, alert_threshold_brier: float = 0.30,
                 alert_threshold_accuracy: float = 0.45):
        self.window = window
        self.alert_threshold_brier = alert_threshold_brier
        self.alert_threshold_accuracy = alert_threshold_accuracy
        self.metrics_history: list[dict] = []
        self.alerts: list[dict] = []

    def log_prediction(self, y_true: float, y_prob: float, meta: Optional[dict] = None):
        self.metrics_history.append({
            "timestamp": datetime.now(timezone.utc),
            "y_true": y_true,
            "y_prob": y_prob,
            "correct": bool((y_prob >= 0.5) == (y_true == 1)),
            **(meta or {}),
        })

        if len(self.metrics_history) >= self.window:
            self._check_alerts()

    def current_metrics(self) -> TrainMetrics:
        if not self.metrics_history:
            return TrainMetrics()

        recent = self.metrics_history[-self.window:]
        y_true = np.array([m["y_true"] for m in recent])
        y_prob = np.array([m["y_prob"] for m in recent])

        from backend.domains.ml.evaluation.metrics import compute_metrics
        return compute_metrics(y_true, y_prob)

    def _check_alerts(self):
        metrics = self.current_metrics()
        now = datetime.now(timezone.utc)

        if metrics.brier > self.alert_threshold_brier:
            self.alerts.append({
                "timestamp": now,
                "type": "brier_threshold_exceeded",
                "value": metrics.brier,
                "threshold": self.alert_threshold_brier,
            })

        if metrics.accuracy < self.alert_threshold_accuracy:
            self.alerts.append({
                "timestamp": now,
                "type": "accuracy_below_threshold",
                "value": metrics.accuracy,
                "threshold": self.alert_threshold_accuracy,
            })

    def metrics_trend(self, n_points: int = 10) -> dict:
        if len(self.metrics_history) < n_points * 2:
            return {"trend": "insufficient_data"}

        recent = self._rolling_brier(n_points)
        if len(recent) < 2:
            return {"trend": "insufficient_data"}

        slope = (recent[-1] - recent[0]) / len(recent)
        return {
            "trend": "degrading" if slope > 0.005 else "improving" if slope < -0.005 else "stable",
            "brier_slope": float(slope),
            "current_brier": float(recent[-1]) if len(recent) > 0 else 0.0,
        }

    def _rolling_brier(self, n_points: int) -> list[float]:
        if len(self.metrics_history) < self.window:
            return []
        results = []
        step = max(1, len(self.metrics_history) // (n_points + 1))
        for i in range(step, len(self.metrics_history), step):
            window_data = self.metrics_history[max(0, i - self.window):i]
            if len(window_data) < 10:
                continue
            y_true = np.array([m["y_true"] for m in window_data])
            y_prob = np.array([m["y_prob"] for m in window_data])
            from sklearn.metrics import brier_score_loss
            results.append(brier_score_loss(y_true, y_prob))
        return results[-n_points:]

    def summary(self) -> dict:
        metrics = self.current_metrics()
        trend = self.metrics_trend()
        return {
            "n_predictions": len(self.metrics_history),
            "n_alerts": len(self.alerts),
            "current_brier": metrics.brier,
            "current_accuracy": metrics.accuracy,
            "current_auc_roc": metrics.auc_roc,
            "trend": trend.get("trend", "unknown"),
            "last_alert": self.alerts[-1]["timestamp"].isoformat()
                         if self.alerts else None,
        }


class AlertManager:
    def __init__(self, min_alert_interval: int = 3600):
        self.min_alert_interval = min_alert_interval
        self._last_alert_time: dict[str, datetime] = {}

    def should_alert(self, alert_type: str) -> bool:
        now = datetime.now(timezone.utc)
        last = self._last_alert_time.get(alert_type)
        if last is None or (now - last).total_seconds() > self.min_alert_interval:
            self._last_alert_time[alert_type] = now
            return True
        return False

    def reset(self, alert_type: Optional[str] = None):
        if alert_type:
            self._last_alert_time.pop(alert_type, None)
        else:
            self._last_alert_time.clear()
