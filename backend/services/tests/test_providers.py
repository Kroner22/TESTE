from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from backend.services.providers.base import ProviderConfig, OddsEvent, OddsUpdate
from backend.services.providers.mock_provider import MockProvider, SPORTS, BOOKMAKERS


@pytest.fixture
def mock_provider():
    return MockProvider(ProviderConfig(name="test", update_interval_seconds=0.1))


@pytest.mark.asyncio
async def test_fetch_events_returns_multiple_sports(mock_provider):
    events = await mock_provider.fetch_events()
    assert len(events) >= 3
    sports = {e.sport for e in events}
    for s in SPORTS:
        assert s in sports


@pytest.mark.asyncio
async def test_fetch_odds_all_bookmakers(mock_provider):
    events = await mock_provider.fetch_events()
    assert events
    odds = await mock_provider.fetch_odds(events[0].event_id)
    bookmakers = {o.bookmaker for o in odds}
    for bk in BOOKMAKERS:
        assert bk in bookmakers


@pytest.mark.asyncio
async def test_fetch_odds_positive_odds(mock_provider):
    events = await mock_provider.fetch_events()
    odds = await mock_provider.fetch_odds(events[0].event_id)
    assert odds
    for o in odds:
        assert o.odd >= Decimal("1.01")


@pytest.mark.asyncio
async def test_stream_odds_produces_ticks(mock_provider):
    events = await mock_provider.fetch_events()
    updates = []
    async for batch in mock_provider.stream_odds(events[0].event_id):
        updates.extend(batch)
        if len(updates) >= 20:
            break
    assert len(updates) >= 10
    timestamps = {u.timestamp for u in updates}
    assert len(timestamps) > 1


@pytest.mark.asyncio
async def test_stream_odds_closing_flag(mock_provider):
    events = await mock_provider.fetch_events()
    all_updates = []
    async for batch in mock_provider.stream_odds(events[0].event_id):
        all_updates.extend(batch)
        if any(u.is_closing for u in batch):
            break
    assert any(u.is_closing for u in all_updates)


@pytest.mark.asyncio
async def test_odds_idempotent_fetch(mock_provider):
    events = await mock_provider.fetch_events()
    odds1 = await mock_provider.fetch_odds(events[0].event_id)
    # re-init
    provider2 = MockProvider(ProviderConfig(name="test"))
    await provider2.fetch_events()
    odds2 = await provider2.fetch_odds(events[0].event_id)
    assert len(odds1) == len(odds2)
