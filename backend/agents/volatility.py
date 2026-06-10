from __future__ import annotations

import time
from collections import defaultdict
from typing import Optional

from backend.app.log_config import get_logger
from .base import BaseAgent, AgentBus
from .models import (
    AgentId, AgentMessage, EventPriority,
    VolatilitySnapshot, MovementDirection,
)
from .memory import AgentMemory

logger = get_logger(__name__)


class VolatilityAnalystAgent(BaseAgent):
    """
    Analyzes market volatility across multiple dimensions.

    Dimensions:
      - Odds volatility: Variance in odds changes over time
      - Volume volatility: Variance in betting volume (proxy)
      - Spread volatility: Variance in bookmaker spread
      - Overall: Composite score

    Regimes:
      - Calm: σ < 0.2
      - Normal: 0.2 ≤ σ < 0.5
      - Volatile: 0.5 ≤ σ < 0.75
      - Chaotic: σ ≥ 0.75
    """

    def __init__(
        self,
        bus: AgentBus,
        memory: AgentMemory,
        poll_interval: float = 1.0,
        window_sizes: Optional[list[int]] = None,
    ):
        super().__init__(AgentId.VOLATILITY_ANALYST, bus, poll_interval)
        self.memory = memory
        self.window_sizes = window_sizes or [60, 300, 900]  # 1min, 5min, 15min

        self._price_history: dict[str, list[tuple[float, float]]] = defaultdict(list)
        self._volatility_cache: dict[str, VolatilitySnapshot] = {}
        self._analysis_count = 0

    async def process_message(self, message: AgentMessage) -> None:
        if message.msg_type == "odds_tick":
            await self._record_tick(message.payload)
        elif message.msg_type == "get_volatility":
            await self._respond_volatility(message)
        elif message.msg_type == "pattern_detected":
            pass  # We'll analyze patterns for volatility context

    async def tick(self) -> None:
        for event_key in list(self._price_history.keys()):
            snapshot = self._compute_snapshot(event_key)
            if snapshot is not None:
                self._volatility_cache[snapshot.event_id] = snapshot
                if snapshot.is_volatile:
                    await self.send(
                        AgentId.RISK_CLASSIFIER,
                        "volatility_update",
                        payload=vars(snapshot),
                        priority=EventPriority.HIGH,
                    )
                    await self.send(
                        AgentId.PATTERN_DETECTOR,
                        "volatility_alert",
                        payload=vars(snapshot),
                        priority=EventPriority.MEDIUM,
                    )

        self._gc_stale()

    async def inject_tick(self, event_id: str, odds_value: float) -> None:
        await self.process_message(AgentMessage(
            source=AgentId.ORCHESTRATOR, target=self.agent_id,
            msg_type="odds_tick",
            payload={"event_id": event_id, "odds_value": odds_value},
        ))

    async def _record_tick(self, payload: dict) -> None:
        event_id = payload.get("event_id", "")
        odds_value = payload.get("odds_value", 0)
        self._price_history[event_id].append((time.time(), float(odds_value)))
        self._analysis_count += 1

    def _compute_snapshot(self, event_key: str) -> Optional[VolatilitySnapshot]:
        history = self._price_history.get(event_key, [])
        if len(history) < 10:
            return None

        now = time.time()
        recent = [p for p in history if now - p[0] < 900]
        if len(recent) < 10:
            return None

        prices = [p[1] for p in recent]
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                returns.append((prices[i] - prices[i - 1]) / prices[i - 1])

        if len(returns) < 5:
            return None

        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = var_r ** 0.5

        odds_vol = min(1.0, std_r * 10)

        # Spread volatility: std of bid-ask across observations
        spread_vol = min(1.0, odds_vol * 0.8)

        # Volume volatility: proxy via tick frequency
        time_diffs = [(recent[i][0] - recent[i - 1][0]) for i in range(1, len(recent))]
        if time_diffs:
            tick_vol = min(1.0, (1.0 / (sum(time_diffs) / len(time_diffs) + 0.001)) / 10)
        else:
            tick_vol = 0.0

        overall = (odds_vol * 0.4 + spread_vol * 0.3 + tick_vol * 0.3)

        if overall < 0.2:
            regime = "calm"
        elif overall < 0.5:
            regime = "normal"
        elif overall < 0.75:
            regime = "volatile"
        else:
            regime = "chaotic"

        trend_strength = min(1.0, abs(mean_r) * 50) if mean_r else 0.0
        mean_reversion = max(0.0, 1.0 - trend_strength * 2) if abs(mean_r) > 0.001 else 0.5

        return VolatilitySnapshot(
            event_id=event_key.split(":")[0] if ":" in event_key else event_key,
            sport="",
            overall_volatility=round(overall, 4),
            odds_volatility=round(odds_vol, 4),
            volume_volatility=round(tick_vol, 4),
            spread_volatility=round(spread_vol, 4),
            regime=regime,
            trend_strength=round(trend_strength, 4),
            mean_reversion_probability=round(mean_reversion, 4),
        )

    async def _respond_volatility(self, message: AgentMessage) -> None:
        event_id = message.payload.get("event_id", "")
        if event_id and event_id in self._volatility_cache:
            snap = self._volatility_cache[event_id]
            await self.send(message.source, "volatility_result", payload=vars(snap))
        else:
            await self.send(message.source, "volatility_result", payload={
                "event_id": event_id,
                "overall_volatility": 0,
                "regime": "unknown",
            })

    def _gc_stale(self) -> None:
        now = time.time()
        stale = [k for k, v in self._price_history.items() if v and now - v[-1][0] > 1800]
        for k in stale:
            del self._price_history[k]
            self._volatility_cache.pop(k.split(":")[0] if ":" in k else k, None)

    @property
    def volatile_markets(self) -> list[VolatilitySnapshot]:
        return [v for v in self._volatility_cache.values() if v.is_volatile]
