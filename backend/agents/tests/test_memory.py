import pytest

from backend.agents.memory import (
    ShortTermMemory, LongTermMemory, LearningStore, AgentMemory,
)
from backend.agents.models import AgentId, AgentMemoryEntry


class TestShortTermMemory:
    def setup_method(self):
        self.mem = ShortTermMemory()

    def test_set_and_get(self):
        self.mem.set("key1", {"value": 42}, importance=0.8)
        assert self.mem.get("key1") == {"value": 42}

    def test_expired(self):
        self.mem.set("key2", "data", ttl=0.0)
        import time; time.sleep(0.01)
        assert self.mem.get("key2") is None

    def test_delete(self):
        self.mem.set("key3", "data")
        self.mem.delete("key3")
        assert self.mem.get("key3") is None

    def test_search(self):
        self.mem.set("event:e1", "data1")
        self.mem.set("event:e2", "data2")
        self.mem.set("other:x", "data3")
        results = self.mem.search(prefix="event:")
        assert len(results) == 2

    def test_eviction(self):
        mem = ShortTermMemory(max_size=5)
        for i in range(10):
            mem.set(f"k{i}", f"v{i}", importance=0.1)
        assert mem.size <= 5


class TestLongTermMemory:
    def setup_method(self):
        self.mem = LongTermMemory(file_path="/tmp/test_agent_mem.json")

    def test_remember_and_recall(self):
        self.mem.remember("k1", AgentId.LEARNING, {"data": "test"}, importance=0.9)
        entry = self.mem.recall("k1")
        assert entry is not None
        assert entry.value == {"data": "test"}
        assert entry.agent == AgentId.LEARNING

    def test_forget(self):
        self.mem.remember("k2", AgentId.LEARNING, {"data": "test"})
        self.mem.forget("k2")
        assert self.mem.recall("k2") is None

    def test_search_by_agent(self):
        self.mem.remember("a1", AgentId.LEARNING, {"v": 1})
        self.mem.remember("a2", AgentId.PATTERN_DETECTOR, {"v": 2})
        results = self.mem.search(agent=AgentId.LEARNING)
        assert len(results) == 1
        assert results[0].key == "a1"

    def test_ttl_expiry(self):
        self.mem.remember("ttl_key", AgentId.LEARNING, {"data": "test"}, ttl=0)
        import time; time.sleep(0.01)
        assert self.mem.recall("ttl_key") is None


class TestLearningStore:
    def setup_method(self):
        self.store = LearningStore(file_path="/tmp/test_agent_learn.json")

    def test_record_value(self):
        self.store.record_value(AgentId.PATTERN_DETECTOR, "confidence", 0.8)
        t = self.store.get_threshold(AgentId.PATTERN_DETECTOR, "confidence")
        assert t is not None
        assert t.mean == 0.8
        assert t.n_samples == 1

    def test_online_update(self):
        self.store.record_value(AgentId.PATTERN_DETECTOR, "volatility", 0.5)
        self.store.record_value(AgentId.PATTERN_DETECTOR, "volatility", 0.7)
        self.store.record_value(AgentId.PATTERN_DETECTOR, "volatility", 0.6)
        t = self.store.get_threshold(AgentId.PATTERN_DETECTOR, "volatility")
        assert t.n_samples == 3
        assert abs(t.mean - 0.6) < 0.1

    def test_is_anomalous_insufficient_samples(self):
        self.store.record_value(AgentId.ODDS_MOVEMENT, "movement_size", 5.0)
        assert self.store.is_anomalous(AgentId.ODDS_MOVEMENT, "movement_size", 100.0) is False

    def test_is_anomalous_detected(self):
        store = self.store
        for v in [1.0, 1.1, 0.9, 1.0, 1.05, 0.95, 1.0, 1.02, 0.98, 1.0, 1.03]:
            store.record_value(AgentId.ODDS_MOVEMENT, "movement_size", v)
        assert store.is_anomalous(AgentId.ODDS_MOVEMENT, "movement_size", 100.0) is True

    def test_track_stats(self):
        self.store.track_stats(AgentId.ALERT_MANAGER, "alerts", {"count": 5})
        stats = self.store.get_stats(AgentId.ALERT_MANAGER, "alerts")
        assert stats["count"] == 5


class TestAgentMemory:
    def setup_method(self):
        self.mem = AgentMemory(persist_path="/tmp")

    def test_remember_and_recall_event(self):
        self.mem.remember_event("e1", AgentId.PATTERN_DETECTOR, {"pattern": "steam"}, importance=0.9)
        recalled = self.mem.recall_event("e1", AgentId.PATTERN_DETECTOR)
        assert recalled is not None
        assert recalled.get("pattern") == "steam"
