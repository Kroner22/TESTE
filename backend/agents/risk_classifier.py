from __future__ import annotations

from typing import Optional

from backend.app.log_config import get_logger
from .base import BaseAgent, AgentBus
from .models import (
    AgentId, AgentMessage, EventPriority,
    RiskAssessment, VolatilitySnapshot,
)
from .memory import AgentMemory

logger = get_logger(__name__)


class RiskClassifierAgent(BaseAgent):
    """
    Multi-dimensional risk classification for each opportunity/market.

    Risk dimensions:
      - Market risk: How liquid/deep is the market
      - Timing risk: How close to event start
      - Liquidity risk: Available stake capacity
      - Volatility risk: Current market volatility
      - Information risk: How much is known vs unknown
      - Overall: Weighted composite (adaptive weights)
    """

    def __init__(
        self,
        bus: AgentBus,
        memory: AgentMemory,
        poll_interval: float = 0.2,
    ):
        super().__init__(AgentId.RISK_CLASSIFIER, bus, poll_interval)
        self.memory = memory
        self._assessments: dict[str, RiskAssessment] = {}
        self._volatility_cache: dict[str, VolatilitySnapshot] = {}

        # Adaptive weights — these evolve via the learning agent
        self._weights = {
            "market": 0.25,
            "timing": 0.20,
            "liquidity": 0.20,
            "volatility": 0.20,
            "information": 0.15,
        }

    async def process_message(self, message: AgentMessage) -> None:
        handler_map = {
            "volatility_update": self._handle_volatility,
            "market_info": self._handle_market_info,
            "classify_opportunity": self._handle_classify,
            "update_weights": self._handle_weight_update,
        }
        handler = handler_map.get(message.msg_type)
        if handler:
            await handler(message)

    async def tick(self) -> None:
        pass

    async def _handle_volatility(self, message: AgentMessage) -> None:
        payload = message.payload
        event_id = payload.get("event_id", "")
        try:
            snap = VolatilitySnapshot(**{
                k: v for k, v in payload.items()
                if k in VolatilitySnapshot.__dataclass_fields__
            })
            self._volatility_cache[event_id] = snap
        except Exception:
            pass

    async def _handle_market_info(self, message: AgentMessage) -> None:
        pass

    async def _handle_classify(self, message: AgentMessage) -> None:
        payload = message.payload
        event_id = payload.get("event_id", "")
        assessment = self._classify(event_id, payload)
        self._assessments[event_id] = assessment

        await self.send(
            AgentId.ALERT_MANAGER,
            "risk_assessment",
            payload=vars(assessment),
            priority=EventPriority.MEDIUM,
        )

        await self.send(
            AgentId.LEARNING,
            "risk_classified",
            payload=vars(assessment),
        )

    async def _handle_weight_update(self, message: AgentMessage) -> None:
        new_weights = message.payload.get("weights", {})
        for k, v in new_weights.items():
            if k in self._weights:
                self._weights[k] = max(0.05, min(0.50, v))
        total = sum(self._weights.values())
        if total > 0:
            for k in self._weights:
                self._weights[k] /= total

    def _classify(self, event_id: str, payload: dict) -> RiskAssessment:
        market_risk = self._calc_market_risk(payload)
        timing_risk = self._calc_timing_risk(payload)
        liquidity_risk = self._calc_liquidity_risk(payload)
        volatility_risk = self._calc_volatility_risk(event_id)
        information_risk = self._calc_information_risk(payload)

        overall = (
            market_risk * self._weights["market"] +
            timing_risk * self._weights["timing"] +
            liquidity_risk * self._weights["liquidity"] +
            volatility_risk * self._weights["volatility"] +
            information_risk * self._weights["information"]
        )

        if overall >= 0.75:
            risk_level = "EXTREME"
        elif overall >= 0.50:
            risk_level = "HIGH"
        elif overall >= 0.25:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        factors = []
        if market_risk > 0.5: factors.append(f"market_depth:{market_risk:.2f}")
        if timing_risk > 0.5: factors.append(f"timing_pressure:{timing_risk:.2f}")
        if liquidity_risk > 0.5: factors.append(f"liquidity:{liquidity_risk:.2f}")
        if volatility_risk > 0.5: factors.append(f"volatility:{volatility_risk:.2f}")
        if information_risk > 0.5: factors.append(f"information_asymmetry:{information_risk:.2f}")

        return RiskAssessment(
            event_id=event_id,
            sport=payload.get("sport", ""),
            overall_risk=round(overall, 4),
            market_risk=round(market_risk, 4),
            timing_risk=round(timing_risk, 4),
            liquidity_risk=round(liquidity_risk, 4),
            volatility_risk=round(volatility_risk, 4),
            information_risk=round(information_risk, 4),
            risk_level=risk_level,
            factors=factors,
        )

    def _calc_market_risk(self, payload: dict) -> float:
        n_bookmakers = len(payload.get("bookmakers", payload.get("bookmakers_involved", [])))
        if n_bookmakers >= 5: return 0.1
        if n_bookmakers >= 3: return 0.3
        if n_bookmakers >= 2: return 0.6
        return 0.9

    def _calc_timing_risk(self, payload: dict) -> float:
        expires_at = payload.get("expires_at")
        if not expires_at:
            return 0.3
        try:
            remaining = expires_at - __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            seconds = remaining.total_seconds()
            if seconds <= 0: return 1.0
            if seconds < 300: return 0.9
            if seconds < 1800: return 0.7
            if seconds < 7200: return 0.5
            if seconds < 86400: return 0.3
            return 0.1
        except Exception:
            return 0.3

    def _calc_liquidity_risk(self, payload: dict) -> float:
        total_max_stake = 0
        for leg in payload.get("legs", payload.get("data", {}).get("legs", [])):
            if isinstance(leg, dict):
                total_max_stake += float(leg.get("max_stake", leg.get("stake", 0)))
        if total_max_stake <= 0: return 0.8
        if total_max_stake < 100: return 0.7
        if total_max_stake < 500: return 0.5
        if total_max_stake < 2000: return 0.3
        return 0.1

    def _calc_volatility_risk(self, event_id: str) -> float:
        snap = self._volatility_cache.get(event_id)
        if snap is None:
            return 0.3
        return snap.overall_volatility

    def _calc_information_risk(self, payload: dict) -> float:
        confidence = payload.get("confidence", 0.5)
        pattern = payload.get("pattern_type", "")
        if pattern in ("steam_move", "sharp_money"):
            return 0.2  # These signals are reliable
        if pattern in ("bookmaker_error",):
            return 0.9
        return max(0.1, 1.0 - float(confidence))

    @property
    def assessments(self) -> dict[str, RiskAssessment]:
        return dict(self._assessments)
