from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

import aiohttp
from bs4 import BeautifulSoup

from backend.app.log_config import get_logger
from backend.services.providers.base import BaseProvider, OddsEvent, OddsUpdate, ProviderConfig
from backend.services.pipeline.odds_normalizer import normalize_team, normalize_bookmaker, normalize_outcome

logger = get_logger(__name__)

SCRAPE_SOURCES: dict[str, list[dict]] = {
    "oddsportal": [
        {"url": "https://www.oddsportal.com/soccer/", "sport": "soccer", "selector": "table.table-main tr"},
        {"url": "https://www.oddsportal.com/basketball/", "sport": "basketball", "selector": "table.table-main tr"},
        {"url": "https://www.oddsportal.com/tennis/", "sport": "tennis", "selector": "table.table-main tr"},
    ],
}

REQUEST_DELAY = 1.5
MAX_RETRIES = 3
BACKOFF_FACTOR = 2.0


class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 3, recovery_time: float = 60.0):
        self.name = name
        self.threshold = threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure: Optional[datetime] = None

    def record_success(self):
        self.failures = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failures += 1
        self.last_failure = datetime.now(timezone.utc)
        if self.failures >= self.threshold:
            self.state = CircuitState.OPEN

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.last_failure and (datetime.now(timezone.utc) - self.last_failure).total_seconds() > self.recovery_time:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failures,
            "threshold": self.threshold,
        }


class ScraperProvider(BaseProvider):
    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="scraper", update_interval_seconds=60.0))
        self._session: Optional[aiohttp.ClientSession] = None
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            name: CircuitBreaker(name) for name in SCRAPE_SOURCES
        }
        self._scraped_events: list[OddsEvent] = []
        self._last_scrape: Optional[datetime] = None
        self._scrape_interval = timedelta(minutes=15)

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
            )

    async def fetch_events(self) -> list[OddsEvent]:
        if self._last_scrape and (datetime.now(timezone.utc) - self._last_scrape) < self._scrape_interval:
            return self._scraped_events

        await self._ensure_session()
        events: list[OddsEvent] = []
        event_ids: set[str] = set()
        eid_counter = [0]

        for source_name, pages in SCRAPE_SOURCES.items():
            cb = self._circuit_breakers[source_name]
            if cb.is_open():
                logger.warning("scraper_circuit_open", source=source_name)
                continue

            for page in pages:
                try:
                    events_batch = await self._scrape_page(source_name, page, eid_counter, event_ids)
                    events.extend(events_batch)
                    cb.record_success()
                except Exception as e:
                    cb.record_failure()
                    logger.warning("scraper_page_failed", source=source_name, url=page["url"], error=str(e))

                await asyncio.sleep(REQUEST_DELAY)

        self._scraped_events = events
        self._last_scrape = datetime.now(timezone.utc)
        logger.info("scraper_events_fetched", count=len(events), sources=len(SCRAPE_SOURCES))
        return events

    async def _scrape_page(
        self,
        source_name: str,
        page: dict,
        counter: list[int],
        seen: set[str],
    ) -> list[OddsEvent]:
        await self._ensure_session()
        url = page["url"]
        sport = page["sport"]

        for attempt in range(MAX_RETRIES):
            try:
                async with self._session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("scraper_http_error", url=url, status=resp.status)
                        await asyncio.sleep(BACKOFF_FACTOR ** attempt)
                        continue

                    html = await resp.text()
                    soup = BeautifulSoup(html, "lxml")
                    events: list[OddsEvent] = []
                    rows = soup.select(page["selector"])

                    for row in rows[:50]:
                        cols = row.find_all("td")
                        if len(cols) < 3:
                            continue

                        text = row.get_text(" ", strip=True)
                        teams = self._extract_teams(text, sport)
                        if not teams:
                            continue

                        home, away = teams
                        counter[0] += 1
                        eid = f"scrape_{source_name}_{counter[0]}"
                        if eid in seen:
                            continue
                        seen.add(eid)

                        start = datetime.now(timezone.utc) + timedelta(hours=counter[0] % 48)
                        events.append(OddsEvent(
                            event_id=eid,
                            sport=sport,
                            home_team=normalize_team(home),
                            away_team=normalize_team(away),
                            start_time=start,
                        ))

                    return events

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning("scraper_attempt_failed", url=url, attempt=attempt + 1, error=str(e))
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BACKOFF_FACTOR ** attempt)

        return []

    def _extract_teams(self, text: str, sport: str) -> Optional[tuple[str, str]]:
        separators = [r"\s+vs\.?\s+", r"\s+v\s+", r"\s+-\s+", r"\s+–\s+"]
        for sep in separators:
            parts = re.split(sep, text, maxsplit=1)
            if len(parts) == 2:
                home = parts[0].strip()[:40]
                away = parts[1].strip()[:40]
                if home and away and home.lower() != away.lower():
                    return home, away
        return None

    async def fetch_odds(self, event_id: str) -> list[OddsUpdate]:
        return []

    async def stream_odds(self, event_id: str) -> AsyncGenerator[list[OddsUpdate], None]:
        if False:
            yield

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    def get_circuit_stats(self) -> dict[str, dict]:
        return {name: cb.stats() for name, cb in self._circuit_breakers.items()}
