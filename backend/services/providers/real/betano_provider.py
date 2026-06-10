"""
Betano odds provider — soft bookmaker market feed.

Betano is a popular European sportsbook. This provider uses
The Odds API as its data source (Betano is a supported bookmaker
there) rather than direct integration, since Betano has no public API.

Note: Betano odds are considered "soft" (less efficient than Pinnacle)
and are used for market consensus comparison, not as truth source.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

import aiohttp

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig

logger = get_logger(__name__)

BETANO_ODDS_API_BASE = "https://api.the-odds-api.com/v4"


class BetanoProvider(BaseProvider):
    """
    Betano odds provider sourced via The Odds API.

    Betano is a supported bookmaker on The Odds API under
    the key 'betano'. This provider filters The Odds API
    response to extract only Betano-specific odds.

    Used for:
    - Cross-bookmaker market comparison
    - Soft bookmaker price reference
    - Consensus deviation analysis
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="betano", update_interval_seconds=60.0))
        self._api_key = os.getenv("THE_ODDS_API_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._has_key = bool(self._api_key) and self._api_key != "your_api_key_here"
        self._mode = "SIMULATION" if not self._has_key else "LIVE"
        self._mode_reason = "THE_ODDS_API_KEY nao configurada" if not self._has_key else "Betano via The Odds API"
        self._healthy = self._has_key

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def healthy(self) -> bool:
        return self._healthy

    def status(self) -> dict:
        return {
            "name": self.name,
            "mode": self._mode,
            "healthy": self._healthy,
            "source": "the_odds_api (betano filter)",
        }

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
            )

    async def _request(self, path: str, params: Optional[dict] = None) -> Optional[list]:
        if not self._has_key:
            return None
        await self._ensure_session()
        url = f"{BETANO_ODDS_API_BASE}{path}"
        p = {"apiKey": self._api_key, **(params or {})}
        try:
            async with self._session.get(url, params=p) as resp:
                if resp.status != 200:
                    logger.warning("betano_api_error", status=resp.status)
                    return None
                data = await resp.json()
                return data if isinstance(data, list) else None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("betano_request_failed", error=str(e))
            return None

    async def fetch_events(self) -> list[OddsEvent]:
        sports = await self._request("/sports")
        if not sports:
            return []

        events: list[OddsEvent] = []
        for sport in sports[:10]:
            sk = sport.get("key", "")
            if sk not in ("soccer", "basketball", "tennis", "americanfootball"):
                continue
            fixtures = await self._request(f"/sports/{sk}/events", {
                "regions": "eu,us",
            })
            if not fixtures:
                continue
            for fxt in fixtures:
                events.append(OddsEvent(
                    event_id=fxt.get("id", f"betano_{sk}_{len(events)}"),
                    sport=sk,
                    home_team=fxt.get("home_team", "Home"),
                    away_team=fxt.get("away_team", "Away"),
                    start_time=datetime.now(timezone.utc),
                ))
            await asyncio.sleep(0.2)

        logger.info("betano_events_fetched", count=len(events))
        return events

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        return []  # odds fetched via primary provider; Betano is a filter

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        if not self._has_key:
            return
        while True:
            await asyncio.sleep(self.config.update_interval_seconds)
            yield []

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


async def filter_betano_odds(odds_data: list[dict]) -> list[dict]:
    """Filter The Odds API response for Betano-specific odds."""
    betano_odds = []
    for event in odds_data:
        bookmakers = event.get("bookmakers", [])
        for bm in bookmakers:
            if bm.get("key", "").lower() in ("betano",):
                betano_odds.append({
                    "event_id": event.get("id"),
                    "sport": event.get("sport_key"),
                    "home_team": event.get("home_team"),
                    "away_team": event.get("away_team"),
                    "bookmaker": "Betano",
                    "markets": bm.get("markets", []),
                })
                break
    return betano_odds
