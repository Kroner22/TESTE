from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from backend.app.log_config import get_logger
from backend.services.providers.base import OddsUpdate

logger = get_logger(__name__)


class MarketSnapshot:
    snapshot_id: str
    timestamp: float
    events: dict[str, dict]
    provider_count: int
    total_odds_points: int
    total_opportunities: int

    def __init__(self, snapshot_id: str, timestamp: float, events: dict[str, dict], provider_count: int, total_odds_points: int, total_opportunities: int):
        self.snapshot_id = snapshot_id
        self.timestamp = timestamp
        self.events = events
        self.provider_count = provider_count
        self.total_odds_points = total_odds_points
        self.total_opportunities = total_opportunities


class SnapshotDiff:
    event_id: str
    field: str
    old_value: float
    new_value: float
    delta_pct: float

    def __init__(self, event_id: str, field: str, old_value: float, new_value: float, delta_pct: float):
        self.event_id = event_id
        self.field = field
        self.old_value = old_value
        self.new_value = new_value
        self.delta_pct = delta_pct


class MarketSnapshotEngine:
    """
    Periodic full-market snapshot with history and diff detection.

    Flow:
    1. Collect all current odds + opportunities at interval T
    2. Store as MarketSnapshot with full state
    3. Compare with previous snapshot -> SnapshotDiff[]
    4. Detect significant changes (new opportunities, odds > X%, closed events)
    5. Broadcast snapshot + diffs
    """

    def __init__(self, interval_seconds: float = 10.0):
        self._interval = interval_seconds
        self._snapshots: list[MarketSnapshot] = []
        self._max_snapshots = 500
        self._current_odds: dict[str, dict] = {}
        self._last_snapshot: Optional[MarketSnapshot] = None
        self._broadcast_callback: Optional[Callable[[dict], Awaitable[None]]] = None
        self._snapshot_counter = 0

    def set_broadcast_callback(self, callback: Callable[[dict], Awaitable[None]]):
        self._broadcast_callback = callback

    def record_odds(self, updates: list[OddsUpdate]):
        for u in updates:
            key = f"{u.event_id}:{u.market}:{u.outcome}:{u.bookmaker}"
            self._current_odds[key] = {
                "event_id": u.event_id,
                "market": u.market,
                "outcome": u.outcome,
                "bookmaker": u.bookmaker,
                "odd": float(u.odd),
                "timestamp": u.timestamp.isoformat() if hasattr(u.timestamp, "isoformat") else str(u.timestamp),
                "is_opening": u.is_opening,
                "is_closing": u.is_closing,
            }

    def take_snapshot(self, opportunities: list[dict] | None = None) -> Optional[MarketSnapshot]:
        now = time.time()
        self._snapshot_counter += 1
        snapshot_id = f"snap_{self._snapshot_counter}_{int(now)}"

        odds_by_event: dict[str, dict] = defaultdict(dict)
        providers: set[str] = set()

        for key, data in self._current_odds.items():
            eid = data["event_id"]
            bk = data["bookmaker"]
            providers.add(bk)

            if "bookmakers" not in odds_by_event[eid]:
                odds_by_event[eid]["bookmakers"] = {}
            if bk not in odds_by_event[eid]["bookmakers"]:
                odds_by_event[eid]["bookmakers"][bk] = {}
            odds_by_event[eid]["bookmakers"][bk][data["outcome"]] = data["odd"]

        if opportunities:
            for opp in opportunities:
                eid = opp.get("event_id", "")
                if eid in odds_by_event:
                    odds_by_event[eid]["ev"] = opp.get("ev", 0)
                    odds_by_event[eid]["grade"] = opp.get("grade", "")
                    odds_by_event[eid]["confidence"] = opp.get("confidence", 0)

        snapshot = MarketSnapshot(
            snapshot_id=snapshot_id,
            timestamp=now,
            events=dict(odds_by_event),
            provider_count=len(providers),
            total_odds_points=len(self._current_odds),
            total_opportunities=len(opportunities or []),
        )

        diffs: list[SnapshotDiff] = []
        if self._last_snapshot:
            diffs = self._compute_diff(self._last_snapshot, snapshot)

        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots:]

        self._last_snapshot = snapshot

        if self._broadcast_callback:
            import asyncio
            asyncio.ensure_future(self._broadcast_callback({
                "type": "market_snapshot",
                "data": {
                    "snapshot_id": snapshot_id,
                    "timestamp": now,
                    "event_count": len(odds_by_event),
                    "provider_count": snapshot.provider_count,
                    "odds_point_count": snapshot.total_odds_points,
                    "opportunity_count": snapshot.total_opportunities,
                    "diff_count": len(diffs),
                    "diffs": [
                        {"event_id": d.event_id, "field": d.field,
                         "delta_pct": round(d.delta_pct, 2)}
                        for d in diffs[:20]
                    ] if diffs else [],
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        return snapshot

    def _compute_diff(self, prev: MarketSnapshot, curr: MarketSnapshot) -> list[SnapshotDiff]:
        diffs: list[SnapshotDiff] = []

        for event_id, curr_data in curr.events.items():
            prev_data = prev.events.get(event_id)
            if not prev_data:
                continue

            curr_bks = curr_data.get("bookmakers", {})
            prev_bks = prev_data.get("bookmakers", {})

            for bk, curr_outcomes in curr_bks.items():
                prev_outcomes = prev_bks.get(bk, {})
                for outcome, curr_odd in curr_outcomes.items():
                    prev_odd = prev_outcomes.get(outcome)
                    if prev_odd and abs(curr_odd - prev_odd) / prev_odd > 0.001:
                        delta_pct = (curr_odd - prev_odd) / prev_odd * 100
                        diffs.append(SnapshotDiff(
                            event_id=event_id,
                            field=f"{bk}:{outcome}",
                            old_value=prev_odd,
                            new_value=curr_odd,
                            delta_pct=round(delta_pct, 2),
                        ))

        diffs.sort(key=lambda d: abs(d.delta_pct), reverse=True)
        return diffs

    def get_snapshot(self, snapshot_id: str) -> Optional[MarketSnapshot]:
        for s in self._snapshots:
            if s.snapshot_id == snapshot_id:
                return s
        return None

    def get_latest_snapshot(self) -> Optional[MarketSnapshot]:
        return self._snapshots[-1] if self._snapshots else None

    def get_recent_snapshots(self, n: int = 10) -> list[MarketSnapshot]:
        return self._snapshots[-n:]

    def get_snapshot_count(self) -> int:
        return len(self._snapshots)

    def get_odds_count(self) -> int:
        return len(self._current_odds)

    def clear(self):
        self._snapshots.clear()
        self._current_odds.clear()
        self._last_snapshot = None
