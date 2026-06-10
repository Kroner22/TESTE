from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Optional

from backend.app.log_config import get_logger
from .base import BaseAgent, AgentBus
from .models import (
    AgentId, AgentMessage, EventPriority, LearnedThreshold,
)
from .memory import AgentMemory

logger = get_logger(__name__)


class LearningAgent(BaseAgent):
    """
    Autonomous learning agent that improves the system over time.

    Responsibilities:
      - Track performance of all agent detections
      - Optimize detection thresholds (steam_move_pct, min_ev, etc.)
      - Identify false positives and adjust
      - Maintain agent-level statistics
      - Periodically persist learned knowledge
      - Detect concept drift in market behavior
    """

    def __init__(
        self,
        bus: AgentBus,
        memory: AgentMemory,
        poll_interval: float = 5.0,
        persist_interval: float = 60.0,
    ):
        super().__init__(AgentId.LEARNING, bus, poll_interval)
        self.memory = memory
        self.persist_interval = persist_interval
        self._last_persist = time.time()

        self._pattern_outcomes: dict[str, list[dict]] = defaultdict(list)
        self._agent_performance: dict[str, dict] = defaultdict(lambda: {
            "detections": 0, "actionable": 0, "true_positives": 0, "false_positives": 0,
        })
        self._market_regime_history: list[dict] = []

    async def process_message(self, message: AgentMessage) -> None:
        handler_map = {
            "pattern_occurred": self._handle_pattern,
            "alert_emitted": self._handle_alert,
            "risk_classified": self._handle_risk,
            "outcome_result": self._handle_outcome,
            "regime_update": self._handle_regime,
        }
        handler = handler_map.get(message.msg_type)
        if handler:
            await handler(message)

    async def tick(self) -> None:
        now = time.time()
        if now - self._last_persist >= self.persist_interval:
            self.memory.save()
            self._last_persist = now

        self._maybe_optimize_thresholds()

    async def _handle_pattern(self, payload: dict) -> None:
        pattern_type = payload.get("pattern_type", "")
        confidence = payload.get("confidence", 0.5)
        is_actionable = payload.get("is_actionable", False)

        perf = self._agent_performance["pattern_detector"]
        perf["detections"] += 1
        if is_actionable:
            perf["actionable"] += 1

        self.memory.learning.record_value(
            AgentId.PATTERN_DETECTOR,
            f"{pattern_type}_confidence",
            confidence,
        )

    async def _handle_alert(self, payload: dict) -> None:
        severity = payload.get("severity", "INFO")
        source = payload.get("source", "")

        self.memory.learning.track_stats(
            AgentId(source) if source else AgentId.ALERT_MANAGER,
            "alert_volume",
            {"severity": severity},
        )

    async def _handle_risk(self, payload: dict) -> None:
        risk_level = payload.get("risk_level", "LOW")
        overall = payload.get("overall_risk", 0)

        self.memory.learning.record_value(
            AgentId.RISK_CLASSIFIER,
            "overall_risk",
            float(overall),
        )

    async def _handle_outcome(self, payload: dict) -> None:
        """Record actual outcome for pattern verification."""
        event_id = payload.get("event_id", "")
        pattern_type = payload.get("pattern_type", "")
        was_correct = payload.get("was_correct", False)

        perf = self._agent_performance["pattern_detector"]
        if was_correct:
            perf["true_positives"] += 1
        else:
            perf["false_positives"] += 1

        self._pattern_outcomes[pattern_type].append({
            "event_id": event_id,
            "was_correct": was_correct,
            "timestamp": time.time(),
        })

    async def _handle_regime(self, payload: dict) -> None:
        self._market_regime_history.append({
            "regime": payload.get("regime", "unknown"),
            "volatility": payload.get("overall_volatility", 0),
            "timestamp": time.time(),
        })

    def _maybe_optimize_thresholds(self) -> None:
        """Periodically check if thresholds should be adjusted."""
        perf = self._agent_performance["pattern_detector"]
        total = perf["detections"]
        if total < 50:
            return

        fp_rate = perf["false_positives"] / max(total, 1)

        # If FP rate > 30%, thresholds need tightening
        if fp_rate > 0.30:
            self.memory.learning.record_value(
                AgentId.PATTERN_DETECTOR,
                "false_positive_rate",
                fp_rate,
            )

    def performance_summary(self) -> dict:
        return dict(self._agent_performance)

    def pattern_accuracy(self, pattern_type: Optional[str] = None) -> dict:
        if pattern_type:
            outcomes = self._pattern_outcomes.get(pattern_type, [])
        else:
            outcomes = [o for vals in self._pattern_outcomes.values() for o in vals]

        total = len(outcomes)
        correct = sum(1 for o in outcomes if o.get("was_correct", False))
        return {
            "total": total,
            "correct": correct,
            "accuracy": correct / max(total, 1),
        }
