from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.log_config import get_logger
from .models import AgentId, AgentMemoryEntry, LearnedThreshold

logger = get_logger(__name__)


@dataclass
class ShortTermMemory:
    """Ephemeral in-memory state with TTL-based eviction."""
    max_size: int = 10_000
    default_ttl: float = 300.0

    _data: dict[str, tuple[Any, float, float]] = field(default_factory=dict)
    # key → (value, expiry_timestamp, importance)

    def get(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expiry, _ = entry
        if time.time() > expiry:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None, importance: float = 0.5) -> None:
        if len(self._data) >= self.max_size:
            self._evict()
        expiry = time.time() + (ttl if ttl is not None else self.default_ttl)
        self._data[key] = (value, expiry, importance)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def _evict(self) -> None:
        """Evict lowest-importance expired entries."""
        now = time.time()
        expired = [k for k, (_, exp, _) in self._data.items() if now > exp]
        for k in expired:
            del self._data[k]
        if len(self._data) < self.max_size * 0.8:
            return
        sorted_by_imp = sorted(
            self._data.items(),
            key=lambda x: x[1][2],
        )
        to_remove = int(self.max_size * 0.2)
        for k, _ in sorted_by_imp[:to_remove]:
            del self._data[k]

    def search(self, prefix: str = "") -> list[tuple[str, Any]]:
        return [
            (k, v[0]) for k, v in self._data.items()
            if k.startswith(prefix)
        ]

    @property
    def size(self) -> int:
        return len(self._data)


@dataclass
class LongTermMemory:
    """Persistent memory backed by JSON file."""
    file_path: str = "data/agent_memory.json"
    max_entries: int = 100_000

    _entries: dict[str, AgentMemoryEntry] = field(default_factory=dict)
    _dirty: bool = False

    def load(self) -> None:
        path = Path(self.file_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            return
        try:
            raw = json.loads(path.read_text())
            for item in raw:
                entry = AgentMemoryEntry(**item)
                self._entries[entry.key] = entry
            logger.info("memory_loaded", path=self.file_path, entries=len(self._entries))
        except Exception as e:
            logger.warning("memory_load_failed", error=str(e))

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            path = Path(self.file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = [vars(e) for e in self._entries.values()]
            path.write_text(json.dumps(data, default=str, indent=2))
            self._dirty = False
            logger.info("memory_saved", path=self.file_path, entries=len(data))
        except Exception as e:
            logger.warning("memory_save_failed", error=str(e))

    def remember(self, key: str, agent: AgentId, value: dict, ttl: Optional[int] = None, importance: float = 0.5) -> None:
        if len(self._entries) >= self.max_entries:
            self._prune()
        self._entries[key] = AgentMemoryEntry(
            key=key, agent=agent, value=value,
            ttl_seconds=ttl, importance=importance,
        )
        self._dirty = True

    def recall(self, key: str) -> Optional[AgentMemoryEntry]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.ttl_seconds is not None:
            age = (datetime.now(timezone.utc) - entry.timestamp).total_seconds()
            if age > entry.ttl_seconds:
                del self._entries[key]
                self._dirty = True
                return None
        return entry

    def forget(self, key: str) -> None:
        self._entries.pop(key, None)
        self._dirty = True

    def search(self, agent: Optional[AgentId] = None, prefix: str = "") -> list[AgentMemoryEntry]:
        results = []
        for entry in self._entries.values():
            if agent and entry.agent != agent:
                continue
            if prefix and not entry.key.startswith(prefix):
                continue
            results.append(entry)
        return results

    def _prune(self) -> None:
        sorted_by_imp = sorted(
            self._entries.values(),
            key=lambda e: e.importance,
        )
        to_remove = int(self.max_entries * 0.2)
        for entry in sorted_by_imp[:to_remove]:
            del self._entries[entry.key]
        self._dirty = True

    @property
    def size(self) -> int:
        return len(self._entries)


@dataclass
class LearningStore:
    """Stores learned thresholds and agent statistics."""
    file_path: str = "data/agent_learning.json"

    _thresholds: dict[str, LearnedThreshold] = field(default_factory=dict)
    _stats: dict[str, dict] = field(default_factory=dict)
    _dirty: bool = False

    def load(self) -> None:
        path = Path(self.file_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            return
        try:
            raw = json.loads(path.read_text())
            for item in raw.get("thresholds", []):
                t = LearnedThreshold(**item)
                self._thresholds[t.agent.value + ":" + t.metric] = t
            self._stats = raw.get("stats", {})
            logger.info("learning_loaded", path=self.file_path)
        except Exception as e:
            logger.warning("learning_load_failed", error=str(e))

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            path = Path(self.file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "thresholds": [vars(t) for t in self._thresholds.values()],
                "stats": self._stats,
            }
            path.write_text(json.dumps(data, default=str, indent=2))
            self._dirty = False
        except Exception as e:
            logger.warning("learning_save_failed", error=str(e))

    def record_value(self, agent: AgentId, metric: str, value: float) -> None:
        key = agent.value + ":" + metric
        if key not in self._thresholds:
            self._thresholds[key] = LearnedThreshold(
                agent=agent, metric=metric,
                current_value=value, mean=value, std=0.0,
                min_value=value, max_value=value, n_samples=1,
            )
        else:
            t = self._thresholds[key]
            n = t.n_samples
            old_mean = t.mean
            t.mean = old_mean + (value - old_mean) / (n + 1)
            t.std = ((n * (t.std ** 2 + (old_mean - t.mean) ** 2) + (value - t.mean) ** 2) / (n + 1)) ** 0.5
            t.min_value = min(t.min_value, value)
            t.max_value = max(t.max_value, value)
            t.n_samples = n + 1
            t.current_value = value
            t.last_updated = datetime.now(timezone.utc)

        self._dirty = True

    def get_threshold(self, agent: AgentId, metric: str) -> Optional[LearnedThreshold]:
        return self._thresholds.get(agent.value + ":" + metric)

    def is_anomalous(self, agent: AgentId, metric: str, value: float, z_score_threshold: float = 2.0) -> bool:
        t = self.get_threshold(agent, metric)
        if t is None or t.std < 0.001 or t.n_samples < 10:
            return False
        z = abs(value - t.mean) / max(t.std, 0.001)
        return z > z_score_threshold

    def track_stats(self, agent: AgentId, category: str, data: dict) -> None:
        key = f"{agent.value}:{category}"
        if key not in self._stats:
            self._stats[key] = {"count": 0}
        self._stats[key]["count"] += 1
        self._stats[key].update(data)
        self._dirty = True

    def get_stats(self, agent: AgentId, category: str) -> dict:
        return self._stats.get(f"{agent.value}:{category}", {})


class AgentMemory:
    """Unified memory system combining short-term, long-term, and learning."""

    def __init__(self, persist_path: str = "data"):
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory(file_path=f"{persist_path}/agent_memory.json")
        self.learning = LearningStore(file_path=f"{persist_path}/agent_learning.json")

    def load(self) -> None:
        self.long_term.load()
        self.learning.load()

    def save(self) -> None:
        self.long_term.save()
        self.learning.save()

    def remember_event(self, event_id: str, agent: AgentId, data: dict, importance: float = 0.5) -> None:
        key = f"{agent.value}:event:{event_id}:{datetime.now(timezone.utc).timestamp()}"
        self.long_term.remember(key, agent, data, importance=importance)
        self.short_term.set(f"event:{event_id}", data, importance=importance)

    def recall_event(self, event_id: str, agent: AgentId) -> Optional[dict]:
        entries = self.long_term.search(agent=agent, prefix=f"{agent.value}:event:{event_id}")
        if entries:
            return entries[-1].value
        return self.short_term.get(f"event:{event_id}")
