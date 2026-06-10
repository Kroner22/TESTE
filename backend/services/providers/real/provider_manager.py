from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate
from backend.services.providers.real.odds_provider_primary import RealPrimaryProvider
from backend.services.providers.real.odds_provider_secondary import RealSecondaryProvider
from backend.services.providers.real.fallback_provider import RealFallbackProvider

logger = get_logger(__name__)


ProviderStatus = dict[str, str | int | float | bool | None]


class ProviderManager:
    """
    Central provider orchestrator with:
    - Priority-based failover (primary -> secondary -> fallback)
    - Automatic health checks every N seconds
    - Exponential backoff reconnection
    - Per-provider status reporting
    - Provider count and mode aggregation

    Provider priority:
    1. RealPrimaryProvider (LIVE if API key set)
    2. RealSecondaryProvider (LIVE if API key set, else SIMULATION)
    3. RealFallbackProvider (always SIMULATION, always available)
    """

    HEALTH_CHECK_INTERVAL = 30.0
    RECONNECT_BASE_DELAY = 5.0
    RECONNECT_MAX_DELAY = 300.0

    def __init__(self):
        self._providers: list[BaseProvider] = []
        self._mode = "SIMULATION"
        self._mode_reason = "Nenhum provider registrado"
        self._live_provider: Optional[str] = None
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._provider_status: dict[str, ProviderStatus] = {}
        self._on_status_change: Optional[Callable[[str, ProviderStatus], Awaitable[None]]] = None
        self._last_successful_poll: dict[str, float] = {}
        self._consecutive_failures: dict[str, int] = defaultdict(int)
        self._reconnect_delays: dict[str, float] = defaultdict(lambda: self.RECONNECT_BASE_DELAY)

    async def initialize(self) -> bool:
        """Initialize all providers in priority order."""
        primary = RealPrimaryProvider()
        primary_ok = await primary.initialize()
        if primary_ok:
            self._providers.append(primary)
            self._mode = "LIVE"
            self._mode_reason = "Provider primário ativo (The Odds API)"
            self._live_provider = "primary"
            logger.info("provider_manager_primary_live")

        secondary = RealSecondaryProvider()
        sec_ok = await secondary.initialize()
        if sec_ok:
            self._providers.append(secondary)
            if self._mode == "SIMULATION":
                self._mode = "LIVE"
                self._mode_reason = "Provider secundário ativo"
                self._live_provider = "secondary"
            logger.info("provider_manager_secondary_live")

        if not primary_ok and not sec_ok:
            fallback = RealFallbackProvider()
            self._providers.append(fallback)
            self._mode = "SIMULATION"
            self._mode_reason = "Fallback sintético — nenhuma fonte real disponível"
            self._live_provider = None
            logger.info("provider_manager_fallback_mode")

        # Always add fallback as last resort
        if not any(isinstance(p, RealFallbackProvider) for p in self._providers):
            fallback = RealFallbackProvider()
            self._providers.append(fallback)

        for p in self._providers:
            self._provider_status[p.name] = self._build_status(p)

        logger.info("provider_manager_initialized",
                    mode=self._mode, providers=[p.name for p in self._providers])
        return len(self._providers) > 0

    def _build_status(self, provider: BaseProvider) -> ProviderStatus:
        last_success = self._last_successful_poll.get(provider.name)
        return {
            "name": provider.name,
            "type": type(provider).__name__,
            "healthy": True,
            "last_success": last_success,
            "consecutive_failures": self._consecutive_failures.get(provider.name, 0),
        }

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def mode_reason(self) -> str:
        return self._mode_reason

    @property
    def providers(self) -> list[BaseProvider]:
        return self._providers

    @property
    def live_provider(self) -> Optional[str]:
        return self._live_provider

    def set_on_status_change(self, callback: Callable[[str, ProviderStatus], Awaitable[None]]):
        self._on_status_change = callback

    def record_success(self, provider_name: str):
        self._last_successful_poll[provider_name] = time.time()
        self._consecutive_failures[provider_name] = 0
        self._reconnect_delays[provider_name] = self.RECONNECT_BASE_DELAY
        if provider_name in self._provider_status:
            self._provider_status[provider_name]["healthy"] = True
            self._provider_status[provider_name]["last_success"] = time.time()

    def record_failure(self, provider_name: str):
        self._consecutive_failures[provider_name] += 1
        delay = min(
            self.RECONNECT_BASE_DELAY * (2 ** self._consecutive_failures[provider_name]),
            self.RECONNECT_MAX_DELAY,
        )
        self._reconnect_delays[provider_name] = delay
        if self._consecutive_failures[provider_name] >= 3:
            if provider_name in self._provider_status:
                self._provider_status[provider_name]["healthy"] = False
            logger.warning("provider_marked_unhealthy", provider=provider_name,
                           failures=self._consecutive_failures[provider_name])

    def get_provider_status(self) -> dict[str, ProviderStatus]:
        return dict(self._provider_status)

    def get_summary(self) -> dict:
        active = sum(1 for s in self._provider_status.values() if s.get("healthy"))
        total = len(self._provider_status)
        return {
            "mode": self._mode,
            "mode_reason": self._mode_reason,
            "live_provider": self._live_provider,
            "providers": self.get_provider_status(),
            "active_count": active,
            "total_count": total,
            "all_healthy": active == total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def start_health_checks(self):
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("provider_manager_health_checks_started")

    def stop_health_checks(self):
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()

    async def _health_check_loop(self):
        while True:
            await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
            for provider in self._providers:
                if hasattr(provider, "healthy") and not provider.healthy:
                    delay = self._reconnect_delays.get(provider.name, self.RECONNECT_BASE_DELAY)
                    logger.info("provider_reconnect_attempt",
                                provider=provider.name, delay_seconds=delay)
                    try:
                        if hasattr(provider, "attempt_reconnect"):
                            ok = await provider.attempt_reconnect()
                            if ok:
                                self.record_success(provider.name)
                                if self._live_provider is None:
                                    self._live_provider = provider.name
                                    self._mode = "LIVE"
                                    self._mode_reason = f"Provider {provider.name} reconectado"
                                if self._on_status_change:
                                    await self._on_status_change(
                                        provider.name, self._provider_status.get(provider.name, {})
                                    )
                            else:
                                self.record_failure(provider.name)
                    except Exception as e:
                        logger.error("provider_reconnect_error", provider=provider.name, error=str(e))
                        self.record_failure(provider.name)
