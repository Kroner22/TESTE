from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class RateLimitStrategy(str, Enum):
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    FIXED_WINDOW = "fixed_window"


class LogFormat(str, Enum):
    JSON = "json"
    CONSOLE = "console"


class TracingExporter(str, Enum):
    CONSOLE = "console"
    OTLP = "otlp"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    secret_key: str = "change-me-in-production"
    project_name: str = "Sports Quant Platform"
    version: str = "0.1.0"

    # Runtime mode
    runtime_mode: str = "SIMULATION"  # SIMULATION | HYBRID | REAL_MARKET

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    max_connections: int = 1000
    backlog: int = 2048
    keepalive: int = 5
    timeout: int = 30
    graceful_timeout: int = 30
    limit_max_requests: int = 10000

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    cors_allow_credentials: bool = True

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_sentinel_url: Optional[str] = None
    redis_sentinel_master: str = "mymaster"
    redis_pool_size: int = 50
    redis_timeout: float = 2.0

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    rate_limit_default: int = 100
    rate_limit_window: int = 60
    rate_limit_burst: int = 200
    rate_limit_ws_per_connection: int = 20
    rate_limit_ws_global: int = 500

    # Background tasks
    scan_enabled: bool = True
    scan_interval_seconds: float = 5.0
    scan_total_stake: int = 100
    scan_min_profit_pct: float = 0.005
    scan_max_concurrency: int = 4

    # Observability
    metrics_enabled: bool = True
    metrics_port: int = 9090
    tracing_enabled: bool = False
    tracing_exporter: TracingExporter = TracingExporter.CONSOLE
    otlp_endpoint: str = "http://otel-collector:4318"
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON
    log_include_trace_id: bool = True

    # Resilience
    circuit_breaker_enabled: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_seconds: int = 30
    circuit_breaker_half_open_max: int = 3
    retry_max_attempts: int = 3
    retry_backoff_factor: float = 2.0
    retry_max_delay: float = 30.0
    bulkhead_max_concurrent: int = 20
    bulkhead_max_queue: int = 50
    timeout_default: float = 10.0
    timeout_heavy: float = 60.0

    # Cache
    cache_enabled: bool = True
    cache_default_ttl_seconds: int = 30
    cache_max_size_mb: int = 512
    cache_key_prefix: str = "sq:"

    # WebSocket
    ws_heartbeat_interval: int = 30
    ws_max_clients: int = 10000
    ws_max_backpressure: int = 128
    ws_message_queue_size: int = 256

    # Database (future)
    database_url: Optional[str] = None
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_pool_timeout: int = 30
    database_echo: bool = False

    # External integrations
    bookmaker_api_keys: str = ""
    bookmaker_request_timeout: float = 5.0
    bookmaker_max_retries: int = 3
    bookmaker_cache_ttl: int = 15

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    return Settings()
