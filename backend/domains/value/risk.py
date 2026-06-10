"""
risk.py — Risk score classifier for value opportunities.

The risk score quantifies how risky a given value bet is, independent of EV.
It is composed of 4 dimensions:

  1. Edge Volatility (0.0 - 1.0):
     High CV of edge → higher risk.
     Unstable edges suggest the market is mispricing inconsistently.
    
  2. Time Pressure (0.0 - 1.0):
     Events starting soon → higher risk of sharp market correction.
     Events far away → more time for price discovery.
     Scaled as: 1 / (1 + hours_to_event / 24)
    
  3. Regime Stability (0.0 - 1.0):
     From regime detection: STABLE → low risk, CHAOTIC → high risk.
     Maps: STABLE=0.1, SEMI_STABLE=0.4, CHAOTIC=0.8
    
  4. Market Depth Proxy (0.0 - 1.0):
     Number of bookmakers offering the market.
     More bookmakers → deeper market → more reliable odds.
     Scaled as: 1 / (1 + n_bookmakers / 5)

Final risk score: weighted arithmetic mean (allows compensation).
Risk classification:
  0.00 - 0.25 → LOW
  0.25 - 0.50 → MEDIUM
  0.50 - 0.75 → HIGH
  0.75 - 1.00 → EXTREME
"""

from .models import RiskLevel


def edge_volatility_risk(
    edge_estimates: list[float] | None = None,
    std: float | None = None,
    mean_ev: float | None = None,
) -> float:
    """
    CV-based risk. Higher CV = higher risk.
    0.0 → CV=0 (perfectly stable)
    0.5 → CV=1.5
    1.0 → CV→∞
    """
    if edge_estimates and len(edge_estimates) >= 3:
        m = sum(edge_estimates) / len(edge_estimates)
        if m == 0:
            return 0.7
        v = sum((x - m) ** 2 for x in edge_estimates) / (len(edge_estimates) - 1)
        import math
        cv = math.sqrt(v) / abs(m)
    elif std is not None and mean_ev is not None and mean_ev != 0:
        cv = std / abs(mean_ev)
    else:
        return 0.5  # unknown → medium risk

    # Logistic: risk = 1 / (1 + e^(-1.5*(cv - 1.0)))
    import math
    return 1.0 / (1.0 + math.exp(-1.5 * (cv - 1.0)))


def time_pressure_risk(hours_to_event: float | None = None) -> float:
    """
    Risk from time until event start.
    
    hours_to_event = None → assume unknown, return 0.5
    hours_to_event = 0 (in-play) → 1.0
    hours_to_event = 24 → 0.5
    hours_to_event = 168 (7 days) → 0.125
    """
    if hours_to_event is None:
        return 0.5
    return 1.0 / (1.0 + hours_to_event / 24.0)


def regime_risk(regime: str | None = None) -> float:
    """Map regime to risk contribution."""
    mapping = {
        "STABLE": 0.1,
        "SEMI_STABLE": 0.4,
        "CHAOTIC": 0.8,
        None: 0.5,
    }
    return mapping.get(regime, 0.5)


def market_depth_risk(n_bookmakers: int = 1) -> float:
    """
    Risk from number of bookmakers.
    More bookmakers → more competitive → more reliable odds.
    """
    return 1.0 / (1.0 + n_bookmakers / 5.0)


def classify_risk(risk_score: float) -> RiskLevel:
    """Map continuous score to discrete level."""
    if risk_score < 0.25:
        return RiskLevel.LOW
    elif risk_score < 0.50:
        return RiskLevel.MEDIUM
    elif risk_score < 0.75:
        return RiskLevel.HIGH
    return RiskLevel.EXTREME


def compute_risk_score(
    edge_estimates: list[float] | None = None,
    std: float | None = None,
    mean_ev: float | None = None,
    hours_to_event: float | None = None,
    regime: str | None = None,
    n_bookmakers: int = 1,
    weights: dict[str, float] | None = None,
) -> tuple[float, RiskLevel]:
    """
    Composite risk score (0.0 - 1.0).
    
    Default weights:
      edge_volatility: 0.35
      time_pressure:   0.25
      regime:          0.25
      market_depth:    0.15
    """
    w = weights or {"volatility": 0.35, "time": 0.25,
                    "regime": 0.25, "depth": 0.15}

    components = {
        "volatility": edge_volatility_risk(edge_estimates, std, mean_ev),
        "time": time_pressure_risk(hours_to_event),
        "regime": regime_risk(regime),
        "depth": market_depth_risk(n_bookmakers),
    }

    score = sum(w[k] * components[k] for k in w if k in components)
    total_weight = sum(w.values())
    score = score / total_weight if total_weight > 0 else 0.5
    score = max(0.0, min(1.0, score))

    return round(score, 3), classify_risk(score)
