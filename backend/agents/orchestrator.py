from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.app.log_config import get_logger
from .base import AgentBus, BaseAgent
from .models import (
    AgentId, AgentState, AgentHealth, AgentMessage,
    EventPriority, OrchestratorSnapshot,
)
from .memory import AgentMemory
from .priority import PriorityEngine, EventScheduler
from .odds_movement import OddsMovementAgent
from .pattern_detector import PatternDetectionAgent
from .opportunity_scout import OpportunityScoutAgent
from .volatility import VolatilityAnalystAgent
from .risk_classifier import RiskClassifierAgent
from .alert_manager import AlertManagerAgent
from .learning import LearningAgent

logger = get_logger(__name__)


class AgentOrchestrator(BaseAgent):
    """
    Central orchestrator that manages the complete agent lifecycle.

    Responsibilities:
      - Initialize all agents with shared bus and memory
      - Start/stop agents in dependency order
      - Route inter-agent messages
      - Monitor agent health with heartbeat
      - Schedule periodic maintenance
      - Provide unified API for external consumers
      - Handle graceful shutdown
    """

    def __init__(self, bus: AgentBus, memory: AgentMemory, persist_path: str = "data"):
        super().__init__(AgentId.ORCHESTRATOR, bus, poll_interval=0.5)
        self.memory = memory
        self.persist_path = persist_path
        self.priority_engine = PriorityEngine()
        self.scheduler = EventScheduler()

        self._agents: dict[AgentId, BaseAgent] = {}
        self._start_time = time.monotonic()

    async def build(self) -> "AgentOrchestrator":
        """Factory: build all agents with shared dependencies."""
        self._agents = {
            AgentId.ODDS_MOVEMENT: OddsMovementAgent(self.bus, self.memory),
            AgentId.PATTERN_DETECTOR: PatternDetectionAgent(self.bus, self.memory),
            AgentId.OPPORTUNITY_SCOUT: OpportunityScoutAgent(self.bus, self.memory),
            AgentId.VOLATILITY_ANALYST: VolatilityAnalystAgent(self.bus, self.memory),
            AgentId.RISK_CLASSIFIER: RiskClassifierAgent(self.bus, self.memory),
            AgentId.ALERT_MANAGER: AlertManagerAgent(self.bus, self.memory),
            AgentId.LEARNING: LearningAgent(self.bus, self.memory),
        }
        self._agents[self.agent_id] = self
        return self

    async def start_all(self) -> None:
        """Start agents in dependency order."""
        logger.info("orchestrator_starting_all")

        self.memory.load()

        start_order = [
            AgentId.LEARNING,          # Must learn first
            AgentId.VOLATILITY_ANALYST, # Baseline volatility
            AgentId.RISK_CLASSIFIER,    # Risk model ready
            AgentId.ALERT_MANAGER,      # Alerting ready
            AgentId.PATTERN_DETECTOR,   # Pattern engine
            AgentId.OPPORTUNITY_SCOUT,  # Opportunity finder
            AgentId.ODDS_MOVEMENT,      # Last: ingests ticks
        ]

        for agent_id in start_order:
            agent = self._agents.get(agent_id)
            if agent:
                await agent.start()
                await asyncio.sleep(0.01)

        await self.start()
        logger.info("orchestrator_all_started", n_agents=len(self._agents))

    async def stop_all(self) -> None:
        """Graceful shutdown in reverse order."""
        logger.info("orchestrator_stopping_all")

        stop_order = list(reversed([
            AgentId.ODDS_MOVEMENT,
            AgentId.OPPORTUNITY_SCOUT,
            AgentId.PATTERN_DETECTOR,
            AgentId.ALERT_MANAGER,
            AgentId.RISK_CLASSIFIER,
            AgentId.VOLATILITY_ANALYST,
            AgentId.LEARNING,
        ]))

        for agent_id in stop_order:
            agent = self._agents.get(agent_id)
            if agent:
                await agent.stop()

        await self.stop()
        self.memory.save()
        logger.info("orchestrator_all_stopped")

    async def process_message(self, message: AgentMessage) -> None:
        if message.msg_type == "restart_agent":
            await self._restart_agent(message.payload.get("agent_id", ""))
        elif message.msg_type == "pause_agent":
            await self._pause_agent(message.payload.get("agent_id", ""))
        elif message.msg_type == "resume_agent":
            await self._resume_agent(message.payload.get("agent_id", ""))
        elif message.msg_type == "get_snapshot":
            await self._respond_snapshot(message)

    async def tick(self) -> None:
        due = self.scheduler.get_due()
        for key, callback in due:
            if callback:
                try:
                    await callback()
                except Exception as e:
                    logger.error("scheduled_callback_error", key=key, error=str(e))

        unhealthy = [aid for aid, agent in self._agents.items()
                     if agent.health.state == AgentState.ERROR]
        for aid in unhealthy:
            logger.warning("agent_unhealthy", agent=aid.value)
            await self._restart_agent(aid.value)

    async def inject_tick(self, event_id: str, bookmaker: str, outcome: str, old_odd: float, new_odd: float) -> None:
        """External API: inject an odds tick into the agent system."""
        movement_agent = self._agents.get(AgentId.ODDS_MOVEMENT)
        if movement_agent and isinstance(movement_agent, OddsMovementAgent):
            from decimal import Decimal
            await movement_agent.inject_tick(event_id, bookmaker, outcome, Decimal(str(old_odd)), Decimal(str(new_odd)))

    async def inject_volatility(self, event_id: str, odds_value: float) -> None:
        """External API: inject a price observation for volatility analysis."""
        vol_agent = self._agents.get(AgentId.VOLATILITY_ANALYST)
        if vol_agent and isinstance(vol_agent, VolatilityAnalystAgent):
            await vol_agent.inject_tick(event_id, odds_value)

    async def _restart_agent(self, agent_id_str: str) -> None:
        try:
            agent_id = AgentId(agent_id_str)
        except ValueError:
            return
        agent = self._agents.get(agent_id)
        if agent:
            await agent.stop()
            await asyncio.sleep(0.5)
            await agent.start()

    async def _pause_agent(self, agent_id_str: str) -> None:
        try:
            agent_id = AgentId(agent_id_str)
        except ValueError:
            return
        agent = self._agents.get(agent_id)
        if agent:
            await agent.pause()

    async def _resume_agent(self, agent_id_str: str) -> None:
        try:
            agent_id = AgentId(agent_id_str)
        except ValueError:
            return
        agent = self._agents.get(agent_id)
        if agent:
            await agent.resume()

    async def _respond_snapshot(self, message: AgentMessage) -> None:
        await self.send(
            message.source,
            "orchestrator_snapshot",
            payload=vars(self.snapshot()),
            priority=EventPriority.LOW,
        )

    def snapshot(self) -> OrchestratorSnapshot:
        agents_health = {
            aid.value: agent.health
            for aid, agent in self._agents.items()
        }
        return OrchestratorSnapshot(
            n_agents=len(self._agents),
            agents={k: v for k, v in agents_health.items()},
            queue_depth=self.bus.total_queue_depth(),
            messages_processed_total=self.bus.message_count,
            alerts_active=(
                self._agents.get(AgentId.ALERT_MANAGER)
                and self._agents[AgentId.ALERT_MANAGER].unacknowledged_count
            ) if hasattr(self._agents.get(AgentId.ALERT_MANAGER, None), "unacknowledged_count") else 0,
            patterns_active=len(
                self._agents.get(AgentId.PATTERN_DETECTOR, {}).active_patterns
            ) if hasattr(self._agents.get(AgentId.PATTERN_DETECTOR, None), "active_patterns") else 0,
            uptime_seconds=time.monotonic() - self._start_time,
        )

    def get_agent(self, agent_id: AgentId) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    def learning_summary(self) -> dict:
        agent = self._agents.get(AgentId.LEARNING)
        if agent and isinstance(agent, LearningAgent):
            return agent.performance_summary()
        return {}

    def pattern_accuracy(self, pattern_type: Optional[str] = None) -> dict:
        agent = self._agents.get(AgentId.LEARNING)
        if agent and isinstance(agent, LearningAgent):
            return agent.pattern_accuracy(pattern_type)
        return {}
