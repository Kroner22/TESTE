from __future__ import annotations

from decimal import Decimal
from typing import Optional

from backend.app.log_config import get_logger
from .base import BaseAgent, AgentBus
from .models import (
    AgentId, AgentMessage, EventPriority,
    DetectedPattern, PatternType,
)
from .memory import AgentMemory

logger = get_logger(__name__)


class OpportunityScoutAgent(BaseAgent):
    """
    Continuously scouts for the best market opportunities.

    Responsibilities:
      - Scan markets for value bets using the EV engine
      - Scan cross-bookmaker odds for arbitrage
      - Cross-reference patterns with current odds
      - Rank opportunities by combined score (EV × confidence × urgency)
      - Surface top opportunities to alert manager
    """

    def __init__(
        self,
        bus: AgentBus,
        memory: AgentMemory,
        poll_interval: float = 0.5,
    ):
        super().__init__(AgentId.OPPORTUNITY_SCOUT, bus, poll_interval)
        self.memory = memory
        self._opportunity_cache: dict[str, dict] = {}
        self._scout_count = 0

    async def process_message(self, message: AgentMessage) -> None:
        if message.msg_type == "detected_pattern":
            await self._evaluate_pattern(message.payload)
        elif message.msg_type == "market_odds_update":
            await self._scan_market(message.payload)
        elif message.msg_type == "request_top":
            await self._respond_top(message)

    async def tick(self) -> None:
        self._gc_stale_opportunities()

    async def _evaluate_pattern(self, payload: dict) -> None:
        event_id = payload.get("event_id", "")
        pattern_type = payload.get("pattern_type", "")
        confidence = payload.get("confidence", 0)

        existing = self._opportunity_cache.get(event_id)
        if existing and existing.get("confidence", 0) >= confidence:
            return

        score = confidence * 100
        if pattern_type in ("steam_move", "arbitrage"):
            score *= 1.3
        elif pattern_type in ("value_bet", "sharp_money"):
            score *= 1.1

        self._opportunity_cache[event_id] = {
            "event_id": event_id,
            "pattern_type": pattern_type,
            "confidence": confidence,
            "score": score,
            "timestamp": __import__("time").time(),
            "data": payload,
        }

        if score >= 50:
            await self.send(
                AgentId.ALERT_MANAGER,
                "high_value_opportunity",
                payload=self._opportunity_cache[event_id],
                priority=EventPriority.HIGH,
            )

        self._scout_count += 1

    async def _scan_market(self, payload: dict) -> None:
        """Scan a market update for both value and arb opportunities."""
        event_id = payload.get("event_id", "")
        odds_by_bookmaker = payload.get("odds_by_bookmaker", {})

        outcomes = list(odds_by_bookmaker.keys())
        if len(outcomes) < 2:
            return

        from backend.domains.arbitrage.core import scan_for_arbitrage
        from backend.domains.arbitrage.models import BookmakerOdds

        for outcome, bookmaker_odds_list in odds_by_bookmaker.items():
            odds_by_outcome = {
                outcome: [
                    BookmakerOdds(
                        bookmaker=b.get("bookmaker", ""),
                        outcome=outcome,
                        odd=Decimal(str(b.get("odd", 0))),
                        max_stake=Decimal(str(b["max_stake"])) if b.get("max_stake") else None,
                        commission=Decimal(str(b.get("commission", "0"))),
                    )
                    for b in bookmaker_odds_list
                ]
            }

    async def _respond_top(self, message: AgentMessage) -> None:
        sorted_ops = sorted(
            self._opportunity_cache.values(),
            key=lambda x: x.get("score", 0),
            reverse=True,
        )[:20]

        await self.send(
            message.source,
            "top_opportunities",
            payload={"opportunities": sorted_ops, "count": len(sorted_ops)},
        )

    def _gc_stale_opportunities(self) -> None:
        now = __import__("time").time()
        stale = [k for k, v in self._opportunity_cache.items()
                 if now - v.get("timestamp", 0) > 300]
        for k in stale:
            del self._opportunity_cache[k]

    @property
    def top_opportunities(self) -> list[dict]:
        return sorted(
            self._opportunity_cache.values(),
            key=lambda x: x.get("score", 0),
            reverse=True,
        )[:20]
