from __future__ import annotations

import time
from typing import Optional

from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST,
)
from starlette.responses import Response

logger = __import__("structlog").get_logger(__name__)

# ── HTTP Metrics ─────────────────────────────────────────────────
http_requests_total = Counter(
    "sq_http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "sq_http_request_duration_seconds",
    "HTTP request duration",
    labelnames=["method", "path"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_requests_in_flight = Gauge(
    "sq_http_requests_in_flight",
    "Current in-flight HTTP requests",
    labelnames=["method"],
)

# ── Domain Metrics ──────────────────────────────────────────────
value_opportunities_total = Counter(
    "sq_value_opportunities_total",
    "Total value opportunities detected",
    labelnames=["sport", "grade"],
)

arb_opportunities_total = Counter(
    "sq_arb_opportunities_total",
    "Total arbitrage opportunities detected",
    labelnames=["sport", "arb_type", "grade"],
)

scan_duration_seconds = Histogram(
    "sq_scan_duration_seconds",
    "Market scan duration",
    labelnames=["scanner_type"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

scan_total = Counter(
    "sq_scan_total",
    "Total market scans performed",
    labelnames=["scanner_type", "status"],
)

# ── Cache Metrics ───────────────────────────────────────────────
cache_hits_total = Counter("sq_cache_hits_total", "Cache hits", labelnames=["backend"])
cache_misses_total = Counter("sq_cache_misses_total", "Cache misses", labelnames=["backend"])
cache_errors_total = Counter("sq_cache_errors_total", "Cache errors", labelnames=["backend"])

# ── WebSocket Metrics ───────────────────────────────────────────
ws_connections_total = Counter("sq_ws_connections_total", "Total WebSocket connections")
ws_connections_active = Gauge("sq_ws_connections_active", "Active WebSocket connections")
ws_messages_total = Counter(
    "sq_ws_messages_total",
    "WebSocket messages",
    labelnames=["direction", "channel"],
)

# ── System Metrics ──────────────────────────────────────────────
circuit_breaker_state = Gauge(
    "sq_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    labelnames=["name"],
)

queue_depth = Gauge("sq_queue_depth", "Background task queue depth", labelnames=["queue"])
worker_active = Gauge("sq_worker_active", "Active background workers", labelnames=["worker_type"])


def record_http(method: str, path: str, status: int, duration: float) -> None:
    http_requests_total.labels(method=method, path=path, status=status).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration)


def metrics_exporter(request) -> Response:
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-cache"},
    )
