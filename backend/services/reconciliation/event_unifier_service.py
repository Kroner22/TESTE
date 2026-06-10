from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.app.log_config import get_logger
from backend.services.pipeline.event_matcher import EventMatcher, EventCandidate
from backend.services.pipeline.odds_normalizer import normalize_event, guess_sport_from_league
from backend.services.providers.base import OddsEvent

logger = get_logger(__name__)


class UnifiedEvent:
    canonical_id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime
    provider_ids: dict[str, str]
    matched_at: datetime
    confidence: float
    is_resolved: bool

    def __init__(self, canonical_id: str, sport: str, league: str, home_team: str, away_team: str, start_time: datetime, provider_ids: dict[str, str] | None = None, matched_at: datetime | None = None, confidence: float = 1.0):
        self.canonical_id = canonical_id
        self.sport = sport
        self.league = league
        self.home_team = home_team
        self.away_team = away_team
        self.start_time = start_time
        self.provider_ids = provider_ids or {}
        self.matched_at = matched_at or datetime.now(timezone.utc)
        self.confidence = confidence
        self.is_resolved = False

    def add_provider_id(self, provider: str, event_id: str):
        self.provider_ids[provider] = event_id

    def matches_teams(self, home: str, away: str) -> bool:
        return (self.home_team.lower() == home.lower() and self.away_team.lower() == away.lower()) or \
               (self.home_team.lower() == away.lower() and self.away_team.lower() == home.lower())

    def has_provider(self, provider: str) -> bool:
        return provider in self.provider_ids

    def provider_count(self) -> int:
        return len(self.provider_ids)

    def to_dict(self) -> dict:
        return {
            "canonical_id": self.canonical_id,
            "sport": self.sport,
            "league": self.league,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "start_time": self.start_time.isoformat() if self.start_time else "",
            "provider_ids": self.provider_ids,
            "provider_count": self.provider_count(),
            "confidence": self.confidence,
            "is_resolved": self.is_resolved,
        }


class EventUnifierService:
    """
    Unifies events from multiple providers into a single canonical event.

    Strategy:
    1. Normalize sport, team names, league
    2. Match by: (sport + league + time proximity) -> then team name fuzzy
    3. If no league match: (sport + time proximity) -> then team name fuzzy
    4. Deduplicate across providers: same event from provider_A and provider_B
       get merged into one canonical event with provider_ids tracking
    """

    TIME_TOLERANCE_MINUTES = 180
    NAME_THRESHOLD = 0.75

    def __init__(self):
        self._events: dict[str, UnifiedEvent] = {}
        self._event_matcher = EventMatcher()

    def ingest_from_provider(self, provider_name: str, event: OddsEvent, league: str = "") -> UnifiedEvent:
        normalized = normalize_event(event.sport, event.home_team, event.away_team, league)
        sport = normalized.sport if normalized.sport else event.sport
        home = normalized.home_team
        away = normalized.away_team
        league_name = league or normalized.league

        existing = self._find_match(sport, league_name, event.start_time, home, away)

        if existing:
            existing.add_provider_id(provider_name, event.event_id)
            if not existing.league and league_name:
                existing.league = league_name
            logger.info("event_unified", canonical=existing.canonical_id, provider=provider_name)
            return existing

        canonical_id = self._generate_id(sport, home, away, event.start_time)
        unified = UnifiedEvent(
            canonical_id=canonical_id,
            sport=sport,
            league=league_name,
            home_team=home,
            away_team=away,
            start_time=event.start_time,
            provider_ids={provider_name: event.event_id},
            confidence=1.0,
        )
        self._events[canonical_id] = unified

        logger.info("event_created", canonical=canonical_id, provider=provider_name, sport=sport)
        return unified

    def _find_match(self, sport: str, league: str, start_time: datetime, home: str, away: str) -> Optional[UnifiedEvent]:
        candidates: list[tuple[UnifiedEvent, float]] = []

        for event in self._events.values():
            if event.is_resolved:
                continue
            if event.sport != sport:
                continue

            time_diff = abs((event.start_time - start_time).total_seconds()) / 60
            if time_diff > self.TIME_TOLERANCE_MINUTES:
                continue

            if league and event.league and league.lower() == event.league.lower():
                if event.matches_teams(home, away):
                    candidates.append((event, 1.0))
                    continue

            if event.matches_teams(home, away):
                score = 0.85 - (time_diff / self.TIME_TOLERANCE_MINUTES) * 0.1 if time_diff > 0 else 0.95
                candidates.append((event, score))

        if not candidates:
            return None
        candidates.sort(key=lambda c: c[1], reverse=True)
        return candidates[0][0] if candidates[0][1] >= self.NAME_THRESHOLD else None

    def get_by_canonical_id(self, canonical_id: str) -> Optional[UnifiedEvent]:
        return self._events.get(canonical_id)

    def get_by_provider_event(self, provider: str, provider_event_id: str) -> Optional[UnifiedEvent]:
        for event in self._events.values():
            if event.provider_ids.get(provider) == provider_event_id:
                return event
        return None

    def get_all(self) -> list[UnifiedEvent]:
        return list(self._events.values())

    def get_multi_provider_events(self, min_providers: int = 2) -> list[UnifiedEvent]:
        return [e for e in self._events.values() if e.provider_count() >= min_providers]

    def get_unmatched(self) -> list[UnifiedEvent]:
        return [e for e in self._events.values() if e.provider_count() < 2]

    def mark_resolved(self, canonical_id: str):
        event = self._events.get(canonical_id)
        if event:
            event.is_resolved = True

    def stats(self) -> dict:
        total = len(self._events)
        multi = len(self.get_multi_provider_events())
        return {
            "total_events": total,
            "multi_provider": multi,
            "single_provider": total - multi,
            "providers_seen": list(set(
                pid for e in self._events.values() for pid in e.provider_ids
            )),
        }

    def clear(self):
        self._events.clear()

    def _generate_id(self, sport: str, home: str, away: str, start_time: datetime) -> str:
        ts = start_time.strftime("%Y%m%d_%H%M")
        h = "".join(c for c in home[:12] if c.isalnum()).lower()
        a = "".join(c for c in away[:12] if c.isalnum()).lower()
        return f"ev_{sport[:4]}_{h}_{a}_{ts}"
