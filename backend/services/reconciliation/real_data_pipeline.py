from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Callable, Awaitable

from backend.app.log_config import get_logger
from backend.app.settings import get_settings
from backend.services.providers.base import BaseProvider, ProviderConfig, OddsUpdate, OddsEvent
from backend.services.providers.real_api_provider import TheOddsApiProvider
from backend.services.providers.fallback_provider import FallbackProvider
from backend.services.providers.mock_provider import MockProvider
from backend.services.pipeline.event_matcher import EventMatcher, EventCandidate
from backend.services.pipeline.odds_normalizer import normalize_event

logger = get_logger(__name__)


class RealDataPipeline:
    """
    Orchestrates the real data ingestion chain.

    Provider priority:
    1. TheOddsApiProvider (if API key set)
    2. FallbackProvider (enhanced synthetic)
    3. MockProvider (simple fallback)

    Auto-detects available providers, manages lifecycle,
    and marks mode as LIVE or SIMULATION explicitly.
    """

    def __init__(self):
        self._providers: list[BaseProvider] = []
        self._event_matcher = EventMatcher()
        self._mode: str = "SIMULATION"
        self._mode_reason: str = "Nenhum provider configurado"
        self._live_provider_name: Optional[str] = None
        self._ingestion_callback: Optional[Callable[[list[OddsUpdate], str], Awaitable[None]]] = None
        self._started = False
        self._tasks: list[asyncio.Task] = []

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_reason(self) -> str:
        return self._mode_reason

    @property
    def live_provider_name(self) -> Optional[str]:
        return self._live_provider_name

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    def set_ingestion_callback(self, callback: Callable[[list[OddsUpdate], str], Awaitable[None]]):
        self._ingestion_callback = callback

    async def detect_and_initialize(self):
        """Auto-detect available data sources and initialize providers."""
        providers: list[BaseProvider] = []
        api_key = os.getenv("THE_ODDS_API_KEY", "")

        if api_key and api_key != "your_api_key_here":
            logger.info("real_data_api_key_detected", key_prefix=api_key[:8])
            real_provider = TheOddsApiProvider(api_key=api_key)
            try:
                events = await real_provider.fetch_events()
                if events:
                    providers.append(real_provider)
                    self._mode = "LIVE"
                    self._mode_reason = f"The Odds API conectado ({len(events)} eventos)"
                    self._live_provider_name = "the_odds_api"
                    logger.info("real_data_mode_live", events=len(events))
                else:
                    logger.warning("real_data_api_returned_empty")
            except Exception as e:
                logger.warning("real_data_api_init_failed", error=str(e))

        if not providers:
            logger.info("real_data_using_fallback_provider")
            fallback = FallbackProvider(ProviderConfig(name="fallback", update_interval_seconds=5.0))
            try:
                events = await fallback.fetch_events()
                if events:
                    providers.append(fallback)
                    self._mode = "SIMULATION"
                    self._mode_reason = "Fallback aprimorado (sem API real)"
                    self._live_provider_name = None
                    logger.info("real_data_fallback_initialized", events=len(events))
            except Exception as e:
                logger.warning("real_data_fallback_init_failed", error=str(e))

        if not providers:
            logger.info("real_data_using_mock_provider")
            mock = MockProvider(ProviderConfig(name="mock", update_interval_seconds=0.15))
            providers.append(mock)
            self._mode = "SIMULATION"
            self._mode_reason = "Modo simulação local (sem fontes externas)"
            self._live_provider_name = None

        self._providers = providers
        logger.info("real_data_pipeline_ready", mode=self._mode, providers=[p.name for p in providers])

    def get_providers(self) -> list[BaseProvider]:
        return self._providers

    def get_event_matcher(self) -> EventMatcher:
        return self._event_matcher

    def normalize_and_match(self, sport: str, home: str, away: str, league: str = "") -> tuple[str, str]:
        normalized = normalize_event(sport, home, away, league)
        return normalized.home_team, normalized.away_team
