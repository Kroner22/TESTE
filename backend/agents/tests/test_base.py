import asyncio
import pytest
from decimal import Decimal

from backend.agents.base import AgentBus
from backend.agents.models import AgentId, AgentMessage, EventPriority


class TestAgentBus:
    def setup_method(self):
        self.bus = AgentBus()
        self.bus.register(AgentId.ODDS_MOVEMENT)
        self.bus.register(AgentId.PATTERN_DETECTOR)

    @pytest.mark.asyncio
    async def test_publish_and_consume(self):
        msg = AgentMessage(
            source=AgentId.ORCHESTRATOR,
            target=AgentId.ODDS_MOVEMENT,
            msg_type="test",
        )
        sent = await self.bus.publish(msg)
        assert sent is True

        gen = self.bus.consume(AgentId.ODDS_MOVEMENT)
        received = await anext(gen)
        assert received is not None
        assert received.msg_type == "test"
        assert received.source == AgentId.ORCHESTRATOR
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_subscription(self):
        received = []

        async def callback(msg):
            received.append(msg)

        self.bus.subscribe("broadcast_event", callback)

        msg = AgentMessage(
            source=AgentId.ORCHESTRATOR,
            target=AgentId.ODDS_MOVEMENT,
            msg_type="broadcast_event",
        )
        await self.bus.publish(msg)

        # Give event loop a chance to invoke callback
        await asyncio.sleep(0.01)
        assert len(received) == 1
        assert received[0].msg_type == "broadcast_event"

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self):
        received = []
        async def cb(msg):
            received.append(msg)

        self.bus.subscribe("*", cb)

        for i in range(3):
            await self.bus.publish(AgentMessage(
                source=AgentId.ORCHESTRATOR,
                target=AgentId.ODDS_MOVEMENT,
                msg_type=f"type_{i}",
            ))

        await asyncio.sleep(0.01)
        assert len(received) == 3

    def test_queue_depth(self):
        assert self.bus.queue_depth(AgentId.ODDS_MOVEMENT) == 0
        assert self.bus.total_queue_depth() == 0

    def test_message_count(self):
        assert self.bus.message_count >= 0
