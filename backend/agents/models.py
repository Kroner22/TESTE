from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum, auto
from typing import Optional


class AgentId(str, Enum):
    ORCHESTRATOR = "orchestrator"
    ODDS_MOVEMENT = "odds_movement"
    PATTERN_DETECTOR = "pattern_detector"
    OPPORTUNITY_SCOUT = "opportunity_scout"
    VOLATILITY_ANALYST = "volatility_analyst"
    RISK_CLASSIFIER = "risk_classifier"
    ALERT_MANAGER = "alert_manager"
    LEARNING = "learning"


class EventPriority(int, Enum):
    CRITICAL = 100
    HIGH = 75
    MEDIUM = 50
    LOW = 25
    BACKGROUND = 0


class AgentState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class MovementDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class MovementSpeed(str, Enum):
    INSTANT = "instant"     # < 1 min
    FAST = "fast"           # 1-5 min
    MODERATE = "moderate"   # 5-15 min
    SLOW = "slow"           # 15-60 min
    DRIFT = "drift"         # > 60 min


class PatternType(str, Enum):
    STEAM_MOVE = "steam_move"
    REVERSE_LINE = "reverse_line"
    ARBITRAGE = "arbitrage"
    VALUE_BET = "value_bet"
    MARKET_COOLING = "market_cooling"
    LATE_MOVEMENT = "late_movement"
    ODDS_SHOPPING = "odds_shopping"
    SHARP_MONEY = "sharp_money"
    FADE_THE_PUBLIC = "fade_the_public"
    BOOKMAKER_ERROR = "bookmaker_error"


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


# ─── Agent Messages ─────────────────────────────────────────────

@dataclass
class AgentMessage:
    source: AgentId
    target: AgentId
    msg_type: str
    payload: dict = field(default_factory=dict)
    priority: EventPriority = EventPriority.MEDIUM
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str = ""

    @property
    def key(self) -> str:
        return f"{self.source.value}:{self.target.value}:{self.msg_type}:{self.timestamp.timestamp()}"


# ─── Odds Movement ──────────────────────────────────────────────

@dataclass
class OddsTick:
    event_id: str
    bookmaker: str
    outcome: str
    old_odd: Decimal
    new_odd: Decimal
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def change_pct(self) -> float:
        if self.old_odd <= 0:
            return 0.0
        return float((self.new_odd - self.old_odd) / self.old_odd * 100)

    @property
    def direction(self) -> MovementDirection:
        if self.change_pct > 0.5:
            return MovementDirection.UP
        elif self.change_pct < -0.5:
            return MovementDirection.DOWN
        return MovementDirection.FLAT


@dataclass
class OddsMovementEvent:
    event_id: str
    sport: str
    home_team: str
    away_team: str
    outcome: str
    old_odd: Decimal
    new_odd: Decimal
    change_pct: float
    direction: MovementDirection
    speed: MovementSpeed
    bookmakers_involved: list[str]
    n_bookmakers_moved: int
    time_span_seconds: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MovementSummary:
    event_id: str
    n_ticks: int = 0
    max_change_pct: float = 0.0
    avg_change_pct: float = 0.0
    volatility_pct: float = 0.0
    dominant_direction: MovementDirection = MovementDirection.FLAT
    recent_ticks: list[OddsTick] = field(default_factory=list)
    window_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    window_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_notable: bool = False


# ─── Patterns ───────────────────────────────────────────────────

@dataclass
class DetectedPattern:
    pattern_type: PatternType
    event_id: str
    sport: str
    confidence: float  # 0-1
    description: str
    supporting_data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    is_actionable: bool = False


# ─── Volatility ─────────────────────────────────────────────────

@dataclass
class VolatilitySnapshot:
    event_id: str
    sport: str
    overall_volatility: float       # 0-1
    odds_volatility: float          # 0-1
    volume_volatility: float        # 0-1
    spread_volatility: float        # 0-1
    regime: str                     # "calm" | "normal" | "volatile" | "chaotic"
    trend_strength: float           # 0-1
    mean_reversion_probability: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_volatile(self) -> bool:
        return self.overall_volatility > 0.5

    @property
    def is_chaotic(self) -> bool:
        return self.overall_volatility > 0.75


# ─── Risk ───────────────────────────────────────────────────────

@dataclass
class RiskAssessment:
    event_id: str
    sport: str
    overall_risk: float              # 0-1
    market_risk: float               # 0-1
    timing_risk: float               # 0-1
    liquidity_risk: float            # 0-1
    volatility_risk: float           # 0-1
    information_risk: float          # 0-1
    risk_level: str                  # "LOW" | "MEDIUM" | "HIGH" | "EXTREME"
    factors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Alerts ─────────────────────────────────────────────────────

@dataclass
class AgentAlert:
    alert_id: str
    source: AgentId
    severity: AlertSeverity
    title: str
    description: str
    event_id: Optional[str] = None
    pattern: Optional[PatternType] = None
    confidence: float = 1.0
    payload: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    acknowledged: bool = False
    n_suppressed: int = 0


# ─── Learning ───────────────────────────────────────────────────

@dataclass
class AgentMemoryEntry:
    key: str
    agent: AgentId
    value: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: Optional[int] = None
    importance: float = 0.5          # 0-1, used for memory pruning


@dataclass
class LearnedThreshold:
    agent: AgentId
    metric: str
    current_value: float
    mean: float
    std: float
    min_value: float
    max_value: float
    n_samples: int
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Orchestrator ───────────────────────────────────────────────

@dataclass
class AgentHealth:
    agent_id: AgentId
    state: AgentState
    uptime_seconds: float
    messages_processed: int
    errors_last_hour: int
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    memory_usage_mb: float = 0.0
    is_healthy: bool = True


@dataclass
class OrchestratorSnapshot:
    n_agents: int
    agents: dict[str, AgentHealth]
    queue_depth: int
    messages_processed_total: int
    alerts_active: int
    patterns_active: int
    uptime_seconds: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
