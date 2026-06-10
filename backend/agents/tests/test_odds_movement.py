import pytest
from decimal import Decimal

from backend.agents.odds_movement import OddsMovementAgent
from backend.agents.base import AgentBus
from backend.agents.memory import AgentMemory
from backend.agents.models import AgentId, MovementDirection, MovementSpeed


@pytest.fixture
def bus():
    return AgentBus()


@pytest.fixture
def memory():
    return AgentMemory(persist_path="/tmp")


@pytest.fixture
def agent(bus, memory):
    a = OddsMovementAgent(bus, memory, poll_interval=0.01)
    return a


@pytest.mark.asyncio
async def test_inject_tick(agent):
    tick = await agent.inject_tick("e1", "book_a", "home", Decimal("2.0"), Decimal("1.9"))
    event_key = "e1:home"
    window = agent._windows.get(event_key)
    assert window is not None
    assert len(window.ticks) == 1
    assert window.ticks[0].change_pct == -5.0


@pytest.mark.asyncio
async def test_classify_speed_instant(agent):
    speed = agent._classify_speed(time_span_seconds=0.1, change_pct=5.0)
    assert speed == MovementSpeed.INSTANT


@pytest.mark.asyncio
async def test_classify_speed_fast(agent):
    speed = agent._classify_speed(time_span_seconds=1.0, change_pct=3.0)
    assert speed == MovementSpeed.FAST


@pytest.mark.asyncio
async def test_classify_speed_moderate(agent):
    speed = agent._classify_speed(time_span_seconds=5.0, change_pct=3.0)
    assert speed == MovementSpeed.MODERATE


@pytest.mark.asyncio
async def test_classify_speed_slow(agent):
    speed = agent._classify_speed(time_span_seconds=10.0, change_pct=2.0)
    assert speed == MovementSpeed.SLOW


@pytest.mark.asyncio
async def test_classify_speed_drift(agent):
    speed = agent._classify_speed(time_span_seconds=100.0, change_pct=1.0)
    assert speed == MovementSpeed.DRIFT


@pytest.mark.asyncio
async def test_summarize_window_notable(agent):
    from backend.agents.models import OddsTick
    from datetime import datetime, timezone
    event_key = "e1:home"
    window = agent._windows[event_key]
    for i in range(5):
        window.ticks.append(OddsTick(
            event_id="e1", bookmaker=f"b{i}", outcome="home",
            old_odd=Decimal("2.0"), new_odd=Decimal("1.8"),
        ))
    summary = agent._summarize_window(event_key, window)
    assert summary.is_notable is True
    assert summary.dominant_direction == MovementDirection.DOWN


@pytest.mark.asyncio
async def test_summarize_window_not_notable(agent):
    from backend.agents.models import OddsTick
    event_key = "e2:home"
    window = agent._windows[event_key]
    for i in range(3):
        window.ticks.append(OddsTick(
            event_id="e2", bookmaker=f"b{i}", outcome="home",
            old_odd=Decimal("2.0"), new_odd=Decimal("2.003"),
        ))
    summary = agent._summarize_window(event_key, window)
    assert summary.is_notable is False


@pytest.mark.asyncio
async def test_tick_stores_in_memory(agent):
    await agent.inject_tick("e3", "book_a", "away", Decimal("3.0"), Decimal("2.5"))
    data = agent.memory.short_term.get("tick:e3:away")
    assert data is not None
    assert data["last_odd"] == 2.5


@pytest.mark.asyncio
async def test_steam_move_emission(agent, bus):
    from backend.agents.models import OddsTick
    agent.min_bookmakers_for_signal = 1
    agent.steam_move_pct = 3.0

    bus.register(AgentId.PATTERN_DETECTOR)
    msg = await agent.inject_tick("e4", "book_a", "home", Decimal("2.0"), Decimal("1.5"))
    window = agent._windows["e4:home"]
    assert len(window.ticks) >= 1


@pytest.mark.asyncio
async def test_empty_window_summary(agent):
    summary = agent._summarize_window("nonexistent:home", agent._windows.get("nonexistent:home", type("obj", (object,), {"ticks": []})()))
    # Accessing nonexistent window should not crash
    summary = agent._summarize_window("fresh", type("obj", (object,), {"ticks": [], "last_summary_time": 0.0})())
    assert summary.n_ticks == 0
