from __future__ import annotations

import asyncio
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig
from backend.services.pipeline.odds_normalizer import normalize_bookmaker

logger = get_logger(__name__)

FALLBACK_SPORTS = ["soccer", "basketball", "tennis", "american_football"]

FALLBACK_TEAMS: dict[str, list[str]] = {
    "soccer": [
        "Manchester City", "Liverpool", "Arsenal", "Chelsea", "Tottenham",
        "Manchester United", "Newcastle", "Aston Villa", "Brighton", "West Ham",
    ],
    "basketball": [
        "Boston Celtics", "Milwaukee Bucks", "Denver Nuggets", "LA Lakers",
        "Golden State Warriors", "Miami Heat", "Phoenix Suns", "New York Knicks",
        "Philadelphia 76ers", "Dallas Mavericks",
    ],
    "tennis": [
        "Alcaraz C.", "Sinner J.", "Djokovic N.", "Medvedev D.",
        "Federer R.", "Nadal R.", "Rublev A.", "Hurkacz H.",
    ],
    "american_football": [
        "Kansas City Chiefs", "San Francisco 49ers", "Philadelphia Eagles",
        "Dallas Cowboys", "Buffalo Bills", "Cincinnati Bengals",
        "Baltimore Ravens", "Detroit Lions", "Miami Dolphins", "Houston Texans",
    ],
}

FALLBACK_BOOKMAKERS = ["Pinnacle", "Bet365", "DraftKings", "FanDuel", "Betway"]

FALLBACK_MARKETS = ["h2h", "spreads", "totals"]

ODDS_TEMPLATES: dict[str, list[tuple[float, ...]]] = {
    "soccer": [(2.0, 3.3, 3.8), (1.8, 3.5, 4.5), (2.5, 3.2, 2.8), (1.5, 4.0, 6.0)],
    "basketball": [(1.8, 2.1), (1.6, 2.4), (2.2, 1.7), (1.4, 3.0)],
    "tennis": [(1.7, 2.2), (2.0, 1.9), (1.5, 2.8), (1.3, 3.5)],
    "american_football": [(1.5, 2.8), (1.9, 2.0), (2.2, 1.7), (1.3, 3.5)],
}


class FallbackProvider(BaseProvider):
    """
    Enhanced fallback with more realistic data patterns:
    - Odds drift towards start time
    - Volume clustering
    - Bookmaker-specific spreads
    - Time-based volatility
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="fallback", update_interval_seconds=5.0))
        self._events: dict[str, OddsEvent] = {}
        self._seeds: dict[str, float] = {}
        self._initialized = False
        self._rng = random.Random(42)
        self._bookmaker_biases: dict[str, float] = {
            "Pinnacle": 0.0,
            "Bet365": 0.02,
            "DraftKings": 0.03,
            "FanDuel": 0.025,
            "Betway": 0.015,
        }

    def _init(self):
        if self._initialized:
            return
        self._initialized = True
        now = datetime.now(timezone.utc)
        eid = 0
        for sport in FALLBACK_SPORTS:
            teams = FALLBACK_TEAMS[sport]
            for i in range(0, len(teams) - 1, 2):
                if i + 1 >= len(teams):
                    break
                eid += 1
                event_id = f"fallback_{sport}_{eid}"
                start = now + timedelta(hours=random.uniform(1, 72))
                self._events[event_id] = OddsEvent(
                    event_id=event_id,
                    sport=sport,
                    home_team=teams[i],
                    away_team=teams[i + 1],
                    start_time=start,
                )
                self._seeds[event_id] = random.random()

    async def fetch_events(self) -> list[OddsEvent]:
        self._init()
        return list(self._events.values())

    def _compute_odds(self, event_id: str) -> dict[str, dict[str, Decimal]]:
        event = self._events[event_id]
        seed = self._seeds[event_id]
        sport = event.sport
        templates = ODDS_TEMPLATES.get(sport, ODDS_TEMPLATES["soccer"])
        template = self._rng.choice(templates)
        outcomes = FALLBACK_MARKETS[0]

        now = datetime.now(timezone.utc)
        hours_to_start = (event.start_time - now).total_seconds() / 3600
        time_factor = max(0.1, min(2.0, 24.0 / max(1.0, hours_to_start)))

        result: dict[str, dict[str, Decimal]] = {}
        result["h2h"] = {}

        for i, bk in enumerate(FALLBACK_BOOKMAKERS):
            bias = self._bookmaker_biases.get(bk, 0.0)
            for j, raw_odd in enumerate(template):
                noise = self._rng.gauss(0, 0.015 * time_factor)
                drift = bias + noise * seed
                val = raw_odd * (1 + drift)
                val = max(1.01, val)
                outcome_key = ["home", "draw", "away"][j] if len(template) == 3 else ["home", "away"][j]
                result[f"h2h_{bk}_{outcome_key}"] = Decimal(str(round(val, 2)))

        # Occasionally introduce a value slip: one bookmaker significantly misprices one outcome
        # This simulates real market inefficiencies (promotions, late odds, bookmaker errors)
        if self._rng.random() < 0.25:
            slip_bk = self._rng.choice(FALLBACK_BOOKMAKERS)
            slip_outcome = self._rng.choice(["home", "draw", "away"]) if len(template) == 3 else self._rng.choice(["home", "away"])
            slip_key = f"h2h_{slip_bk}_{slip_outcome}"
            current = float(result.get(slip_key, Decimal("2.0")))
            slip_factor = 1.0 + self._rng.uniform(0.08, 0.30)
            result[slip_key] = Decimal(str(round(current * slip_factor, 2)))

        return result

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        self._init()
        if event_id not in self._events:
            return []
        now = datetime.now(timezone.utc)
        updates: list[OddsUpdate] = []
        odds = self._compute_odds(event_id)
        for bk in FALLBACK_BOOKMAKERS:
            for j, outcome in enumerate((["home", "draw", "away"] if len(ODDS_TEMPLATES[self._events[event_id].sport][0]) == 3 else ["home", "away"])):
                key = f"h2h_{bk}_{outcome}"
                updates.append(OddsUpdate(
                    event_id=event_id,
                    market="h2h",
                    outcome=outcome,
                    bookmaker=bk,
                    odd=odds.get(key, Decimal("2.0")),
                    timestamp=now,
                    is_opening=True,
                ))
        return updates

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        self._init()
        if event_id not in self._events:
            return
        event = self._events[event_id]
        now = datetime.now(timezone.utc)

        # Seed initial odds from _compute_odds to include value slip
        initial = self._compute_odds(event_id)
        last_odds: dict[str, Decimal] = {}
        for bk in FALLBACK_BOOKMAKERS:
            for outcome in (["home", "draw", "away"] if len(ODDS_TEMPLATES[event.sport][0]) == 3 else ["home", "away"]):
                key = f"h2h_{bk}_{outcome}"
                last_odds[f"{bk}:{outcome}"] = initial.get(key, Decimal("2.0"))

        # Store fair reference odds for mean reversion (no cumulative bias)
        fair_odds: dict[str, float] = {}
        for bk in FALLBACK_BOOKMAKERS:
            for outcome in (["home", "draw", "away"] if len(ODDS_TEMPLATES[event.sport][0]) == 3 else ["home", "away"]):
                ikey = f"h2h_{bk}_{outcome}"
                lkey = f"{bk}:{outcome}"
                fair_odds[lkey] = float(initial.get(ikey, Decimal("2.0")))
        
        ticks = 0
        while ticks < 500:
            await asyncio.sleep(self.config.update_interval_seconds)
            updates: list[OddsUpdate] = []
            now = datetime.now(timezone.utc)
            hours_to_start = (event.start_time - now).total_seconds() / 3600
            time_factor = max(1.0, 24.0 / max(1.0, hours_to_start))

            # Occasionally inject a value slip during streaming
            slip_bk = None
            slip_outcome = None
            slip_factor = 1.0
            if self._rng.random() < 0.08:
                slip_bk = self._rng.choice(FALLBACK_BOOKMAKERS)
                slip_outcome = self._rng.choice(
                    ["home", "draw", "away"] if len(ODDS_TEMPLATES[event.sport][0]) == 3 else ["home", "away"]
                )
                slip_factor = 1.0 + self._rng.uniform(0.08, 0.30)

            for bk in FALLBACK_BOOKMAKERS:
                for outcome in (["home", "draw", "away"] if len(ODDS_TEMPLATES[event.sport][0]) == 3 else ["home", "away"]):
                    key = f"{bk}:{outcome}"
                    current = float(last_odds[key])
                    fair = fair_odds.get(key, current)
                    # Mean-reverting drift: pull toward fair value, add noise
                    mean_revert = (fair - current) * 0.05
                    noise = self._rng.gauss(0, 0.002 * time_factor)
                    current += mean_revert + noise
                    current = max(1.01, current)
                    if bk == slip_bk and outcome == slip_outcome:
                        current *= slip_factor
                    new_odd = Decimal(str(round(current, 2)))
                    last_odds[key] = new_odd
                    updates.append(OddsUpdate(
                        event_id=event_id,
                        market="h2h",
                        outcome=outcome,
                        bookmaker=bk,
                        odd=new_odd,
                        timestamp=now,
                        is_closing=(ticks >= 499),
                    ))
            ticks += 1
            yield updates

    def get_stats(self) -> dict:
        return {
            "events_loaded": len(self._events),
            "sports": list(set(e.sport for e in self._events.values())),
            "bookmakers": FALLBACK_BOOKMAKERS,
        }
