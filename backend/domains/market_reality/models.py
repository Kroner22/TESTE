from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class MoveDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class SteamStrength(str, Enum):
    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    EXTREME = "extreme"


class VolatilityRegime(str, Enum):
    CALM = "calm"
    NORMAL = "normal"
    VOLATILE = "volatile"
    CHAOTIC = "chaotic"


class DriftType(str, Enum):
    NONE = "none"
    EARLY = "early"
    LATE = "late"
    SUSTAINED = "sustained"
    REVERSAL = "reversal"


class LiquidityClass(str, Enum):
    DEEP = "deep"
    MODERATE = "moderate"
    THIN = "thin"
    FRAGILE = "fragile"


class BookmakerStyle(str, Enum):
    AGGRESSIVE = "aggressive"
    CONSERVATIVE = "conservative"
    REACTIVE = "reactive"
    PROACTIVE = "proactive"
    MIXED = "mixed"


class DistortionType(str, Enum):
    NONE = "none"
    LINE_MISMATCH = "line_mismatch"
    SLOW_REACTION = "slow_reaction"
    OVERREACTION = "overreaction"
    ARTIFICIAL = "artificial"
    ARBITRAGE = "arbitrage"


@dataclass
class OddsTick:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    odd: Decimal
    timestamp: datetime
    is_opening: bool = False
    is_closing: bool = False

    @property
    def implied_prob(self) -> float:
        if self.odd <= Decimal("1"):
            return 0.0
        return float(Decimal("1") / self.odd)

    def change_from(self, other: OddsTick) -> float:
        if other.odd <= 0:
            return 0.0
        return float((self.odd - other.odd) / other.odd * 100)


@dataclass
class OddsTimeSeries:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    ticks: list[OddsTick] = field(default_factory=list)

    @property
    def opening_odd(self) -> Optional[Decimal]:
        open_ticks = [t for t in self.ticks if t.is_opening]
        return open_ticks[0].odd if open_ticks else None

    @property
    def closing_odd(self) -> Optional[Decimal]:
        close_ticks = [t for t in self.ticks if t.is_closing]
        return close_ticks[-1].odd if close_ticks else (
            self.ticks[-1].odd if self.ticks else None
        )

    @property
    def num_ticks(self) -> int:
        return len(self.ticks)

    @property
    def duration_hours(self) -> float:
        if len(self.ticks) < 2:
            return 0.0
        return (self.ticks[-1].timestamp - self.ticks[0].timestamp).total_seconds() / 3600

    def closing_line_value(self) -> Optional[float]:
        if not self.opening_odd or not self.closing_odd:
            return None
        return float((self.closing_odd - self.opening_odd) / self.opening_odd * 100)


@dataclass
class SteamMove:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    start_odd: Decimal
    end_odd: Decimal
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    change_pct: float
    strength: SteamStrength
    velocity_pct_per_min: float
    sustained: bool

    @property
    def magnitude(self) -> float:
        return abs(self.change_pct)


@dataclass
class DriftAnalysis:
    event_id: str
    market: str
    outcome: str
    opening_odd: Decimal
    closing_odd: Optional[Decimal]
    drift_pct: float
    drift_type: DriftType
    closing_line_value_pct: Optional[float]
    early_volatility: float
    late_volatility: float
    reversal_detected: bool
    num_reversals: int

    @property
    def direction(self) -> MoveDirection:
        if abs(self.drift_pct) < 0.1:
            return MoveDirection.FLAT
        return MoveDirection.UP if self.drift_pct > 0 else MoveDirection.DOWN


@dataclass
class VolatilityMetrics:
    event_id: str
    market: str
    overall_std: float
    mean_absolute_change: float
    max_single_move_pct: float
    coefficient_variation: float
    regime: VolatilityRegime
    volatility_score: float
    num_moves: int
    large_moves_count: int
    large_move_threshold_pct: float

    @property
    def is_calm(self) -> bool:
        return self.regime == VolatilityRegime.CALM

    @property
    def is_chaotic(self) -> bool:
        return self.regime == VolatilityRegime.CHAOTIC


@dataclass
class LiquidityEstimate:
    event_id: str
    market: str
    outcome: str
    liquidity_class: LiquidityClass
    depth_score: float
    avg_tick_size: float
    max_delta_between_ticks: float
    implied_depth: float
    spread_volatility_ratio: float
    confidence: float

    @property
    def is_deep(self) -> bool:
        return self.liquidity_class == LiquidityClass.DEEP

    @property
    def is_fragile(self) -> bool:
        return self.liquidity_class == LiquidityClass.FRAGILE


@dataclass
class MarketPressure:
    event_id: str
    market: str
    pressure_score: float
    directional_bias: float
    consistency: float
    accumulated_flow: float
    pressure_direction: MoveDirection
    is_significant: bool
    dominant_bookmakers: list[str]

    @property
    def bias_label(self) -> str:
        if abs(self.directional_bias) < 0.1:
            return "neutral"
        return "fading" if self.directional_bias < 0 else "chasing"


@dataclass
class OddsMomentum:
    event_id: str
    market: str
    outcome: str
    momentum_value: float
    acceleration: float
    duration_minutes: float
    is_rising: bool
    strength: str
    recent_velocity: float
    smoothed_velocity: float


@dataclass
class MarketSensitivity:
    event_id: str
    market: str
    cross_correlation: dict[str, float]
    own_sensitivity: float
    market_elasticity: float
    mean_reversion_speed: float
    overreaction_detected: bool
    sensitivity_score: float

    @property
    def is_elastic(self) -> bool:
        return self.market_elasticity > 0.5


@dataclass
class BookmakerProfile:
    bookmaker: str
    style: BookmakerStyle
    reaction_time_avg_seconds: float
    adjustment_magnitude_avg: float
    overround_avg: float
    aggressiveness_score: float
    proactiveness_score: float
    consistency_score: float
    samples_analyzed: int


@dataclass
class MarketDistortion:
    event_id: str
    market: str
    distortion_type: DistortionType
    severity: float
    description: str
    detected_at: datetime
    confidence: float
    involved_bookmakers: list[str]


@dataclass
class MarketRealitySnapshot:
    event_id: str
    market: str
    timestamp: datetime

    drift: Optional[DriftAnalysis] = None
    volatility: Optional[VolatilityMetrics] = None
    liquidity: Optional[LiquidityEstimate] = None
    pressure: Optional[MarketPressure] = None
    momentum: Optional[OddsMomentum] = None
    sensitivity: Optional[MarketSensitivity] = None
    distortions: list[MarketDistortion] = field(default_factory=list)
    steam_moves: list[SteamMove] = field(default_factory=list)

    @property
    def has_steam(self) -> bool:
        return any(s.strength in (SteamStrength.STRONG, SteamStrength.EXTREME) for s in self.steam_moves)

    @property
    def has_distortion(self) -> bool:
        return any(d.confidence > 0.5 for d in self.distortions)


@dataclass
class BookmakerBehaviorReport:
    profiles: dict[str, BookmakerProfile] = field(default_factory=dict)
    market_share_by_reaction: dict[str, float] = field(default_factory=dict)
    avg_reaction_time: float = 0.0
    most_aggressive: Optional[str] = None
    most_conservative: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
