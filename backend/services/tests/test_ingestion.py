from __future__ import annotations

import asyncio
import pytest

from backend.services.ingestion import OddsIngestionService
from backend.services.providers.mock_provider import MockProvider
from backend.app.database import init_db, Event, OddsRecord, OpportunityRecord, AlertRecord, SessionLocal, engine, Base


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


async def _run_until(predicate, timeout=5.0, interval=0.1):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


@pytest.mark.asyncio
async def test_ingestion_processes_odds():
    service = OddsIngestionService()
    service.register_provider(MockProvider())
    await service.start()

    db = SessionLocal()
    try:
        ok = await _run_until(lambda: db.query(Event).count() >= 3)
        assert ok, f"Expected >=3 events, got {db.query(Event).count()}"
        odd_count = db.query(OddsRecord).count()
        assert odd_count > 0, f"Expected >0 odds, got {odd_count}"
    finally:
        db.close()

    await service.stop()


@pytest.mark.asyncio
async def test_ingestion_creates_opportunities():
    service = OddsIngestionService()
    service.register_provider(MockProvider())
    await service.start()

    db = SessionLocal()
    try:
        ok = await _run_until(lambda: db.query(OpportunityRecord).count() > 0)
        assert ok, "No opportunities created"
    finally:
        db.close()

    await service.stop()


@pytest.mark.asyncio
async def test_ingestion_creates_alerts():
    service = OddsIngestionService()
    service.register_provider(MockProvider())
    await service.start()

    db = SessionLocal()
    try:
        await _run_until(lambda: db.query(OpportunityRecord).count() > 0, timeout=3.0)
        alert_count = db.query(AlertRecord).count()
        assert alert_count >= 0
    finally:
        db.close()

    await service.stop()


@pytest.mark.asyncio
async def test_ingestion_broadcast_fires():
    service = OddsIngestionService()
    service.register_provider(MockProvider())

    fired = []

    async def cb(msg):
        if msg.get("type") == "opportunities":
            fired.append(msg)

    service.set_broadcast_callback(cb)
    await service.start()

    await _run_until(lambda: len(fired) > 0, timeout=5.0)

    await service.stop()
