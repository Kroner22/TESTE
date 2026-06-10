from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional


@dataclass
class OddsEvent:
    event_id: str
    sport: str
    home_team: str
    away_team: str
    start_time: datetime
    status: str = "scheduled"


@dataclass
class OddsUpdate:
    event_id: str
    market: str
    outcome: str
    bookmaker: str
    odd: Decimal
    timestamp: datetime
    is_opening: bool = False
    is_closing: bool = False


@dataclass
class ProviderConfig:
    name: str
    enabled: bool = True
    update_interval_seconds: float = 5.0


class BaseProvider(ABC):
    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def fetch_events(self) -> list[OddsEvent]:
        ...

    @abstractmethod
    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        ...

    @abstractmethod
    async def stream_odds(self, event_id: str):
        ...
        yield  # type: ignore

    @property
    def name(self) -> str:
        return self.config.name
