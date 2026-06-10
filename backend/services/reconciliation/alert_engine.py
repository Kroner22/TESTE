from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from backend.app.log_config import get_logger

logger = get_logger(__name__)


class AlertEvent:
    alert_type: str
    severity: str
    message: str
    event_id: str
    timestamp: float
    metadata: dict

    ALERT_TYPES = {
        "SHARP_MOVE": "Movimento brusco de odds detectado",
        "VALUE_OPENED": "Oportunidade de valor aberta",
        "VALUE_CLOSED": "Janela de valor fechada",
        "MARKET_DIVERGENCE": "Divergência entre providers detectada",
        "LATENCY_ADVANTAGE": "Provider com vantagem de latência identificado",
    }

    def __init__(self, alert_type: str, severity: str, message: str, event_id: str = "", metadata: dict | None = None):
        self.alert_type = alert_type
        self.severity = severity
        self.message = message
        self.event_id = event_id
        self.timestamp = datetime.now(timezone.utc).timestamp()
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class AlertEngine:
    """
    Real-time market alert classification engine.

    Generates 5 alert types:
    1. SHARP_MOVE — odds move > threshold within time window
    2. VALUE_OPENED — new EV+ opportunity detected
    3. VALUE_CLOSED — opportunity no longer active (market moved)
    4. MARKET_DIVERGENCE — provider odds diverge > threshold
    5. LATENCY_ADVANTAGE — provider consistently faster than others
    """

    def __init__(self):
        self._alerts: list[AlertEvent] = []
        self._max_alerts = 200
        self._suppressed_types: dict[str, float] = {}
        self._suppress_seconds = 30.0
        self._odds_history: dict[str, list[float]] = defaultdict(list)
        self._sharp_move_threshold = 3.0
        self._sharp_move_window_seconds = 60.0
        self._on_alert: Optional[Callable[[AlertEvent], Awaitable[None]]] = None

    def set_on_alert(self, callback: Callable[[AlertEvent], Awaitable[None]]):
        self._on_alert = callback

    def evaluate_odds_move(self, event_id: str, outcome: str, bookmaker: str, old_odd: float, new_odd: float, timestamp: float) -> Optional[AlertEvent]:
        key = f"{event_id}:{outcome}:{bookmaker}"
        self._odds_history[key].append((timestamp, new_odd))

        # Clean old entries
        cutoff = timestamp - self._sharp_move_window_seconds * 2
        self._odds_history[key] = [(t, o) for t, o in self._odds_history[key] if t > cutoff]

        if old_odd <= 0 or new_odd <= 0:
            return None

        delta_pct = abs((new_odd - old_odd) / old_odd) * 100

        if delta_pct >= self._sharp_move_threshold:
            # Check recent odds for velocity
            recent = [(t, o) for t, o in reversed(self._odds_history[key]) if t > timestamp - self._sharp_move_window_seconds]
            if len(recent) >= 3:
                first_odd = recent[-1][1]
                total_move = abs((new_odd - first_odd) / first_odd) * 100
                velocity = total_move / min(self._sharp_move_window_seconds, (timestamp - recent[-1][0]) if len(recent) > 1 else 60)
                direction = "up" if new_odd > old_odd else "down"
                return self._create_alert(
                    "SHARP_MOVE", "high",
                    f"Movimento brusco de {delta_pct:.1f}% em {outcome} ({bookmaker}) — {direction} — {velocity:.1f}%/min",
                    event_id,
                    {"delta_pct": delta_pct, "direction": direction, "velocity": velocity,
                     "old_odd": old_odd, "new_odd": new_odd, "bookmaker": bookmaker, "outcome": outcome},
                )
        return None

    def evaluate_value_opened(self, event_id: str, outcome: str, bookmaker: str, ev: float, odd: float, confidence: float) -> Optional[AlertEvent]:
        if ev > 0.05 and confidence > 0.6:
            return self._create_alert(
                "VALUE_OPENED", "info",
                f"Valor aberto: EV+ {ev*100:.1f}% em {outcome} ({bookmaker}) @ {odd:.2f}",
                event_id,
                {"ev": ev, "odd": odd, "confidence": confidence, "bookmaker": bookmaker, "outcome": outcome},
            )
        return None

    def evaluate_value_closed(self, event_id: str, outcome: str, bookmaker: str, old_ev: float, new_ev: float) -> Optional[AlertEvent]:
        if old_ev > 0.05 and new_ev <= 0:
            return self._create_alert(
                "VALUE_CLOSED", "warning",
                f"Janela de valor fechada em {outcome} ({bookmaker}) — EV caiu de {old_ev*100:.1f}% para {new_ev*100:.1f}%",
                event_id,
                {"old_ev": old_ev, "new_ev": new_ev, "bookmaker": bookmaker, "outcome": outcome},
            )
        return None

    def evaluate_market_divergence(self, event_id: str, market: str, outcome: str, provider_a: str, provider_b: str, odd_a: float, odd_b: float) -> Optional[AlertEvent]:
        if odd_a <= 0 or odd_b <= 0:
            return None
        deviation = abs(odd_a - odd_b) / max(odd_a, odd_b) * 100
        if deviation > 3.0:
            return self._create_alert(
                "MARKET_DIVERGENCE", "warning",
                f"Divergência de {deviation:.1f}% entre {provider_a} e {provider_b} em {outcome} ({event_id[:12]})",
                event_id,
                {"deviation_pct": deviation, "provider_a": provider_a, "provider_b": provider_b,
                 "odd_a": odd_a, "odd_b": odd_b, "market": market, "outcome": outcome},
            )
        return None

    def evaluate_latency_advantage(self, provider: str, avg_latency: float, market_avg: float) -> Optional[AlertEvent]:
        if market_avg <= 0 or avg_latency <= 0:
            return None
        advantage = ((market_avg - avg_latency) / market_avg) * 100
        if advantage > 20:
            return self._create_alert(
                "LATENCY_ADVANTAGE", "info",
                f"{provider} {advantage:.0f}% mais rápido que a média do mercado ({avg_latency:.0f}ms vs {market_avg:.0f}ms)",
                metadata={"provider": provider, "avg_latency": avg_latency,
                          "market_avg": market_avg, "advantage_pct": advantage},
            )
        return None

    def _create_alert(self, alert_type: str, severity: str, message: str,
                      event_id: str = "", metadata: dict | None = None) -> Optional[AlertEvent]:
        now = datetime.now(timezone.utc).timestamp()
        # Suppression check
        last = self._suppressed_types.get(alert_type, 0)
        if now - last < self._suppress_seconds:
            return None

        alert = AlertEvent(alert_type, severity, message, event_id, metadata)
        self._alerts.append(alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]

        self._suppressed_types[alert_type] = now
        logger.info("alert_engine_generated", type=alert_type, severity=severity, event_id=event_id[:16])

        if self._on_alert:
            import asyncio
            asyncio.ensure_future(self._on_alert(alert))

        return alert

    def get_recent_alerts(self, n: int = 20) -> list[AlertEvent]:
        return self._alerts[-n:]

    def get_alerts_by_type(self, alert_type: str) -> list[AlertEvent]:
        return [a for a in self._alerts if a.alert_type == alert_type]

    def clear(self):
        self._alerts.clear()
        self._suppressed_types.clear()
