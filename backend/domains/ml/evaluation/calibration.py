"""Probability calibration: Platt, Isotonic, Beta."""

from typing import Optional
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from backend.domains.ml.models import CalibrationMethod


def platt_scale(y_val: np.ndarray, val_probs: np.ndarray, test_probs: np.ndarray) -> np.ndarray:
    log_odds = np.clip(np.log(val_probs / (1 - val_probs + 1e-15)), -10, 10)
    lr = LogisticRegression(C=1e10, solver="lbfgs", max_iter=1000)
    lr.fit(log_odds.reshape(-1, 1), y_val)
    test_log_odds = np.clip(np.log(test_probs / (1 - test_probs + 1e-15)), -10, 10)
    cal_probs = lr.predict_proba(test_log_odds.reshape(-1, 1))[:, 1]
    return np.clip(cal_probs, 1e-6, 1 - 1e-6)


def isotonic_calibrate(val_probs: np.ndarray, test_probs: np.ndarray) -> np.ndarray:
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(val_probs, np.clip(val_probs, 0, 1))
    return np.clip(iso.transform(test_probs), 1e-6, 1 - 1e-6)


def beta_calibrate(y_val: np.ndarray, val_probs: np.ndarray, test_probs: np.ndarray) -> np.ndarray:
    val_probs_clipped = np.clip(val_probs, 1e-6, 1 - 1e-6)
    logit_p = np.log(val_probs_clipped / (1 - val_probs_clipped))
    logit_1_minus_p = np.log((1 - val_probs_clipped) / val_probs_clipped)

    lr = LogisticRegression(C=1e8, solver="lbfgs", max_iter=1000)
    features = np.column_stack([logit_p, logit_1_minus_p])
    lr.fit(features, y_val)

    test_clipped = np.clip(test_probs, 1e-6, 1 - 1e-6)
    test_logit_p = np.log(test_clipped / (1 - test_clipped))
    test_logit_1p = np.log((1 - test_clipped) / test_clipped)
    test_features = np.column_stack([test_logit_p, test_logit_1p])
    cal_probs = lr.predict_proba(test_features)[:, 1]
    return np.clip(cal_probs, 1e-6, 1 - 1e-6)


def calibrate_predictions(
    y_val: np.ndarray,
    val_probs: np.ndarray,
    test_probs: np.ndarray,
    method: CalibrationMethod = CalibrationMethod.PLATT,
) -> np.ndarray:
    if method == CalibrationMethod.NONE:
        return test_probs
    elif method == CalibrationMethod.PLATT:
        return platt_scale(y_val, val_probs, test_probs)
    elif method == CalibrationMethod.ISOTONIC:
        return isotonic_calibrate(val_probs, test_probs)
    elif method == CalibrationMethod.BETA:
        return beta_calibrate(y_val, val_probs, test_probs)
    return test_probs
