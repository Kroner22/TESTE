from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from backend.services.pipeline.event_matcher import EventCandidate, EventMatcher


@pytest.fixture
def matcher():
    return EventMatcher(time_tolerance_minutes=120, name_threshold=0.7)


class TestEventMatcher:
    def test_new_event_creates_canonical(self, matcher):
        now = datetime.now(timezone.utc)
        candidate = EventCandidate(
            provider="test",
            provider_event_id="p1",
            sport="soccer",
            home_team="FC Barcelona",
            away_team="Real Madrid CF",
            start_time=now,
        )
        match = matcher.find_or_create(candidate)
        assert match.is_new
        assert match.confidence == 1.0
        assert matcher.get_known_count() == 1

    def test_duplicate_event_matches(self, matcher):
        now = datetime.now(timezone.utc)
        c1 = EventCandidate("t", "e1", "soccer", "FC Barcelona", "Real Madrid CF", now)
        m1 = matcher.find_or_create(c1)
        assert m1.is_new

        c2 = EventCandidate("t", "e2", "soccer", "Barcelona", "Real Madrid", now + timedelta(minutes=30))
        m2 = matcher.find_or_create(c2)
        assert not m2.is_new
        assert m2.confidence > 0.8
        assert m2.canonical_event_id == m1.canonical_event_id

    def test_different_sport_no_match(self, matcher):
        now = datetime.now(timezone.utc)
        c1 = EventCandidate("t", "e1", "soccer", "Barcelona", "Real Madrid", now)
        matcher.find_or_create(c1)

        c2 = EventCandidate("t", "e2", "basketball", "Barcelona", "Real Madrid", now)
        m2 = matcher.find_or_create(c2)
        assert m2.is_new

    def test_time_tolerance_respected(self, matcher):
        now = datetime.now(timezone.utc)
        c1 = EventCandidate("t", "e1", "soccer", "Barcelona", "Real Madrid", now)
        matcher.find_or_create(c1)

        far_future = now + timedelta(hours=5)
        c2 = EventCandidate("t", "e2", "soccer", "Barcelona", "Real Madrid", far_future)
        m2 = matcher.find_or_create(c2)
        assert m2.is_new

    def test_swapped_home_away_matches(self, matcher):
        now = datetime.now(timezone.utc)
        c1 = EventCandidate("t", "e1", "soccer", "Barcelona", "Real Madrid", now)
        m1 = matcher.find_or_create(c1)

        c2 = EventCandidate("t", "e2", "soccer", "Real Madrid", "Barcelona", now + timedelta(minutes=15))
        m2 = matcher.find_or_create(c2)
        assert not m2.is_new
        assert m2.home_team == "Barcelona"
        assert m2.away_team == "Real Madrid"

    def test_clear_resets(self, matcher):
        now = datetime.now(timezone.utc)
        c = EventCandidate("t", "e1", "soccer", "Barcelona", "Real Madrid", now)
        matcher.find_or_create(c)
        assert matcher.get_known_count() == 1
        matcher.clear()
        assert matcher.get_known_count() == 0

    def test_low_confidence_no_match(self, matcher):
        strict = EventMatcher(time_tolerance_minutes=120, name_threshold=0.95)
        now = datetime.now(timezone.utc)
        c1 = EventCandidate("t", "e1", "soccer", "FC Barcelona Official", "Real Madrid CF", now)
        strict.find_or_create(c1)

        c2 = EventCandidate("t", "e2", "soccer", "Barca", "Madrid", now + timedelta(minutes=15))
        m2 = strict.find_or_create(c2)
        assert m2.is_new
