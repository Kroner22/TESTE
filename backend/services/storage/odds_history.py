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
class OddsSnapshot:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    odd: Decimal
    timestamp: datetime
    version: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["odd"] = str(d["odd"])
        d["timestamp"] = d["timestamp"].isoformat() if isinstance(d["timestamp"], datetime) else d["timestamp"]
        return d


class OddsHistoryStore:
    """
    Append-only versioned odds store with in-memory + optional JSON persistence.
    Tracks every odds update as a versioned snapshot for full audit trail.
    """

    def __init__(self, persist_path: Optional[str] = None, max_versions_per_key: int = 500):
        self._versions: dict[str, list[OddsSnapshot]] = defaultdict(list)
        self._latest: dict[str, OddsSnapshot] = {}
        self._lock = Lock()
        self._persist_path = persist_path
        self._max_versions = max_versions_per_key
        self._load()
        self._total_appends = 0

    def append(self, snapshot: OddsSnapshot) -> int:
        with self._lock:
            key = f"{snapshot.event_id}:{snapshot.market}:{snapshot.outcome}:{snapshot.bookmaker}"
            existing = self._latest.get(key)
            if existing and existing.odd == snapshot.odd:
                return existing.version

            prev_version = existing.version if existing else 0
            snapshot.version = prev_version + 1

            self._versions[key].append(snapshot)
            self._latest[key] = snapshot
            self._total_appends += 1

            if len(self._versions[key]) > self._max_versions:
                self._versions[key] = self._versions[key][-self._max_versions:]

            self._save()
            return snapshot.version

    def get_latest(self, event_id: str, market: str, outcome: str, bookmaker: str) -> Optional[OddsSnapshot]:
        key = f"{event_id}:{market}:{outcome}:{bookmaker}"
        with self._lock:
            return self._latest.get(key)

    def get_history(
        self,
        event_id: str,
        market: str,
        outcome: str,
        bookmaker: str,
        limit: int = 100,
    ) -> list[OddsSnapshot]:
        key = f"{event_id}:{market}:{outcome}:{bookmaker}"
        with self._lock:
            history = list(self._versions.get(key, []))
        return history[-limit:]

    def get_history_for_event(self, event_id: str, limit: int = 100) -> list[OddsSnapshot]:
        results: list[OddsSnapshot] = []
        with self._lock:
            for key, snapshots in self._versions.items():
                if key.startswith(f"{event_id}:"):
                    results.extend(snapshots[-limit:])
        return sorted(results, key=lambda s: s.timestamp)

    def get_odds_movement(
        self,
        event_id: str,
        market: str,
        outcome: str,
        bookmaker: str,
    ) -> list[tuple[datetime, Decimal]]:
        history = self.get_history(event_id, market, outcome, bookmaker)
        return [(s.timestamp, s.odd) for s in history]

    def stats(self) -> dict:
        with self._lock:
            unique_keys = len(self._versions)
            total_snapshots = sum(len(v) for v in self._versions.values())
            event_keys = len(set(k.split(":")[0] for k in self._versions))
        return {
            "unique_odds_keys": unique_keys,
            "total_snapshots": total_snapshots,
            "events_tracked": event_keys,
            "total_appends": self._total_appends,
            "avg_versions_per_key": round(total_snapshots / max(1, unique_keys), 1),
        }

    def _load(self):
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path) as f:
                data = json.load(f)
            for item in data:
                item["odd"] = Decimal(str(item["odd"]))
                item["timestamp"] = datetime.fromisoformat(item["timestamp"])
                snap = OddsSnapshot(**item)
                key = f"{snap.event_id}:{snap.market}:{snap.outcome}:{snap.bookmaker}"
                self._versions[key].append(snap)
                existing = self._latest.get(key)
                if not existing or snap.version > existing.version:
                    self._latest[key] = snap
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    def _save(self):
        if not self._persist_path:
            return
        os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
        all_snapshots: list[dict] = []
        with self._lock:
            for snapshots in self._versions.values():
                all_snapshots.extend(s.to_dict() for s in snapshots[-100:])
        with open(self._persist_path, "w") as f:
            json.dump(all_snapshots, f, indent=2)
