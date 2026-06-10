from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class ArbType(str, Enum):
    TWO_WAY = "2-way"
    THREE_WAY = "3-way"
    TWO_WAY_HEDGE = "2-way_hedge"


class StakeMethod(str, Enum):
    EQUAL_PROFIT = "equal_profit"       # Same profit regardless of outcome
    WEIGHTED = "weighted"               # Proportional to odds
    RISK_PARITY = "risk_parity"         # Minimize variance


class ArbGrade(str, Enum):
    ELITE = "ELITE"                     # > 5% return
    STRONG = "STRONG"                   # > 3% return
    SOLID = "SOLID"                     # > 1.5% return
    MARGINAL = "MARGINAL"              # > 0.5% return
    NOISE = "NOISE"                     # <= 0.5% return


@dataclass
class BookmakerOdds:
    bookmaker: str
    outcome: str
    odd: Decimal
    max_stake: Optional[Decimal] = None
    commission: Decimal = Decimal("0")
    liquidity: Decimal = Decimal("0")


@dataclass
class ArbOutcome:
    """A single leg of an arbitrage opportunity."""
    bookmaker: str
    outcome: str
    odd: Decimal
    stake: Decimal = Decimal("0")
    return_amount: Decimal = Decimal("0")
    max_stake: Optional[Decimal] = None
    commission: Decimal = Decimal("0")
    effective_odd: Decimal = Decimal("0")


@dataclass
class ArbOpportunity:
    event_id: str
    sport: str
    home_team: str
    away_team: str
    market: str
    arb_type: ArbType
    legs: list[ArbOutcome]
    total_stake: Decimal = Decimal("0")
    guaranteed_return: Decimal = Decimal("0")
    profit: Decimal = Decimal("0")
    profit_pct: Decimal = Decimal("0")
    grade: ArbGrade = ArbGrade.NOISE
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    is_actionable: bool = False
    constraints: Optional[dict] = None


@dataclass
class HedgePosition:
    """A position to be hedged."""
    event_id: str
    original_outcome: str
    original_odd: Decimal
    original_stake: Decimal
    current_hedge_odd: Decimal
    hedge_bookmaker: str
    lock_profit: Decimal = Decimal("0")
    hedge_stake: Decimal = Decimal("0")
    is_locked: bool = False


@dataclass
class ArbScanResult:
    n_opportunities: int = 0
    opportunities: list[ArbOpportunity] = field(default_factory=list)
    scan_duration_ms: float = 0.0
    n_comparisons: int = 0
    n_markets_scanned: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ArbFilter:
    min_profit_pct: Decimal = Decimal("0.005")    # 0.5% minimum
    max_commission: Decimal = Decimal("0.05")     # 5% max commission
    min_stake_per_leg: Decimal = Decimal("1")     # Minimum $1 per leg
    max_stake_per_leg: Optional[Decimal] = None
    exclude_bookmakers: list[str] = field(default_factory=list)
    require_actionable: bool = True
