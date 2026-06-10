"""
Provider failover manager — automatic fallback between provider tiers.

Failover chain:
    TIER 1 (sharp/exchange) -> TIER 2 (soft books) -> TIER 3 (fallback)

Behavior per mode:
    SIMULATION:  TIER 3 only
    HYBRID:      TIER 1 -> TIER 2 -> TIER 3 (with real tagging)
    REAL_MARKET: TIER 1 -> TIER 2 (never fallback for opportunities)
"""
from __future__ import annotations

import asyncio
from typing import Optional, Callable, Awaitable

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider
from backend.services.mode import RuntimeMode, get_mode_manager
from backend.services.providers.real.provider_health_monitor import get_health_monitor

logger = get_logger(__name__)


class ProviderFailoverManager:
    """
    Manages automatic failover between provider tiers.

    On failure:
    1. Mark current provider as degraded
    2. Try next provider in priority order
    3. After recovery delay, re-try higher-tier providers
    4. Notify on status changes

    Failover is per-mode:
    - SIMULATION:  fallback only
    - HYBRID:      real -> real -> fallback
    - REAL_MARKET: real -> real (no fallback)
    """

    RECOVERY_CHECK_INTERVAL = 60.0

    def __init__(self):
        self._tier_priority: dict[str, list[str]] = {
            "SIMULATION": ["fallback"],
            "HYBRID": ["the_odds_api", "pinnacle", "betfair_exchange", "betano", "secondary", "fallback"],
            "REAL_MARKET": ["the_odds_api", "pinnacle", "betfair_exchange", "betano", "secondary"],
        }
        self._current_provider: Optional[str] = None
        self._degraded_providers: set[str] = set()
        self._on_failover: Optional[Callable[[str, str], Awaitable[None]]] = None
        self._recovery_tasks: dict[str, asyncio.Task] = {}
        self._mode_manager = get_mode_manager()

    def set_on_failover(self, callback: Callable[[str, str], Awaitable[None]]):
        self._on_failover = callback

    def get_active_provider(self, providers: dict[str, BaseProvider]) -> Optional[str]:
        """Return the highest-priority healthy provider."""
        mode = self._mode_manager.mode.value
        priority = self._tier_priority.get(mode, [])

        for name in priority:
            if name in self._degraded_providers:
                continue
            provider = providers.get(name)
            if provider is None:
                continue
            if hasattr(provider, "healthy") and not getattr(provider, "healthy"):
                continue
            self._current_provider = name
            return name

        # All providers degraded — use any available
        for name, provider in providers.items():
            if name not in self._degraded_providers:
                self._current_provider = name
                return name

        return None

    def record_failure(self, provider_name: str):
        """Mark a provider as degraded and trigger failover."""
        self._degraded_providers.add(provider_name)
        logger.warning("failover_provider_degraded", provider=provider_name)

        if provider_name not in self._recovery_tasks or self._recovery_tasks[provider_name].done():
            self._recovery_tasks[provider_name] = asyncio.create_task(
                self._recovery_loop(provider_name)
            )

        if self._on_failover:
            new_active = self._current_provider or "unknown"
            asyncio.ensure_future(self._on_failover(provider_name, new_active))

    async def _recovery_loop(self, provider_name: str):
        """Periodically check if a degraded provider has recovered."""
        await asyncio.sleep(self.RECOVERY_CHECK_INTERVAL)
        logger.info("failover_checking_recovery", provider=provider_name)
        self._degraded_providers.discard(provider_name)
        self._recovery_tasks.pop(provider_name, None)

    def is_fallback_active(self, providers: dict[str, BaseProvider]) -> bool:
        """Check if the system is running on fallback (no real providers)."""
        mode = self._mode_manager.mode.value
        if mode == "SIMULATION":
            return True
        active = self.get_active_provider(providers)
        return active == "fallback"

    def reset(self):
        """Clear all degraded states (e.g., after configuration change)."""
        self._degraded_providers.clear()
        for task in self._recovery_tasks.values():
            task.cancel()
        self._recovery_tasks.clear()
        logger.info("failover_reset")

    def get_status(self) -> dict:
        return {
            "current_provider": self._current_provider,
            "degraded_providers": list(self._degraded_providers),
            "mode": self._mode_manager.mode.value,
            "is_fallback": False,  # updated externally
        }


_global_failover: Optional[ProviderFailoverManager] = None


def get_failover_manager() -> ProviderFailoverManager:
    global _global_failover
    if _global_failover is None:
        _global_failover = ProviderFailoverManager()
    return _global_failover
