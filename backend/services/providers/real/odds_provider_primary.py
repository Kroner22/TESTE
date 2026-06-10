from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig
from backend.services.providers.real_api_provider import TheOddsApiProvider

logger = get_logger(__name__)


class RealPrimaryProvider(BaseProvider):
    """
    Primary real-market odds provider.

    Wraps TheOddsApiProvider with:
    - Health tracking (last successful poll, failure count)
    - Connection status reporting
    - Reconnection with exponential backoff
    - Explicit LIVE/SIMULATION mode flag
    """

    MODE_LIVE = "LIVE"
    MODE_SIMULATION = "SIMULATION"

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="primary", update_interval_seconds=30.0))
        self._inner = TheOddsApiProvider()
        self._mode = self.MODE_SIMULATION
        self._mode_reason = "THE_ODDS_API_KEY não configurada"
        self._healthy = False
        self._failure_count = 0
        self._success_count = 0
        self._last_success: Optional[float] = None
        self._last_failure: Optional[float] = None
        self._consecutive_failures = 0
        self._reconnect_attempts = 0
        self._max_reconnect_delay = 300.0

    async def initialize(self) -> bool:
        api_key = os.getenv("THE_ODDS_API_KEY", "")
        if api_key and api_key != "your_api_key_here":
            self._inner = TheOddsApiProvider(api_key=api_key)
            try:
                events = await asyncio.wait_for(self._inner.fetch_events(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning('primary_provider_api_timeout')
                self._mode = self.MODE_SIMULATION
                self._mode_reason = 'API timeout — operando em simulação'
                return False
            if events:
                self._mode = self.MODE_LIVE
                self._mode_reason = f"The Odds API conectado ({len(events)} eventos)"
                self._healthy = True
                self._success_count += 1
                self._last_success = datetime.now(timezone.utc).timestamp()
                logger.info("primary_provider_live", events=len(events))
                return True
            else:
                logger.warning("primary_provider_api_empty")
        else:
            logger.info("primary_provider_no_key", detail="THE_ODDS_API_KEY não encontrada")
        self._mode = self.MODE_SIMULATION
        self._mode_reason = "Sem chave de API — operando em simulação"
        return False

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_reason(self) -> str:
        return self._mode_reason

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def success_count(self) -> int:
        return self._success_count

    @property
    def last_success(self) -> Optional[float]:
        return self._last_success

    @property
    def last_failure(self) -> Optional[float]:
        return self._last_failure

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def status(self) -> dict:
        return {
            "name": self.name,
            "mode": self._mode,
            "mode_reason": self._mode_reason,
            "healthy": self._healthy,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "consecutive_failures": self._consecutive_failures,
            "reconnect_attempts": self._reconnect_attempts,
            "last_success": self._last_success,
            "last_failure": self._last_failure,
        }

    def _record_success(self):
        self._healthy = True
        self._success_count += 1
        self._consecutive_failures = 0
        self._last_success = datetime.now(timezone.utc).timestamp()

    def _record_failure(self):
        self._consecutive_failures += 1
        self._failure_count += 1
        self._last_failure = datetime.now(timezone.utc).timestamp()
        if self._consecutive_failures >= 3:
            self._healthy = False
        logger.warning("primary_provider_failure",
                       consecutive=self._consecutive_failures, total=self._failure_count)

    async def _safe_fetch_events(self) -> list[OddsEvent]:
        try:
            events = await self._inner.fetch_events()
            self._record_success()
            return events
        except Exception as e:
            self._record_failure()
            logger.error("primary_provider_events_failed", error=str(e))
            return []

    async def _safe_fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        try:
            odds = await self._inner.fetch_odds(event_id)
            self._record_success()
            return odds
        except Exception as e:
            self._record_failure()
            logger.error("primary_provider_odds_failed", event_id=event_id, error=str(e))
            return []

    async def fetch_events(self) -> list[OddsEvent]:
        if self._mode != self.MODE_LIVE:
            return []
        return await self._safe_fetch_events()

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        if self._mode != self.MODE_LIVE:
            return []
        return await self._safe_fetch_odds(event_id)

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        if self._mode != self.MODE_LIVE:
            return
        while True:
            delay = self.config.update_interval_seconds
            if self._consecutive_failures > 0:
                delay = min(delay * (2 ** self._consecutive_failures), self._max_reconnect_delay)
                self._reconnect_attempts += 1
            await asyncio.sleep(delay)
            odds = await self._safe_fetch_odds(event_id)
            if odds:
                yield odds

    async def attempt_reconnect(self) -> bool:
        """Try to re-establish connection. Returns True if successful."""
        logger.info("primary_provider_reconnecting")
        self._reconnect_attempts += 1
        try:
            try:
                events = await asyncio.wait_for(self._inner.fetch_events(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning('primary_provider_api_timeout')
                self._mode = self.MODE_SIMULATION
                self._mode_reason = 'API timeout — operando em simulação'
                return False
            if events:
                self._mode = self.MODE_LIVE
                self._mode_reason = "Reconectado via The Odds API"
                self._healthy = True
                self._consecutive_failures = 0
                logger.info("primary_provider_reconnected")
                return True
        except Exception as e:
            logger.warning("primary_provider_reconnect_failed", error=str(e))
        self._healthy = False
        return False
