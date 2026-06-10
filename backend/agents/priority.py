from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.app.log_config import get_logger
from .models import (
    AgentMessage, EventPriority, PatternType, AlertSeverity,
    AgentAlert,
)

logger = get_logger(__name__)


@dataclass
class PrioritizedEvent:
    message: AgentMessage
    score: float
    reason: str
    timestamp: float = field(default_factory=time.time)

    def __lt__(self, other: "PrioritizedEvent") -> bool:
        return self.score > other.score  # higher score first


class PriorityEngine:
    """
    Multi-factor event prioritization.

    Factors:
      - Base priority from message type
      - Urgency: how close to event start
      - Impact: profit potential / risk reduction
      - Confidence: pattern confidence / evidence strength
      - Novelty: how different from recent events
      - Decay: priority decreases over time if not processed
    """

    def __init__(self, decay_half_life: float = 30.0):
        self._decay_half_life = decay_half_life
        self._recent_events: dict[str, float] = {}

    def score(self, message: AgentMessage) -> PrioritizedEvent:
        base = float(message.priority.value)
        urgency = self._factor_urgency(message)
        impact = self._factor_impact(message)
        confidence = self._factor_confidence(message)
        novelty = self._factor_novelty(message)

        score = (
            base * 1.0 +
            urgency * 0.25 +
            impact * 0.20 +
            confidence * 0.15 +
            novelty * 0.10
        )

        reason_parts = []
        if urgency > 0: reason_parts.append(f"urgency={urgency:.1f}")
        if impact > 0: reason_parts.append(f"impact={impact:.1f}")
        if confidence > 0: reason_parts.append(f"confidence={confidence:.1f}")
        if novelty > 0: reason_parts.append(f"novelty={novelty:.1f}")
        reason = ", ".join(reason_parts) if reason_parts else "no boosters"

        return PrioritizedEvent(
            message=message,
            score=score,
            reason=reason,
        )

    def _factor_urgency(self, msg: AgentMessage) -> float:
        """Events closer to start time get higher urgency."""
        payload = msg.payload
        expires_at = payload.get("expires_at")
        if expires_at is None:
            return 0.0

        try:
            remaining = expires_at - datetime.now(timezone.utc)
            remaining_seconds = remaining.total_seconds()
        except Exception:
            return 0.0

        if remaining_seconds <= 0:
            return 0.0
        if remaining_seconds < 300:          # < 5 min
            return 1.0
        if remaining_seconds < 1800:         # < 30 min
            return 0.75
        if remaining_seconds < 7200:         # < 2 hours
            return 0.5
        if remaining_seconds < 86400:        # < 1 day
            return 0.25
        return 0.0

    def _factor_impact(self, msg: AgentMessage) -> float:
        """Profit potential or risk reduction."""
        profit = msg.payload.get("profit_pct", msg.payload.get("expected_value", 0))
        if isinstance(profit, (int, float)):
            if profit > 10: return 1.0
            if profit > 5: return 0.8
            if profit > 2: return 0.5
            if profit > 1: return 0.3
            if profit > 0.5: return 0.1
        return 0.0

    def _factor_confidence(self, msg: AgentMessage) -> float:
        confidence = msg.payload.get("confidence", 0.5)
        if isinstance(confidence, (int, float)):
            return min(1.0, max(0.0, confidence))
        return 0.5

    def _factor_novelty(self, msg: AgentMessage) -> float:
        """Higher score for events we haven't seen recently."""
        dedup_key = f"{msg.msg_type}:{msg.payload.get('event_id', '')}:{msg.payload.get('pattern', '')}"
        now = time.time()
        last_seen = self._recent_events.get(dedup_key, 0.0)
        elapsed = now - last_seen
        self._recent_events[dedup_key] = now

        if elapsed > 3600:     # > 1 hour → very novel
            return 1.0
        if elapsed > 900:      # > 15 min → novel
            return 0.75
        if elapsed > 300:      # > 5 min → somewhat novel
            return 0.5
        if elapsed > 60:       # > 1 min → slightly novel
            return 0.25
        return 0.0             # recently seen → redundant

    def cleanup(self, max_age_seconds: int = 3600) -> None:
        now = time.time()
        stale = [k for k, v in self._recent_events.items() if now - v > max_age_seconds]
        for k in stale:
            del self._recent_events[k]


class EventScheduler:
    """
    Schedule delayed or recurring events.

    Supports:
      - Delayed dispatch (e.g., "check again in 5 min")
      - Cron-like periodic dispatch
      - Conditional dispatch (only if condition met)
    """

    def __init__(self):
        self._scheduled: dict[str, float] = {}
        self._periodic: dict[str, tuple[float, callable]] = {}

    def schedule_once(self, key: str, delay_seconds: float) -> None:
        self._scheduled[key] = time.time() + delay_seconds

    def schedule_periodic(self, key: str, interval_seconds: float, callback: callable) -> None:
        self._periodic[key] = (interval_seconds, callback)

    def cancel(self, key: str) -> None:
        self._scheduled.pop(key, None)
        self._periodic.pop(key, None)

    def get_due(self) -> list[tuple[str, Optional[callable]]]:
        now = time.time()
        due: list[tuple[str, Optional[callable]]] = []

        for key, deadline in list(self._scheduled.items()):
            if now >= deadline:
                due.append((key, None))
                del self._scheduled[key]

        for key, (interval, callback) in list(self._periodic.items()):
            last = self._scheduled.get(f"_periodic_{key}", 0)
            if now - last >= interval:
                due.append((key, callback))
                self._scheduled[f"_periodic_{key}"] = now

        return due
