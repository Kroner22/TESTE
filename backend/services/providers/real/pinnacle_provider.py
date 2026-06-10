"""
Pinnacle API provider — sharp market odds feed.

Pinnacle is considered a "sharp" bookmaker whose odds
are used as market truth reference in quantitative sports
trading. This provider integrates with the Pinnacle API
(https://pinnacleapi.com/) to fetch real market data.

Requires PINNACLE_API_KEY env var.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

import aiohttp

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig

logger = get_logger(__name__)

PINNACLE_API_BASE = "https://api.pinnacleapi.com"
PINNACLE_SPORT_IDS = {
    "soccer": 29,
    "basketball": 6,
    "tennis": 33,
    "american_football": 19,
    "baseball": 3,
    "icehockey": 20,
}
PINNACLE_SPORT_NAMES = {v: k for k, v in PINNACLE_SPORT_IDS.items()}


class PinnacleProvider(BaseProvider):
    """
    Real provider using the Pinnacle API (sharp bookmaker odds).

    Pinnacle provides:
    - Moneyline (h2h)
    - Point spreads
    - Totals (over/under)
    - Live odds updates via polling

    Used as a market truth reference due to Pinnacle's reputation
    as a sharp bookmaker with efficient pricing.
    """

    def __init__(self, api_key: Optional[str] = None, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(
            name="pinnacle",
            update_interval_seconds=15.0,
        ))
        self._api_key = api_key or os.getenv("PINNACLE_API_KEY", "")
        self._api_secret = os.getenv("PINNACLE_API_SECRET", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._has_credentials = bool(self._api_key) and self._api_key != "your_api_key_here"
        self._mode = "SIMULATION" if not self._has_credentials else "LIVE"
        self._mode_reason = "PINNACLE_API_KEY nao configurada" if not self._has_credentials else "Pinnacle API ativa"
        self._healthy = self._has_credentials
        self._league_cache: dict[int, list[dict]] = {}
        self._sports_cache: dict[int, dict] = {}

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_reason(self) -> str:
        return self._mode_reason

    @property
    def healthy(self) -> bool:
        return self._healthy

    def _generate_signature(self, endpoint: str, body: str = "") -> str:
        """Generate HMAC-SHA1 signature for Pinnacle API authentication."""
        if not self._api_secret:
            return ""
        data = endpoint + body
        return hmac.new(
            self._api_secret.encode(),
            data.encode(),
            hashlib.sha1,
        ).hexdigest()

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"Content-Type": "application/json"},
            )

    async def _request(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make authenticated request to Pinnacle API."""
        if not self._has_credentials:
            return None
        await self._ensure_session()
        url = f"{PINNACLE_API_BASE}{endpoint}"
        headers = {
            "X-API-Key": self._api_key,
        }
        if self._api_secret:
            sig = self._generate_signature(endpoint)
            headers["X-API-Signature"] = sig

        try:
            async with self._session.get(url, params=params, headers=headers) as resp:
                if resp.status == 401:
                    logger.error("pinnacle_auth_failed")
                    self._healthy = False
                    return None
                if resp.status == 429:
                    logger.warning("pinnacle_rate_limited")
                    return None
                if resp.status != 200:
                    logger.warning("pinnacle_api_error", status=resp.status)
                    return None
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("pinnacle_request_failed", error=str(e))
            return None

    async def _request_list(self, endpoint: str, params: Optional[dict] = None) -> list:
        result = await self._request(endpoint, params)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
        return []

    async def fetch_events(self) -> list[OddsEvent]:
        if not self._has_credentials:
            return []

        events: list[OddsEvent] = []

        for sport_name, sport_id in PINNACLE_SPORT_IDS.items():
            leagues_data = await self._request(f"/v2/leagues/{sport_id}", {"all": "true"})
            if not leagues_data:
                continue

            leagues = leagues_data.get("leagues", []) if isinstance(leagues_data, dict) else []
            for league in leagues[:5]:
                league_id = league.get("id")
                if not league_id:
                    continue

                fixtures = await self._request(
                    f"/v1/fixtures/{sport_id}",
                    {"leagueId": league_id, "since": 0},
                )
                if not fixtures:
                    continue

                fixture_list = []
                if isinstance(fixtures, dict):
                    fixture_list = fixtures.get("fixtures", []) or fixtures.get("events", []) or []
                elif isinstance(fixtures, list):
                    fixture_list = fixtures

                for fxt in fixture_list[:10]:
                    eid = str(fxt.get("id", f"pin_{sport_id}_{league_id}_{len(events)}"))
                    home = fxt.get("homeTeam", fxt.get("participants", [{}])[0].get("name", "Home")) if isinstance(fxt.get("participants", []), list) and len(fxt.get("participants", [])) > 0 else "Home"
                    away = fxt.get("awayTeam", fxt.get("participants", [{}])[1].get("name", "Away")) if isinstance(fxt.get("participants", []), list) and len(fxt.get("participants", [])) > 1 else "Away"
                    start_ts = fxt.get("startTime", fxt.get("commenceTime", 0))
                    if isinstance(start_ts, str):
                        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00")) if "T" in start_ts else datetime.now(timezone.utc)
                    elif isinstance(start_ts, (int, float)):
                        start = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc) if start_ts > 1e10 else datetime.fromtimestamp(start_ts, tz=timezone.utc)
                    else:
                        start = datetime.now(timezone.utc)

                    events.append(OddsEvent(
                        event_id=eid,
                        sport=sport_name,
                        home_team=home if isinstance(home, str) else str(home),
                        away_team=away if isinstance(away, str) else str(away),
                        start_time=start,
                    ))

                await asyncio.sleep(0.3)

        logger.info("pinnacle_events_fetched", count=len(events), mode=self._mode)
        return events

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        if not self._has_credentials:
            return []

        sport_id = None
        for sname, sid in PINNACLE_SPORT_IDS.items():
            if sname in event_id[:20] or sid:
                sport_id = sid
                break
        if not sport_id:
            sport_id = 29

        try:
            odds_data = await self._request(
                f"/v1/odds/{sport_id}",
                {"eventId": int(event_id) if event_id.isdigit() else 0},
            )
            if not odds_data:
                return []
        except (ValueError, AttributeError):
            return []

        updates: list[OddsUpdate] = []
        now = datetime.now(timezone.utc)

        if isinstance(odds_data, dict):
            # Parse moneyline
            prices = odds_data.get("moneyline", odds_data.get("prices", []))
            if isinstance(prices, list):
                outcomes_map = ["home", "away", "draw"]
                for i, price_data in enumerate(prices):
                    if i >= len(outcomes_map):
                        break
                    price = None
                    if isinstance(price_data, dict):
                        price = price_data.get("price", price_data.get("american", 0))
                    elif isinstance(price_data, (int, float)):
                        price = price_data
                    if price and isinstance(price, (int, float)) and price > 0:
                        if price > 100:
                            dec = american_to_decimal(price)
                        else:
                            dec = float(price)
                        updates.append(OddsUpdate(
                            event_id=event_id,
                            market="h2h",
                            outcome=outcomes_map[i],
                            bookmaker="Pinnacle",
                            odd=Decimal(str(round(dec, 2))),
                            timestamp=now,
                        ))

        return updates

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        if not self._has_credentials:
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


def american_to_decimal(american_odds: float) -> float:
    """Convert American odds to decimal format."""
    if american_odds > 0:
        return 1 + american_odds / 100
    else:
        return 1 + 100 / abs(american_odds)
