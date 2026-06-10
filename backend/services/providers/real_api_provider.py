from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

import aiohttp

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig
from backend.services.pipeline.odds_normalizer import (
    denormalize_sport_from_api, normalize_bookmaker, normalize_outcome,
    normalize_team, normalize_market,
)

logger = get_logger(__name__)

THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
DEFAULT_SPORTS = [
    "soccer", "basketball", "tennis", "americanfootball",
    "baseball", "icehockey", "mma",
]
REGIONS = ["us", "uk", "eu", "au"]
MARKETS = ["h2h", "spreads", "totals"]


class TheOddsApiProvider(BaseProvider):
    """
    Real provider using The Odds API (the-odds-api.com).
    Requires THE_ODDS_API_KEY env var.
    Falls back gracefully if key is missing.
    """

    def __init__(self, api_key: Optional[str] = None, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="the_odds_api", update_interval_seconds=30.0))
        self._api_key = api_key or os.getenv("THE_ODDS_API_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._has_key = bool(self._api_key) and self._api_key != "your_api_key_here"
        self._sports_cache: list[dict] = []
        self._events_cache: dict[str, list[dict]] = {}
        self._suppressed_log = False

        if not self._has_key:
            logger.warning("the_odds_api_key_missing", detail="Set THE_ODDS_API_KEY env var for real data")

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Content-Type": "application/json"},
            )

    async def _request(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        if not self._has_key:
            return None
        await self._ensure_session()
        url = f"{THE_ODDS_API_BASE}{path}"
        p = {"apiKey": self._api_key, **(params or {})}
        try:
            async with self._session.get(url, params=p) as resp:
                if resp.status == 401:
                    if not self._suppressed_log:
                        logger.error("the_odds_api_auth_failed")
                        self._suppressed_log = True
                    return None
                if resp.status == 429:
                    logger.warning("the_odds_api_rate_limited")
                    return None
                if resp.status != 200:
                    logger.warning("the_odds_api_error", status=resp.status)
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("the_odds_api_request_failed", error=str(e))
            return None

    async def _request_list(self, path: str, params: Optional[dict] = None) -> list:
        result = await self._request(path, params)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
        return []

    async def fetch_events(self, force_refresh: bool = False) -> list[OddsEvent]:
        if not self._has_key:
            return []

        if self._events_cache and not force_refresh:
            events: list[OddsEvent] = []
            for sport_key, fixtures in self._events_cache.items():
                for fxt in fixtures:
                    home_raw = fxt.get("home_team") or "Unknown"
                    away_raw = fxt.get("away_team") or "Unknown"
                    home = normalize_team(home_raw)
                    away = normalize_team(away_raw)
                    start_str = fxt.get("commence_time", "")
                    start = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else datetime.now(timezone.utc)
                    evt = OddsEvent(
                        event_id=fxt.get("id", f"odds_{sport_key}_{len(events)}"),
                        sport=denormalize_sport_from_api(sport_key),
                        home_team=home,
                        away_team=away,
                        start_time=start,
                        status=fxt.get("status", "scheduled"),
                    )
                    events.append(evt)
            return events

        sports = await self._request_list("/sports")
        if not sports:
            return []

        events: list[OddsEvent] = []
        self._sports_cache = sports[:20]

        for sport in sports:
            sport_key = sport.get("key", "")
            sport_title = sport.get("title", "")

            fixtures = await self._request_list(f"/sports/{sport_key}/events", {
                "regions": ",".join(REGIONS[:2]),
            })
            if not fixtures:
                continue

            self._events_cache[sport_key] = fixtures
            for fxt in fixtures:
                home_raw = fxt.get("home_team") or "Unknown"
                away_raw = fxt.get("away_team") or "Unknown"
                home = normalize_team(home_raw)
                away = normalize_team(away_raw)
                start_str = fxt.get("commence_time", "")
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else datetime.now(timezone.utc)
                evt = OddsEvent(
                    event_id=fxt.get("id", f"odds_{sport_key}_{len(events)}"),
                    sport=denormalize_sport_from_api(sport_key),
                    home_team=home,
                    away_team=away,
                    start_time=start,
                    status=fxt.get("status", "scheduled"),
                )
                events.append(evt)

            await asyncio.sleep(0.3)

        logger.info("the_odds_api_events_fetched", count=len(events))
        return events

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        if not self._has_key:
            return []

        sport_key = None
        event_data = None
        for sk, fixtures in self._events_cache.items():
            for fxt in fixtures:
                if fxt.get("id") == event_id:
                    sport_key = sk
                    event_data = fxt
                    break
            if sport_key:
                break

        if not sport_key or not event_data:
            return []

        odds_data = await self._request(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {"regions": ",".join(REGIONS), "markets": ",".join(MARKETS)},
        )
        if not odds_data:
            return []

        updates: list[OddsUpdate] = []
        now = datetime.now(timezone.utc)
        bookmakers = odds_data.get("bookmakers", [])

        for bm in bookmakers:
            bm_name = normalize_bookmaker(bm.get("title", "Unknown"))
            markets = bm.get("markets", [])
            for mkt in markets:
                mkt_key = normalize_market(mkt.get("key", "h2h"))
                outcomes = mkt.get("outcomes", [])
                for outcome in outcomes:
                    updates.append(OddsUpdate(
                        event_id=event_id,
                        market=mkt_key,
                        outcome=normalize_outcome(outcome.get("name", "")),
                        bookmaker=bm_name,
                        odd=Decimal(str(outcome.get("price", 2.0))),
                        timestamp=now,
                        is_opening=False,
                    ))

        return updates

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        if not self._has_key:
            return

        while True:
            await asyncio.sleep(self.config.update_interval_seconds)
            updates = await self.fetch_odds(event_id)
            if updates:
                yield updates

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
