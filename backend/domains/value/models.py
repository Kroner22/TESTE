"""
Models for the Value Bet Detection Engine.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class OverroundMethod(str, Enum):
    BASIC = "basic"          # Proportional scaling
    POWER = "power"          # Power method (k parameter)
    SHIN = "shin"            # Shin's method (accounts for favorite-longshot bias)


class ValueGrade(str, Enum):
    ELITE = "ELITE"           # EV > 10%, confidence > 0.9
    STRONG = "STRONG"         # EV > 5%, confidence > 0.8
    SOLID = "SOLID"           # EV > 3%, confidence > 0.7
    SPECULATIVE = "SPECULATIVE"  # EV > 1%, any confidence
    NOISE = "NOISE"           # EV <= 1% or insufficient confidence


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class MarketOdds:
    """Raw market odds for a single event."""
    event_id: str
    sport: str
    home_team: str
    away_team: str
    market: str                          # "h2h", "spread", "totals"
    outcomes: dict[str, Decimal]         # {"home": Decimal("2.10"), "away": Decimal("3.40"), "draw": Decimal("3.25")}
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    bookmaker: str = "aggregated"


@dataclass
class FairProbabilities:
    """Calculated fair probabilities after removing overround."""
    outcomes: dict[str, float]           # {"home": 0.45, "away": 0.30, "draw": 0.25}
    overround: float                     # e.g., 0.05 = 5% margin
    method: OverroundMethod
    fair_odds: dict[str, float]          # 1 / fair_prob


@dataclass
class ValueOpportunity:
    """A detected value betting opportunity."""
    event_id: str
    sport: str
    market: str
    outcome: str
    bookmaker_odd: Decimal
    fair_probability: float              # After removing overround
    implied_probability: float           # 1 / odd
    expected_value: float                # (fair_prob * odd) - 1
    edge_pct: float                      # EV as percentage
    kelly_stake: float                   # Optimal Kelly fraction
    confidence: float                    # 0.0 to 1.0
    risk_score: float                    # 0.0 (safe) to 1.0 (extreme)
    risk_level: RiskLevel
    grade: ValueGrade
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    model_probability: Optional[float] = None  # ML model estimate if available
    historical_accuracy: Optional[float] = None
    sample_size: int = 0


@dataclass
class KellyResult:
    """Kelly Criterion calculation results."""
    full_kelly: float                    # Full Kelly fraction
    half_kelly: float                    # 1/2 Kelly
    quarter_kelly: float                 # 1/4 Kelly
    fractional_kelly: float              # User-specified fraction
    expected_growth: float               # Expected log growth
    recommended_stake: float             # Clamped to bankroll %
    is_viable: bool                      # True if EV > 0 and stake > minimum
