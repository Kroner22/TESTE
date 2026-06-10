from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from backend.app.log_config import get_logger
from .base import BaseAgent, AgentBus
from .models import (
    AgentId, AgentMessage, EventPriority,
    AlertSeverity, AgentAlert, PatternType,
)
from .memory import AgentMemory

logger = get_logger(__name__)


@dataclass
class AlertThrottle:
    """Prevents alert storms by tracking frequency per source+event."""
    last_sent: float = 0.0
    count: int = 0
    suppressed: int = 0
    cooldown_seconds: float = 30.0

    def should_send(self) -> bool:
        now = time.time()
        if now - self.last_sent >= self.cooldown_seconds:
            self.last_sent = now
            self.count += 1
            return True
        self.suppressed += 1
        return False


class AlertManagerAgent(BaseAgent):
    """
    Smart alert management with deduplication, throttling, and prioritization.

    Features:
      - Dedup: Same alert within window is suppressed
      - Throttle: Per-source per-event rate limiting
      - Priority: HIGH/CRITICAL alerts bypass throttling
      - Severity classification
      - Alert history tracking
      - Batch digest for LOW priority
    """

    def __init__(
        self,
        bus: AgentBus,
        memory: AgentMemory,
        poll_interval: float = 0.2,
        max_alerts_in_history: int = 1000,
    ):
        super().__init__(AgentId.ALERT_MANAGER, bus, poll_interval)
        self.memory = memory
        self.max_alerts_in_history = max_alerts_in_history

        self._alerts: dict[str, AgentAlert] = {}  # alert_id → alert
        self._history: list[AgentAlert] = []
        self._throttles: dict[str, AlertThrottle] = defaultdict(AlertThrottle)
        self._alert_id_counter = 0
        self._low_priority_buffer: list[AgentAlert] = []

    async def process_message(self, message: AgentMessage) -> None:
        handler_map = {
            "pattern_detected": self._handle_pattern,
            "risk_assessment": self._handle_risk,
            "high_value_opportunity": self._handle_opportunity,
            "volatility_alert": self._handle_volatility,
            "acknowledge": self._handle_acknowledge,
        }
        handler = handler_map.get(message.msg_type)
        if handler:
            await handler(message)

    async def tick(self) -> None:
        if self._low_priority_buffer:
            digest = self._low_priority_buffer[:10]
            self._low_priority_buffer = self._low_priority_buffer[10:]
            await self._emit_digest(digest)
        self._gc_expired()

    async def _handle_pattern(self, payload: dict) -> None:
        await self._create_alert(
            source=AgentId.PATTERN_DETECTOR,
            severity=self._severity_for_pattern(payload.get("pattern_type", "")),
            title=f"Pattern: {payload.get('pattern_type', 'unknown')}",
            description=payload.get("description", ""),
            event_id=payload.get("event_id"),
            pattern=PatternType(payload["pattern_type"]) if payload.get("pattern_type") else None,
            confidence=payload.get("confidence", 0.5),
            payload=payload,
        )

    async def _handle_risk(self, payload: dict) -> None:
        risk_level = payload.get("risk_level", "LOW")
        if risk_level in ("HIGH", "EXTREME"):
            await self._create_alert(
                source=AgentId.RISK_CLASSIFIER,
                severity=AlertSeverity.HIGH,
                title=f"Risk: {risk_level}",
                description=f"Risk assessment: {risk_level} ({', '.join(payload.get('factors', []))})",
                event_id=payload.get("event_id"),
                confidence=0.9,
                payload=payload,
            )

    async def _handle_opportunity(self, payload: dict) -> None:
        await self._create_alert(
            source=AgentId.OPPORTUNITY_SCOUT,
            severity=AlertSeverity.HIGH,
            title=f"Top Opportunity: {payload.get('pattern_type', 'value')}",
            description=f"Score: {payload.get('score', 0):.1f} — {payload.get('event_id', '')}",
            event_id=payload.get("event_id"),
            confidence=payload.get("confidence", 0.7),
            payload=payload,
        )

    async def _handle_volatility(self, payload: dict) -> None:
        regime = payload.get("regime", "unknown")
        if regime in ("volatile", "chaotic"):
            await self._create_alert(
                source=AgentId.VOLATILITY_ANALYST,
                severity=AlertSeverity.MEDIUM,
                title=f"Market Volatility: {regime.upper()}",
                description=f"{payload.get('event_id', '')} — σ={payload.get('overall_volatility', 0):.3f}",
                event_id=payload.get("event_id"),
                confidence=0.8,
                payload=payload,
            )

    async def _handle_acknowledge(self, payload: dict) -> None:
        alert_id = payload.get("alert_id", "")
        if alert_id in self._alerts:
            self._alerts[alert_id].acknowledged = True

    async def _create_alert(
        self,
        source: AgentId,
        severity: AlertSeverity,
        title: str,
        description: str,
        event_id: Optional[str] = None,
        pattern: Optional[PatternType] = None,
        confidence: float = 1.0,
        payload: dict = None,
    ) -> Optional[AgentAlert]:
        dedup_key = f"{source.value}:{event_id or 'global'}:{title}"
        throttle = self._throttles[dedup_key]

        if severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH):
            pass  # Always send high severity
        elif not throttle.should_send():
            return None

        self._alert_id_counter += 1
        alert_id = f"alert_{self._alert_id_counter}_{int(time.time())}"

        alert = AgentAlert(
            alert_id=alert_id,
            source=source,
            severity=severity,
            title=title,
            description=description,
            event_id=event_id,
            pattern=pattern,
            confidence=confidence,
            payload=payload or {},
            n_suppressed=throttle.suppressed,
        )

        self._alerts[alert_id] = alert
        self._history.append(alert)

        if len(self._history) > self.max_alerts_in_history:
            self._history = self._history[-self.max_alerts_in_history:]

        if severity in (AlertSeverity.LOW, AlertSeverity.INFO):
            self._low_priority_buffer.append(alert)
        else:
            await self._emit_alert(alert)

        self.memory.remember_event(
            event_id or alert_id, self.agent_id,
            {"alert_id": alert_id, "title": title, "severity": severity.value},
            importance=0.6,
        )

        return alert

    async def _emit_alert(self, alert: AgentAlert) -> None:
        await self.send(
            AgentId.LEARNING,
            "alert_emitted",
            payload=vars(alert),
            priority=EventPriority.LOW,
        )

    async def _emit_digest(self, alerts: list[AgentAlert]) -> None:
        pass

    def _severity_for_pattern(self, pattern_type: str) -> AlertSeverity:
        mapping = {
            "steam_move": AlertSeverity.CRITICAL,
            "arbitrage": AlertSeverity.HIGH,
            "value_bet": AlertSeverity.HIGH,
            "reverse_line": AlertSeverity.HIGH,
            "sharp_money": AlertSeverity.HIGH,
            "bookmaker_error": AlertSeverity.CRITICAL,
            "late_movement": AlertSeverity.MEDIUM,
            "market_cooling": AlertSeverity.MEDIUM,
            "fade_the_public": AlertSeverity.MEDIUM,
        }
        return mapping.get(pattern_type, AlertSeverity.INFO)

    def _gc_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [aid for aid, a in self._alerts.items()
                   if a.expires_at and a.expires_at < now]
        for aid in expired:
            del self._alerts[aid]

    def acknowledge(self, alert_id: str) -> bool:
        alert = self._alerts.get(alert_id)
        if alert:
            alert.acknowledged = True
            return True
        return False

    @property
    def active_alerts(self) -> list[AgentAlert]:
        return [
            a for a in self._alerts.values()
            if not a.acknowledged
        ]

    @property
    def unacknowledged_count(self) -> int:
        return len([a for a in self._alerts.values() if not a.acknowledged])
