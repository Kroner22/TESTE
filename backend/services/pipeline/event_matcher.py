from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from rapidfuzz import fuzz

from .odds_normalizer import normalize_team, normalize_sport, NormalizedEvent


@dataclass
class EventMatch:
    provider_event_id: str
    canonical_event_id: str
    sport: str
    home_team: str
    away_team: str
    start_time: datetime
    confidence: float
    is_new: bool


@dataclass
class EventCandidate:
    provider: str
    provider_event_id: str
    sport: str
    home_team: str
    away_team: str
    start_time: datetime
    league: str = ""
    raw_sport: str = ""


class EventMatcher:
    def __init__(self, time_tolerance_minutes: int = 120, name_threshold: float = 0.80):
        self.time_tolerance = timedelta(minutes=time_tolerance_minutes)
        self.name_threshold = name_threshold
        self._known_events: dict[str, dict] = {}
        self._normalized_cache: dict[str, str] = {}

    def register_event(self, canonical_id: str, sport: str, home: str, away: str, start: datetime):
        key = (normalize_team(home), normalize_team(away))
        self._known_events[canonical_id] = {
            "sport": normalize_sport(sport),
            "home": normalize_team(home),
            "away": normalize_team(away),
            "start": start,
        }

    def find_or_create(self, candidate: EventCandidate) -> EventMatch:
        nh = normalize_team(candidate.home_team)
        na = normalize_team(candidate.away_team)
        ns = normalize_sport(candidate.sport)
        ct = candidate.start_time

        best_match: Optional[tuple[str, float]] = None

        for cid, known in self._known_events.items():
            if known["sport"] != ns:
                continue

            time_ok = abs((known["start"] - ct).total_seconds()) < self.time_tolerance.total_seconds()
            if not time_ok:
                continue

            home_sim = fuzz.token_sort_ratio(nh, known["home"]) / 100.0
            away_sim = fuzz.token_sort_ratio(na, known["away"]) / 100.0
            swapped_home = fuzz.token_sort_ratio(nh, known["away"]) / 100.0
            swapped_away = fuzz.token_sort_ratio(na, known["home"]) / 100.0

            direct = (home_sim + away_sim) / 2
            swapped = (swapped_home + swapped_away) / 2
            sim = max(direct, swapped)

            if sim >= self.name_threshold and (best_match is None or sim > best_match[1]):
                best_match = (cid, sim)

        if best_match:
            cid, sim = best_match
            known = self._known_events[cid]
            return EventMatch(
                provider_event_id=candidate.provider_event_id,
                canonical_event_id=cid,
                sport=ns,
                home_team=known["home"],
                away_team=known["away"],
                start_time=known["start"],
                confidence=sim,
                is_new=False,
            )

        new_id = f"evt_{ns}_{nh[:8]}_{na[:8]}_{int(ct.timestamp())}"
        self.register_event(new_id, ns, nh, na, ct)

        return EventMatch(
            provider_event_id=candidate.provider_event_id,
            canonical_event_id=new_id,
            sport=ns,
            home_team=nh,
            away_team=na,
            start_time=ct,
            confidence=1.0,
            is_new=True,
        )

    def get_known_count(self) -> int:
        return len(self._known_events)

    def clear(self):
        self._known_events.clear()
        self._normalized_cache.clear()
