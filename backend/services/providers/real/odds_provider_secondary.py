from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig
from backend.services.reconciliation.secondary_odds_provider import SecondaryOddsProvider

logger = get_logger(__name__)


class RealSecondaryProvider(BaseProvider):
    """
    Secondary real-market odds provider for multi-source validation.

    Wraps SecondaryOddsProvider with:
    - Health/status tracking
    - Independent failover
    - Explicit LIVE/SIMULATION mode
    - Different polling characteristics from primary
    """

    MODE_LIVE = "LIVE"
    MODE_SIMULATION = "SIMULATION"

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="secondary", update_interval_seconds=45.0))
        self._inner = SecondaryOddsProvider()
        self._mode = self.MODE_SIMULATION
        self._mode_reason = "Sem fonte secundária real — usando feed emulado"
        self._healthy = False
        self._failure_count = 0
        self._success_count = 0
        self._consecutive_failures = 0

    async def initialize(self) -> bool:
        api_key = os.getenv("THE_ODDS_API_KEY", "")
        if api_key and api_key != "your_api_key_here":
            self._inner = SecondaryOddsProvider()
            try:
                events = await asyncio.wait_for(self._inner.fetch_events(), timeout=2.0)
                if events:
                    self._mode = self.MODE_LIVE
                    self._mode_reason = "Feed secundário conectado (The Odds API)"
                    self._healthy = True
                    self._success_count += 1
                    logger.info("secondary_provider_live", events=len(events))
                    return True
            except Exception as e:
                logger.warning("secondary_provider_init_failed", error=str(e))
        logger.info("secondary_provider_emulated",
                    detail="Sem API real — usando feed emulado para validação multi-provider")
        self._mode = self.MODE_SIMULATION
        self._mode_reason = "Feed secundário emulado (sem API real)"
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

    def status(self) -> dict:
        return {
            "name": self.name,
            "mode": self._mode,
            "mode_reason": self._mode_reason,
            "healthy": self._healthy,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
        }

    async def fetch_events(self) -> list[OddsEvent]:
        try:
            events = await self._inner.fetch_events()
            if events:
                self._healthy = True
                self._success_count += 1
            return events
        except Exception as e:
            self._failure_count += 1
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._healthy = False
            logger.error("secondary_provider_events_failed", error=str(e))
            return []

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        try:
            odds = await self._inner.fetch_odds(event_id)
            if odds:
                self._healthy = True
                self._success_count += 1
            return odds
        except Exception as e:
            self._failure_count += 1
            self._consecutive_failures += 1
            logger.error("secondary_provider_odds_failed", event_id=event_id, error=str(e))
            return []

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        while True:
            await asyncio.sleep(self.config.update_interval_seconds)
            odds = await self.fetch_odds(event_id)
            if odds:
                yield odds

    async def attempt_reconnect(self) -> bool:
        logger.info("secondary_provider_reconnecting")
        try:
            events = await self._inner.fetch_events()
            if events:
                self._healthy = True
                self._consecutive_failures = 0
                logger.info("secondary_provider_reconnected")
                return True
        except Exception as e:
            logger.warning("secondary_provider_reconnect_failed", error=str(e))
        return False
