from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from backend.services.storage.event_store import EventStore, StoredEvent
from backend.services.storage.odds_history import OddsHistoryStore, OddsSnapshot
from decimal import Decimal


class TestEventStore:
    @pytest.fixture
    def store(self):
        return EventStore()

    def test_upsert_new_event(self, store):
        e = StoredEvent(
            canonical_id="evt_1",
            sport="soccer",
            home_team="Barcelona",
            away_team="Real Madrid",
            league="La Liga",
            start_time=datetime.now(timezone.utc),
        )
        stored = store.upsert(e)
        assert stored.canonical_id == "evt_1"
        assert store.count() == 1

    def test_upsert_existing_updates_last_seen(self, store):
        now = datetime.now(timezone.utc)
        e = StoredEvent(
            canonical_id="evt_1",
            sport="soccer",
            home_team="Barcelona",
            away_team="Real Madrid",
            league="La Liga",
            start_time=now,
        )
        store.upsert(e)

        e2 = StoredEvent(
            canonical_id="evt_1",
            sport="soccer",
            home_team="Barcelona",
            away_team="Real Madrid",
            league="La Liga",
            start_time=now,
            status="started",
        )
        updated = store.upsert(e2)
        assert updated.status == "started"
        assert store.count() == 1

    def test_get_event(self, store):
        now = datetime.now(timezone.utc)
        e = StoredEvent(canonical_id="evt_1", sport="soccer", home_team="A", away_team="B", start_time=now)
        store.upsert(e)
        assert store.get("evt_1") is not None
        assert store.get("nonexistent") is None

    def test_get_all_with_filters(self, store):
        now = datetime.now(timezone.utc)
        for i, sport in enumerate(["soccer", "basketball", "soccer"]):
            store.upsert(StoredEvent(
                canonical_id=f"evt_{i}",
                sport=sport,
                home_team=f"Team{i}A",
                away_team=f"Team{i}B",
                league="",
                start_time=now + timedelta(hours=i),
            ))
        soccer_events = store.get_all(sport="soccer")
        assert len(soccer_events) == 2
        assert store.get_all(sport="tennis") == []

    def test_stats(self, store):
        now = datetime.now(timezone.utc)
        store.upsert(StoredEvent(canonical_id="e1", sport="soccer", home_team="A", away_team="B", start_time=now))
        store.upsert(StoredEvent(canonical_id="e2", sport="basketball", home_team="C", away_team="D", start_time=now))
        stats = store.stats()
        assert stats["total_events"] == 2
        assert stats["events_by_sport"]["soccer"] == 1
        assert stats["events_by_sport"]["basketball"] == 1

    def test_persistence(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = EventStore(persist_path=path)
            now = datetime.now(timezone.utc)
            store.upsert(StoredEvent(
                canonical_id="evt_persist",
                sport="tennis",
                home_team="Djokovic",
                away_team="Alcaraz",
                league="ATP",
                start_time=now,
            ))
            assert store.count() == 1
            del store

            store2 = EventStore(persist_path=path)
            assert store2.count() == 1
            loaded = store2.get("evt_persist")
            assert loaded is not None
            assert loaded.home_team == "Djokovic"
        finally:
            os.unlink(path)


class TestOddsHistoryStore:
    @pytest.fixture
    def hist(self):
        return OddsHistoryStore()

    def test_append_new_version(self, hist):
        snap = OddsSnapshot(
            event_id="evt_1",
            market="h2h",
            outcome="home",
            bookmaker="Pinnacle",
            odd=Decimal("2.10"),
            timestamp=datetime.now(timezone.utc),
        )
        version = hist.append(snap)
        assert version == 1

    def test_append_increments_version(self, hist):
        ts = datetime.now(timezone.utc)
        s1 = OddsSnapshot("evt_1", "h2h", "home", "Pinnacle", Decimal("2.10"), ts)
        s2 = OddsSnapshot("evt_1", "h2h", "home", "Pinnacle", Decimal("2.20"), ts)
        assert hist.append(s1) == 1
        assert hist.append(s2) == 2

    def test_append_duplicate_odd_returns_same_version(self, hist):
        ts = datetime.now(timezone.utc)
        s1 = OddsSnapshot("evt_1", "h2h", "home", "Pinnacle", Decimal("2.10"), ts)
        s2 = OddsSnapshot("evt_1", "h2h", "home", "Pinnacle", Decimal("2.10"), ts)
        assert hist.append(s1) == 1
        assert hist.append(s2) == 1

    def test_get_latest(self, hist):
        ts = datetime.now(timezone.utc)
        hist.append(OddsSnapshot("evt_1", "h2h", "home", "Pinnacle", Decimal("2.00"), ts))
        hist.append(OddsSnapshot("evt_1", "h2h", "home", "Pinnacle", Decimal("2.10"), ts))
        latest = hist.get_latest("evt_1", "h2h", "home", "Pinnacle")
        assert latest is not None
        assert latest.odd == Decimal("2.10")
        assert latest.version == 2

    def test_get_history(self, hist):
        ts = datetime.now(timezone.utc)
        for i in range(5):
            hist.append(OddsSnapshot("evt_1", "h2h", "home", "Pinnacle", Decimal(f"2.{i}0"), ts))
        history = hist.get_history("evt_1", "h2h", "home", "Pinnacle")
        assert len(history) == 5
        assert history[0].odd == Decimal("2.00")
        assert history[-1].odd == Decimal("2.40")

    def test_get_history_for_event(self, hist):
        ts = datetime.now(timezone.utc)
        hist.append(OddsSnapshot("evt_1", "h2h", "home", "P1", Decimal("2.00"), ts))
        hist.append(OddsSnapshot("evt_1", "spread", "home", "P1", Decimal("1.90"), ts))
        hist.append(OddsSnapshot("evt_2", "h2h", "away", "P2", Decimal("3.00"), ts))
        event1 = hist.get_history_for_event("evt_1")
        assert len(event1) == 2
        event2 = hist.get_history_for_event("evt_2")
        assert len(event2) == 1

    def test_stats(self, hist):
        ts = datetime.now(timezone.utc)
        hist.append(OddsSnapshot("e1", "h2h", "home", "P1", Decimal("2.0"), ts))
        hist.append(OddsSnapshot("e1", "h2h", "home", "P1", Decimal("2.1"), ts))
        hist.append(OddsSnapshot("e1", "h2h", "away", "P2", Decimal("3.0"), ts))
        stats = hist.stats()
        assert stats["total_snapshots"] == 3
        assert stats["events_tracked"] == 1
        assert stats["unique_odds_keys"] == 2
