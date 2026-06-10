from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock
from typing import Optional


@dataclass
class StoredEvent:
    canonical_id: str
    sport: str
    home_team: str
    away_team: str
    start_time: datetime
    league: str = ""
    status: str = "scheduled"
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provider_ids: dict[str, str] = field(default_factory=dict)
    n_providers: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start_time"] = d["start_time"].isoformat() if isinstance(d["start_time"], datetime) else d["start_time"]
        d["first_seen"] = d["first_seen"].isoformat() if isinstance(d["first_seen"], datetime) else d["first_seen"]
        d["last_seen"] = d["last_seen"].isoformat() if isinstance(d["last_seen"], datetime) else d["last_seen"]
        return d


class EventStore:
    def __init__(self, persist_path: Optional[str] = None):
        self._events: dict[str, StoredEvent] = {}
        self._lock = Lock()
        self._persist_path = persist_path
        self._load()

    def upsert(self, event: StoredEvent) -> StoredEvent:
        with self._lock:
            existing = self._events.get(event.canonical_id)
            if existing:
                existing.last_seen = datetime.now(timezone.utc)
                existing.status = event.status or existing.status
                existing.provider_ids.update(event.provider_ids)
                existing.n_providers = len(existing.provider_ids)
                self._save()
                return existing
            self._events[event.canonical_id] = event
            self._save()
            return event

    def get(self, canonical_id: str) -> Optional[StoredEvent]:
        with self._lock:
            return self._events.get(canonical_id)

    def get_all(self, sport: Optional[str] = None, status: Optional[str] = None) -> list[StoredEvent]:
        with self._lock:
            result = list(self._events.values())
        if sport:
            result = [e for e in result if e.sport == sport]
        if status:
            result = [e for e in result if e.status == status]
        return sorted(result, key=lambda e: e.start_time)

    def count(self) -> int:
        with self._lock:
            return len(self._events)

    def stats(self) -> dict:
        with self._lock:
            n = len(self._events)
            by_sport: dict[str, int] = defaultdict(int)
            for e in self._events.values():
                by_sport[e.sport] += 1
            n_provider_ids = sum(len(e.provider_ids) for e in self._events.values())
        return {
            "total_events": n,
            "events_by_sport": dict(by_sport),
            "total_provider_ids": n_provider_ids,
            "avg_providers_per_event": round(n_provider_ids / max(1, n), 2),
        }

    def _load(self):
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path) as f:
                data = json.load(f)
            for item in data:
                item["start_time"] = datetime.fromisoformat(item["start_time"])
                item["first_seen"] = datetime.fromisoformat(item["first_seen"])
                item["last_seen"] = datetime.fromisoformat(item["last_seen"])
                self._events[item["canonical_id"]] = StoredEvent(**item)
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    def _save(self):
        if not self._persist_path:
            return
        os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
        with open(self._persist_path, "w") as f:
            json.dump([e.to_dict() for e in self._events.values()], f, indent=2)
