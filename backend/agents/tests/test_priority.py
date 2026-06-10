import pytest
import time

from backend.agents.priority import PriorityEngine, EventScheduler
from backend.agents.models import AgentId, AgentMessage, EventPriority


class TestPriorityEngine:
    def setup_method(self):
        self.engine = PriorityEngine()

    def test_score_base_priority(self):
        msg = AgentMessage(
            source=AgentId.ODDS_MOVEMENT,
            target=AgentId.PATTERN_DETECTOR,
            msg_type="odds_movement",
            priority=EventPriority.HIGH,
        )
        scored = self.engine.score(msg)
        assert scored.score >= EventPriority.HIGH.value

    def test_score_urgency_high(self):
        from datetime import datetime, timedelta, timezone
        soon = datetime.now(timezone.utc) + timedelta(minutes=2)
        msg = AgentMessage(
            source=AgentId.ODDS_MOVEMENT,
            target=AgentId.PATTERN_DETECTOR,
            msg_type="odds_movement",
            payload={"expires_at": soon},
        )
        scored = self.engine.score(msg)
        assert scored.score > EventPriority.MEDIUM.value

    def test_score_critical_priority(self):
        msg = AgentMessage(
            source=AgentId.PATTERN_DETECTOR,
            target=AgentId.ALERT_MANAGER,
            msg_type="pattern_detected",
            priority=EventPriority.CRITICAL,
        )
        scored = self.engine.score(msg)
        assert scored.score >= EventPriority.CRITICAL.value

    def test_novelty_decreases_over_time(self):
        msg = AgentMessage(
            source=AgentId.PATTERN_DETECTOR,
            target=AgentId.ALERT_MANAGER,
            msg_type="pattern_detected",
            payload={"pattern": "steam_move", "event_id": "e1"},
        )
        first = self.engine.score(msg)
        second = self.engine.score(msg)  # Same dedup key → lower novelty
        assert second.score < first.score

    def test_impact_factor(self):
        msg = AgentMessage(
            source=AgentId.OPPORTUNITY_SCOUT,
            target=AgentId.ALERT_MANAGER,
            msg_type="high_value",
            priority=EventPriority.HIGH,
            payload={"profit_pct": 8.0, "confidence": 0.9},
        )
        scored = self.engine.score(msg)
        assert scored.score > EventPriority.HIGH.value

    def test_cleanup(self):
        old = time.time() - 7200
        self.engine._recent_events = {"stale_key": old, "fresh_key": time.time()}
        self.engine.cleanup(max_age_seconds=3600)
        assert "stale_key" not in self.engine._recent_events
        assert "fresh_key" in self.engine._recent_events


class TestEventScheduler:
    def setup_method(self):
        self.scheduler = EventScheduler()

    def test_schedule_once(self):
        self.scheduler.schedule_once("test_key", delay_seconds=0)
        due = self.scheduler.get_due()
        assert len(due) == 1
        assert due[0][0] == "test_key"

    def test_not_due_yet(self):
        self.scheduler.schedule_once("future_key", delay_seconds=3600)
        due = self.scheduler.get_due()
        assert len(due) == 0

    def test_cancel(self):
        self.scheduler.schedule_once("to_cancel", delay_seconds=0)
        self.scheduler.cancel("to_cancel")
        due = self.scheduler.get_due()
        assert len(due) == 0

    def test_periodic(self):
        calls = []
        async def cb():
            calls.append(True)
        self.scheduler.schedule_periodic("periodic_test", interval_seconds=0, callback=cb)
        due = self.scheduler.get_due()
        assert len(due) == 1
