"""
Betfair Exchange API provider — exchange-driven market truth source.

Betfair Exchange provides the deepest liquidity and most accurate
market pricing in sports betting. This provider uses the Betfair
API (https://developer.betfair.com/) to fetch:

- Back odds (BACK) — the price at which you can back an outcome
- Lay odds (LAY) — the price at which you can lay an outcome
- Traded volume — total matched at each price level
- Market depth — available liquidity at each price
- Spread calculation — back/lay spread as market efficiency metric

Betfair serves as the REFERENCE MARKET TRUTH SOURCE due to its
exchange-driven price discovery mechanism.

Requires BETFAIR_APP_KEY, BETFAIR_USERNAME, BETFAFF_PASSWORD env vars.
"""
from __future__ import annotations

import asyncio
import base64
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional, Any

import aiohttp

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig

logger = get_logger(__name__)

BETFAIR_API_BASE = "https://api.betfair.com/exchange/betting/rest/v1.0"
BETFAIR_AUTH_URL = "https://identitysso.betfair.com/api/login"
BETFAIR_NG_BASE = "https://api.betfair.com/exchange/betting/json-rpc/v1"

BETFAIR_SPORT_IDS = {
    "soccer": 1,
    "basketball": 4,
    "tennis": 2,
    "american_football": 6,
    "baseball": 3,
    "icehockey": 7,
}


class BetfairExchangeProvider(BaseProvider):
    """
    Exchange-driven market truth provider using Betfair API.

    Provides:
    - Back odds (market efficiency reference)
    - Lay odds (liquidity depth)
    - Traded volume
    - Market depth snapshot
    - Back/lay spread

    This is the designated TRUTH SOURCE provider for the
    reconciliation engine when running in REAL_MARKET mode.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(
            name="betfair_exchange",
            update_interval_seconds=10.0,
        ))
        self._app_key = os.getenv("BETFAIR_APP_KEY", "")
        self._username = os.getenv("BETFAIR_USERNAME", "")
        self._password = os.getenv("BETFAIR_PASSWORD", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_token: Optional[str] = None
        self._session_expiry: float = 0
        self._has_credentials = (
            bool(self._app_key)
            and bool(self._username)
            and bool(self._password)
            and self._app_key != "your_app_key_here"
        )
        self._mode = "SIMULATION" if not self._has_credentials else "LIVE"
        self._mode_reason = "BETFAIR_APP_KEY/USERNAME/PASSWORD nao configurados" if not self._has_credentials else "Betfair Exchange ativo"
        self._healthy = self._has_credentials
        self._market_cache: dict[str, dict] = {}
        self._consecutive_login_failures = 0

    def status(self) -> dict:
        return {
            "name": self.name,
            "mode": self._mode,
            "mode_reason": self._mode_reason,
            "healthy": self._healthy,
            "has_credentials": self._has_credentials,
            "session_active": self._session_token is not None,
            "session_expires_in": max(0, self._session_expiry - time.time()) if self._session_expiry > 0 else 0,
        }

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_reason(self) -> str:
        return self._mode_reason

    @property
    def healthy(self) -> bool:
        return self._healthy

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
            )

    async def _login(self) -> bool:
        """Authenticate with Betfair identity service."""
        if not self._has_credentials:
            return False

        await self._ensure_session()

        try:
            cert_path = os.getenv("BETFAIR_CERT_PATH", "")
            headers = {
                "X-Application": self._app_key,
                "Content-Type": "application/x-www-form-urlencoded",
            }

            if cert_path and os.path.exists(cert_path):
                conn = aiohttp.TCPConnector(ssl_context=None)
                login_session = aiohttp.ClientSession(
                    connector=conn,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers=headers,
                )
            else:
                login_session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers=headers,
                )

            data = f"username={self._username}&password={self._password}"
            async with login_session.post(BETFAIR_AUTH_URL, data=data) as resp:
                result = await resp.json()
                if result.get("status") == "SUCCESS":
                    self._session_token = result.get("token")
                    self._session_expiry = time.time() + 3600
                    self._consecutive_login_failures = 0
                    logger.info("betfair_login_success")
                    await login_session.close()
                    return True
                else:
                    error = result.get("error", "unknown")
                    logger.error("betfair_login_failed", error=error)
                    self._consecutive_login_failures += 1
                    await login_session.close()
                    return False
        except Exception as e:
            logger.error("betfair_login_error", error=str(e))
            self._consecutive_login_failures += 1
            return False

    async def _ensure_authenticated(self) -> bool:
        """Ensure valid session token, log in if needed."""
        if self._session_token and time.time() < self._session_expiry - 60:
            return True
        return await self._login()

    async def _json_rpc(self, method: str, params: dict) -> Optional[dict]:
        """Execute Betfair JSON-RPC API call."""
        if not await self._ensure_authenticated():
            return None

        await self._ensure_session()
        headers = {
            "X-Application": self._app_key,
            "X-Authentication": self._session_token or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }

        try:
            async with self._session.post(BETFAIR_NG_BASE, json=payload, headers=headers) as resp:
                if resp.status == 401:
                    logger.warning("betfair_session_expired, re-logging")
                    self._session_token = None
                    if await self._login():
                        headers["X-Authentication"] = self._session_token or ""
                        async with self._session.post(BETFAIR_NG_BASE, json=payload, headers=headers) as retry_resp:
                            if retry_resp.status == 200:
                                return await retry_resp.json()
                    return None
                if resp.status != 200:
                    logger.warning("betfair_api_error", status=resp.status, method=method)
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("betfair_request_failed", error=str(e), method=method)
            return None

    async def fetch_events(self) -> list[OddsEvent]:
        if not self._has_credentials:
            return []

        events: list[OddsEvent] = []

        for sport_name, bf_sport_id in BETFAIR_SPORT_IDS.items():
            result = await self._json_rpc("SportsAPING/v1.0/listEvents", {
                "filter": {
                    "eventTypeIds": [str(bf_sport_id)],
                    "marketStartTime": {
                        "from": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "to": datetime.now(timezone.utc).strftime("%Y-%m-%dT23:59:59Z"),
                    },
                },
                "locale": "en",
            })

            if not result or "result" not in result:
                continue

            for event_data in result["result"]:
                event_info = event_data.get("event", {})
                eid = event_info.get("id", "")
                name = event_info.get("name", "")
                start_str = event_info.get("openDate", "")

                # Parse event name into teams
                parts = name.split(" v ")
                home = parts[0].strip() if len(parts) > 0 else name
                away = parts[1].strip() if len(parts) > 1 else "Unknown"

                start = datetime.now(timezone.utc)
                if start_str:
                    try:
                        start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                events.append(OddsEvent(
                    event_id=eid,
                    sport=sport_name,
                    home_team=home,
                    away_team=away,
                    start_time=start,
                ))

            await asyncio.sleep(0.2)

        logger.info("betfair_events_fetched", count=len(events), mode=self._mode)
        return events

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        if not self._has_credentials:
            return []

        # List markets for this event
        markets_result = await self._json_rpc("SportsAPING/v1.0/listMarketCatalogue", {
            "filter": {"eventIds": [event_id]},
            "marketProjection": ["MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"],
            "sort": "FIRST_TO_START",
            "maxResults": 20,
        })

        if not markets_result or "result" not in markets_result:
            return []

        updates: list[OddsUpdate] = []
        now = datetime.now(timezone.utc)

        for market in markets_result["result"]:
            market_id = market.get("marketId", "")
            market_name = market.get("marketName", "")
            desc = market.get("description", {})

            market_type = "h2h"
            if "Over/Under" in market_name:
                market_type = "totals"
            elif "handicap" in market_name.lower():
                market_type = "spreads"

            # Get prices for this market
            prices_result = await self._json_rpc("SportsAPING/v1.0/listMarketBook", {
                "marketIds": [market_id],
                "priceProjection": {
                    "priceData": ["EX_BEST_OFFERS", "EX_TRADED_VOLUME"],
                    "virtualise": True,
                },
                "orderProjection": "ALL",
                "matchProjection": "ROLLED_UP_BY_AVG_PRICE",
            })

            if not prices_result or "result" not in prices_result:
                continue

            for book in prices_result["result"]:
                runners = book.get("runners", [])
                for runner in runners:
                    selection_id = runner.get("selectionId", 0)
                    runner_name = runner.get("runnerName", f"outcome_{selection_id}")
                    outcome = runner_name.lower().replace(" ", "_")

                    # Get best back and lay prices
                    ex_data = runner.get("ex", {})
                    best_offers = ex_data.get("availableToBack", [])
                    best_lays = ex_data.get("availableToLay", [])

                    # Use back price (the price at which you can back)
                    best_back = best_offers[0].get("price", 0) if best_offers else None
                    best_lay = best_lays[0].get("price", 0) if best_lays else None

                    # Middle price = fair market price
                    if best_back and best_lay:
                        fair_price = (best_back + best_lay) / 2
                    elif best_back:
                        fair_price = best_back
                    elif best_lay:
                        fair_price = best_lay
                    else:
                        continue

                    updates.append(OddsUpdate(
                        event_id=event_id,
                        market=market_type,
                        outcome=outcome,
                        bookmaker="BetfairExchange",
                        odd=Decimal(str(round(fair_price, 2))),
                        timestamp=now,
                    ))

            await asyncio.sleep(0.1)

        return updates

    async def fetch_market_depth(self, event_id: str) -> dict:
        """
        Fetch full market depth for an event.
        Returns back/lay prices with volume at each level.
        """
        markets_result = await self._json_rpc("SportsAPING/v1.0/listMarketCatalogue", {
            "filter": {"eventIds": [event_id]},
            "maxResults": 10,
        })

        if not markets_result or "result" not in markets_result:
            return {}

        depth = {}
        for market in markets_result["result"]:
            market_id = market.get("marketId", "")
            market_name = market.get("marketName", "")

            prices_result = await self._json_rpc("SportsAPING/v1.0/listMarketBook", {
                "marketIds": [market_id],
                "priceProjection": {
                    "priceData": ["EX_BEST_OFFERS", "EX_TRADED_VOLUME"],
                },
            })

            if not prices_result or "result" not in prices_result:
                continue

            depth[market_name] = []
            for book in prices_result["result"]:
                for runner in book.get("runners", []):
                    ex = runner.get("ex", {})
                    depth[market_name].append({
                        "selection_id": runner.get("selectionId"),
                        "name": runner.get("runnerName"),
                        "back": ex.get("availableToBack", []),
                        "lay": ex.get("availableToLay", []),
                        "traded_volume": ex.get("tradedVolume", []),
                        "total_matched": runner.get("totalMatched", 0),
                        "status": runner.get("status", ""),
                        "spread": self._calc_spread(ex.get("availableToBack", []), ex.get("availableToLay", [])),
                    })

        return depth

    def _calc_spread(self, back: list, lay: list) -> Optional[float]:
        """Calculate back/lay spread as percentage."""
        best_back = back[0].get("price", 0) if back else None
        best_lay = lay[0].get("price", 0) if lay else None
        if best_back and best_lay:
            return round((best_lay - best_back) / best_back * 100, 2)
        return None

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        if not self._has_credentials:
            return
        while True:
            await asyncio.sleep(self.config.update_interval_seconds)
            updates = await self.fetch_odds(event_id)
            if updates:
                yield updates

    async def close(self):
        self._session_token = None
        if self._session:
            await self._session.close()
            self._session = None
