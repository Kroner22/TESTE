from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

from backend.app.log_config import get_logger

from .models import (
    AgentId, AgentState, AgentMessage, AgentHealth, EventPriority,
)

logger = get_logger(__name__)


Callback = Callable[[AgentMessage], Any]


class AgentBus:
    """Typed async message bus for inter-agent communication."""

    def __init__(self):
        self._queues: dict[AgentId, asyncio.Queue] = {}
        self._subscriptions: dict[str, list[Callback]] = {}
        self._total_messages = 0

    def register(self, agent_id: AgentId, max_queue: int = 1024) -> None:
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue(maxsize=max_queue)

    def subscribe(self, msg_type: str, callback: Callback) -> None:
        if msg_type not in self._subscriptions:
            self._subscriptions[msg_type] = []
        self._subscriptions[msg_type].append(callback)

    async def publish(self, message: AgentMessage) -> bool:
        self._total_messages += 1
        target = message.target
        sent_to_queue = False

        if target in self._queues:
            try:
                await asyncio.wait_for(
                    self._queues[target].put(message),
                    timeout=1.0,
                )
                sent_to_queue = True
            except asyncio.TimeoutError:
                logger.warning("bus_queue_full", target=target.value)

        for pattern, cbs in self._subscriptions.items():
            if message.msg_type.startswith(pattern) or pattern == "*":
                for cb in cbs:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(message)
                        else:
                            cb(message)
                    except Exception as e:
                        logger.error("bus_callback_error", error=str(e))

        return sent_to_queue or True

    async def consume(self, agent_id: AgentId) -> AsyncIterator[AgentMessage]:
        queue = self._queues.get(agent_id)
        if queue is None:
            return
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield msg
            except asyncio.TimeoutError:
                yield None  # heartbeat tick

    @property
    def message_count(self) -> int:
        return self._total_messages

    def queue_depth(self, agent_id: AgentId) -> int:
        q = self._queues.get(agent_id)
        return q.qsize() if q else 0

    def total_queue_depth(self) -> int:
        return sum(q.qsize() for q in self._queues.values())


class BaseAgent(ABC):
    """Abstract base agent with lifecycle, message bus, health tracking."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: AgentBus,
        poll_interval: float = 0.1,
    ):
        self.agent_id = agent_id
        self.bus = bus
        self.poll_interval = poll_interval
        self.state = AgentState.IDLE
        self._task: Optional[asyncio.Task] = None
        self._messages_processed = 0
        self._errors_this_hour = 0
        self._start_time = time.monotonic()
        self._last_activity = datetime.now(timezone.utc)

        bus.register(agent_id)

    @abstractmethod
    async def process_message(self, message: AgentMessage) -> None:
        """Handle an incoming message."""

    @abstractmethod
    async def tick(self) -> None:
        """Periodic maintenance — called every poll_interval when no message."""

    async def send(self, target: AgentId, msg_type: str, payload: dict = None, priority: EventPriority = EventPriority.MEDIUM) -> bool:
        msg = AgentMessage(
            source=self.agent_id,
            target=target,
            msg_type=msg_type,
            payload=payload or {},
            priority=priority,
        )
        return await self.bus.publish(msg)

    async def broadcast(self, msg_type: str, payload: dict = None, priority: EventPriority = EventPriority.MEDIUM) -> None:
        for agent in AgentId:
            if agent != self.agent_id and agent != AgentId.ORCHESTRATOR:
                await self.send(agent, msg_type, payload, priority)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self.state = AgentState.RUNNING
        self._start_time = time.monotonic()
        self._task = asyncio.create_task(self._run())
        logger.info("agent_started", agent=self.agent_id.value)

    async def stop(self) -> None:
        self.state = AgentState.STOPPED
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("agent_stopped", agent=self.agent_id.value)

    async def pause(self) -> None:
        self.state = AgentState.PAUSED

    async def resume(self) -> None:
        self.state = AgentState.RUNNING

    @property
    def uptime(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def health(self) -> AgentHealth:
        return AgentHealth(
            agent_id=self.agent_id,
            state=self.state,
            uptime_seconds=self.uptime,
            messages_processed=self._messages_processed,
            errors_last_hour=self._errors_this_hour,
            last_activity=self._last_activity,
            is_healthy=self.state == AgentState.RUNNING and self._errors_this_hour < 10,
        )

    async def _run(self) -> None:
        async for msg in self.bus.consume(self.agent_id):
            if self.state == AgentState.STOPPED:
                break
            if self.state == AgentState.PAUSED:
                await asyncio.sleep(self.poll_interval)
                continue

            if msg is None:
                try:
                    await self.tick()
                except Exception as e:
                    logger.error("agent_tick_error", agent=self.agent_id.value, error=str(e))
                    self._errors_this_hour += 1
                await asyncio.sleep(self.poll_interval)
                continue

            try:
                await self.process_message(msg)
                self._messages_processed += 1
                self._last_activity = datetime.now(timezone.utc)
            except Exception as e:
                logger.error("agent_process_error", agent=self.agent_id.value, msg_type=msg.msg_type, error=str(e))
                self._errors_this_hour += 1
                if self._errors_this_hour > 50:
                    self.state = AgentState.ERROR
