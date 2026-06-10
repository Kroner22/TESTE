"""
Runtime mode system for the sports quant platform.

Controls which data sources are active and how results are classified.
Transitions: SIMULATION -> HYBRID -> REAL_MARKET (one-way, progressive).
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional


class RuntimeMode(str, Enum):
    SIMULATION = "SIMULATION"
    HYBRID = "HYBRID"
    REAL_MARKET = "REAL_MARKET"


MODE_TRANSITIONS: dict[str, list[str]] = {
    "SIMULATION": ["HYBRID"],
    "HYBRID": ["REAL_MARKET"],
    "REAL_MARKET": [],
}


class ModeManager:
    """
    Manages the runtime mode with one-way progressive transitions.

    - SIMULATION: only simulated/fallback providers. No real API calls.
    - HYBRID: real providers active, fallback supplements. Data tagged.
    - REAL_MARKET: only real providers. Fallback disabled for opportunity gen.

    Tagging rules:
      SIMULATION  -> market_type = "simulation"
      HYBRID      -> market_type = "hybrid" (or "real" for real sources)
      REAL_MARKET -> market_type = "real" (always)
    """

    def __init__(self, initial_mode: RuntimeMode = RuntimeMode.SIMULATION):
        self._mode = initial_mode
        self._reason = "Initialized in SIMULATION mode"
        self._transitions: list[tuple[RuntimeMode, str, str]] = []

    @property
    def mode(self) -> RuntimeMode:
        return self._mode

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def is_simulation(self) -> bool:
        return self._mode == RuntimeMode.SIMULATION

    @property
    def is_hybrid(self) -> bool:
        return self._mode == RuntimeMode.HYBRID

    @property
    def is_real_market(self) -> bool:
        return self._mode == RuntimeMode.REAL_MARKET

    @property
    def market_type(self) -> str:
        return self._mode.value.lower()

    def transition_to(self, target: RuntimeMode, reason: str, actor: str = "system") -> bool:
        if self._mode == target:
            self._reason = reason
            return True

        allowed = MODE_TRANSITIONS.get(self._mode.value, [])
        if target.value not in allowed:
            raise ValueError(
                f"Cannot transition from {self._mode.value} to {target.value}. "
                f"Allowed: {allowed}"
            )

        prev = self._mode
        self._mode = target
        self._reason = reason
        self._transitions.append((prev, target, reason, actor))
        return True

    def get_summary(self) -> dict:
        return {
            "mode": self._mode.value,
            "reason": self._reason,
            "market_type": self.market_type,
            "is_simulation": self.is_simulation,
            "is_hybrid": self.is_hybrid,
            "is_real_market": self.is_real_market,
            "transitions": len(self._transitions),
        }

    def status_report(self) -> dict:
        return {
            "current_mode": self._mode.value,
            "reason": self._reason,
            "market_type": self.market_type,
            "providers_allowed": {
                "fallback": self.is_simulation or self.is_hybrid,
                "real": self.is_hybrid or self.is_real_market,
                "exchange": self.is_real_market,
            },
        }


@lru_cache
def get_mode_manager() -> ModeManager:
    return ModeManager()
