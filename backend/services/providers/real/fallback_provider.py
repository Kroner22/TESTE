from __future__ import annotations

from typing import AsyncGenerator, Optional

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig
from backend.services.providers.fallback_provider import FallbackProvider

logger = get_logger(__name__)


class RealFallbackProvider(BaseProvider):
    """
    Explicitly-labeled fallback provider for SIMULATION mode.

    Wraps FallbackProvider but:
    - Always reports mode as SIMULATION
    - Includes reason in every status response
    - Never masquerades as real data
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="fallback", update_interval_seconds=5.0))
        self._inner = FallbackProvider(config)
        self._mode = "SIMULATION"
        self._mode_reason = "Fallback sintético — nenhuma fonte real disponível"
        logger.info("fallback_provider_init", mode=self._mode, reason=self._mode_reason)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_reason(self) -> str:
        return self._mode_reason

    def status(self) -> dict:
        return {
            "name": self.name,
            "mode": self._mode,
            "mode_reason": self._mode_reason,
            "healthy": True,
        }

    async def fetch_events(self) -> list[OddsEvent]:
        return await self._inner.fetch_events()

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        return await self._inner.fetch_odds(event_id)

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        async for batch in self._inner.stream_odds(event_id):
            yield batch
