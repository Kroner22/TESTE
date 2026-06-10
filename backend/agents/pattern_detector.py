from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from backend.app.log_config import get_logger
from .base import BaseAgent, AgentBus
from .models import (
    AgentId, AgentMessage, EventPriority, PatternType,
    DetectedPattern, MovementDirection, MovementSpeed, OddsMovementEvent,
)
from .memory import AgentMemory

logger = get_logger(__name__)


@dataclass
class PatternConfig:
    steam_move_min_pct: float = 5.0
    steam_move_max_minutes: float = 5.0
    steam_move_min_bookmakers: int = 2

    reverse_line_min_bet_pct: float = 60.0
    reverse_line_odd_direction: str = "opposite"

    arb_min_profit_pct: float = 0.5

    value_min_ev: float = 5.0
    value_min_confidence: float = 0.6

    cooling_min_odds_drop: float = 3.0
    cooling_min_bookmakers: int = 2
    cooling_window_minutes: float = 15.0

    late_movement_min_pct: float = 2.0
    late_movement_max_hours: float = 1.0

    sharp_money_min_odd_drop: float = 10.0
    sharp_money_volume_weight: float = 0.7


class PatternDetectionAgent(BaseAgent):
    """
    Detects abnormal patterns in sports markets.

    Patterns:
      - Steam Move: Fast odds drop across multiple bookmakers (sharp money)
      - Reverse Line: Public bets one way, odds move the opposite
      - Arbitrage: Cross-bookmaker arbitrage opportunity
      - Value Bet: Positive EV with high confidence
      - Market Cooling: Odds freeze/drop before major announcement
      - Late Movement: Significant odds change close to event start
      - Sharp Money: Large bet(s) moving the line
      - Fade the Public: Public heavy on one side, line moving other
      - Bookmaker Error: Mispriced odds (suspended market correction)
    """

    def __init__(
        self,
        bus: AgentBus,
        memory: AgentMemory,
        poll_interval: float = 0.1,
        config: Optional[PatternConfig] = None,
    ):
        super().__init__(AgentId.PATTERN_DETECTOR, bus, poll_interval)
        self.memory = memory
        self.config = config or PatternConfig()

        self._detected_patterns: dict[str, DetectedPattern] = {}
        self._recent_movements: dict[str, list[OddsMovementEvent]] = defaultdict(list)
        self._public_bet_pcts: dict[str, float] = {}  # event_id → % public on home
        self._pattern_counts: dict[str, int] = defaultdict(int)

    async def process_message(self, message: AgentMessage) -> None:
        handler_map = {
            "odds_movement": self._handle_movement,
            "movement_summary": self._handle_summary,
            "potential_steam_move": self._handle_potential_steam,
            "public_bet_pct": self._handle_public_bet,
            "market_odds": self._handle_market_odds,
            "value_result": self._handle_value_result,
        }
        handler = handler_map.get(message.msg_type)
        if handler:
            await handler(message)

    async def tick(self) -> None:
        self._gc_expired_patterns()
        self._gc_old_movements()

    async def _handle_movement(self, message: AgentMessage) -> None:
        payload = message.payload
        event = OddsMovementEvent(**{
            k: v for k, v in payload.items()
            if k in OddsMovementEvent.__dataclass_fields__
        })

        self._recent_movements[event.event_id].append(event)

        if event.speed in (MovementSpeed.INSTANT, MovementSpeed.FAST) and event.n_bookmakers_moved >= self.config.steam_move_min_bookmakers:
            await self._detect_steam_move(event)

        await self._check_late_movement(event)

    async def _handle_summary(self, message: AgentMessage) -> None:
        payload = message.payload
        event_id = payload.get("event_id", "")
        volatility = payload.get("volatility_pct", 0)
        max_change = payload.get("max_change_pct", 0)

        if volatility > 3.0 or max_change > 5.0:
            pattern = DetectedPattern(
                pattern_type=PatternType.ODDS_SHOPPING,
                event_id=event_id.split(":")[0] if ":" in event_id else event_id,
                sport=payload.get("sport", ""),
                confidence=min(1.0, volatility / 10.0),
                description=f"High volatility window: σ={volatility:.1f}%, max Δ={max_change:.1f}%",
                supporting_data=payload,
                is_actionable=volatility > 5.0,
            )
            await self._emit_pattern(pattern)

    async def _handle_potential_steam(self, message: AgentMessage) -> None:
        payload = message.payload
        event_id = payload["event_id"]
        outcome = payload["outcome"]
        change_pct = payload["change_pct"]
        bookmakers = payload["bookmakers"]

        pattern = DetectedPattern(
            pattern_type=PatternType.STEAM_MOVE,
            event_id=event_id,
            sport=payload.get("sport", ""),
            confidence=min(1.0, abs(change_pct) / 15.0),
            description=f"Steam move: {outcome} dropped {abs(change_pct):.1f}% across {len(bookmakers)} bookmakers",
            supporting_data=payload,
            is_actionable=True,
        )
        await self._emit_pattern(pattern)

    async def _detect_steam_move(self, event: OddsMovementEvent) -> None:
        pattern = DetectedPattern(
            pattern_type=PatternType.STEAM_MOVE,
            event_id=event.event_id,
            sport=event.sport,
            confidence=min(1.0, abs(event.change_pct) / 15.0),
            description=f"Steam move detected: {event.outcome} moved {abs(event.change_pct):.1f}% ({event.speed.value}) across {event.n_bookmakers_moved} books",
            supporting_data=vars(event),
            is_actionable=True,
        )
        await self._emit_pattern(pattern)

    async def _check_late_movement(self, event: OddsMovementEvent) -> None:
        expires_at = event.timestamp
        if not expires_at:
            return

        try:
            remaining = expires_at - datetime.now(timezone.utc)
            if 0 < remaining.total_seconds() < self.config.late_movement_max_hours * 3600:
                if abs(event.change_pct) >= self.config.late_movement_min_pct:
                    pattern = DetectedPattern(
                        pattern_type=PatternType.LATE_MOVEMENT,
                        event_id=event.event_id,
                        sport=event.sport,
                        confidence=0.7,
                        description=f"Late movement: {abs(event.change_pct):.1f}% change within {remaining.total_seconds() / 60:.0f}min of start",
                        supporting_data=vars(event),
                        expires_at=expires_at,
                        is_actionable=True,
                    )
                    await self._emit_pattern(pattern)
        except Exception:
            pass

    async def _handle_public_bet(self, message: AgentMessage) -> None:
        payload = message.payload
        event_id = payload["event_id"]
        home_pct = payload.get("home_bet_pct", 50.0)
        away_pct = payload.get("away_bet_pct", 50.0)
        home_odds_movement = payload.get("home_odds_movement", 0.0)

        self._public_bet_pcts[event_id] = home_pct

        if home_pct > self.config.reverse_line_min_bet_pct and home_odds_movement > 0:
            pattern = DetectedPattern(
                pattern_type=PatternType.REVERSE_LINE,
                event_id=event_id,
                sport=payload.get("sport", ""),
                confidence=min(1.0, (home_pct - 50) / 50),
                description=f"Reverse line: {home_pct:.0f}% public on home but odds moving away ({home_odds_movement:+.1f}%)",
                supporting_data=payload,
                is_actionable=True,
            )
            await self._emit_pattern(pattern)
        elif away_pct > self.config.reverse_line_min_bet_pct and home_odds_movement < 0:
            pattern = DetectedPattern(
                pattern_type=PatternType.FADE_THE_PUBLIC,
                event_id=event_id,
                sport=payload.get("sport", ""),
                confidence=min(1.0, (away_pct - 50) / 50),
                description=f"Fade public: {away_pct:.0f}% public on away but odds moving toward home",
                supporting_data=payload,
                is_actionable=True,
            )
            await self._emit_pattern(pattern)

    async def _handle_market_odds(self, message: AgentMessage) -> None:
        payload = message.payload
        odds = payload.get("odds", [])
        commissions = payload.get("commissions", None)

        from backend.domains.arbitrage.core import has_arb, arb_profit_pct
        from decimal import Decimal

        odd_decimals = [Decimal(str(o)) for o in odds]
        if has_arb(odd_decimals, [Decimal(str(c)) for c in commissions] if commissions else None):
            profit_pct = arb_profit_pct(odd_decimals, [Decimal(str(c)) for c in commissions] if commissions else None)
            if float(profit_pct) >= self.config.arb_min_profit_pct:
                pattern = DetectedPattern(
                    pattern_type=PatternType.ARBITRAGE,
                    event_id=payload.get("event_id", ""),
                    sport=payload.get("sport", ""),
                    confidence=min(1.0, float(profit_pct) * 10),
                    description=f"Arbitrage: {float(profit_pct):.2f}% guaranteed return",
                    supporting_data=payload,
                    is_actionable=True,
                )
                await self._emit_pattern(pattern)

    async def _handle_value_result(self, message: AgentMessage) -> None:
        payload = message.payload
        ev = payload.get("expected_value", 0)
        confidence = payload.get("confidence", 0)

        if isinstance(ev, (int, float)) and isinstance(confidence, (int, float)):
            if ev >= self.config.value_min_ev and confidence >= self.config.value_min_confidence:
                pattern = DetectedPattern(
                    pattern_type=PatternType.VALUE_BET,
                    event_id=payload.get("event_id", ""),
                    sport=payload.get("sport", ""),
                    confidence=confidence,
                    description=f"Value bet: EV={ev:.1f}%, confidence={confidence:.0%}",
                    supporting_data=payload,
                    is_actionable=True,
                )
                await self._emit_pattern(pattern)

    async def _emit_pattern(self, pattern: DetectedPattern) -> None:
        dedup_key = f"{pattern.pattern_type.value}:{pattern.event_id}:{pattern.timestamp.timestamp() // 60}"
        if dedup_key in self._detected_patterns:
            return

        self._detected_patterns[dedup_key] = pattern
        self._pattern_counts[pattern.pattern_type.value] += 1

        self.memory.remember_event(
            pattern.event_id, self.agent_id,
            vars(pattern), importance=0.7,
        )

        priority = EventPriority.CRITICAL if pattern.is_actionable and pattern.confidence > 0.8 else \
                   EventPriority.HIGH if pattern.is_actionable else EventPriority.MEDIUM

        await self.send(AgentId.OPPORTUNITY_SCOUT, "detected_pattern", payload=vars(pattern), priority=priority)
        await self.send(AgentId.ALERT_MANAGER, "pattern_detected", payload=vars(pattern), priority=priority)
        await self.send(AgentId.LEARNING, "pattern_occurred", payload={
            "pattern_type": pattern.pattern_type.value,
            "confidence": pattern.confidence,
            "is_actionable": pattern.is_actionable,
        })

    def _gc_expired_patterns(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [k for k, p in self._detected_patterns.items()
                   if p.expires_at and p.expires_at < now]
        for k in expired:
            del self._detected_patterns[k]

    def _gc_old_movements(self) -> None:
        now = time.time()
        stale = [eid for eid, moves in self._recent_movements.items()
                 if moves and (now - moves[-1].timestamp.timestamp()) > 3600]
        for eid in stale:
            del self._recent_movements[eid]

    @property
    def active_patterns(self) -> list[DetectedPattern]:
        return list(self._detected_patterns.values())
