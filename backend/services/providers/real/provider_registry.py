"""
Provider registry — central registry of all available providers.

Manages provider discovery, registration, and capability queries.
Allows runtime inspection of which providers are available and
their capabilities (sports, markets, update frequency, etc.).
"""
from __future__ import annotations

from typing import Optional

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider
from backend.services.providers.real.odds_provider_primary import RealPrimaryProvider
from backend.services.providers.real.odds_provider_secondary import RealSecondaryProvider
from backend.services.providers.real.fallback_provider import RealFallbackProvider
from backend.services.providers.real.pinnacle_provider import PinnacleProvider
from backend.services.providers.real.betfair_provider import BetfairExchangeProvider
from backend.services.providers.real.betano_provider import BetanoProvider

logger = get_logger(__name__)

TIER_1_PROVIDERS = ["the_odds_api", "pinnacle", "betfair_exchange"]
TIER_2_PROVIDERS = ["betano"]
TIER_3_PROVIDERS = ["secondary", "fallback"]


class ProviderRegistry:
    """
    Central registry for all data providers.

    Allows:
    - Registration of providers at startup
    - Lookup by name, tier, or capability
    - Capability queries (sports, markets, real-time support)
    - Runtime provider discovery
    """

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}
        self._initialized = False

    async def initialize(self, pre_initialized: Optional[dict[str, BaseProvider]] = None) -> bool:
        if self._initialized:
            return True

        if pre_initialized:
            for name, instance in pre_initialized.items():
                self._providers[name] = instance
                logger.info("registry_provider_registered", name=name, type=type(instance).__name__)

        providers_to_register = [
            ("the_odds_api", RealPrimaryProvider),
            ("secondary", RealSecondaryProvider),
            ("fallback", RealFallbackProvider),
            ("pinnacle", PinnacleProvider),
            ("betfair_exchange", BetfairExchangeProvider),
            ("betano", BetanoProvider),
        ]

        pre_init_types = {type(p).__name__ for p in pre_initialized.values()} if pre_initialized else set()
        pre_init_names = set(pre_initialized.keys()) if pre_initialized else set()

        for name, provider_class in providers_to_register:
            if name in self._providers or provider_class.__name__ in pre_init_types:
                if name not in self._providers:
                    pre_prov = [p for n, p in (pre_initialized or {}).items() if type(p).__name__ == provider_class.__name__]
                    if pre_prov:
                        self._providers[name] = pre_prov[0]
                        logger.info("registry_provider_mapped", name=name, source_name=[n for n,p in (pre_initialized or {}).items() if p is pre_prov[0]][0])
                continue
                continue
            try:
                instance = provider_class()
                if hasattr(instance, "initialize") and callable(getattr(instance, "initialize")):
                    await instance.initialize()
                self._providers[name] = instance
                logger.info("registry_provider_registered", name=name, type=type(instance).__name__)
            except Exception as e:
                logger.error("registry_provider_failed", name=name, error=str(e))

        self._initialized = True
        logger.info("provider_registry_initialized", count=len(self._providers))
        return len(self._providers) > 0

    def register(self, name: str, provider: BaseProvider):
        self._providers[name] = provider

    def get(self, name: str) -> Optional[BaseProvider]:
        return self._providers.get(name)

    def get_all(self) -> dict[str, BaseProvider]:
        return dict(self._providers)

    def get_by_tier(self, tier: int) -> dict[str, BaseProvider]:
        tier_map = {
            1: TIER_1_PROVIDERS,
            2: TIER_2_PROVIDERS,
            3: TIER_3_PROVIDERS,
        }
        names = tier_map.get(tier, [])
        return {n: p for n, p in self._providers.items() if n in names}

    def get_real_providers(self) -> dict[str, BaseProvider]:
        """Return only providers that have LIVE mode (real data)."""
        real = {}
        for name, provider in self._providers.items():
            if hasattr(provider, "mode") and getattr(provider, "mode") == "LIVE":
                real[name] = provider
        return real

    def get_simulation_providers(self) -> dict[str, BaseProvider]:
        sim = {}
        for name, provider in self._providers.items():
            if hasattr(provider, "mode") and getattr(provider, "mode") == "SIMULATION":
                sim[name] = provider
        return sim

    def get_active_providers(self) -> dict[str, BaseProvider]:
        return {n: p for n, p in self._providers.items() if self._is_active(p)}

    def _is_active(self, provider: BaseProvider) -> bool:
        if hasattr(provider, "healthy"):
            return bool(getattr(provider, "healthy"))
        return True

    def get_summary(self) -> dict:
        return {
            "total": len(self._providers),
            "real": len(self.get_real_providers()),
            "simulation": len(self.get_simulation_providers()),
            "active": len(self.get_active_providers()),
            "providers": {
                name: {
                    "type": type(p).__name__,
                    "mode": getattr(p, "mode", "UNKNOWN"),
                    "healthy": getattr(p, "healthy", True),
                }
                for name, p in self._providers.items()
            },
        }


_global_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ProviderRegistry()
    return _global_registry
