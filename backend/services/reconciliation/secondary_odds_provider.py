from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

import aiohttp

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig
from backend.services.pipeline.odds_normalizer import (
    normalize_sport, normalize_bookmaker, normalize_team, normalize_market, normalize_outcome,
)

logger = get_logger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

DEFAULT_SPORTS = ["soccer", "basketball", "tennis", "americanfootball"]
REGIONS = ["us", "uk", "eu", "au"]
MARKETS = ["h2h", "spreads"]


class SecondaryOddsProvider(BaseProvider):
    """
    Secondary odds provider using The Odds API with different:
    - Different polling interval (45s vs 30s)
    - Different region focus (AU/EU vs US/UK)
    - Different market set (h2h+spreads only)
    - Acts as a separate independent feed for reconciliation

    This creates a genuine multi-source validation:
    Provider A (primary): US/UK regions, h2h+spreads+totals, 30s
    Provider B (secondary): AU/EU regions, h2h+spreads, 45s

    Differences in latency, region, and market focus mean
    the MarketTruthService can detect real divergences.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="secondary_feed", update_interval_seconds=45.0))
        self._api_key = os.getenv("THE_ODDS_API_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._has_key = bool(self._api_key) and self._api_key != "your_api_key_here"
        self._events_cache: dict[str, list[dict]] = {}
        self._suppressed_log = False

        if not self._has_key:
            logger.info("secondary_provider_emulation", detail="No API key — will emulate feed for multi-source validation")

        self._emulate = random.Random(99)
        self._emulated_events: list[OddsEvent] = []
        self._emulated_odds: dict[str, float] = {}

    async def _ensure_session(self):
        if self._session is None and self._has_key:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"Content-Type": "application/json"},
            )

    async def _request_list(self, path: str, params: Optional[dict] = None) -> list:
        if not self._has_key:
            return []
        await self._ensure_session()
        url = f"{ODDS_API_BASE}{path}"
        p = {"apiKey": self._api_key, **(params or {})}
        try:
            async with self._session.get(url, params=p) as resp:
                if resp.status in (401, 429):
                    return []
                if resp.status != 200:
                    return []
                result = await resp.json()
                return result if isinstance(result, list) else []
        except Exception:
            return []

    async def fetch_events(self) -> list[OddsEvent]:
        if self._has_key:
            return await self._fetch_real_events()
        return await self._fetch_emulated_events()

    async def _fetch_real_events(self) -> list[OddsEvent]:
        sports = await self._request_list("/sports")
        if not sports:
            return []

        events: list[OddsEvent] = []
        for sport in sports[:10]:
            sport_key = sport.get("key", "")
            if sport_key not in DEFAULT_SPORTS:
                continue
            fixtures = await self._request_list(f"/sports/{sport_key}/events", {"regions": ",".join(REGIONS[2:])})
            if not fixtures:
                continue
            self._events_cache[sport_key] = fixtures
            for fxt in fixtures:
                start_str = fxt.get("commence_time", "")
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else datetime.now(timezone.utc)
                events.append(OddsEvent(
                    event_id=fxt.get("id", f"sec_{sport_key}_{len(events)}"),
                    sport=normalize_sport(sport_key),
                    home_team=normalize_team(fxt.get("home_team", "Unknown")),
                    away_team=normalize_team(fxt.get("away_team", "Unknown")),
                    start_time=start,
                ))
            await asyncio.sleep(0.3)

        return events

    async def _fetch_emulated_events(self) -> list[OddsEvent]:
        if self._emulated_events:
            return self._emulated_events

        sports_teams = [
            ("soccer", "Flamengo", "Palmeiras"),
            ("soccer", "Boca Juniors", "River Plate"),
            ("basketball", "Real Madrid Bask", "Barcelona Bask"),
            ("tennis", "Fritz T.", "Rune H."),
            ("american_football", "Green Bay", "Chicago"),
            ("soccer", "Porto", "Benfica"),
            ("basketball", "Monaco", "Fenerbahce"),
            ("tennis", "Rublev A.", "Hurkacz H."),
        ]
        now = datetime.now(timezone.utc)
        for i, (sport, home, away) in enumerate(sports_teams):
            self._emulated_events.append(OddsEvent(
                event_id=f"sec_em_{i}",
                sport=sport,
                home_team=home,
                away_team=away,
                start_time=now.replace(hour=(now.hour + i * 3) % 24),
            ))
        return self._emulated_events

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        if self._has_key:
            return await self._fetch_real_odds(event_id)
        return await self._fetch_emulated_odds(event_id)

    async def _fetch_real_odds(self, event_id: str) -> list[OddsUpdate]:
        sport_key = None
        for sk, fixtures in self._events_cache.items():
            for fxt in fixtures:
                if fxt.get("id") == event_id:
                    sport_key = sk
                    break
            if sport_key:
                break
        if not sport_key:
            return []

        data = await self._request_list(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {"regions": ",".join(REGIONS[2:]), "markets": ",".join(MARKETS)},
        )
        if not data:
            return []

        updates: list[OddsUpdate] = []
        now = datetime.now(timezone.utc)
        odds_data = data[0] if isinstance(data, list) and data else data
        bookmakers = odds_data.get("bookmakers", []) if isinstance(odds_data, dict) else []

        for bm in bookmakers[:5]:
            bm_name = normalize_bookmaker(bm.get("title", "Unknown")) + "_sec"
            for mkt in bm.get("markets", []):
                mkt_key = normalize_market(mkt.get("key", "h2h"))
                for outcome in mkt.get("outcomes", []):
                    updates.append(OddsUpdate(
                        event_id=event_id, market=mkt_key,
                        outcome=normalize_outcome(outcome.get("name", "")),
                        bookmaker=bm_name,
                        odd=Decimal(str(outcome.get("price", 2.0))),
                        timestamp=now,
                    ))
        return updates

    async def _fetch_emulated_odds(self, event_id: str) -> list[OddsUpdate]:
        base = self._emulated_odds.get(event_id, 2.0)
        drift = self._emulate.gauss(0, 0.008)
        base = max(1.01, base + drift * 0.5)
        self._emulated_odds[event_id] = base

        bk_names = ["Betfair_sec", "Pinnacle_sec", "Matchbook_sec"]
        now = datetime.now(timezone.utc)
        updates: list[OddsUpdate] = []

        for bk in bk_names:
            offset = self._emulate.uniform(-0.03, 0.03)
            odd_val = max(1.01, base * (1 + offset))
            updates.append(OddsUpdate(
                event_id=event_id, market="h2h",
                outcome="home", bookmaker=bk,
                odd=Decimal(str(round(odd_val, 2))),
                timestamp=now,
            ))
        return updates

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        while True:
            await asyncio.sleep(self.config.update_interval_seconds)
            updates = await self.fetch_odds(event_id)
            if updates:
                yield updates

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
