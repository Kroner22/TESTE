from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

from ..settings import get_settings, RateLimitStrategy

logger = __import__("structlog").get_logger(__name__)


@dataclass
class SlidingWindowEntry:
    timestamps: list[float] = field(default_factory=list)


@dataclass
class TokenBucket:
    tokens: float
    last_refill: float
    max_tokens: float
    refill_rate: float


class RateLimiter:
    """In-memory + optional Redis-backed rate limiter (sliding window / token bucket)."""

    def __init__(self):
        self._windows: dict[str, SlidingWindowEntry] = defaultdict(SlidingWindowEntry)
        self._buckets: dict[str, TokenBucket] = {}
        self._settings = get_settings()

    def _key(self, identifier: str, route: str = "") -> str:
        return f"{route}:{identifier}" if route else identifier

    def _gc_window(self, entry: SlidingWindowEntry, window: float) -> None:
        now = time.monotonic()
        cutoff = now - window
        entry.timestamps = [t for t in entry.timestamps if t > cutoff]

    def check_sliding_window(
        self, identifier: str, route: str = "",
        max_requests: Optional[int] = None,
        window: Optional[float] = None,
    ) -> tuple[bool, int, float]:
        key = self._key(identifier, route)
        max_r = max_requests or self._settings.rate_limit_default
        win = window or self._settings.rate_limit_window
        burst = self._settings.rate_limit_burst

        entry = self._windows[key]
        self._gc_window(entry, win)

        current = len(entry.timestamps)

        if current >= max_r + burst:
            wait = (entry.timestamps[0] + win) - time.monotonic()
            return False, current, max(0.0, wait)

        entry.timestamps.append(time.monotonic())
        return True, current + 1, 0.0

    def check_token_bucket(
        self, identifier: str, route: str = "",
        max_requests: Optional[int] = None,
        window: Optional[float] = None,
    ) -> tuple[bool, int, float]:
        key = self._key(identifier, route)
        max_r = float(max_requests or self._settings.rate_limit_default)
        win = window or self._settings.rate_limit_window
        refill = max_r / win if win > 0 else max_r

        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                tokens=max_r,
                last_refill=time.monotonic(),
                max_tokens=max_r,
                refill_rate=refill,
            )

        bucket = self._buckets[key]
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        bucket.tokens = min(bucket.max_tokens, bucket.tokens + elapsed * bucket.refill_rate)
        bucket.last_refill = now

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True, int(bucket.tokens), 0.0

        wait = (1.0 - bucket.tokens) / bucket.refill_rate
        return False, int(bucket.tokens), wait

    def check(
        self, identifier: str, route: str = "",
        max_requests: Optional[int] = None,
        window: Optional[float] = None,
    ) -> tuple[bool, int, float]:
        if not self._settings.rate_limit_enabled:
            return True, 0, 0.0

        strategy = self._settings.rate_limit_strategy
        if strategy == RateLimitStrategy.TOKEN_BUCKET:
            return self.check_token_bucket(identifier, route, max_requests, window)
        return self.check_sliding_window(identifier, route, max_requests, window)


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def close_rate_limiter():
    global _rate_limiter
    _rate_limiter = None
