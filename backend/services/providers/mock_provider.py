from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

from .base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig


SPORTS = {
    "soccer": {
        "outcomes": ["home", "draw", "away"],
        "base_odds": [(2.0, 3.3, 3.8), (1.8, 3.5, 4.5), (2.5, 3.2, 2.8)],
        "teams": [
            ("Manchester City", "Liverpool"),
            ("Real Madrid", "Barcelona"),
            ("Bayern Munich", "Borussia Dortmund"),
            ("Juventus", "AC Milan"),
            ("PSG", "Marseille"),
        ],
    },
    "basketball": {
        "outcomes": ["home", "away"],
        "base_odds": [(1.8, 2.1), (1.6, 2.4), (2.2, 1.7)],
        "teams": [
            ("LA Lakers", "Boston Celtics"),
            ("Golden State", "Miami Heat"),
            ("Chicago Bulls", "New York Knicks"),
            ("Brooklyn Nets", "Milwaukee Bucks"),
        ],
    },
    "tennis": {
        "outcomes": ["player1", "player2"],
        "base_odds": [(1.7, 2.2), (2.0, 1.9), (1.5, 2.8)],
        "teams": [
            ("Djokovic N.", "Alcaraz C."),
            ("Sinner J.", "Medvedev D."),
            ("Federer R.", "Nadal R."),
        ],
    },
    "american_football": {
        "outcomes": ["home", "away"],
        "base_odds": [(1.5, 2.8), (1.9, 2.0), (2.2, 1.7)],
        "teams": [
            ("Kansas City", "San Francisco"),
            ("Buffalo Bills", "Cincinnati Bengals"),
            ("Philadelphia", "Dallas Cowboys"),
        ],
    },
}

BOOKMAKERS = ["Pinnacle", "Bet365", "DraftKings", "FanDuel", "Betway"]


class MockProvider(BaseProvider):
    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="mock"))
        self._events: dict[str, OddsEvent] = {}
        self._odds: dict[str, dict[str, Decimal]] = {}
        self._rng = random.Random(42)
        self._base_time = datetime.now(timezone.utc)
        self._initialized = False

    def _init_events(self):
        if self._initialized:
            return
        self._initialized = True
        eid = 1
        now = datetime.now(timezone.utc)
        for sport, cfg in SPORTS.items():
            for home, away in cfg["teams"]:
                event_id = f"{sport}_{eid}"
                start = now + timedelta(hours=self._rng.uniform(1, 72))
                self._events[event_id] = OddsEvent(
                    event_id=event_id,
                    sport=sport,
                    home_team=home,
                    away_team=away,
                    start_time=start,
                )
                eid += 1

    async def fetch_events(self) -> list[OddsEvent]:
        self._init_events()
        return list(self._events.values())

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        self._init_events()
        if event_id not in self._events:
            return []
        event = self._events[event_id]
        sport = event.sport
        cfg = SPORTS[sport]
        outcomes = cfg["outcomes"]
        odds_template = self._rng.choice(cfg["base_odds"])
        updates = []
        now = datetime.now(timezone.utc)
        for bk in BOOKMAKERS:
            for i, outcome in enumerate(outcomes):
                base = odds_template[i] * self._rng.uniform(0.95, 1.05)
                noise = self._rng.gauss(0, 0.02)
                odd = Decimal(str(round(base * (1 + noise), 2)))
                odd = max(Decimal("1.01"), odd)
                updates.append(OddsUpdate(
                    event_id=event_id,
                    market="h2h",
                    outcome=outcome,
                    bookmaker=bk,
                    odd=odd,
                    timestamp=now,
                    is_opening=True,
                ))
        return updates

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        self._init_events()
        if event_id not in self._events:
            return
        event = self._events[event_id]
        sport = event.sport
        cfg = SPORTS[sport]
        outcomes = cfg["outcomes"]
        odds_template = self._rng.choice(cfg["base_odds"])

        last_odds: dict[str, Decimal] = {}
        for bk in BOOKMAKERS:
            for i, outcome in enumerate(outcomes):
                base = odds_template[i] * self._rng.uniform(0.95, 1.05)
                odd = Decimal(str(round(base, 2)))
                last_odds[f"{bk}:{outcome}"] = max(Decimal("1.01"), odd)

        ticks = 0
        while ticks < 200:
            await asyncio.sleep(self.config.update_interval_seconds)
            updates = []
            now = datetime.now(timezone.utc)
            hours_to_start = (event.start_time - now).total_seconds() / 3600

            for bk in BOOKMAKERS:
                for outcome in outcomes:
                    key = f"{bk}:{outcome}"
                    current = last_odds[key]
                    drift = self._rng.gauss(0, 0.003)
                    if hours_to_start < 6:
                        drift *= 2
                    new_val = float(current) * (1 + drift)
                    new_val = max(1.01, new_val)
                    new_odd = Decimal(str(round(new_val, 2)))
                    last_odds[key] = new_odd
                    updates.append(OddsUpdate(
                        event_id=event_id,
                        market="h2h",
                        outcome=outcome,
                        bookmaker=bk,
                        odd=new_odd,
                        timestamp=now,
                        is_closing=(ticks >= 199),
                    ))
            ticks += 1
            yield updates
