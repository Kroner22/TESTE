from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum, auto
from typing import Any, AsyncIterator, Callable, Optional

from .log_config import get_logger
from .settings import get_settings

logger = get_logger(__name__)


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


@dataclass
class CircuitBreaker:
    name: str
    threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max: int = 3

    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
    _half_open_count: int = 0
    _last_failure_time: float = 0.0
    _last_success_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_count = 0
        return self._state

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.threshold:
            self._state = CircuitState.OPEN
            logger.warning("circuit_open", name=self.name, failures=self._failure_count)

    def record_success(self) -> None:
        self._failure_count = 0
        self._half_open_count = 0
        self._last_success_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            logger.info("circuit_closed", name=self.name)

    def can_proceed(self) -> bool:
        st = self.state
        if st == CircuitState.CLOSED:
            return True
        if st == CircuitState.HALF_OPEN:
            if self._half_open_count < self.half_open_max:
                self._half_open_count += 1
                return True
            return False
        return False


class CircuitBreakerError(Exception):
    pass


@dataclass
class RedisPool:
    """Lazy Redis connection pool with circuit breaker."""
    url: str
    pool_size: int = 50
    timeout: float = 2.0
    max_retries: int = 3

    _client: Any = None

    async def get_client(self):
        if self._client is not None:
            return self._client
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(
                self.url,
                max_connections=self.pool_size,
                socket_timeout=self.timeout,
                socket_connect_timeout=self.timeout,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            await self._client.ping()
            logger.info("redis_connected", url=self.url)
        except Exception as e:
            logger.error("redis_connect_failed", error=str(e))
            raise
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


_circuit_breakers: dict[str, CircuitBreaker] = {}
_redis_pool: Optional[RedisPool] = None


def _get_cb(name: str) -> CircuitBreaker:
    if name not in _circuit_breakers:
        s = get_settings()
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            threshold=s.circuit_breaker_threshold,
            recovery_timeout=s.circuit_breaker_recovery_seconds,
            half_open_max=s.circuit_breaker_half_open_max,
        )
    return _circuit_breakers[name]


async def get_redis() -> Any:
    global _redis_pool
    if _redis_pool is None:
        s = get_settings()
        _redis_pool = RedisPool(
            url=s.redis_url,
            pool_size=s.redis_pool_size,
            timeout=s.redis_timeout,
        )
    return await _redis_pool.get_client()


async def close_redis():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None


async def cache_get(key: str) -> Optional[str]:
    cb = _get_cb("redis_get")
    if not cb.can_proceed():
        raise CircuitBreakerError("circuit_open:redis_get")

    s = get_settings()
    full_key = f"{s.cache_key_prefix}{key}"

    try:
        r = await get_redis()
        value = await r.get(full_key)
        if value is not None:
            cb.record_success()
            return value.decode() if isinstance(value, bytes) else value
        cb.record_success()
        return None
    except Exception as e:
        cb.record_failure()
        logger.warning("cache_get_failed", key=key, error=str(e))
        return None


async def cache_set(key: str, value: str, ttl: Optional[int] = None) -> bool:
    cb = _get_cb("redis_set")
    if not cb.can_proceed():
        return False

    s = get_settings()
    full_key = f"{s.cache_key_prefix}{key}"
    ttl = ttl or s.cache_default_ttl_seconds

    try:
        r = await get_redis()
        await r.setex(full_key, ttl, value)
        cb.record_success()
        return True
    except Exception as e:
        cb.record_failure()
        logger.warning("cache_set_failed", key=key, error=str(e))
        return False


async def cache_delete(key: str) -> bool:
    s = get_settings()
    full_key = f"{s.cache_key_prefix}{key}"
    try:
        r = await get_redis()
        await r.delete(full_key)
        return True
    except Exception:
        return False


async def cache_get_or_compute(
    key: str,
    factory: Callable[[], Any],
    ttl: Optional[int] = None,
    serialize: Callable[[Any], str] = json.dumps,
    deserialize: Callable[[str], Any] = json.loads,
) -> Any:
    cached = await cache_get(key)
    if cached is not None:
        try:
            return deserialize(cached)
        except Exception:
            pass

    value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
    serialized = serialize(value)
    await cache_set(key, serialized, ttl)
    return value


async def cache_heatlbeat() -> dict:
    try:
        r = await get_redis()
        info = await r.info(section="server")
        return {
            "status": "ok",
            "version": info.get("redis_version", "unknown"),
            "uptime_seconds": info.get("uptime_in_seconds", 0),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
