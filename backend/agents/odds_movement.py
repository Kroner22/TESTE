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
    AgentId, AgentMessage, EventPriority, MovementDirection,
    MovementSpeed, OddsTick, OddsMovementEvent, MovementSummary,
)
from .memory import AgentMemory

logger = get_logger(__name__)


@dataclass
class MovementWindow:
    ticks: list[OddsTick] = field(default_factory=list)
    last_summary_time: float = 0.0


class OddsMovementAgent(BaseAgent):
    """
    Monitors real-time odds changes and detects significant movements.

    Responsibilities:
      - Track odds ticks per event per bookmaker per outcome
      - Calculate movement velocity and acceleration
      - Classify movement speed (instant → drift)
      - Detect significant cross-bookmaker movements
      - Emit OddsMovementEvent when thresholds breached
    """

    def __init__(
        self,
        bus: AgentBus,
        memory: AgentMemory,
        poll_interval: float = 0.05,
        window_seconds: float = 60.0,
        significant_change_pct: float = 2.0,
        steam_move_pct: float = 5.0,
        min_bookmakers_for_signal: int = 2,
    ):
        super().__init__(AgentId.ODDS_MOVEMENT, bus, poll_interval)
        self.memory = memory
        self.window_seconds = window_seconds
        self.significant_change_pct = significant_change_pct
        self.steam_move_pct = steam_move_pct
        self.min_bookmakers_for_signal = min_bookmakers_for_signal

        self._windows: dict[str, MovementWindow] = defaultdict(MovementWindow)
        self._last_movement_time: dict[str, float] = {}
        self._movement_count = 0

    async def process_message(self, message: AgentMessage) -> None:
        if message.msg_type == "odds_tick":
            await self._handle_tick(message.payload)
        elif message.msg_type == "get_movements":
            await self._respond_movements(message)
        elif message.msg_type == "reset_window":
            event_id = message.payload.get("event_id", "")
            self._windows.pop(event_id, None)

    async def tick(self) -> None:
        now = time.monotonic()
        for event_key, window in list(self._windows.items()):
            if now - window.last_summary_time >= 10.0:
                summary = self._summarize_window(event_key, window)
                if summary.is_notable:
                    await self.send(
                        AgentId.PATTERN_DETECTOR,
                        "movement_summary",
                        payload=vars(summary),
                        priority=EventPriority.HIGH,
                    )
                window.last_summary_time = now

        self._gc_windows()

    async def inject_tick(self, event_id: str, bookmaker: str, outcome: str, old_odd: Decimal, new_odd: Decimal) -> None:
        """Public API for external data sources to push odds ticks."""
        await self.process_message(AgentMessage(
            source=AgentId.ORCHESTRATOR,
            target=self.agent_id,
            msg_type="odds_tick",
            payload={
                "event_id": event_id,
                "bookmaker": bookmaker,
                "outcome": outcome,
                "old_odd": float(old_odd),
                "new_odd": float(new_odd),
            },
        ))

    async def _handle_tick(self, payload: dict) -> None:
        tick = OddsTick(
            event_id=payload["event_id"],
            bookmaker=payload["bookmaker"],
            outcome=payload["outcome"],
            old_odd=Decimal(str(payload["old_odd"])),
            new_odd=Decimal(str(payload["new_odd"])),
        )

        event_key = f"{tick.event_id}:{tick.outcome}"
        window = self._windows[event_key]
        window.ticks.append(tick)

        self.memory.short_term.set(
            f"tick:{event_key}",
            {"last_odd": float(tick.new_odd), "timestamp": time.time()},
            ttl=30.0,
        )

        # Check steam move (fast, large, multi-bookmaker)
        if abs(tick.change_pct) >= self.steam_move_pct:
            await self._check_steam_move(tick, event_key)

        # Check significant move
        if abs(tick.change_pct) >= self.significant_change_pct:
            await self._emit_movement(tick, event_key)

    async def _check_steam_move(self, tick: OddsTick, event_key: str) -> None:
        window = self._windows[event_key]
        recent = [t for t in window.ticks if (time.monotonic() - t.timestamp.timestamp()) < 60.0]
        bookmakers = set(t.bookmaker for t in recent if abs(t.change_pct) >= self.steam_move_pct)

        if len(bookmakers) >= self.min_bookmakers_for_signal:
            await self.send(
                AgentId.PATTERN_DETECTOR,
                "potential_steam_move",
                payload={
                    "event_id": tick.event_id,
                    "outcome": tick.outcome,
                    "change_pct": tick.change_pct,
                    "bookmakers": list(bookmakers),
                    "n_bookmakers": len(bookmakers),
                },
                priority=EventPriority.CRITICAL,
            )

    async def _emit_movement(self, tick: OddsTick, event_key: str) -> None:
        window = self._windows[event_key]
        recent = [t for t in window.ticks if (time.monotonic() - t.timestamp.timestamp()) < self.window_seconds]
        bookmakers = set(t.bookmaker for t in recent)

        time_span = 0.0
        if len(recent) >= 2:
            time_span = (recent[-1].timestamp - recent[0].timestamp).total_seconds()

        speed = self._classify_speed(time_span, abs(tick.change_pct))
        direction = MovementDirection.DOWN if tick.change_pct < 0 else MovementDirection.UP

        event = OddsMovementEvent(
            event_id=tick.event_id,
            sport="",  # filled by caller context
            home_team="",
            away_team="",
            outcome=tick.outcome,
            old_odd=tick.old_odd,
            new_odd=tick.new_odd,
            change_pct=tick.change_pct,
            direction=direction,
            speed=speed,
            bookmakers_involved=list(bookmakers),
            n_bookmakers_moved=len(bookmakers),
            time_span_seconds=time_span,
        )

        self._movement_count += 1
        await self.send(
            AgentId.PATTERN_DETECTOR,
            "odds_movement",
            payload=vars(event),
            priority=EventPriority.HIGH if speed in (MovementSpeed.INSTANT, MovementSpeed.FAST) else EventPriority.MEDIUM,
        )

    def _summarize_window(self, event_key: str, window: MovementWindow) -> MovementSummary:
        if not window.ticks:
            return MovementSummary(event_id=event_key)

        changes = [abs(t.change_pct) for t in window.ticks]
        max_change = max(changes) if changes else 0
        avg_change = sum(changes) / len(changes) if changes else 0

        directions = [t.direction for t in window.ticks]
        dominant = max(set(directions), key=directions.count) if directions else MovementDirection.FLAT

        # Volatility = std of changes
        if len(changes) > 1:
            mean_c = sum(changes) / len(changes)
            variance = sum((c - mean_c) ** 2 for c in changes) / len(changes)
            vol = variance ** 0.5
        else:
            vol = 0.0

        is_notable = max_change >= self.significant_change_pct or vol > 1.0

        return MovementSummary(
            event_id=event_key,
            n_ticks=len(window.ticks),
            max_change_pct=max_change,
            avg_change_pct=avg_change,
            volatility_pct=vol,
            dominant_direction=dominant,
            recent_ticks=window.ticks[-20:],
            window_start=window.ticks[0].timestamp,
            window_end=window.ticks[-1].timestamp,
            is_notable=is_notable,
        )

    def _classify_speed(self, time_span_seconds: float, change_pct: float) -> MovementSpeed:
        """Classify movement speed based on time span and change magnitude."""
        rate = abs(change_pct) / max(time_span_seconds, 0.1)
        if rate > 10:       # > 10% per second
            return MovementSpeed.INSTANT
        if rate > 2:        # 2-10% per second
            return MovementSpeed.FAST
        if rate > 0.5:      # 0.5-2% per second
            return MovementSpeed.MODERATE
        if rate > 0.1:      # 0.1-0.5% per second
            return MovementSpeed.SLOW
        return MovementSpeed.DRIFT

    def _gc_windows(self) -> None:
        now = time.monotonic()
        stale = [k for k, w in self._windows.items() if w.ticks and (now - w.ticks[-1].timestamp.timestamp()) > self.window_seconds * 2]
        for k in stale:
            del self._windows[k]

    async def _respond_movements(self, message: AgentMessage) -> None:
        summaries = {
            k: self._summarize_window(k, w)
            for k, w in self._windows.items()
        }
        await self.send(
            message.source,
            "movements_snapshot",
            payload={k: vars(v) for k, v in summaries.items()},
        )
